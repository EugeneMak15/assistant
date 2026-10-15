"""Reconcile advisor availability and prices with the BZB Gear shopping feed.

Rows missing from the feed are retained for reference but excluded from
recommendations. New SKUs require technical-spec review before import.
Dry-run by default; --apply backs up SQLite before changing any rows.
"""

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import sqlite3
import urllib.request
from lxml import html

from sync_catalog_feed import _camera_alias
from site_feed_products import SITE_FEED_URL, parse_site_availability, parse_shipping_estimate

TAA_URL = "https://bzbgear.com/taa-compliant/"


def fetch_feed_products(feed_url: str = SITE_FEED_URL) -> dict[str, dict]:
    request = urllib.request.Request(feed_url, headers={"User-Agent": "BZBAdvisor/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return parse_site_availability(response.read())


def fetch_taa_skus(url: str = TAA_URL) -> set[str]:
    """Only the site's explicit TAA product list can confirm compliance."""
    request = urllib.request.Request(url, headers={"User-Agent": "BZBAdvisor/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        page = html.fromstring(response.read())
    skus = {" ".join(node.text_content().split()).upper() for node in page.xpath(
        "//div[contains(concat(' ', normalize-space(@class), ' '), ' product_card2_title ')]"
    )}
    if len(skus) < 20 or "BG-4K-44MA" not in skus:
        raise ValueError("TAA product list unexpectedly incomplete")
    return skus


def plan_updates(conn: sqlite3.Connection, feed: dict[str, dict], taa_skus: set[str] | None = None) -> dict:
    has_taa = "taa_compliant" in {row[1] for row in conn.execute("PRAGMA table_info(products)")}
    rows = {row["id"].upper(): row for row in conn.execute(
        "SELECT id, category, stock_status, site_category, price_usd, inputs, outputs, max_distance_m, what_it_does"
        + (", taa_compliant" if has_taa else "") + " FROM products"
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
    spec_updates = []
    category_updates = []
    taa_updates = []
    for sku, row in rows.items():
        product = normalized_feed.get(sku)
        if product is None:
            status, site_category, price = "Not in Feed", row["site_category"], row["price_usd"]
        else:
            availability = product["availability"]
            if availability in {"out_of_stock", "out of stock"}:
                status = "Out of Stock"
            elif availability == "discontinued":
                status = "Discontinued"
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
        if (product and row["category"] == "sdi" and site_category == "Audio"
                and sku in {"BG-8K-AE", "BG-8K-AD", "BG-8K-AA", "BG-8K-SA"}):
            category_updates.append(("audio", row["id"]))
        if product and sku == "BG-EXH-8KF" and re.search(r"up to 300\s*m\b", product["description"], re.I):
            accurate = ("8K60/4K120 HDMI 2.1 fiber extender; up to 300 m with OM4 fiber "
                        "(OM3: 200 m; OM2: 40 m).")
            if row["max_distance_m"] != 300 or row["what_it_does"] != accurate:
                spec_updates.append((row["inputs"], row["outputs"], 300, accurate, row["id"]))
        if product and sku == "BG-4K-VP1616" and re.search(r"16\s*x\s*16", product["description"], re.I):
            if row["inputs"] != 16 or row["outputs"] != 16:
                spec_updates.append((16, 16, row["max_distance_m"], row["what_it_does"], row["id"]))
        # Reviewed distance limits from the product specifications. Do not
        # treat a missing numeric distance as zero and suppress these extenders.
        reviewed_distances = {
            "BG-EXT-H70P": (40, "4K30 HDMI over CAT, up to 131 ft / 40 m, with HDMI loop-out."),
            "BG-EXUF": (100, "USB 3.1 over fiber, four device ports; real-time USB 3.x up to 100 m (longer non-real-time modes vary)."),
            "BG-FES12G": (10000, "12G-SDI over fiber up to 10 km with a suitable single-mode SFP module."),
        }
        if product and sku in reviewed_distances:
            distance, description = reviewed_distances[sku]
            if row["max_distance_m"] != distance or row["what_it_does"] != description:
                spec_updates.append((row["inputs"], row["outputs"], distance, description, row["id"]))
        if taa_skus is not None:
            confirmed = int(sku in taa_skus)
            if not has_taa or row["taa_compliant"] != confirmed:
                taa_updates.append((confirmed, row["id"]))
    return {
        "feed_skus": len(feed),
        "matched_skus": len(rows.keys() & normalized_feed.keys()),
        "existing_variant_aliases": aliases,
        "new_skus_for_review": sorted(feed.keys() - rows.keys() - aliases.keys()),
        "missing_from_feed": sorted(rows.keys() - normalized_feed.keys()),
        "changed_skus": [row[3] for row in updates],
        "corrected_specs": [row[4] for row in spec_updates],
        "corrected_categories": [row[1] for row in category_updates],
        "updates": updates,
        "spec_updates": spec_updates,
        "category_updates": category_updates,
        "taa_updates": taa_updates,
    }


def refresh(db_path: str, apply: bool = False, backup_dir: str | None = None) -> dict:
    feed = fetch_feed_products()
    taa_skus = fetch_taa_skus()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        result = plan_updates(conn, feed, taa_skus)
        shipping_updates = []
        nutrix = feed.get("BG-NUTRIX")
        if nutrix and nutrix["availability"] == "preorder" and nutrix.get("link", "").startswith("https://bzbgear.com/product/"):
            try:
                request = urllib.request.Request(nutrix["link"], headers={"User-Agent": "BZBAdvisor/1.0"})
                with urllib.request.urlopen(request, timeout=15) as response:
                    estimate = parse_shipping_estimate(response.read())
                if estimate:
                    shipping_updates.append((estimate, "BG-NUTRIX"))
            except Exception as exc:
                logging.getLogger(__name__).warning("Could not verify BG-NUTRIX shipping badge: %s", exc)
        if apply and (result["updates"] or result["spec_updates"] or result["category_updates"] or result["taa_updates"] or shipping_updates):
            if not backup_dir:
                raise ValueError("--backup-dir is required with --apply")
            target = Path(backup_dir)
            target.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_path = target / f"catalog-availability-{stamp}.db"
            with sqlite3.connect(backup_path) as backup:
                conn.backup(backup)
            if "taa_compliant" not in {row[1] for row in conn.execute("PRAGMA table_info(products)")}:
                conn.execute("ALTER TABLE products ADD COLUMN taa_compliant INTEGER")
            if "shipping_estimate" not in {row[1] for row in conn.execute("PRAGMA table_info(products)")}:
                conn.execute("ALTER TABLE products ADD COLUMN shipping_estimate TEXT")
            conn.executemany(
                "UPDATE products SET stock_status=?, site_category=?, price_usd=? WHERE id=?",
                result["updates"],
            )
            conn.executemany(
                "UPDATE products SET inputs=?, outputs=?, max_distance_m=?, what_it_does=? WHERE id=?",
                result["spec_updates"],
            )
            conn.executemany("UPDATE products SET category=? WHERE id=?", result["category_updates"])
            conn.executemany("UPDATE products SET taa_compliant=? WHERE id=?", result["taa_updates"])
            conn.executemany("UPDATE products SET shipping_estimate=? WHERE id=?", shipping_updates)
            conn.commit()
            result["backup_path"] = str(backup_path)
        result.pop("updates")
        result.pop("spec_updates")
        result.pop("category_updates")
        result.pop("taa_updates")
        result["shipping_estimates"] = [sku for _, sku in shipping_updates]
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
