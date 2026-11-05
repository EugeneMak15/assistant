"""Compare current WooCommerce product pages against Advisor SQLite/Chroma."""
from __future__ import annotations

import collections
import json
import sqlite3
import sys
from pathlib import Path

import chromadb

products = json.load(sys.stdin)
conn = sqlite3.connect("file:/opt/assistant/products.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
advisor = {row["id"].upper(): dict(row) for row in conn.execute(
    "SELECT id,name,description,specs_json,manual_url,brochure_url,product_url,stock_status FROM products")}
conn.close()
chroma = chromadb.PersistentClient(path="/opt/assistant/chroma_db")
manuals = collections.Counter()
web = collections.Counter()
web_pages: dict[str, set[str]] = collections.defaultdict(set)
for meta in chroma.get_collection("manual_chunks").get(include=["metadatas"])["metadatas"]:
    manuals[str(meta.get("product_id", "")).upper()] += 1
for meta in chroma.get_collection("website_content").get(include=["metadatas"])["metadatas"]:
    try:
        related = json.loads(meta.get("related_skus", "[]"))
    except (ValueError, TypeError):
        related = []
    for sku in related:
        web[sku.upper()] += 1
        web_pages[sku.upper()].add(meta.get("url", ""))

rows = []
for p in products:
    sku = str(p.get("sku") or "").upper()
    if not sku:
        continue
    a = advisor.get(sku)
    attached = p.get("resources", [])
    pdfs = [r for r in attached if str(r.get("url", "")).lower().split("?")[0].endswith(".pdf")]
    diagrams = [r for r in attached if "diagram" in str(r.get("title", "")).lower()
                or "diag" in str(r.get("url", "")).lower()]
    manual_files = [r for r in attached if "manual" in str(r.get("title", "")).lower()]
    gaps = []
    if not a:
        gaps.append("missing_product")
    else:
        if p["description_chars"] >= 300 and len(a.get("description") or "") < 100:
            gaps.append("thin_description")
        if p["spec_chars"] >= 300 and len(a.get("specs_json") or "") < 30:
            gaps.append("missing_specs")
        if manual_files and not a.get("manual_url"):
            gaps.append("manual_link_missing")
    if manual_files and manuals[sku] == 0:
        gaps.append("manual_not_indexed")
    if diagrams:
        gaps.append("diagram_not_indexed")  # No image/diagram collection exists.
    if web[sku] == 0:
        gaps.append("no_linked_site_articles")
    rows.append({
        "sku": sku, "title": p["title"], "url": p["url"], "date": p["date"],
        "modified": p["modified"], "type": p["type"], "variants": p["variants"],
        "stock": p["stock"], "visibility": p["visibility"], "lifecycle": p["lifecycle"],
        "advisor": bool(a), "manual_chunks": manuals[sku], "web_chunks": web[sku],
        "web_pages": len(web_pages[sku]), "manual_files": len(manual_files),
        "pdf_files": len(pdfs), "diagrams": len(diagrams), "gaps": gaps,
        "resources": attached,
    })

new = [r for r in rows if r["date"] >= "2026-08-01"]
summary = {
    "site_products": len(rows), "advisor_products": len(advisor),
    "new_since_2026_08_01": len(new),
    "missing_in_advisor": sum(not r["advisor"] for r in rows),
    "new_with_manual_not_indexed": sum("manual_not_indexed" in r["gaps"] for r in new),
    "new_with_diagram_not_indexed": sum("diagram_not_indexed" in r["gaps"] for r in new),
    "new_with_no_linked_articles": sum("no_linked_site_articles" in r["gaps"] for r in new),
}
compact = [{k: v for k, v in r.items() if k != "resources"} for r in new]
print(json.dumps({"summary": summary, "new_products": compact}, ensure_ascii=False))
