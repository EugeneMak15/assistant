"""
Post-process website_content ChromaDB collection:
1. Scan each chunk for BZB Gear SKU mentions (BG-XXXXX pattern)
2. Also match product titles/names to SKUs
3. Update metadata with related_skus field

Run after ingest_website.py completes.
Safe to re-run.
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import re, json, sqlite3
from pathlib import Path

import chromadb
from rich.console import Console
from rich.progress import track

console = Console()
CHROMA_PATH = "./chroma_db"

# BZB Gear SKU pattern: BG- followed by alphanumeric and hyphens
SKU_RE = re.compile(r'\bBG-[A-Z0-9][A-Z0-9\-]{2,30}\b')


def load_products(db_path="./products.db") -> dict:
    """Load all products: {sku: {title, category, ...}}"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, title, name, category FROM products").fetchall()
    conn.close()

    products = {}
    for r in rows:
        products[r["id"]] = {
            "title":    r["title"] or r["name"] or "",
            "category": r["category"] or "",
        }
    return products


def build_title_index(products: dict) -> list[tuple[str, str]]:
    """Build list of (search_term, sku) for fuzzy name matching."""
    index = []
    for sku, p in products.items():
        title = p["title"].lower()
        # Extract meaningful keywords from title (skip generic words)
        stopwords = {"the","a","an","with","and","or","for","to","in","of",
                     "by","from","up","is","are","was","be","been","has","have"}
        words = [w for w in re.findall(r'[a-z0-9]+', title) if w not in stopwords and len(w) > 3]
        if words:
            # Use first 4 significant words as search phrase
            phrase = " ".join(words[:4])
            index.append((phrase, sku))
    return index


def extract_skus_from_text(text: str, valid_skus: set) -> list[str]:
    """Find all valid BZB Gear SKUs mentioned in text."""
    found = set()

    # Direct SKU pattern match
    for match in SKU_RE.finditer(text.upper()):
        sku = match.group()
        if sku in valid_skus:
            found.add(sku)
        # Also try prefix match (e.g. "BG-ADAMO-4K" matches "BG-ADAMO-4K12X-W")
        for valid in valid_skus:
            if valid.startswith(sku + "-") or valid == sku:
                found.add(valid)

    return sorted(found)


def main():
    chroma     = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = chroma.get_or_create_collection("website_content")

    total = collection.count()
    console.print(f"website_content collection: [cyan]{total}[/cyan] chunks")

    if total == 0:
        console.print("[yellow]Collection empty — run ingest_website.py first[/yellow]")
        return

    products   = load_products()
    valid_skus = set(products.keys())
    console.print(f"Valid SKUs loaded: [cyan]{len(valid_skus)}[/cyan]")

    # Fetch all chunks in batches
    BATCH = 200
    updated = 0
    with_skus = 0

    for offset in track(range(0, total, BATCH), description="Processing chunks..."):
        result = collection.get(
            limit=BATCH,
            offset=offset,
            include=["documents", "metadatas"],
        )

        if not result["ids"]:
            break

        new_ids    = []
        new_docs   = []
        new_metas  = []

        for chunk_id, doc, meta in zip(result["ids"], result["documents"], result["metadatas"]):
            # Already processed
            if meta.get("related_skus") is not None:
                continue

            skus = extract_skus_from_text(doc, valid_skus)

            new_meta = dict(meta)
            new_meta["related_skus"]   = json.dumps(skus)
            new_meta["has_sku_mention"] = len(skus) > 0

            new_ids.append(chunk_id)
            new_docs.append(doc)
            new_metas.append(new_meta)

            if skus:
                with_skus += 1
            updated += 1

        if new_ids:
            # Update metadata only — don't touch embeddings
            collection.update(
                ids=new_ids,
                metadatas=new_metas,
            )

    console.print(f"\n[bold green]Done![/bold green]")
    console.print(f"  Chunks processed: {updated}")
    console.print(f"  Chunks with SKU mentions: {with_skus}")

    # Show sample of what was found
    console.print("\n[cyan]Sample chunks with SKU mentions:[/cyan]")
    result = collection.get(
        where={"has_sku_mention": {"$eq": True}},
        limit=8,
        include=["documents", "metadatas"],
    )
    for doc, meta in zip(result["documents"], result["metadatas"]):
        skus  = json.loads(meta.get("related_skus", "[]"))
        title = meta.get("title", "")[:60]
        print(f"  [{meta.get('doc_type','?')}] {title}")
        print(f"    SKUs: {skus}")
        print(f"    Preview: {doc[:100].strip()}")
        print()


if __name__ == "__main__":
    main()
