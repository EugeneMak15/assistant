"""Reconcile advisor availability and prices with the BZB Gear shopping feed.

Rows missing from the feed are retained for reference but excluded from
recommendations. New SKUs require technical-spec review before import.
Dry-run by default; --apply backs up SQLite before changing any rows.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from sync_catalog_feed import FEED_URL, G, _camera_alias, _feed_items, _price


def fetch_feed_products(feed_url: str = FEED_URL) -> dict[str, dict]:
    items = _feed_items(feed_url)
    if len(items) < 200:
        raise ValueError(f"Shopping feed unexpectedly small: {len(items)} SKUs")
    products = {}
    for sku, item in items.items():
        raw_status = (item.findtext(G + "availability") or "").strip().lower()
        if raw_status not in {"in_stock", "in stock", "out_of_stock", "out of stock", "preorder"}:
            raise ValueError(f"Unknown feed availability for {sku}: {raw_status!r}")
        products[sku] = {
            "availability": raw_status,
            "price": _price(item.findtext(G + "price")),
            "product_type": (item.findtext(G + "product_type") or "").strip(),
        }
    return products


def plan_updates(conn: sqlite3.Connection, feed: dict[str, dict]) -> dict:
    rows = {row["id"].upper(): row for row in conn.execute(
        "SELECT id, stock_status, site_category, price_usd FROM products"
    )}
    # Some feed camera variants append -31 to an otherwise identical legacy SKU.
    # Reconcile that alias to the existing row; do not hide a still-stocked camera.
    normalized_feed = dict(feed)
    aliases = {}
    for sku, product in feed.items():
        if sku not in rows and _camera_alias(sku, rows.keys()):
            original = sku[:-3]
            normalized_feed[original] = product
            aliases[sku] = original
    updates = []
    for sku, row in rows.items():
        product = normalized_feed.get(sku)
        if product is None:
            status, site_category, price = "Not in Feed", row["site_category"], row["price_usd"]
        else:
            availability = product["availability"]
            if availability in {"out_of_stock", "out of stock"}:
                status = "Out of Stock"
            elif availability == "preorder":
                status = "Pre-Order"
            else:
                status = "In Stock"
            site_category = product["product_type"].split(">", 1)[0].strip() or row["site_category"]
            price = product["price"] if product["price"] is not None else row["price_usd"]
        if (status, site_category, price) != (
            row["stock_status"], row["site_category"], row["price_usd"]
        ):
            updates.append((status, site_category, price, row["id"]))
    return {
        "feed_skus": len(feed),
        "matched_skus": len(rows.keys() & normalized_feed.keys()),
        "existing_variant_aliases": aliases,
        "new_skus_for_review": sorted(feed.keys() - rows.keys() - aliases.keys()),
        "missing_from_feed": sorted(rows.keys() - normalized_feed.keys()),
        "changed_skus": [row[3] for row in updates],
        "updates": updates,
    }


def refresh(db_path: str, apply: bool = False, backup_dir: str | None = None) -> dict:
    feed = fetch_feed_products()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        result = plan_updates(conn, feed)
        if apply and result["updates"]:
            if not backup_dir:
                raise ValueError("--backup-dir is required with --apply")
            target = Path(backup_dir)
            target.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_path = target / f"catalog-availability-{stamp}.db"
            with sqlite3.connect(backup_path) as backup:
                conn.backup(backup)
            conn.executemany(
                "UPDATE products SET stock_status=?, site_category=?, price_usd=? WHERE id=?",
                result["updates"],
            )
            conn.commit()
            result["backup_path"] = str(backup_path)
        result.pop("updates")
        return result
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="products.db")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir")
    args = parser.parse_args()
    print(json.dumps(refresh(args.db, args.apply, args.backup_dir), indent=2))
