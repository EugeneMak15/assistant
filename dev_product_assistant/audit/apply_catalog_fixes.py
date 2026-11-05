"""Focused production Advisor data correction from the live shopping feed/site.

Run as advisor from /opt/assistant. Requires a verified SQLite backup first.
"""
from __future__ import annotations

import argparse
import sqlite3
import subprocess
import xml.etree.ElementTree as ET

FEED = "https://bzbgear.com/wp-content/uploads/woo-feed/google/xml/bzbgearshoppingfeed.xml"
TARGETS = {
    "BG-4K-VP1616PRO", "BG-IPGEAR-PRO-T", "BG-IPGEAR-PRO-R", "BG-UHD-VWP110L",
    "BG-EXH-8K100U", "BG-EXH-8K50C", "BG-EXH-4KFE", "BG-8KCH",
}
MANUALS = {
    "BG-EXH-8K100U": "https://bzbgear.com/wp-content/uploads/2026/08/BG-EXH-8K100U-manual.pdf",
    "BG-EXH-8K50C": "https://bzbgear.com/wp-content/uploads/2026/08/BG-EXH-8K50C-manual.pdf",
    "BG-EXH-4KFE": "https://bzbgear.com/wp-content/uploads/2026/08/BG-EXH-4KFE-manual.pdf",
    "BG-8KCH": "https://bzbgear.com/wp-content/uploads/2026/08/BG-8KCH-manual.pdf",
}
FAMILY_NOTES = {
    "BG-IPGEAR-PRO-T": "BG-IPGEAR-PRO family; transmitter (T) variation. Pair with receiver BG-IPGEAR-PRO-R as required by setup.",
    "BG-IPGEAR-PRO-R": "BG-IPGEAR-PRO family; receiver (R) variation. Pair with transmitter BG-IPGEAR-PRO-T as required by setup.",
}

parser = argparse.ArgumentParser()
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()

feed_bytes = subprocess.run(
    ["curl", "-fsSL", "--max-time", "30", "--resolve", "bzbgear.com:443:10.77.0.10", FEED],
    check=True, capture_output=True,
).stdout
root = ET.fromstring(feed_bytes)
feed = {}
for item in root.iter("item"):
    data = {node.tag.split("}")[-1]: (node.text or "").strip() for node in item}
    sku = data.get("id", "")
    if sku in TARGETS:
        feed[sku] = data
if set(feed) != TARGETS:
    raise SystemExit(f"Feed missing target SKUs: {sorted(TARGETS - set(feed))}")

db = sqlite3.connect("/opt/assistant/products.db")
db.row_factory = sqlite3.Row
changes = []
try:
    db.execute("BEGIN IMMEDIATE")
    for sku in sorted(TARGETS):
        row = db.execute("SELECT id,description,stock_status,product_url,manual_url,notes FROM products WHERE id=?", (sku,)).fetchone()
        if row is None:
            raise ValueError(f"Advisor row missing: {sku}")
        source = feed[sku]
        availability = source.get("availability")
        if availability != "in_stock":
            raise ValueError(f"Unexpected feed availability for {sku}: {availability}")
        description = source.get("description", "")
        mention = "BG-IPGEAR-PRO" if sku.startswith("BG-IPGEAR-PRO-") else sku
        if len(description) < 300 or mention.lower() not in description.lower():
            raise ValueError(f"Unexpected feed description for {sku}")
        values = {
            "description": description,
            "stock_status": "In Stock",
            "product_url": source.get("link", ""),
            "manual_url": MANUALS.get(sku, row["manual_url"]),
            "notes": FAMILY_NOTES.get(sku, row["notes"]),
        }
        if not values["product_url"].startswith("https://bzbgear.com/product/"):
            raise ValueError(f"Unexpected URL for {sku}")
        changed = {k: (len(v) if k == "description" and v is not None else v)
                   for k, v in values.items() if (row[k] or "") != (v or "")}
        if changed:
            changes.append((sku, changed))
            if args.apply:
                db.execute("UPDATE products SET description=?,stock_status=?,product_url=?,manual_url=?,notes=? WHERE id=?",
                           (values["description"], values["stock_status"], values["product_url"],
                            values["manual_url"], values["notes"], sku))
    if args.apply:
        db.commit()
    else:
        db.rollback()
finally:
    db.close()
for sku, fields in changes:
    print(sku, fields)
print("mode", "APPLIED" if args.apply else "DRY_RUN", "rows_changed", len(changes))
