"""
Ingest BZB Gear website content (FAQ, Case Studies, Knowledge Base, Solutions, Blog)
into ChromaDB for RAG search.

Pipeline: sitemap → fetch page → extract clean text → chunk → embed → ChromaDB
Collection: "website_content" (separate from manual_chunks and products)

Run:   python ingest_website.py
Resume: safe to re-run — skips already-indexed URLs
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import os, re, time, hashlib, json
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import xml.etree.ElementTree as ET

import truststore; truststore.inject_into_ssl()
from dotenv import load_dotenv; load_dotenv()
from bs4 import BeautifulSoup
from openai import OpenAI
import chromadb
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

console = Console()
client  = OpenAI()

CHROMA_PATH = "./chroma_db"
COLLECTION  = "website_content"

SITEMAPS = [
    ("faq",            "https://bzbgear.com/faq_item-sitemap.xml"),
    ("case_study",     "https://bzbgear.com/case-sitemap.xml"),
    ("knowledge_base", "https://bzbgear.com/knowledge_base-sitemap.xml"),
    ("solution",       "https://bzbgear.com/solution-sitemap.xml"),
    ("blog",           "https://bzbgear.com/post-sitemap.xml"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

MIN_TEXT_LEN  = 200   # skip pages with less content
CHUNK_WORDS   = 400   # target words per chunk
CHUNK_OVERLAP = 50    # overlap in words
FETCH_DELAY   = 0.8   # seconds between requests


# ── Sitemap parsing ───────────────────────────────────────────────────────────

def fetch_sitemap(url: str) -> list[str]:
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=15) as r:
        xml = r.read()
    root = ET.fromstring(xml)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [loc.text for loc in root.findall(".//sm:loc", ns) if loc.text]


# ── Page fetching & cleaning ──────────────────────────────────────────────────

def fetch_page(url: str) -> str | None:
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="replace")
        return html
    except (URLError, HTTPError) as e:
        console.print(f"[yellow]  Fetch error {url[-50:]}: {e}[/yellow]")
        return None


def extract_text(html: str, url: str) -> dict | None:
    """Extract clean text + metadata from page HTML."""
    soup = BeautifulSoup(html, "lxml")

    # Remove noise
    for tag in soup(["script", "style", "nav", "header", "footer",
                     "aside", "form", ".sidebar", ".menu", ".widget",
                     ".related-posts", ".comments", ".breadcrumb"]):
        tag.decompose()

    # Title
    title = ""
    if soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)
    elif soup.find("title"):
        title = soup.find("title").get_text(strip=True)

    # Main content — try common selectors
    content = None
    for selector in ["article", "main", ".entry-content", ".post-content",
                     ".page-content", ".content-area", "#content", "body"]:
        el = soup.select_one(selector)
        if el:
            content = el
            break

    if not content:
        return None

    # Clean text
    raw = content.get_text(separator="\n", strip=True)
    # Collapse excessive blank lines
    lines = [l.strip() for l in raw.splitlines()]
    lines = [l for l in lines if l]
    # Remove lines that are just numbers or single chars (nav artifacts)
    lines = [l for l in lines if len(l) > 3]
    text = "\n".join(lines)

    if len(text) < MIN_TEXT_LEN:
        return None

    return {"title": title, "text": text, "url": url}


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_text(text: str, title: str, url: str, doc_type: str) -> list[dict]:
    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    idx   = 0

    while start < len(words):
        end   = min(start + CHUNK_WORDS, len(words))
        chunk = " ".join(words[start:end])
        # Try to break at sentence boundary
        last_period = chunk.rfind(". ")
        if last_period > len(chunk) * 0.6:
            chunk = chunk[:last_period + 1]

        chunk_id = hashlib.md5(f"{url}::{idx}".encode()).hexdigest()[:16]

        chunks.append({
            "id":   chunk_id,
            "text": f"{title}\n\n{chunk}" if idx == 0 else chunk,
            "meta": {
                "source":    url,
                "title":     title[:200],
                "doc_type":  doc_type,
                "chunk_idx": idx,
                "url":       url,
            }
        })

        start += CHUNK_WORDS - CHUNK_OVERLAP
        idx   += 1
        if end == len(words):
            break

    return chunks


# ── Embeddings ────────────────────────────────────────────────────────────────

def embed_batch(texts: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [r.embedding for r in resp.data]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    chroma     = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = chroma.get_or_create_collection(COLLECTION)

    existing = set(collection.get(include=[])["ids"])
    console.print(f"Already indexed: [cyan]{len(existing)}[/cyan] chunks in '{COLLECTION}'")

    # Gather all URLs
    all_urls: list[tuple[str, str]] = []   # (doc_type, url)
    for doc_type, sitemap_url in SITEMAPS:
        try:
            urls = fetch_sitemap(sitemap_url)
            console.print(f"  {doc_type:15s}: {len(urls)} URLs")
            all_urls.extend([(doc_type, u) for u in urls])
        except Exception as e:
            console.print(f"[red]  {doc_type}: sitemap error — {e}[/red]")

    console.print(f"\nTotal URLs to process: [cyan]{len(all_urls)}[/cyan]")

    # Filter already-done URLs (check by URL hash)
    def url_done(url: str) -> bool:
        h = hashlib.md5(url.encode()).hexdigest()[:16]
        return h + "_0" in existing  # first chunk of this URL exists

    to_process = [(dt, u) for dt, u in all_urls if not url_done(u)]
    console.print(f"New URLs (not yet indexed): [cyan]{len(to_process)}[/cyan]\n")

    if not to_process:
        console.print("[green]All URLs already indexed![/green]")
        return

    stats = {"fetched": 0, "skipped_cf": 0, "skipped_short": 0,
             "chunks": 0, "errors": 0}

    UPSERT_BATCH = 50
    pending_ids, pending_texts, pending_metas, pending_embeddings = [], [], [], []

    def flush():
        if not pending_ids:
            return
        collection.upsert(
            ids=pending_ids[:],
            documents=pending_texts[:],
            embeddings=pending_embeddings[:],
            metadatas=pending_metas[:],
        )
        pending_ids.clear(); pending_texts.clear()
        pending_metas.clear(); pending_embeddings.clear()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching pages...", total=len(to_process))

        for doc_type, url in to_process:
            slug = url.split("/")[-2] if url.endswith("/") else url.split("/")[-1]
            progress.update(task, description=f"[cyan]{slug[:35]}[/cyan]")

            html = fetch_page(url)
            if not html:
                stats["errors"] += 1
                progress.advance(task)
                time.sleep(FETCH_DELAY)
                continue

            # Detect Cloudflare block (returns JS challenge page)
            if "cf-browser-verification" in html or "Just a moment" in html or len(html) < 500:
                stats["skipped_cf"] += 1
                progress.advance(task)
                time.sleep(FETCH_DELAY)
                continue

            page = extract_text(html, url)
            if not page:
                stats["skipped_short"] += 1
                progress.advance(task)
                time.sleep(FETCH_DELAY)
                continue

            chunks = chunk_text(page["text"], page["title"], url, doc_type)
            if not chunks:
                progress.advance(task)
                time.sleep(FETCH_DELAY)
                continue

            # Embed this page's chunks
            try:
                texts_to_embed = [c["text"] for c in chunks]
                embeddings     = embed_batch(texts_to_embed)

                for c, emb in zip(chunks, embeddings):
                    if c["id"] not in existing:
                        pending_ids.append(c["id"])
                        pending_texts.append(c["text"])
                        pending_metas.append(c["meta"])
                        pending_embeddings.append(emb)
                        stats["chunks"] += 1

                if len(pending_ids) >= UPSERT_BATCH:
                    flush()

                stats["fetched"] += 1

            except Exception as e:
                console.print(f"[red]  Embed error {slug}: {e}[/red]")
                stats["errors"] += 1

            progress.advance(task)
            time.sleep(FETCH_DELAY)

    flush()

    console.print(f"""
[bold green]Done![/bold green]
  Pages fetched:         {stats['fetched']}
  Cloudflare blocks:     {stats['skipped_cf']}
  Too short / empty:     {stats['skipped_short']}
  Errors:                {stats['errors']}
  New chunks indexed:    {stats['chunks']}
  Total in collection:   {collection.count()}
""")


if __name__ == "__main__":
    main()
