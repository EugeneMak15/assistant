"""
Index all 429 products as embeddings in ChromaDB.
Each product becomes a rich text document: title + specs + what_it_does + use_cases + signals.
This enables semantic search: "SDI camera 4K broadcast" finds BG-ADAMO without SQL category matching.

Run: python ingest_products.py
Safe to re-run — skips already-indexed products.
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import os, json, sqlite3
from pathlib import Path

import truststore; truststore.inject_into_ssl()
from dotenv import load_dotenv; load_dotenv()
from openai import OpenAI
import chromadb
from rich.console import Console
from rich.progress import track

console = Console()
client  = OpenAI()

DB_PATH    = "./products.db"
CHROMA_PATH = "./chroma_db"
COLLECTION  = "products"   # separate collection from manual chunks


def get_collection():
    chroma = chromadb.PersistentClient(path=CHROMA_PATH)
    return chroma.get_or_create_collection(COLLECTION)


def product_to_text(p: dict) -> str:
    """Convert product row to rich searchable text."""
    parts = []

    title = p.get("title") or p.get("name") or ""
    parts.append(f"Product: {p['id']}")
    parts.append(f"Title: {title}")
    parts.append(f"Category: {p.get('category', '')} ({p.get('site_category', '')} / {p.get('site_subcategory', '')})")

    ins  = json.loads(p.get("input_signals")  or "[]")
    outs = json.loads(p.get("output_signals") or "[]")
    res  = json.loads(p.get("resolutions")    or "[]")

    if ins:  parts.append(f"Input signals: {', '.join(ins)}")
    if outs: parts.append(f"Output signals: {', '.join(outs)}")
    if res:  parts.append(f"Resolutions: {', '.join(res)}")

    if p.get("inputs") and p.get("outputs"):
        parts.append(f"Configuration: {p['inputs']} inputs × {p['outputs']} outputs")
    if p.get("max_distance_m"):
        parts.append(f"Max distance: {p['max_distance_m']}m")
    if p.get("max_bandwidth_gbps"):
        parts.append(f"Bandwidth: {p['max_bandwidth_gbps']} Gbps")
    if p.get("price_usd"):
        parts.append(f"Price: ${p['price_usd']:,.0f}")
    if p.get("stock_status"):
        parts.append(f"Stock: {p['stock_status']}")

    if p.get("what_it_does"):
        parts.append(f"\nWhat it does: {p['what_it_does']}")

    use_cases = []
    try:
        use_cases = json.loads(p.get("use_cases") or "[]")
    except Exception:
        pass
    if use_cases:
        parts.append(f"\nUse cases:\n" + "\n".join(f"  - {uc}" for uc in use_cases[:8]))

    # Key specs
    specs = {}
    try:
        specs = json.loads(p.get("specs_json") or "{}")
    except Exception:
        pass
    if specs:
        top = dict(list(specs.items())[:10])
        parts.append("\nKey specs:\n" + "\n".join(f"  {k}: {v}" for k, v in top.items()))

    # Features
    features = []
    try:
        features = json.loads(p.get("features") or "[]")
    except Exception:
        pass
    if features:
        parts.append("\nFeatures:\n" + "\n".join(f"  - {f}" for f in features[:8]))

    return "\n".join(parts)


def embed_batch(texts: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [r.embedding for r in resp.data]


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM products ORDER BY category, id").fetchall()
    conn.close()

    products = [dict(r) for r in rows]
    console.print(f"Loaded [cyan]{len(products)}[/cyan] products from DB")

    collection = get_collection()
    existing   = set(collection.get(include=[])["ids"])
    console.print(f"Already indexed: [cyan]{len(existing)}[/cyan] products")

    to_index = [p for p in products if p["id"] not in existing]
    console.print(f"To index: [cyan]{len(to_index)}[/cyan] products")

    if not to_index:
        console.print("[green]All products already indexed![/green]")
        return

    # Process in batches of 50 (embedding API limit)
    BATCH = 50
    indexed = 0

    for i in range(0, len(to_index), BATCH):
        batch = to_index[i:i + BATCH]

        ids       = [p["id"] for p in batch]
        texts     = [product_to_text(p) for p in batch]
        metadatas = [{
            "category":         p.get("category", ""),
            "site_category":    p.get("site_category", "") or "",
            "input_signals":    json.dumps(json.loads(p.get("input_signals")  or "[]")),
            "output_signals":   json.dumps(json.loads(p.get("output_signals") or "[]")),
            "resolutions":      json.dumps(json.loads(p.get("resolutions")    or "[]")),
            "max_distance_m":   p.get("max_distance_m") or 0,
            "max_bandwidth_gbps": p.get("max_bandwidth_gbps") or 0,
            "inputs":           p.get("inputs") or 0,
            "outputs":          p.get("outputs") or 0,
            "price_usd":        p.get("price_usd") or 0,
            "stock_status":     p.get("stock_status") or "",
        } for p in batch]

        embeddings = embed_batch(texts)

        collection.upsert(
            ids        = ids,
            documents  = texts,
            embeddings = embeddings,
            metadatas  = metadatas,
        )
        indexed += len(batch)
        console.print(f"  [{indexed}/{len(to_index)}] indexed up to {ids[-1]}")

    console.print(f"\n[bold green]Done! {indexed} products indexed in ChromaDB collection '{COLLECTION}'[/bold green]")
    console.print(f"Total in collection: {collection.count()}")


if __name__ == "__main__":
    main()
