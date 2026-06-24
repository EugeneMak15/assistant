"""
Vision-based manual ingestion.
Extracts images from DOCX manuals → GPT-4o Vision → structured AV knowledge → ChromaDB.

Run: python ingest_vision.py
Resume: safe to re-run — skips already-processed images (cached in vision_cache.db)
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import os, json, base64, zipfile, time, hashlib, sqlite3
from pathlib import Path
from io import BytesIO

import truststore; truststore.inject_into_ssl()
from dotenv import load_dotenv; load_dotenv()
from openai import OpenAI
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

# ── ChromaDB
import chromadb

console = Console()
client  = OpenAI()

MANUALS_DIR  = Path("./manuals")
CACHE_DB     = Path("./vision_cache.db")
CHROMA_PATH  = Path("./chroma_db")
COLLECTION   = "manual_chunks"

MIN_IMAGE_KB = 5      # skip tiny images (icons, bullets)
MAX_IMAGES_PER_MANUAL = 40   # cap per manual to avoid spending on repetitive pages
BATCH_DELAY  = 0.3   # seconds between API calls

VISION_PROMPT = """You are analyzing a page from an AV (Audio-Visual) equipment manual.

Extract ALL of the following that are visible:

1. CONNECTION DIAGRAMS — describe exactly what connects to what:
   e.g. "Camera 12G-SDI output → SDI input port 1 on switcher → HDMI output → display"

2. SPECIFICATIONS — any table or listed specs:
   e.g. "Input: 4x HDMI 2.0, Output: 8x HDBaseT, Max resolution: 4K60, Bandwidth: 18Gbps"

3. COMPATIBILITY NOTES — what works with what, requirements, warnings:
   e.g. "Requires Cat6 cable for 4K60. Not compatible with HDBaseT 1.0 devices."

4. INSTALLATION STEPS — any numbered steps or instructions for connecting/configuring

5. PORT LABELS — names of all visible ports/connectors on diagrams

6. LIMITATIONS — what this device CANNOT do, maximum distances, unsupported formats

Return as JSON:
{
  "connections": ["description of each connection shown"],
  "specs": {"key": "value"},
  "compatibility": ["note 1", "note 2"],
  "installation": ["step 1", "step 2"],
  "ports": ["port name 1", "port name 2"],
  "limitations": ["limitation 1"],
  "summary": "1-2 sentence summary of what this page shows"
}

If the image is a logo, decorative photo, or contains no technical information, return:
{"skip": true, "reason": "decorative/logo/photo"}"""


# ── Cache DB ──────────────────────────────────────────────────────────────────

def init_cache():
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed (
            image_hash TEXT PRIMARY KEY,
            manual_name TEXT,
            image_name TEXT,
            result_json TEXT,
            processed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def image_hash(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def get_cached(conn, h: str):
    row = conn.execute("SELECT result_json FROM processed WHERE image_hash=?", (h,)).fetchone()
    return json.loads(row[0]) if row else None


def save_cache(conn, h: str, manual: str, img_name: str, result: dict):
    conn.execute(
        "INSERT OR REPLACE INTO processed (image_hash, manual_name, image_name, result_json) VALUES (?,?,?,?)",
        (h, manual, img_name, json.dumps(result))
    )
    conn.commit()


# ── GPT-4o Vision call ────────────────────────────────────────────────────────

def analyze_image(image_data: bytes, manual_name: str) -> dict:
    b64 = base64.standard_b64encode(image_data).decode()
    # Detect format
    fmt = "png" if image_data[:4] == b'\x89PNG' else "jpeg"

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text",  "text": f"Manual: {manual_name}\n\n{VISION_PROMPT}"},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/{fmt};base64,{b64}",
                    "detail": "high"
                }},
            ]
        }],
        temperature=0.1,
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


# ── ChromaDB ──────────────────────────────────────────────────────────────────

def get_collection():
    chroma = chromadb.PersistentClient(path=str(CHROMA_PATH))
    # Get collection without embedding function — we embed manually to avoid conflicts
    return chroma.get_or_create_collection(COLLECTION)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using OpenAI text-embedding-3-small."""
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [r.embedding for r in resp.data]


def result_to_chunks(result: dict, manual_name: str, img_name: str, product_id: str) -> list[dict]:
    """Convert vision result to indexable text chunks."""
    chunks = []

    # Build a rich text chunk from all extracted info
    parts = []

    if result.get("summary"):
        parts.append(f"Summary: {result['summary']}")

    if result.get("connections"):
        parts.append("Connections:\n" + "\n".join(f"  - {c}" for c in result["connections"]))

    if result.get("specs"):
        spec_lines = "\n".join(f"  {k}: {v}" for k, v in result["specs"].items())
        parts.append(f"Specifications:\n{spec_lines}")

    if result.get("compatibility"):
        parts.append("Compatibility:\n" + "\n".join(f"  - {c}" for c in result["compatibility"]))

    if result.get("limitations"):
        parts.append("Limitations:\n" + "\n".join(f"  - {l}" for l in result["limitations"]))

    if result.get("installation"):
        parts.append("Installation:\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(result["installation"])))

    if result.get("ports"):
        parts.append("Ports: " + ", ".join(result["ports"]))

    text = "\n\n".join(parts).strip()
    if not text or len(text) < 30:
        return []

    chunk_id = f"{product_id}__vision__{img_name}"
    has_limitation = bool(result.get("limitations"))
    feature_tags = []
    if result.get("connections"):   feature_tags.append("connection_diagram")
    if result.get("specs"):         feature_tags.append("specifications")
    if result.get("compatibility"): feature_tags.append("compatibility")
    if result.get("limitations"):   feature_tags.append("limitation")
    if result.get("installation"):  feature_tags.append("installation")

    chunks.append({
        "id":       chunk_id,
        "text":     text,
        "metadata": {
            "product_id":     product_id,
            "source":         manual_name,
            "doc_type":       "vision_extracted",
            "heading":        f"Image: {img_name}",
            "has_limitation": has_limitation,
            "feature_tags":   json.dumps(feature_tags),
            "summary":        result.get("summary", "")[:200],
        }
    })
    return chunks


def product_id_from_manual(filename: str) -> str:
    """Extract SKU from manual filename like 'BG-4K-88MA Manual.docx'"""
    name = Path(filename).stem
    # Remove common suffixes
    for suffix in [" Manual", " User Manual", " user manual", " manual", "_Manual"]:
        name = name.replace(suffix, "")
    # Normalize
    name = name.strip().upper().replace(" ", "-")
    return name


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not os.environ.get("OPENAI_API_KEY"):
        console.print("[red]OPENAI_API_KEY not set[/red]")
        return

    cache_conn = init_cache()
    collection = get_collection()

    already_in_chroma = set(collection.get(include=[])["ids"])
    console.print(f"ChromaDB already has [cyan]{len(already_in_chroma)}[/cyan] chunks")

    manuals = sorted(MANUALS_DIR.glob("*.docx"))
    console.print(f"Found [cyan]{len(manuals)}[/cyan] manuals to process")

    total_images    = 0
    skipped_tiny    = 0
    skipped_cached  = 0
    skipped_decor   = 0
    processed       = 0
    errors          = 0
    new_chunks      = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing manuals...", total=len(manuals))

        for manual_path in manuals:
            manual_name = manual_path.name
            product_id  = product_id_from_manual(manual_name)
            progress.update(task, description=f"[cyan]{product_id[:25]}[/cyan]")

            try:
                zf = zipfile.ZipFile(manual_path)
            except Exception as e:
                console.print(f"[red]Cannot open {manual_name}: {e}[/red]")
                progress.advance(task)
                continue

            # Get image entries, sorted by size desc (biggest = most useful diagrams)
            image_entries = [
                e for e in zf.infolist()
                if e.filename.startswith("word/media/")
                and Path(e.filename).suffix.lower() in (".png", ".jpg", ".jpeg")
            ]
            image_entries.sort(key=lambda e: e.file_size, reverse=True)

            manual_new_chunks = []
            images_this_manual = 0

            for entry in image_entries:
                total_images += 1
                kb = entry.file_size / 1024

                # Skip tiny images
                if kb < MIN_IMAGE_KB:
                    skipped_tiny += 1
                    continue

                # Cap per manual
                if images_this_manual >= MAX_IMAGES_PER_MANUAL:
                    break

                img_data = zf.read(entry.filename)
                h = image_hash(img_data)
                img_name = Path(entry.filename).name

                # Check cache
                cached = get_cached(cache_conn, h)
                if cached:
                    skipped_cached += 1
                    if not cached.get("skip"):
                        chunks = result_to_chunks(cached, manual_name, img_name, product_id)
                        for c in chunks:
                            if c["id"] not in already_in_chroma:
                                manual_new_chunks.append(c)
                    continue

                # Call Vision API
                try:
                    result = analyze_image(img_data, manual_name)
                    save_cache(cache_conn, h, manual_name, img_name, result)
                    processed += 1
                    images_this_manual += 1

                    if result.get("skip"):
                        skipped_decor += 1
                    else:
                        chunks = result_to_chunks(result, manual_name, img_name, product_id)
                        for c in chunks:
                            if c["id"] not in already_in_chroma:
                                manual_new_chunks.append(c)

                    time.sleep(BATCH_DELAY)

                except Exception as e:
                    console.print(f"[red]  Vision error {img_name}: {e}[/red]")
                    errors += 1
                    time.sleep(2)

            zf.close()

            # Upsert this manual's chunks to ChromaDB (with explicit embeddings)
            if manual_new_chunks:
                try:
                    texts = [c["text"] for c in manual_new_chunks]
                    embeddings = embed_texts(texts)
                    collection.upsert(
                        ids        = [c["id"]       for c in manual_new_chunks],
                        documents  = texts,
                        embeddings = embeddings,
                        metadatas  = [c["metadata"] for c in manual_new_chunks],
                    )
                    new_chunks += len(manual_new_chunks)
                    console.print(f"  [green]+{len(manual_new_chunks)} chunks[/green] for {product_id}")
                except Exception as e:
                    console.print(f"[red]  ChromaDB error for {product_id}: {e}[/red]")

            progress.advance(task)

    cache_conn.close()

    console.print(f"""
[bold green]Done![/bold green]
  Total images found:     {total_images}
  Skipped (tiny <5KB):    {skipped_tiny}
  Skipped (cached):       {skipped_cached}
  Skipped (decorative):   {skipped_decor}
  Processed by Vision:    {processed}
  Errors:                 {errors}
  New chunks in ChromaDB: {new_chunks}
""")


if __name__ == "__main__":
    main()
