"""Lazy, exact-SKU FTS index of PDFs attached to Dev products."""
from __future__ import annotations

import os
import base64
import re
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse

from pypdf import PdfReader

DB_PATH = Path("/opt/product-assistant-dev/product_docs.db")
ROOTS = {
    "dev.bzbgear.com": Path("/var/www/bzbdev/data/www/dev.bzbgear.com/wp-content/uploads"),
    "bzbgear.com": Path("/var/www/bzbprod/data/www/bzbgear.com/wp-content/uploads"),
    "www.bzbgear.com": Path("/var/www/bzbprod/data/www/bzbgear.com/wp-content/uploads"),
}


def local_attachment(url: str) -> Path | None:
    parsed = urlparse(url)
    root = ROOTS.get(parsed.hostname or "")
    prefix = "/wp-content/uploads/"
    if parsed.scheme != "https" or root is None or not parsed.path.startswith(prefix):
        return None
    path = (root / unquote(parsed.path[len(prefix):])).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        return None
    if path.stat().st_size > 20_000_000:
        return None
    return path


def open_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.execute("CREATE TABLE IF NOT EXISTS indexed_files (sku TEXT, url TEXT, mtime INTEGER, size INTEGER, PRIMARY KEY(sku,url))")
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks USING fts5(sku UNINDEXED, title UNINDEXED, url UNINDEXED, text)")
    db.execute("CREATE TABLE IF NOT EXISTS diagram_descriptions (sku TEXT, url TEXT, mtime INTEGER, text TEXT, PRIMARY KEY(sku,url))")
    return db


def index_resources(skus: list[str], resources: list[dict]) -> None:
    db = open_db()
    try:
        for item in resources:
            url = item.get("url", "")
            path = local_attachment(url)
            if path is None or path.suffix.lower() != ".pdf":
                continue
            stat = path.stat()
            for sku in skus:
                old = db.execute("SELECT mtime,size FROM indexed_files WHERE sku=? AND url=?", (sku, url)).fetchone()
                if old == (stat.st_mtime_ns, stat.st_size):
                    continue
                db.execute("DELETE FROM doc_chunks WHERE sku=? AND url=?", (sku, url))
                try:
                    reader = PdfReader(str(path))
                    for page_num, page in enumerate(reader.pages[:100], 1):
                        text = re.sub(r"\s+", " ", page.extract_text() or "").strip()
                        if len(text) < 60:
                            continue
                        for pos in range(0, len(text), 1800):
                            chunk = text[pos:pos + 2200]
                            db.execute("INSERT INTO doc_chunks(sku,title,url,text) VALUES(?,?,?,?)",
                                       (sku, f"{item.get('title', 'PDF')} p. {page_num}", url, chunk))
                    db.execute("INSERT OR REPLACE INTO indexed_files VALUES(?,?,?,?)",
                               (sku, url, stat.st_mtime_ns, stat.st_size))
                    db.commit()
                except Exception:
                    db.rollback()
    finally:
        db.close()


def index_diagrams(skus: list[str], resources: list[dict], client) -> list[dict]:
    """Describe attached connection diagrams once, then reuse the bounded description."""
    db = open_db()
    out = []
    try:
        for item in resources:
            url = item.get("url", "")
            title = item.get("title", "")
            path = local_attachment(url)
            if (path is None or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}
                    or path.stat().st_size > 4_000_000
                    or not re.search(r"diagram|connection|wiring|schematic|diag", title + " " + path.name, re.I)):
                continue
            stamp = path.stat().st_mtime_ns
            row = db.execute("SELECT mtime,text FROM diagram_descriptions WHERE sku=? AND url=?", (skus[0], url)).fetchone()
            if row is None or row[0] != stamp:
                mime = "image/png" if path.suffix.lower() == ".png" else ("image/webp" if path.suffix.lower() == ".webp" else "image/jpeg")
                encoded = base64.b64encode(path.read_bytes()).decode("ascii")
                response = client.chat.completions.create(
                    model=os.getenv("PRODUCT_AI_VISION_MODEL", "gpt-4o-mini"),
                    messages=[{"role": "user", "content": [
                        {"type": "text", "text": f"Transcribe the visible device labels, ports, arrows and connection flow in this {skus[0]} diagram. Do not infer any hidden capabilities or specifications. Keep under 250 words."},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                    ]}], max_tokens=350,
                )
                description = (response.choices[0].message.content or "").strip()[:2000]
                if description:
                    db.execute("INSERT OR REPLACE INTO diagram_descriptions VALUES(?,?,?,?)", (skus[0], url, stamp, description))
                    db.commit()
            else:
                description = row[1]
            if description:
                out.append({"kind": "Product diagram", "title": title, "url": url, "text": description})
            if len(out) >= 3:
                break
    finally:
        db.close()
    return out


def search(skus: list[str], question: str, limit: int = 6) -> list[dict]:
    tokens = re.findall(r"[\w]{3,}", question.lower())[:12]
    if not tokens:
        return []
    query = " OR ".join(f'"{token}"' for token in tokens)
    placeholders = ",".join("?" for _ in skus)
    db = open_db()
    try:
        rows = db.execute(
            f"SELECT title,url,text FROM doc_chunks WHERE sku IN ({placeholders}) AND doc_chunks MATCH ? ORDER BY bm25(doc_chunks) LIMIT ?",
            (*skus, query, limit),
        ).fetchall()
        return [{"kind": "Product PDF", "title": title, "url": url, "text": text} for title, url, text in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        db.close()
