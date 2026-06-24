"""
BZB Gear Manual Ingestion Pipeline
Reads DOCX manuals -> chunks by headings -> extracts metadata via LLM -> embeds -> stores in ChromaDB
"""

import os
import re
import json
import hashlib
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import chromadb
from docx import Document
from rich.console import Console
from rich.progress import track

load_dotenv()

import truststore
truststore.inject_into_ssl()

console = Console()
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
chroma = chromadb.PersistentClient(path="./chroma_db")
collection = chroma.get_or_create_collection(
    name="manual_chunks",
    metadata={"hnsw:space": "cosine"},
)

MANUALS_DIR = Path("./manuals")
CHUNK_MAX_TOKENS = 600  # approximate, by word count
CHUNK_OVERLAP_WORDS = 60


def extract_product_id(filename: str) -> str:
    """Extract product model number from filename."""
    name = Path(filename).stem
    # Match BG-XXX-YYY or HDC-XXX or HDP-XXX patterns
    match = re.search(r"(BG-[\w-]+|HDC-[\w]+|HDP-[\w]+|PTN[\w-]*)", name, re.IGNORECASE)
    if match:
        return match.group(1).upper().rstrip("-")
    # Fallback: first token before space
    return name.split()[0].upper()


def docx_to_sections(path: Path) -> list[dict]:
    """Parse DOCX into sections based on heading styles."""
    doc = Document(path)
    sections = []
    current_heading = "Introduction"
    current_level = 0
    current_paragraphs = []

    def flush():
        text = "\n".join(p for p in current_paragraphs if p.strip())
        if text.strip():
            sections.append({
                "heading": current_heading,
                "level": current_level,
                "text": text,
            })

    for para in doc.paragraphs:
        style = para.style.name if para.style else ""
        text = para.text.strip()

        if not text:
            continue

        if style.startswith("Heading"):
            flush()
            current_paragraphs = []
            try:
                current_level = int(style.split()[-1])
            except ValueError:
                current_level = 1
            current_heading = text
        else:
            current_paragraphs.append(text)

    flush()
    return sections


def chunk_section(section: dict, max_words: int = CHUNK_MAX_TOKENS, overlap: int = CHUNK_OVERLAP_WORDS) -> list[str]:
    """Split a section into overlapping word-window chunks."""
    words = section["text"].split()
    if len(words) <= max_words:
        return [section["text"]]

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end == len(words):
            break
        start = end - overlap
    return chunks


def extract_metadata(chunk_text: str, product_id: str) -> dict:
    """Use GPT-4o-mini to classify chunk and extract metadata."""
    prompt = f"""You are a metadata extractor for AV equipment documentation.
Given a chunk of text from a product manual for {product_id}, return JSON only:
{{
  "doc_type": "spec"|"limitation"|"compatibility"|"setup"|"marketing",
  "feature_tags": ["tag1", "tag2"],
  "has_limitation": true|false,
  "summary": "one sentence max 20 words"
}}

Rules:
- "limitation": text describes restrictions, maximums, mode requirements, caveats
- "compatibility": text discusses what works with what, signal types, connector types
- "spec": technical specifications, port counts, resolutions, bandwidth
- "setup": installation steps, configuration procedures
- "marketing": promotional text with no technical constraints

Chunk:
{chunk_text[:1500]}"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        console.print(f"[yellow]Metadata extraction failed: {e}[/yellow]")
        return {
            "doc_type": "spec",
            "feature_tags": [],
            "has_limitation": False,
            "summary": chunk_text[:80],
        }


def embed(texts: list[str]) -> list[list[float]]:
    """Batch embed texts with text-embedding-3-small."""
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [r.embedding for r in resp.data]


def chunk_id(product_id: str, heading: str, chunk_index: int) -> str:
    key = f"{product_id}:{heading}:{chunk_index}"
    return hashlib.md5(key.encode()).hexdigest()


def ingest_file(path: Path):
    product_id = extract_product_id(path.name)
    console.print(f"  Product: [bold cyan]{product_id}[/bold cyan]")

    sections = docx_to_sections(path)
    if not sections:
        console.print(f"  [yellow]No sections found, skipping[/yellow]")
        return 0

    all_chunks = []
    seen_ids = set()
    for section in sections:
        chunks = chunk_section(section)
        for i, chunk_text in enumerate(chunks):
            cid = chunk_id(product_id, section["heading"], i)
            if cid in seen_ids:
                # Make unique by appending text hash
                cid = chunk_id(product_id, section["heading"] + chunk_text[:20], i)
            seen_ids.add(cid)
            all_chunks.append({
                "id": cid,
                "text": chunk_text,
                "heading": section["heading"],
                "product_id": product_id,
                "source_file": path.name,
            })

    # Check which IDs already exist to avoid re-processing
    existing_ids = set()
    try:
        existing = collection.get(ids=[c["id"] for c in all_chunks])
        existing_ids = set(existing["ids"])
    except Exception:
        pass

    new_chunks = [c for c in all_chunks if c["id"] not in existing_ids]
    if not new_chunks:
        console.print(f"  [dim]All {len(all_chunks)} chunks already ingested[/dim]")
        return 0

    console.print(f"  Processing {len(new_chunks)} new chunks (skipping {len(existing_ids)} existing)...")

    # Extract metadata in individual calls (cheap model, no rate limit issues)
    metadatas = []
    for chunk in new_chunks:
        meta = extract_metadata(chunk["text"], product_id)
        metadatas.append(meta)

    # Batch embed
    texts = [c["text"] for c in new_chunks]
    embeddings = embed(texts)

    # Store in ChromaDB
    collection.add(
        ids=[c["id"] for c in new_chunks],
        embeddings=embeddings,
        documents=texts,
        metadatas=[
            {
                "product_id": chunk["product_id"],
                "heading": chunk["heading"],
                "source_file": chunk["source_file"],
                "doc_type": meta.get("doc_type", "spec"),
                "feature_tags": json.dumps(meta.get("feature_tags", [])),
                "has_limitation": str(meta.get("has_limitation", False)),
                "summary": meta.get("summary", "")[:200],
            }
            for chunk, meta in zip(new_chunks, metadatas)
        ],
    )

    return len(new_chunks)


def main():
    console.print("[bold green]BZB Gear Manual Ingestion Pipeline[/bold green]")
    console.print(f"Manuals dir: {MANUALS_DIR.resolve()}")
    console.print(f"ChromaDB: ./chroma_db\n")

    docx_files = sorted(MANUALS_DIR.glob("*.docx"))
    # Skip duplicate files (those with " (2)" suffix)
    docx_files = [f for f in docx_files if " (2)" not in f.name]

    console.print(f"Found [bold]{len(docx_files)}[/bold] manuals\n")

    total_chunks = 0
    for path in docx_files:
        console.print(f"[bold]{path.name}[/bold]")
        count = ingest_file(path)
        total_chunks += count
        console.print()

    existing_count = collection.count()
    console.print(f"[bold green]Done! Added {total_chunks} new chunks. Total in DB: {existing_count}[/bold green]")


if __name__ == "__main__":
    main()
