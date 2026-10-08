"""Import three reviewed products from the full BZBGEAR product feed.

The Google Shopping XML omits these SKUs. Dry-run by default; --apply backs
up the SQLite catalog before inserting/updating reviewed records.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from site_feed_products import fetch_site_products


PRODUCT_PROFILES = {
    "BG-8K-KVM21A": {
        "category": "kvm_switch", "inputs": 2, "outputs": 1,
        "signals": ["HDMI 2.1", "USB 3.0"], "resolutions": ["4K120", "8K60"],
        "bandwidth": 40, "description": "2x1 HDMI 2.1 KVM switch for two computers, one display and shared USB 3.0 peripherals; up to 8K60.",
        "interface": {"in_hdmi": 1, "in_hdmi_count": 2, "in_hdmi_ver": "2.1",
                      "out_hdmi": 1, "out_hdmi_count": 1, "out_hdmi_ver": "2.1",
                      "max_res": "8K60", "supports_4k": 1, "supports_8k": 1,
                      "supports_hdr": 1, "ctrl_ip": 0, "ctrl_rs232": 1,
                      "ctrl_ir": 1, "ctrl_front": 1, "primary_fn": "kvm-switcher",
                      "notes": "HDMI video KVM with USB 3.0 peripheral switching."},
    },
    "BG-USM-44": {
        "category": "kvm_switch", "inputs": 4, "outputs": 4,
        "signals": ["USB 3.2 Gen 1"], "resolutions": [],
        "bandwidth": None, "description": "4x4 USB 3.2 Gen 1 matrix for sharing four USB peripherals among four computers; no HDMI video switching.",
        "interface": {"in_hdmi": 0, "in_hdmi_count": 0, "out_hdmi": 0,
                      "out_hdmi_count": 0, "supports_4k": 0, "supports_8k": 0,
                      "ctrl_ip": 1, "ctrl_rs232": 1, "ctrl_ir": 1,
                      "ctrl_front": 1, "primary_fn": "usb-matrix-switcher",
                      "notes": "Four USB hosts and four USB devices; USB-A/B/C, 5 Gbps. No HDMI video routing or DP Alt Mode."},
    },
    "BG-8K-28A": {
        "category": "distribution_amp", "inputs": 2, "outputs": 8,
        "signals": ["HDMI 2.1"], "resolutions": ["4K120", "8K60"],
        "bandwidth": 48, "description": "2x8 HDMI 2.1 splitter: select one of two sources for eight displays; independent downscaling and audio de-embedding.",
        "interface": {"in_hdmi": 1, "in_hdmi_count": 2, "in_hdmi_ver": "2.1",
                      "out_hdmi": 1, "out_hdmi_count": 8, "out_hdmi_ver": "2.1",
                      "max_res": "8K60", "supports_4k": 1, "supports_8k": 1,
                      "supports_hdr": 1, "audio_deembed": 1, "ctrl_rs232": 1,
                      "ctrl_front": 1, "primary_fn": "splitter",
                      "notes": "One selected HDMI source is duplicated to eight outputs; not eight independent matrix routes."},
    },
}


def _upsert(conn: sqlite3.Connection, table: str, key: str, fields: dict) -> None:
    allowed = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    data = {name: value for name, value in fields.items() if name in allowed}
    names = list(data)
    assignments = ",".join(f"{name}=excluded.{name}" for name in names if name != key)
    conn.execute(
        f"INSERT INTO {table} ({','.join(names)}) VALUES ({','.join('?' for _ in names)}) "
        f"ON CONFLICT({key}) DO UPDATE SET {assignments}",
        list(data.values()),
    )


def sync(db_path: str, apply: bool = False, backup_dir: str | None = None,
         site_products: dict | None = None) -> dict:
    site_products = site_products if site_products is not None else fetch_site_products()
    if set(site_products) != set(PRODUCT_PROFILES):
        raise ValueError("Reviewed full-feed SKU set changed")
    conn = sqlite3.connect(db_path)
    try:
        existing = {row[0] for row in conn.execute("SELECT id FROM products WHERE id IN (?,?,?)", tuple(PRODUCT_PROFILES))}
        result = {"insert": sorted(set(PRODUCT_PROFILES) - existing), "update": sorted(existing)}
        if not apply:
            return result
        if not backup_dir:
            raise ValueError("--backup-dir is required with --apply")
        backup_path = Path(backup_dir) / f"products-pre-site-sync-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.db"
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup = sqlite3.connect(backup_path)
        try:
            conn.backup(backup)
        finally:
            backup.close()
        conn.execute("BEGIN IMMEDIATE")
        for sku, profile in PRODUCT_PROFILES.items():
            site = site_products[sku]
            categories = site["categories"]
            preferred = next((path for path in categories if path.startswith("Video Switchers >")), categories[0])
            category_parts = [part.strip() for part in preferred.split(">")]
            product = {
                "id": sku, "name": site["title"], "title": site["title"],
                "category": profile["category"],
                "site_category": category_parts[0],
                "site_subcategory": category_parts[1] if len(category_parts) > 1 else None,
                "site_categories_raw": json.dumps(categories),
                "inputs": profile["inputs"], "outputs": profile["outputs"],
                "input_signals": json.dumps(profile["signals"]),
                "output_signals": json.dumps(profile["signals"]),
                "resolutions": json.dumps(profile["resolutions"]),
                "max_bandwidth_gbps": profile["bandwidth"],
                "price_usd": site["price"], "stock_status": site["status"],
                "description": profile["description"], "what_it_does": profile["description"],
                "features": json.dumps(site["features"]), "specs_json": json.dumps(site["specs"]),
                "product_url": site["link"], "image_url": site["image_url"],
                "additional_images": json.dumps(site["additional_images"]),
                "manual_url": site["manual_url"], "brochure_url": site["brochure_url"],
                "scraped": 1,
            }
            interface = {"sku": sku, **profile["interface"], "confidence": 0.95,
                         "extracted_at": datetime.now(timezone.utc).isoformat()}
            _upsert(conn, "products", "id", product)
            _upsert(conn, "product_interfaces", "sku", interface)
        conn.commit()
        result["backup"] = str(backup_path)
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="products.db")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir")
    args = parser.parse_args()
    print(json.dumps(sync(args.db, args.apply, args.backup_dir), indent=2))
