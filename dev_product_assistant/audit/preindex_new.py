"""Populate only the Dev product-assistant PDF index for newly published SKUs."""
import json
import sqlite3
import sys

sys.path.insert(0, "/opt/product-assistant-dev")
from docs_index import DB_PATH, index_resources

products = json.load(sys.stdin)
new = [p for p in products if p.get("date", "") >= "2026-08-01" and p.get("sku")]
for p in new:
    skus = [p["sku"]] + p.get("variants", [])
    pdfs = [r for r in p.get("resources", []) if r.get("url", "").lower().split("?")[0].endswith(".pdf")]
    index_resources(skus, pdfs)

db = sqlite3.connect(DB_PATH)
for p in new:
    sku = p["sku"]
    count = db.execute("SELECT COUNT(*) FROM doc_chunks WHERE sku=?", (sku,)).fetchone()[0]
    files = db.execute("SELECT COUNT(*) FROM indexed_files WHERE sku=?", (sku,)).fetchone()[0]
    print(json.dumps({"sku": sku, "indexed_pdf_files": files, "indexed_chunks": count}, ensure_ascii=False))
db.close()
