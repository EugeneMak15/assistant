"""
BZB Gear Compatibility Advisor - Interactive Query CLI
Ask any AV equipment compatibility question and get a grounded answer from the manuals.
"""

import os
import json
from dotenv import load_dotenv
from openai import OpenAI
import chromadb
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

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

SYSTEM_PROMPT = """You are a BZB Gear AV equipment compatibility advisor.

STRICT RULES:
1. You may ONLY cite information present in the <manual_excerpts> provided.
2. Never use your training knowledge about specific product specifications.
3. If a limitation or compatibility detail is NOT in the excerpts, say "please verify in the product manual" — do not assume or invent.
4. Always cite the product model and section heading when referencing a manual excerpt.
5. If two products are both compatible, present both with a clear comparison.
6. If a required feature is not supported by any product in the excerpts, say so clearly.
7. Never use "typically", "usually", "in most cases" — only state what the manuals say.
8. If the excerpts don't contain enough information to answer confidently, say so explicitly.

Your goal: help the customer understand if specific BZB Gear products work together for their installation scenario."""


def embed_query(text: str) -> list[float]:
    resp = client.embeddings.create(model="text-embedding-3-small", input=[text])
    return resp.data[0].embedding


def search_chunks(query: str, n_results: int = 12, doc_types: list[str] | None = None) -> list[dict]:
    """Search ChromaDB for relevant manual chunks."""
    query_embedding = embed_query(query)

    where = None
    if doc_types:
        where = {"doc_type": {"$in": doc_types}}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({
            "text": doc,
            "product_id": meta.get("product_id", "unknown"),
            "heading": meta.get("heading", ""),
            "source_file": meta.get("source_file", ""),
            "doc_type": meta.get("doc_type", ""),
            "has_limitation": meta.get("has_limitation", "False") == "True",
            "summary": meta.get("summary", ""),
            "relevance": 1 - dist,  # cosine similarity
        })

    return chunks


def format_excerpts(chunks: list[dict]) -> str:
    """Format chunks into structured context for the LLM."""
    by_product: dict[str, list] = {}
    for chunk in chunks:
        pid = chunk["product_id"]
        by_product.setdefault(pid, []).append(chunk)

    parts = []
    for product_id, product_chunks in by_product.items():
        parts.append(f'<manual_excerpts product="{product_id}">')
        for c in product_chunks:
            limitation_flag = " [LIMITATION]" if c["has_limitation"] else ""
            parts.append(f'  [{c["heading"]}]{limitation_flag}')
            parts.append(f'  {c["text"]}')
            parts.append("")
        parts.append("</manual_excerpts>")
        parts.append("")

    return "\n".join(parts)


def ask(question: str, verbose: bool = False):
    console.print(f"\n[dim]Searching manuals...[/dim]")

    # Search for both general relevance and limitation-specific chunks
    general_chunks = search_chunks(question, n_results=10)
    limitation_chunks = search_chunks(
        question + " limitation restriction requirement",
        n_results=6,
        doc_types=["limitation", "compatibility", "spec"],
    )

    # Merge and deduplicate by text
    seen = set()
    all_chunks = []
    for c in general_chunks + limitation_chunks:
        key = c["text"][:100]
        if key not in seen:
            seen.add(key)
            all_chunks.append(c)

    # Sort by relevance
    all_chunks.sort(key=lambda x: x["relevance"], reverse=True)
    top_chunks = all_chunks[:12]

    if verbose:
        console.print(f"\n[dim]Retrieved {len(top_chunks)} chunks from {len(set(c['product_id'] for c in top_chunks))} products[/dim]")
        for c in top_chunks[:5]:
            console.print(f"  [dim]{c['product_id']} | {c['heading']} | relevance={c['relevance']:.3f} | {c['doc_type']}[/dim]")

    if not top_chunks:
        console.print("[red]No relevant manual content found. Have you run ingest.py first?[/red]")
        return

    excerpts = format_excerpts(top_chunks)
    products_mentioned = list(set(c["product_id"] for c in top_chunks))

    user_message = f"""Customer question: {question}

Products found in database: {', '.join(products_mentioned)}

{excerpts}

Based ONLY on the manual excerpts above, answer the customer's compatibility question."""

    console.print("[dim]Asking LLM...[/dim]\n")

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0,
    )

    answer = response.choices[0].message.content
    console.print(Panel(Markdown(answer), title="[bold green]Advisor Response[/bold green]", border_style="green"))

    # Show sources
    console.print("\n[dim]Sources used:[/dim]")
    for c in top_chunks[:6]:
        flag = " ⚠️" if c["has_limitation"] else ""
        console.print(f"  [dim]{c['product_id']} — {c['heading']} ({c['doc_type']}){flag}[/dim]")


def show_stats():
    count = collection.count()
    console.print(f"\n[bold]Database stats:[/bold] {count} chunks indexed")
    if count > 0:
        # Sample to show products
        sample = collection.get(limit=500, include=["metadatas"])
        products = set(m.get("product_id", "?") for m in sample["metadatas"])
        console.print(f"Products: {', '.join(sorted(products))}")


def main():
    console.print(Panel(
        "[bold]BZB Gear AI Equipment Advisor[/bold]\n"
        "Ask about product compatibility, signal chains, and installation requirements.\n\n"
        "Commands: [cyan]stats[/cyan] | [cyan]verbose[/cyan] | [cyan]quit[/cyan]",
        border_style="blue"
    ))

    show_stats()

    verbose = False
    while True:
        try:
            question = console.input("\n[bold cyan]Your question:[/bold cyan] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Bye![/dim]")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            break
        if question.lower() == "stats":
            show_stats()
            continue
        if question.lower() == "verbose":
            verbose = not verbose
            console.print(f"Verbose mode: {'on' if verbose else 'off'}")
            continue

        ask(question, verbose=verbose)


if __name__ == "__main__":
    main()
