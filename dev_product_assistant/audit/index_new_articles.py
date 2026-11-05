"""Targeted, source-preserving Advisor website_content upsert for seven new families."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

parser = argparse.ArgumentParser()
parser.add_argument("--apply", action="store_true")
parser.add_argument("--metadata-only", action="store_true")
args = parser.parse_args()
pages = json.load(sys.stdin)
db = chromadb.PersistentClient(path="/opt/assistant/chroma_db")
collection = db.get_collection("website_content")
load_dotenv("/opt/assistant/.env")
client = OpenAI() if args.apply and not args.metadata_only else None

for page in pages:
    url = page["url"]
    if not url.startswith("https://bzbgear.com/") or "/es/" in url:
        raise ValueError(f"Non-English or unexpected source URL: {url}")
    text = page["text"]
    if len(text) < 150:
        continue
    existing = collection.get(where={"url": url}, include=["metadatas"])
    related = set(page["related_skus"])
    for meta in existing["metadatas"]:
        try:
            related.update(json.loads(meta.get("related_skus", "[]")))
        except (ValueError, TypeError):
            pass
    words = text.split()
    chunks = []
    for start in range(0, len(words), 350):
        segment = " ".join(words[start:start + 400])
        if segment:
            chunks.append(segment)
        if start + 400 >= len(words):
            break
    print(json.dumps({"url": url, "existing_chunks": len(existing["ids"]),
                      "new_chunks": len(chunks), "related_skus": sorted(related)}, ensure_ascii=False))
    if not args.apply:
        continue
    if existing["ids"]:
        # Preserve the existing indexed content/embeddings and unrelated SKU links.
        metas = []
        for meta in existing["metadatas"]:
            updated = dict(meta)
            updated["related_skus"] = json.dumps(sorted(related))
            metas.append(updated)
        collection.update(ids=existing["ids"], metadatas=metas)
        continue
    if args.metadata_only:
        continue
    if not chunks:
        continue
    for attempt in range(5):
        try:
            embeddings = client.embeddings.create(model="text-embedding-3-small", input=[page["title"] + "\n" + x for x in chunks]).data
            break
        except Exception as exc:
            if getattr(exc, "code", None) == "credit_balance_exhausted":
                raise
            if attempt == 4:
                raise
            time.sleep(5 * (attempt + 1))
    ids = [hashlib.md5(f"{url}::{i}".encode()).hexdigest()[:16] for i in range(len(chunks))]
    metas = [{"source": url, "url": url, "title": page["title"][:200],
              "doc_type": "blog" if page["doc_type"] == "post" else page["doc_type"],
              "chunk_idx": i, "related_skus": json.dumps(sorted(related))}
             for i in range(len(chunks))]
    collection.upsert(ids=ids, documents=[page["title"] + "\n\n" + x for x in chunks],
                      embeddings=[item.embedding for item in embeddings], metadatas=metas)
    time.sleep(2)
print("mode", "METADATA_ONLY" if args.metadata_only else ("APPLIED" if args.apply else "DRY_RUN"), "pages", len(pages))
