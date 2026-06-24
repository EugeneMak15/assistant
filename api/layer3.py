"""Layer 3 — LLM final judge with signal chain reasoning.
Uses o4-mini (reasoning model) + av_knowledge.md as ground truth.
"""
import os
import json
from pathlib import Path
from .models import Product, ManualChunk

# Load AV knowledge base once at import time
_KB_PATH = Path(__file__).parent.parent / "av_knowledge.md"
try:
    AV_KNOWLEDGE = _KB_PATH.read_text(encoding="utf-8")
except FileNotFoundError:
    AV_KNOWLEDGE = "(av_knowledge.md not found)"


SYSTEM_PROMPT = f"""You are an expert AV systems integrator and equipment advisor for BZB Gear.
Your job: given customer requirements and available products, design the correct, complete, compatible AV signal chain.

You have three knowledge sources — use ALL of them:
1. AV_KNOWLEDGE_BASE below — authoritative rules for signals, cables, distances, topologies
2. <candidates> — the specific BZB Gear products available for this customer
3. <manual_excerpts> — extracted from actual product manuals (vision + text)

══════════════════════════════════════════════════════════
AV KNOWLEDGE BASE
══════════════════════════════════════════════════════════
{AV_KNOWLEDGE}
══════════════════════════════════════════════════════════

YOUR REASONING PROCESS:
1. Identify what signal type(s) are in play (HDMI, SDI, NDI, etc.)
2. Check if every device in the chain supports the required bandwidth for the required resolution
3. Check cable distance against the distance rules
4. Identify any signal type conversions needed (SDI→HDMI, NDI→HDMI, etc.)
5. Verify the chain is complete: source → [conversion?] → switcher/router → [extender?] → display
6. Flag any missing components (e.g. PTZ cameras without controller, SDI without splitter)
7. Check for common installer mistakes from the knowledge base

OUTPUT FORMAT (Markdown):
## Recommended Configuration
[List each recommended product with its role]

## Signal Chain
[Step-by-step: Device A (signal type) → Device B (signal type) → ... → Display]
[Include cable type and max distance for each link]

## Why This Works
[Brief explanation of signal compatibility at each step]

## Compatibility Warnings
[Any risks, limitations, or things to verify — cite manual excerpts when available]

## What's Also Needed
[Cables, accessories, controllers — anything not in the candidates but required]

STRICT RULES:
- Only recommend products present in <candidates>
- If a spec isn't confirmed by manual excerpts, say "verify in product manual"
- Never say "typically" or "usually" about specific products
- If SDI is involved and no SDI-capable product is in candidates, say so explicitly
- If the signal chain has a gap (e.g. SDI camera → HDMI switcher without converter), call it out"""


def format_candidates(candidates: list[Product]) -> str:
    lines = []
    for p in candidates:
        lines.append(f"\n**{p.id}** (category: {p.category})")
        if p.inputs and p.outputs:
            lines.append(f"  - I/O: {p.inputs}×{p.outputs}")
        if p.input_signals:
            lines.append(f"  - Input signals: {', '.join(p.input_signals)}")
        if p.output_signals:
            lines.append(f"  - Output signals: {', '.join(p.output_signals)}")
        if p.resolutions:
            lines.append(f"  - Resolutions: {', '.join(p.resolutions)}")
        if p.max_bandwidth_gbps:
            lines.append(f"  - Bandwidth: {p.max_bandwidth_gbps} Gbps")
        if p.max_distance_m:
            lines.append(f"  - Max distance: {p.max_distance_m}m")
        if p.notes:
            lines.append(f"  - Notes: {p.notes}")
    return "\n".join(lines)


def format_excerpts(chunks: list[ManualChunk]) -> str:
    if not chunks:
        return "(No manual excerpts available yet — vector DB still indexing)"

    by_product: dict[str, list[ManualChunk]] = {}
    for c in chunks:
        by_product.setdefault(c.product_id, []).append(c)

    parts = []
    for pid, pchunks in by_product.items():
        parts.append(f'<manual product="{pid}">')
        for c in sorted(pchunks, key=lambda x: -x.relevance)[:4]:
            flag = " ⚠️ LIMITATION" if c.has_limitation else ""
            parts.append(f"  [{c.heading}]{flag}")
            parts.append(f"  {c.text[:500]}")
        parts.append("</manual>")
    return "\n".join(parts)


def get_recommendation(
    session_dict: dict,
    candidates: list[Product],
    chunks: list[ManualChunk],
    chain_text: str = "",
    question: str | None = None,
) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    cand_text    = format_candidates(candidates)
    excerpt_text = format_excerpts(chunks)
    customer_q   = question or "What equipment do you recommend for my installation?"

    # Build concise session summary (exclude nulls)
    session_summary = {
        k: v for k, v in session_dict.items()
        if v is not None and k not in ("session_id", "step", "notes")
    }

    user_message = f"""## Customer Requirements
{json.dumps(session_summary, indent=2, default=str)}

## Customer Question
{customer_q}

## Available Products (candidates from our catalog)
<candidates>
{cand_text}
</candidates>

{f'## Signal Chain Analysis{chr(10)}<chain>{chr(10)}{chain_text}{chr(10)}</chain>' if chain_text else ''}

## Manual Excerpts
<manual_excerpts>
{excerpt_text}
</manual_excerpts>

Now design the optimal signal chain for this customer using ONLY the candidates listed above.
Apply the AV Knowledge Base rules to verify compatibility at every link."""

    resp = client.chat.completions.create(
        model="o4-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        # o4-mini uses reasoning_effort instead of temperature
        reasoning_effort="high",
    )
    return resp.choices[0].message.content
