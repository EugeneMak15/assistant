"""Import reviewed products from the full BZBGEAR product feed.

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
    "BG-8K-24A": {
        "category": "distribution_amp", "inputs": 2, "outputs": 4,
        "signals": ["HDMI 2.1"], "resolutions": ["4K120", "8K60"],
        "bandwidth": 48, "description": "2x4 HDMI 2.1 splitter: select one of two sources for four displays, with HDR-to-SDR downscaling and audio de-embedding.",
        "interface": {"in_hdmi": 1, "in_hdmi_count": 2, "out_hdmi": 1, "out_hdmi_count": 4,
                      "max_res": "8K60", "supports_4k": 1, "supports_8k": 1, "supports_hdr": 1,
                      "audio_deembed": 1, "ctrl_rs232": 1, "primary_fn": "splitter"},
    },
    "BG-PSC51-4K": {
        "category": "presentation_switcher", "inputs": 5, "outputs": 1,
        "signals": ["HDMI 2.0", "USB-C video", "Dante audio", "HDBaseT 3.0"],
        "resolutions": ["4K60"], "bandwidth": 18,
        "description": "5x1 presentation switcher with three HDMI and two USB-C inputs, Dante audio, multiview, USB KVM and included HDBaseT receiver; 4K60 output.",
        "interface": {"in_hdmi": 1, "in_hdmi_count": 3, "out_hdmi": 1, "out_hdmi_count": 1,
                      "out_dante": 1, "out_hdbaset": 1, "max_res": "4K60", "supports_4k": 1,
                      "ctrl_ip": 1, "ctrl_rs232": 1, "primary_fn": "production-switcher",
                      "secondary_fns": '["presentation-switcher", "multiviewer"]'},
    },
    "BG-UHD-VWP110L": {
        "category": "switcher", "inputs": 2, "outputs": 10,
        "signals": ["HDMI 2.0", "USB-C video"], "resolutions": ["4K30 output", "4K60 input"],
        "bandwidth": 18, "description": "1x10 video-wall controller with HDMI/USB-C source selection, scaling and rotation; wall outputs up to 4K30.",
        "interface": {"in_hdmi": 1, "in_hdmi_count": 1, "out_hdmi": 1, "out_hdmi_count": 10,
                      "max_res": "4K30", "supports_4k": 1, "ctrl_rs232": 1,
                      "primary_fn": "matrix-switcher", "secondary_fns": '["video-wall"]',
                      "notes": "One selected source across a video wall, not 10 independent matrix routes."},
    },
    "BG-USW-24": {
        "category": "kvm_switch", "inputs": 2, "outputs": 4,
        "signals": ["USB 3.2 Gen 1"], "resolutions": [], "bandwidth": None,
        "description": "2-host, 4-peripheral USB 3.2 switch for sharing USB devices; no video switching.",
        "interface": {"in_hdmi": 0, "in_hdmi_count": 0, "out_hdmi": 0, "out_hdmi_count": 0,
                      "ctrl_rs232": 1, "primary_fn": "usb-switcher",
                      "notes": "Two USB hosts share four USB peripherals; no HDMI or display routing."},
    },
    "BG-USX-B100BC": {
        "category": "extender", "inputs": 2, "outputs": 4, "distance": 100,
        "signals": ["USB 3.2 Gen 1", "HDBaseT 3.0"], "resolutions": [], "bandwidth": None,
        "description": "Dual-host USB 3.2 extender over CAT6A up to 100m; USB-C/USB-B hosts, no video extension.",
        "interface": {"in_hdmi": 0, "out_hdmi": 0, "out_hdbaset": 1, "in_hdbaset": 1,
                      "primary_fn": "extender-tx", "notes": "USB peripherals only; no HDMI video."},
    },
    "BG-USX-B100CH": {
        "category": "extender", "inputs": 2, "outputs": 2, "distance": 100,
        "signals": ["USB-C video", "USB 3.2 Gen 1", "HDMI 2.0", "HDBaseT 3.0"],
        "resolutions": ["4K60"], "bandwidth": 18,
        "description": "Dual USB-C host KVM and extender kit with two HDMI display outputs and USB peripherals over CAT6A up to 100m; 4K60.",
        "interface": {"in_hdmi": 0, "out_hdmi": 1, "out_hdmi_count": 2,
                      "in_hdbaset": 1, "out_hdbaset": 1, "max_res": "4K60", "supports_4k": 1,
                      "ctrl_rs232": 1, "primary_fn": "extender-tx",
                      "secondary_fns": '["kvm-switcher"]',
                      "notes": "USB-C DP Alt Mode video inputs; two HDMI display outputs at the receiver."},
    },
    "BG-USX-WP100BC": {
        "category": "extender", "inputs": 2, "outputs": 4, "distance": 100,
        "signals": ["USB 3.2 Gen 1", "HDBaseT 3.0"], "resolutions": [],
        "bandwidth": None, "description": "Dual-host USB 3.2 wall-plate extender over CAT6A up to 100m; USB-C/USB-B hosts, no video extension.",
        "interface": {"in_hdmi": 0, "out_hdmi": 0, "out_hdbaset": 1, "in_hdbaset": 1,
                      "primary_fn": "extender-tx", "form_factor": "wall plate",
                      "notes": "USB peripherals only; no HDMI video."},
    },
    "BG-USX-WP150HC": {
        "category": "extender", "inputs": 2, "outputs": 1, "distance": 120,
        "signals": ["HDMI 2.0", "USB-C video", "HDBaseT 3.0"], "resolutions": ["4K60"],
        "bandwidth": 18, "description": "HDMI/USB-C wall-plate switcher and HDBaseT extender; up to 120m at 4K60 or 150m at 1080p.",
        "interface": {"in_hdmi": 1, "in_hdmi_count": 1, "out_hdmi": 1, "out_hdmi_count": 1,
                      "in_hdbaset": 1, "out_hdbaset": 1, "max_res": "4K60", "supports_4k": 1,
                      "ctrl_rs232": 1, "ctrl_ir": 1, "primary_fn": "extender-tx",
                      "form_factor": "wall plate"},
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
        placeholders = ",".join("?" * len(PRODUCT_PROFILES))
        existing = {row[0] for row in conn.execute(
            f"SELECT id FROM products WHERE id IN ({placeholders})", tuple(PRODUCT_PROFILES)
        )}
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
        if "shipping_estimate" not in {row[1] for row in conn.execute("PRAGMA table_info(products)")}:
            conn.execute("ALTER TABLE products ADD COLUMN shipping_estimate TEXT")
        for sku, profile in PRODUCT_PROFILES.items():
            site = site_products[sku]
            categories = site["categories"]
            preferred = next((path for path in categories if path != "New Arrivals"), categories[0])
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
                "max_distance_m": profile.get("distance"),
                "price_usd": site["price"], "stock_status": {
                    "Available": "In Stock", "In Stock": "In Stock", "Limited Stock": "In Stock",
                    "Pre-Order": "Pre-Order", "Shipping Soon": "Pre-Order", "Backordered": "Pre-Order",
                    "Out of Stock": "Out of Stock", "Discontinued": "Discontinued",
                }[site["status"]],
                "shipping_estimate": site.get("shipping_estimate") if site["status"] in {"Pre-Order", "Shipping Soon", "Backordered"} else None,
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
