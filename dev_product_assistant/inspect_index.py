"""Small read-only index check, run on the Dev VPS as the advisor user."""
import chromadb
import json

db = chromadb.PersistentClient(path="/opt/assistant/chroma_db")
for name in ("manual_chunks", "website_content"):
    try:
        collection = db.get_collection(name)
        print(name, "total", collection.count())
        if name == "manual_chunks":
            for sku in ("BG-8KCH", "BG-IPGEAR-PRO"):
                print(sku, "manual_chunks", len(collection.get(where={"product_id": sku}, include=[])["ids"]))
        else:
            rows = collection.get(include=["metadatas"])["metadatas"]
            for sku in ("BG-8KCH", "BG-IPGEAR-PRO"):
                matched = [m for m in rows if sku in json.loads(m.get("related_skus", "[]"))]
                print(sku, "website_chunks", len(matched), "unique_pages", len({m.get("url") for m in matched}))
    except Exception as exc:
        print(name, type(exc).__name__)
