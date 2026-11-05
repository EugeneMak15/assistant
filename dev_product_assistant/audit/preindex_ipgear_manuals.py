"""Prewarm the large product-specific IPGEAR-PRO manuals in Dev FTS."""
import json
import logging
import sqlite3
import sys

logging.getLogger("pypdf").setLevel(logging.ERROR)
sys.path.insert(0, "/opt/product-assistant-dev")
from docs_index import DB_PATH, index_resources

product = next(p for p in json.load(sys.stdin) if p.get("sku") == "BG-IPGEAR-PRO")
manuals = [r for r in product["resources"] if "manual" in r["title"].lower()]
skus = [product["sku"]] + product["variants"]
index_resources(skus, manuals)
db = sqlite3.connect(DB_PATH)
for sku in skus:
    print(json.dumps({"sku": sku, "manual_files": db.execute(
        "SELECT COUNT(*) FROM indexed_files WHERE sku=? AND url LIKE '%manual%'", (sku,)).fetchone()[0],
        "manual_chunks": db.execute(
        "SELECT COUNT(*) FROM doc_chunks WHERE sku=? AND url LIKE '%manual%'", (sku,)).fetchone()[0]}))
db.close()
