"""Layer 2 — RAG: semantic search over manual chunks + product embeddings."""
import json
import os
import chromadb
from .db import get_chroma
from .models import ManualChunk

CHROMA_PATH = "./chroma_db"


def embed_query(text: str) -> list[float]:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.embeddings.create(model="text-embedding-3-small", input=[text])
    return resp.data[0].embedding


def semantic_search_products(query: str, n: int = 8, filters: dict | None = None) -> list[dict]:
    """
    Search the products collection semantically.
    Returns list of {id, score, category, input_signals, ...}
    Used by chat to find candidates without rigid SQL filters.
    """
    try:
        chroma = chromadb.PersistentClient(path=CHROMA_PATH)
        col = chroma.get_or_create_collection("products")
        if col.count() == 0:
            return []

        qe = embed_query(query)
        kwargs = dict(
            query_embeddings=[qe],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )
        if filters:
            kwargs["where"] = filters

        results = col.query(**kwargs)
        if not results["ids"] or not results["ids"][0]:
            return []

        out = []
        for id_, meta, dist in zip(
            results["ids"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            out.append({
                "id":              id_,
                "score":           round(1 - dist, 4),
                "category":        meta.get("category", ""),
                "input_signals":   json.loads(meta.get("input_signals",  "[]")),
                "output_signals":  json.loads(meta.get("output_signals", "[]")),
                "resolutions":     json.loads(meta.get("resolutions",    "[]")),
                "max_distance_m":  meta.get("max_distance_m", 0),
                "inputs":          meta.get("inputs", 0),
                "outputs":         meta.get("outputs", 0),
            })
        return out
    except Exception as e:
        return []


def get_chunks_for_candidates(
    candidate_ids: list[str],
    query: str,
    chunks_per_candidate: int = 5,
) -> list[ManualChunk]:
    """
    Layer 2: For each candidate, retrieve the top-k most relevant chunks.
    Searches: manual_chunks (by product_id) + website_content (by related_skus).
    """
    query_embedding = embed_query(query)
    all_chunks: list[ManualChunk] = []
    seen_texts: set[str] = set()

    # ── Source 1: manual chunks (text + vision extracted) ──────────────────
    manual_col = get_chroma()
    if manual_col and manual_col.count() > 0:
        for product_id in candidate_ids:
            # Priority: limitation chunks first
            try:
                results = manual_col.query(
                    query_embeddings=[query_embedding],
                    n_results=min(3, chunks_per_candidate),
                    where={"$and": [
                        {"product_id": {"$eq": product_id}},
                        {"has_limitation": {"$eq": True}},
                    ]},
                    include=["documents", "metadatas", "distances"],
                )
                _add_results(results, all_chunks, seen_texts, source="manual")
            except Exception:
                pass

            # General relevance
            try:
                results = manual_col.query(
                    query_embeddings=[query_embedding],
                    n_results=chunks_per_candidate,
                    where={"product_id": {"$eq": product_id}},
                    include=["documents", "metadatas", "distances"],
                )
                _add_results(results, all_chunks, seen_texts, source="manual")
            except Exception:
                pass

    # ── Source 2: website content (blog, FAQ, KB, case studies) ────────────
    try:
        chroma = chromadb.PersistentClient(path=CHROMA_PATH)
        web_col = chroma.get_or_create_collection("website_content")

        if web_col.count() > 0:
            # Semantic search — top relevant pages for this query
            web_results = web_col.query(
                query_embeddings=[query_embedding],
                n_results=min(10, len(candidate_ids) * 3),
                include=["documents", "metadatas", "distances"],
            )
            # Filter: keep only chunks that mention one of our candidate SKUs
            if web_results["ids"] and web_results["ids"][0]:
                for doc, meta, dist in zip(
                    web_results["documents"][0],
                    web_results["metadatas"][0],
                    web_results["distances"][0],
                ):
                    related = json.loads(meta.get("related_skus", "[]"))
                    if any(sku in candidate_ids for sku in related):
                        key = doc[:80]
                        if key not in seen_texts:
                            seen_texts.add(key)
                            all_chunks.append(ManualChunk(
                                product_id   = related[0] if related else "website",
                                heading      = meta.get("title", "")[:80],
                                text         = doc,
                                doc_type     = meta.get("doc_type", "website"),
                                has_limitation = False,
                                summary      = meta.get("title", "")[:100],
                                relevance    = round(1 - dist, 4),
                            ))
    except Exception:
        pass

    all_chunks.sort(key=lambda c: c.relevance, reverse=True)
    return all_chunks


def _add_results(results: dict, chunks: list, seen: set, source: str = "manual"):
    if not results["documents"] or not results["documents"][0]:
        return
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        key = doc[:80]
        if key in seen:
            continue
        seen.add(key)
        chunks.append(ManualChunk(
            product_id   = meta.get("product_id", "?"),
            heading      = meta.get("heading", ""),
            text         = doc,
            doc_type     = meta.get("doc_type", "spec"),
            has_limitation = bool(meta.get("has_limitation", False)),
            summary      = meta.get("summary", ""),
            relevance    = round(1 - dist, 4),
        ))
