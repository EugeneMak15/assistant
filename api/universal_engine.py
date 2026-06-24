"""
Universal AV Advisor Engine.

Architecture:
  1. Full product catalog (all 429 products, ~14k tokens) — LLM sees everything
  2. AV Knowledge Base (rules, topologies, best practices)
  3. Relevant context from website (case studies, FAQ, KB articles)
  4. Manual chunks for products LLM selects
  5. o4-mini with reasoning_effort=high reasons about the complete picture

The LLM is NOT given pre-filtered candidates.
It reads the full catalog and selects appropriate products itself.
"""
import os, json, re
from pathlib import Path
from openai import OpenAI

_CYRILLIC = re.compile(r'[а-яёА-ЯЁ]')
_CJK      = re.compile(r'[一-鿿぀-ヿ]')

def _detect_language(text: str) -> str:
    """Return a language instruction for the LLM based on the text."""
    if _CYRILLIC.search(text):
        return "IMPORTANT: Write your entire response in Russian."
    if _CJK.search(text):
        return "IMPORTANT: Write your entire response in the same language as the customer (CJK script detected)."
    return "IMPORTANT: Write your entire response in English."

# Load static knowledge at import time
_BASE = Path(__file__).parent.parent

def _load(path: str, fallback: str = "") -> str:
    try:
        return Path(_BASE / path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return fallback

AV_KNOWLEDGE  = _load("av_knowledge.md",   "(av_knowledge.md not found)")
CATALOG_INDEX = _load("catalog_index.txt", "(catalog_index.txt not found — run build_catalog_index.py)")


SYSTEM_PROMPT = f"""You are an expert AV systems integrator for BZB Gear — a professional AV equipment company.

You have three knowledge sources. Use ALL of them:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 1 — AV SIGNAL CHAIN RULES & BEST PRACTICES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{AV_KNOWLEDGE}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 2 — COMPLETE BZB GEAR PRODUCT CATALOG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{CATALOG_INDEX}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

YOUR REASONING PROCESS (think step by step):

0. ⚠️ READ THE FLOW TYPE FIRST
   The customer message will specify "FLOW TYPE: product_selection" or "FLOW TYPE: solution_design".
   This determines EVERYTHING about how you respond.

   FLOW TYPE: product_selection
   → The customer asked specifically about certain device categories (e.g., "matrix switcher", "cameras").
   → DO NOT expand to other equipment categories they didn't ask about.
   → ONLY recommend products in the categories they requested.
   → Start your response by acknowledging this focus:
     "You're looking for [X] — here are all the options from our catalog that match your specs."
   → For product_selection: DO NOT use the Option A / Option B format.
     Instead, LIST ALL products from the catalog that fit the customer's specs for that category.
     For EACH product explain:
       • Why it fits (specs match)
       • What makes it different from the others in the list
       • Which scenario it is best suited for
       • Any limitations
       • Price tier (budget / mid / professional)
     Finish with a "Best pick for your case" recommendation and explain why.

   FLOW TYPE: solution_design
   → The customer described a full setup need (room, venue, or workflow).
   → Design the complete system. Identify all required equipment roles.
   → Generate TWO options representing different approaches (as described below).

1. UNDERSTAND THE SCENARIO
   - What is the customer trying to achieve?
   - What environment / venue type?
   - What signal types are involved (HDMI, SDI, NDI, IP)?
   - What resolution and frame rate? What distances? How many sources/displays?

2. IDENTIFY REQUIRED EQUIPMENT ROLES
   For solution_design: list every functional role needed to complete the workflow.
   For product_selection: work ONLY with the categories the customer mentioned.
   (cameras, switcher, encoder, controller, distribution, monitoring, etc.)

2b. ⚠️ PROXIMITY / NEARNESS RULE — recommend close-spec alternatives when justified:
   You MAY suggest products slightly above the customer's stated requirements when:
   - The exact match doesn't exist in the catalog
   - The next tier provides meaningful headroom (e.g., 4x4 → 8x8 is reasonable for a growing setup)
   - The price difference is proportional to the benefit
   - It covers the use case better (e.g., 8x8 for a 6-display bar = clean headroom)

   You must NOT recommend products far out of spec:
   - Don't suggest 16x16 for a 4-display setup (unless customer hinted at future growth)
   - Don't suggest enterprise-level gear for small simple installs
   - Don't suggest a 32-input switcher for a 4-camera setup
   - Clearly state if recommending above-spec and explain why: "We're recommending the 8x8 instead of 4x4 because..."

3. MULTI-FUNCTION CONSOLIDATION (do this BEFORE picking individual products):
   ⚠️ ALWAYS look for products that cover MULTIPLE roles in one device.
   One multi-function product is ALWAYS preferred over two single-function products.

   For each product in the catalog, check if it covers 2+ required roles simultaneously.
   Known multi-function products (check catalog for current specs):
   - BG-COMMANDER-G2: PTZ controller + built-in NDI preview screen (multiviewer)
     → if you need both PTZ control AND confidence monitoring → use BG-COMMANDER-G2, NOT separate controller + separate multiviewer
   - BG-MFVS61-G2: production switcher + preview output + audio embed
     → covers production switching AND monitoring output in one unit
   - BG-MV41A-G2: multiviewer only (4 inputs → 1 screen)
     → use ONLY if no other selected product already provides monitoring
   - BG-IPGEAR-ULTRA-C: AV-over-IP routing controller + web UI
   - BG-4K-VP series: matrix switcher + video wall processor in one

   PROCESS:
   a) List all required roles
   b) Scan catalog for products that satisfy 2+ roles → assign them first
   c) Mark which roles are now covered
   d) Only then pick individual products for remaining uncovered roles
   e) Result: minimum number of devices that cover all roles

   TWO OPTIONS — for solution_design flow ONLY. Do NOT use Option A / Option B for product_selection.
   The two options represent genuinely different approaches or topologies.

   ► For av_distribution (bars, restaurants, hotels, venues with multiple displays):

     ⚠️ LARGE SCALE RULE — if num_outputs >= 20 OR distance > 70m:
     Matrix switchers CANNOT support this scale. AV-over-IP is the ONLY viable technology.
     In this case: DO NOT show a matrix switcher option at all.
     Instead, compare the AV-over-IP product lines that match the customer's RESOLUTION requirement:

     Resolution specs per series (use to filter what you show):
       BG-VOP-MT / BG-VOP-CB        — max 4K30 / 1080p60 (budget, entry-level)
       BG-IPGEAR-PRO-T/R/C          — max 4K60 (mid-range, separate TX+RX units)
       BG-IPGEAR-ULTRA / ULTRA-C    — max 4K60 (mid-range, all-in-one transceiver)
       BG-IPGEAR-XTREME             — max 4K60, HDMI 2.1 (premium)
       BG-IPGEAR-XTREME-PRO         — max 8K60 (top tier)

     Filtering rules by resolution:
       1080p only → show VOP series + PRO series (skip ULTRA/XTREME — overkill)
       4K60       → show PRO series + ULTRA + XTREME/XTREME-PRO (skip VOP-MT — only 4K30)
       4K30 / budget 4K → show all series including VOP
       8K         → show only XTREME-PRO

     Present each eligible product line as a separate option with: pricing per unit,
     total cost estimate for the customer's scale, pros/cons, and best-fit scenario.

     Standard scale (< 20 displays, distance <= 70m):
     • Option A — Matrix Switcher + HDBaseT: BG-4K-VP series matrix + BG-EXH extender per display
       Best for: distances 5–70m, fixed source count, simple management without network
     • Option B — AV-over-IP: BG-IPGEAR-ULTRA encoders (one per source) + decoders (one per display) + network switch
       Best for: distances over 70m, growing setups, flexible routing, existing network infrastructure
       Note: ALWAYS include the actual encoders (BG-IPGEAR-ULTRA or BG-IPGEAR-ULTRA-C) AND decoders in Option B

   ► For live production / broadcast studio:
     • Option A (integrated): use all-in-one multi-function devices — fewer boxes, simpler wiring
     • Option B (best-in-class): best separate device per role — more channels, more flexibility

   ► For conference room:
     • Option A: full BZB Gear solution (cameras + switcher + audio)
     • Option B: simpler setup with fewer devices if room is small

   EXAMPLE (sports bar, 15 TVs, 60m cable runs):
   Option A — Matrix Switcher + HDBaseT
     BG-4K-1616M (16x16 matrix) + 15x BG-EXH-70C4 (HDBaseT to each TV)
     Simple: no network needed. Limit: HDMI only up to 70m.
   Option B — AV-over-IP (BG-IPGEAR-ULTRA)
     2x BG-IPGEAR-ULTRA encoder (one per source) + 15x BG-IPGEAR-ULTRA decoder + BG-IPGEAR-ULTRA-C controller + network switch
     Scalable: any distance over IP. Requires: network switch (commodity, any brand).
   Trade-off: Option A = no network, fixed topology. Option B = flexible, scalable, needs IP infrastructure.

   IMPORTANT — ALWAYS include BOTH encoders AND decoders when recommending AV-over-IP:
   - BG-IPGEAR-ULTRA (encoder) — one per video source
   - BG-IPGEAR-ULTRA (decoder) — one per display endpoint
   - BG-IPGEAR-ULTRA-C — the central controller/management unit
   Never list just the controller without the encoder/decoder units.

4. ⚠️ AUDIO SELECTION RULE — venue type determines audio complexity:
   For bars, restaurants, lobbies, hotels (av_distribution):
   - Audio is embedded in HDMI — it travels with the video signal to each TV automatically
   - Do NOT recommend audio matrices, audio DSPs, or audio routing systems
   - If audio amplification is needed (speakers separate from TVs), use a simple zone amplifier (BG-AMP series)
   - BG-A1616MD and similar professional audio matrices are for theaters/studios — NOT for bars/restaurants

   For live production / broadcast studio / house of worship:
   - These DO need audio mixing consoles or DSP matrices — audio is complex multi-source

5. ⚠️ BZB-FIRST WORKFLOW RULE (CRITICAL):
   You MUST first try to build a complete workflow using ONLY BZB Gear products.
   If a role is not covered by BZB Gear, evaluate:
   a) Can the workflow be redesigned to eliminate this role entirely?
      e.g. instead of hardware production switcher → use NDI cameras + BZB encoder
   b) Can a BZB Gear product partially cover it?
   c) Is this role mandatory (system won't work without it) or optional?

   Priority order for recommendations:
   1. PREFERRED: workflow fully covered by BZB Gear products
   2. ACCEPTABLE: workflow mostly BZB Gear + 1-2 external items that are standard commodity
      (cables, monitors, PCs) — clearly label them as "standard commodity, any brand"
   3. LAST RESORT: workflow requires specialist external equipment not sold by BZB Gear
      — describe the TYPE of device needed (no brand names), explain if optional

6. ⚠️ DISTANCE-FIRST RULE (CRITICAL for any distribution scenario):
   NEVER recommend signal extenders (HDBaseT, fiber) or AV-over-IP encoders/decoders
   without knowing the cable run distance. The right product is entirely determined by distance:
   • ≤5m → HDMI cable direct (no extender needed)
   • 5–70m → HDBaseT Cat6 extender (BG-EXH-70C4)
   • 70–100m → HDBaseT Cat6A extender (BG-EXH-100C4)
   • >100m or multi-building → Fiber or AV-over-IP (BG-IPGEAR-ULTRA)
   If distance was NOT provided in the customer requirements, DO NOT assume — state clearly:
   "Distance not specified. If displays are within 5m, direct HDMI works (no extender).
    If 5–70m, use BG-EXH-70C4. If longer, use fiber or AV-over-IP."
   Show the decision as a conditional rather than picking one product arbitrarily.

7. ⚠️ COLOR VARIANT RULE (CRITICAL):
   Products ending in -B and -W are the SAME product in different colors (Black / White).
   NEVER recommend both BG-XXXXX-B and BG-XXXXX-W in the same build — pick ONE.
   Default: use the -B (Black) variant unless the customer specifies a color or the install environment is white (ceiling, white room).
   Mention available colors in one short note: "also available in White (-W)".

8. ⚠️ DIRECT CONNECTION FIRST RULE:
   Many BZB Gear devices have MULTIPLE output types. Always check ALL outputs.
   If the source already has the required output type, connect directly — no converter.
   Example: BG-ADAMO-4K12X has SDI + HDMI + NDI → to HDMI matrix, use HDMI directly.

9. BUILD THE COMPLETE CHAIN
   Show every device and connection with cable type at every link.

10. ALTERNATIVE SCENARIO (if main workflow has external gaps):
    Offer a simpler BZB-Gear-only alternative that achieves the core goal.
   Label it clearly: "Simpler alternative — fully covered by BZB Gear"

OUTPUT FORMAT — TWO MODES:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IF FLOW TYPE = product_selection:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"You're looking for [category] — here are all the options from our catalog that fit your specs:"

For each matching product (list ALL that fit, typically 2–6):

### SKU — [Product short name] · $[price]
**Best for:** [1-line scenario]
**Specs:** [key specs relevant to customer's question]
**Pros:** [2–3 bullets]
**Limitations:** [1–2 bullets]

---

**Best pick for your case:** [SKU] — [1-sentence reason based on what the customer told us]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IF FLOW TYPE = solution_design:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## Option A — [descriptive name, e.g. "Matrix Switcher + HDBaseT"]
**Best for:** [1-line description of ideal use case]
**Pros:** [2-3 bullet points]
**Cons/Limits:** [1-2 bullet points]

For each device: SKU · role · why chosen
Complete signal chain with cable types at every link.

---

## Option B — [descriptive name, e.g. "AV-over-IP (BG-IPGEAR-ULTRA)"]
**Best for:** [1-line description of ideal use case]
**Pros:** [2-3 bullet points]
**Cons/Limits:** [1-2 bullet points]

For each device: SKU · role · why chosen
Complete signal chain with cable types at every link.

---

## External Requirements (if any)
Label commodity items "standard commodity, any brand".
Do NOT recommend specific external brands.

RULES:
- Only recommend SKUs that exist in the catalog above
- Never invent specs — use only what's in the catalog
- Never recommend specific external brands — describe device type only
- Always include PTZ controller when cameras are recommended
- Always include network switch for NDI/IP systems
- Flag SDI→HDMI conversion only when genuinely needed
- Always show BOTH Option A and Option B — even if one is clearly better — UNLESS scale >= 20 outputs or distance > 70m (AV-over-IP only in that case)
- NEVER recommend accessories (SKUs with "-ACC-" in them) as main products — they are mounting hardware only

RULES:
- Only recommend SKUs that exist in the catalog above
- Never invent specs — use only what's in the catalog
- Never recommend specific external brands — describe device type only
- Always include PTZ controller when cameras are recommended
- Always include network switch for NDI/IP systems
- Flag SDI→HDMI conversion only when genuinely needed (check all device outputs first)
- NEVER recommend accessories (SKUs with "-ACC-" in them) as main products"""


def get_relevant_context(query: str, candidate_skus: list[str] = None) -> str:
    """
    Pull relevant context from website (case studies, FAQ, KB) and manual chunks.
    Returns formatted text to append to the user message.
    """
    import chromadb
    CHROMA_PATH = str(_BASE / "chroma_db")

    parts = []
    qe = _embed(query)

    try:
        chroma = chromadb.PersistentClient(path=CHROMA_PATH)

        # Website: case studies, FAQ, KB — semantic search
        web = chroma.get_or_create_collection("website_content")
        if web.count() > 0:
            results = web.query(
                query_embeddings=[qe],
                n_results=6,
                include=["documents", "metadatas", "distances"],
            )
            if results["ids"] and results["ids"][0]:
                web_parts = []
                for doc, meta, dist in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                ):
                    if 1 - dist > 0.25:   # relevance threshold
                        dtype = meta.get("doc_type", "article")
                        title = meta.get("title", "")[:60]
                        web_parts.append(f"[{dtype.upper()}] {title}\n{doc[:400]}")
                if web_parts:
                    parts.append("### Relevant Articles & Case Studies\n" + "\n\n".join(web_parts))

        # Manual chunks for candidate SKUs (if provided)
        if candidate_skus:
            manual = chroma.get_or_create_collection("manual_chunks")
            if manual.count() > 0:
                manual_parts = []
                for sku in candidate_skus[:8]:
                    try:
                        results = manual.query(
                            query_embeddings=[qe],
                            n_results=3,
                            where={"product_id": {"$eq": sku}},
                            include=["documents", "metadatas", "distances"],
                        )
                        if results["ids"] and results["ids"][0]:
                            for doc, meta, dist in zip(
                                results["documents"][0],
                                results["metadatas"][0],
                                results["distances"][0],
                            ):
                                if 1 - dist > 0.2:
                                    flag = " ⚠️" if meta.get("has_limitation") else ""
                                    heading = meta.get("heading", "")[:50]
                                    manual_parts.append(f"[{sku}]{flag} {heading}\n{doc[:300]}")
                    except Exception:
                        pass
                if manual_parts:
                    parts.append("### Manual Excerpts\n" + "\n\n".join(manual_parts))

    except Exception:
        pass

    return "\n\n".join(parts)


def _embed(text: str) -> list[float]:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.embeddings.create(model="text-embedding-3-small", input=[text])
    return resp.data[0].embedding


_SKU_RE = re.compile(r'\b(?:BG|BZ)-[A-Z0-9][A-Z0-9\-]{2,30}\b')

PASS1_SYSTEM = f"""You are an AV systems integrator for BZB Gear.

Below is the complete product catalog. Read it carefully.

{CATALOG_INDEX}

Your task: given a customer scenario, identify which BZB Gear SKUs are needed.
Return ONLY a JSON object: {{"skus": ["SKU1", "SKU2", ...]}}
Include every SKU that will appear in the final recommendation — cameras, controllers, switchers, encoders, network gear.
Note: some products have a "BZ-" prefix (not "BG-") — include them too.
If the scenario is product_selection (customer asked about a specific category), include ALL products in that category that match the specs.
Do not explain. Only JSON.

CRITICAL RULES — ALWAYS FOLLOW:

RULE A — NO ACCESSORIES: Never include accessories. Remove any SKU that contains "-ACC-" in its name
(e.g. BG-IPGEAR-PRO-ACC-RM10, BG-VOP-ACC-RM10, BG-IPGEAR-ULTRA-ACC-RM, BG-VPTZ-CM, BG-VPTZ-WM, BG-VPTZ-TPM).
Accessories are mounting brackets, rack kits, and cable management — not products to recommend.

RULE B — LARGE SCALE AV-OVER-IP: If the scenario requires 20 or more display outputs, OR cable distances over 70m:
  - DO NOT include any matrix switchers or HDBaseT kits — they cannot scale to this requirement.
  - Select AV-over-IP product lines based on the required resolution:

  If resolution = 1080p (or not specified):
    Include: BG-IPGEAR-PRO-T, BG-IPGEAR-PRO-R, BG-IPGEAR-PRO-C  (PRO series — up to 4K60, good value)
             BG-VOP-MT, BG-VOP-CB                                  (VOP series — budget 4K30/1080p)
    Skip: ULTRA, XTREME, XTREME-PRO (overkill for 1080p)

  If resolution = 4K or 4K60:
    Include: BG-IPGEAR-PRO-T, BG-IPGEAR-PRO-R, BG-IPGEAR-PRO-C  (PRO — 4K60 capable)
             BG-IPGEAR-ULTRA, BG-IPGEAR-ULTRA-C                   (ULTRA — 4K60, all-in-one)
             BG-IPGEAR-XTREME, BG-IPGEAR-XTREME-PRO               (XTREME — HDMI 2.1, premium)
    Skip: BG-VOP-MT/CB (max 4K30 only, not suitable for 4K60)

  If resolution = 4K30 or budget 4K:
    Include all of the above including VOP series.

  If resolution = 8K:
    Include only: BG-IPGEAR-XTREME-PRO (the only 8K60 option)

  - Always include relevant network switches (NET-* series) needed for IP distribution."""


def _pass1_select_skus(question: str, session_info: dict) -> list[str]:
    """
    Fast first pass: read catalog, identify needed SKUs.
    Uses gpt-4o for speed — just returns a JSON list of SKUs.
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": PASS1_SYSTEM},
            {"role": "user", "content": f"Session: {json.dumps(session_info, default=str)}\n\nScenario: {question}\n\nReturn JSON with skus list."},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    try:
        data = json.loads(resp.choices[0].message.content)
        raw = data.get("skus", [])
        # Normalise and validate against catalog
        return [s.upper() for s in raw if _SKU_RE.match(s.upper())]
    except Exception:
        return []


def _build_product_context(products: list[dict]) -> str:
    """Build focused per-product descriptions from DB rows for Flow A comparison.

    When product_interfaces data is available it is used to provide precise
    signal/port/control details to the LLM instead of the raw generic fields.
    """
    import json as _json
    from api.db_interfaces import get_interface

    from api.db import get_conn as _get_conn

    # Build color-variant map for the batch (checks for -B/-W alternates)
    def _color_note(sku: str) -> str:
        upper = sku.upper()
        if upper.endswith("-B"):
            alt = upper[:-2] + "-W"
        elif upper.endswith("-W"):
            alt = upper[:-2] + "-B"
        else:
            return ""
        conn2 = _get_conn()
        exists = conn2.execute("SELECT 1 FROM products WHERE id=?", (alt,)).fetchone()
        conn2.close()
        color = "Black" if upper.endswith("-B") else "White"
        alt_color = "White" if color == "Black" else "Black"
        if exists:
            return f"Color: {color} — also available in {alt_color} ({alt})"
        return f"Color: {color}"

    lines = []
    for p in products:
        sku = p.get("id", "")
        lines.append(f"SKU: {sku}")
        lines.append(f"Name: {p.get('name', '')}")
        color_info = _color_note(sku)
        if color_info:
            lines.append(color_info)
        if p.get("price_usd"):
            lines.append(f"Price: ${float(p['price_usd']):.0f}")

        # ── Use structured interface data if available ─────────────────────
        iface = get_interface(sku)
        if iface:
            # Signal I/O summary
            in_parts, out_parts = [], []
            if iface.get("in_hdmi"):
                in_parts.append(f"HDMI{iface.get('in_hdmi_ver') and ' ' + iface['in_hdmi_ver'] or ''} x{iface['in_hdmi_count']}")
            if iface.get("in_sdi"):
                in_parts.append(f"{iface.get('in_sdi_ver') or 'SDI'}-SDI x{iface['in_sdi_count']}")
            if iface.get("in_ndi"):    in_parts.append("NDI")
            if iface.get("in_dante"):  in_parts.append("Dante")
            if iface.get("in_hdbaset"): in_parts.append("HDBaseT")
            if iface.get("in_fiber"):  in_parts.append("Fiber")
            if iface.get("in_vga"):    in_parts.append("VGA")
            if iface.get("in_ip_stream"): in_parts.append("IP stream")

            if iface.get("out_hdmi"):
                out_parts.append(f"HDMI{iface.get('out_hdmi_ver') and ' ' + iface['out_hdmi_ver'] or ''} x{iface['out_hdmi_count']}")
            if iface.get("out_sdi"):
                out_parts.append(f"{iface.get('out_sdi_ver') or 'SDI'}-SDI x{iface['out_sdi_count']}")
            if iface.get("out_ndi"):    out_parts.append("NDI")
            if iface.get("out_dante"): out_parts.append("Dante")
            if iface.get("out_hdbaset"): out_parts.append("HDBaseT")
            if iface.get("out_usb_video"): out_parts.append("USB video")
            if iface.get("out_ip_stream"): out_parts.append("IP stream/RTMP/SRT")

            if in_parts:  lines.append(f"Inputs:  {', '.join(in_parts)}")
            if out_parts: lines.append(f"Outputs: {', '.join(out_parts)}")
            if iface.get("max_res"):
                lines.append(f"Max resolution: {iface['max_res']}")

            # Control interfaces
            ctrl = []
            if iface.get("ctrl_ip"):    ctrl.append("IP/Web")
            if iface.get("ctrl_rs232"): ctrl.append("RS-232")
            if iface.get("ctrl_rs422"): ctrl.append("RS-422")
            if iface.get("ctrl_ir"):    ctrl.append("IR")
            if iface.get("ctrl_visca"): ctrl.append("VISCA")
            if iface.get("ctrl_pelco"): ctrl.append("Pelco")
            if iface.get("ctrl_front"): ctrl.append("Front panel")
            if ctrl: lines.append(f"Control: {', '.join(ctrl)}")

            # Camera extras
            if iface.get("zoom_optical"):
                lines.append(f"Optical zoom: {iface['zoom_optical']}x")
            extras = []
            if iface.get("poe"):          extras.append("PoE powered")
            if iface.get("poe_out"):      extras.append("PoE out")
            if iface.get("has_autotrack"): extras.append("auto-tracking")
            if iface.get("has_tally"):    extras.append("tally")
            if iface.get("has_recording"): extras.append("onboard recording")
            if iface.get("supports_hdr"): extras.append("HDR")
            if extras: lines.append(f"Features: {', '.join(extras)}")

        else:
            # Fallback to raw columns
            if p.get("inputs") is not None:
                lines.append(f"Inputs: {p['inputs']}")
            if p.get("outputs") is not None:
                lines.append(f"Outputs: {p['outputs']}")
            try:
                res = p.get("resolutions") or []
                if isinstance(res, str):
                    res = _json.loads(res)
                if res:
                    lines.append(f"Resolution: {', '.join(res)}")
            except Exception:
                pass

        if p.get("what_it_does"):
            lines.append(f"Description: {p['what_it_does'][:250]}")
        try:
            feats = p.get("features") or []
            if isinstance(feats, str):
                feats = _json.loads(feats)
            if feats:
                lines.append(f"Key features: {'; '.join(feats[:5])}")
        except Exception:
            pass
        lines.append("")
    return "\n".join(lines)


SANITY_FILTER_SYSTEM = """You are a strict AV product pre-screener. Filter candidates ruthlessly — only keep products that genuinely fit.

Given:
- Customer's requirement (category, inputs/outputs, venue/distance context)
- A list of candidate products with their properties

Classify each product as KEEP or REMOVE.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REMOVAL RULES — apply all, be strict:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RULE 0 — ACCESSORIES (always remove, no exceptions):
Remove ALL accessory products. Accessories are NEVER part of main product recommendations.
Indicators: SKU contains "-ACC-", or product is described as a rack bracket / mounting bracket / blank panel / cable management.
Examples to always remove: BG-IPGEAR-PRO-ACC-RM10, BG-VOP-ACC-RM10, BG-IPGEAR-ULTRA-ACC-RM, BG-VPTZ-CM, BG-VPTZ-WM, BG-VPTZ-TPM.

RULE 4 — LARGE SCALE (>= 20 outputs or distance > 70m):
If the customer requirement mentions 20 or more display outputs, OR cable distance greater than 70m:
  ✗ REMOVE: ALL matrix switchers and HDBaseT distribution kits — physically cannot support this scale/distance.
  ✓ KEEP: ALL AV-over-IP solutions (BG-IPGEAR-PRO series, BG-IPGEAR-ULTRA, BG-IPGEAR-XTREME, BG-VOP series).
  ✓ KEEP: Network switches (NET-* SKUs).

RULE 1 — WRONG DEVICE TYPE:
Remove if the device's PRIMARY FUNCTION does not match what the customer asked for.

  Customer wants MATRIX SWITCHER (routes any of N inputs to any of M outputs simultaneously):
    ✗ REMOVE: Streaming/production switchers (BG-QUADFUSION-4K = mixer, NOT a router)
    ✗ REMOVE: Capture cards, encoders, recorders
    ✗ REMOVE: KVM switches
    ✗ REMOVE: PTZ camera controllers, joystick controllers
    ✗ REMOVE: N-to-1 selector (picks one source, cannot route to multiple displays independently)
    ✗ REMOVE: Video wall controllers that are NOT also a matrix router
    ✓ KEEP: True matrix switchers (any input → any output independently)
    ✓ KEEP: Seamless matrix + video wall combo units (they ARE matrix switchers with extra features)

  Customer wants VIDEO WALL PROCESSOR (display multiple sources on a multi-screen canvas):
    ✓ KEEP: BG-4K-VP series (VP44, VP44PRO, VP88, VP99PRO, VP1616) — matrix + video wall combo
    ✓ KEEP: BG-UHD-VW series (VW24, VW29, VW2X2, VW2X2A, VWP19, VWP-1X4) — dedicated video wall processors
    ✓ KEEP: BG-MVS series — matrix switcher + video wall processor
    ✗ REMOVE: Production switchers, cameras, encoders — wrong device type

  Customer wants PTZ CAMERA:
    ✗ REMOVE: Camera controllers, joysticks (BG-COMMANDER series — these CONTROL cameras, not cameras)
    ✗ REMOVE: Encoders, capture cards
    ✓ KEEP: Actual PTZ cameras with HDMI/SDI/NDI outputs

  Customer wants VIDEO EXTENDER:
    ✓ KEEP: HDBaseT extenders, fiber extenders, active HDMI cables
    ✗ REMOVE: Matrix switchers, capture cards

RULE 2 — PORT COUNT OVERKILL (strictly numeric, NOT about resolution):
Remove if the product's HDMI port count is MORE THAN 2× what the customer needs.
  - Customer needs 5 inputs → remove anything with 11+ inputs (keep up to 10x10)
  - Customer needs 5 outputs → remove anything with 11+ outputs
  ⚠️ RESOLUTION IS NOT OVERKILL — a 4×4 8K switcher is FINE for a 4-input need
  ⚠️ Keep the smallest next-size-up if nothing exactly fits (e.g. keep 8×8 for a 6×6 need)

RULE 3 — WRONG TRANSMISSION TECHNOLOGY FOR VENUE:
Remove if the product uses the wrong technology for the stated distance and scale.
  Home / small office / bar with <10m cable runs and ≤8×8 need:
    ✗ REMOVE: HDBaseT matrix kits (BG-UM44-100M-KIT, BG-UM88-70M-KIT, etc.) — these need long cable runs to make sense
    ✗ REMOVE: AV-over-IP distribution systems for simple home/office routing
    ✓ KEEP: Standard HDMI matrix switchers — correct for home and small commercial installs
  HDBaseT/AV-over-IP IS appropriate when: customer explicitly says >30m runs OR multiple floors OR >8×8 scale

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIER CLASSIFICATION — for every product in the keep list:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
After deciding what to keep (not remove), classify each kept product as PERFECT or PARTIAL:

PERFECT — product fully satisfies ALL stated customer requirements:
  - Correct device type AND every requested feature is EXPLICITLY present in the product name or description
  - Example: customer asked for multiviewer → product name or description explicitly says "MultiViewer" or "multi-view"

PARTIAL — product is the right device type but a requested feature is absent or not explicitly confirmed:
  - GOLDEN RULE: if a feature is not explicitly mentioned in the product name or description, assume the product does NOT have it → PARTIAL
  - Example: customer asked for multiviewer → product name/description does NOT say "MultiViewer" → PARTIAL, even if it might technically support it
  - Example: customer asked for 4K60 → product only does 4K30 → PARTIAL
  - When in doubt, classify as PARTIAL — it is always better to under-promise than to mislead

It is OK for the perfect list to be EMPTY if no products truly satisfy all requirements.
Do NOT promote partials to perfect just to fill the list — it misleads the customer.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT — JSON only:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "perfect": ["SKU1", "SKU2"],
  "partial": ["SKU3"],
  "removed": [{"sku": "SKU4", "rule": 1, "reason": "streaming mixer, not a matrix switcher"}]
}"""


def _sanity_filter_candidates(
    candidate_skus: list[str],
    requested_categories: list[str],
    answers: dict,
    plan: dict,
) -> tuple[list[str], list[str]]:
    """
    Layer 1+2 LLM filter: remove wrong-function products and overkill technology.
    Returns (perfect_skus, partial_skus) — always at least 1 item in perfect.
    """
    if len(candidate_skus) <= 1:
        return candidate_skus, []  # single product — no point filtering

    from api.db import get_conn, row_to_dict as _row_to_dict
    from api.db_interfaces import get_interface

    # Build full product context (same as FLOW_A sees) so filter can read actual specs/features
    conn = get_conn()
    products = []
    for sku in candidate_skus:
        row = conn.execute("SELECT * FROM products WHERE id=?", (sku,)).fetchone()
        if row:
            products.append(_row_to_dict(row))
    conn.close()

    if not products:
        return candidate_skus, []

    product_context = _build_product_context(products)

    # Build context from answers
    req_lines = [f"Category requested: {', '.join(requested_categories)}"]
    hard_constraints = []
    for q, a in answers.items():
        req_lines.append(f"{q}: {a}")
        q_low, a_low = q.lower(), str(a).lower()
        if "ndi" in q_low and any(w in a_low for w in ("no", "standard", "hdmi", "sdi")):
            hard_constraints.append("HARD: Customer does NOT want NDI — remove any SKU containing 'ND' in its model code (e.g. 4KND, JRND, UPTZ-ND, VPTZN)")
        if "dante" in q_low and any(w in a_low for w in ("no", "standard")):
            hard_constraints.append("HARD: Customer does NOT want Dante — remove any SKU containing 'DA' in its model code")
    scenario_summary = plan.get("scenario_summary", "")
    if scenario_summary:
        req_lines.append(f"Venue/context: {scenario_summary}")

    constraint_section = ("\n\n## Hard constraints (override everything else)\n" + "\n".join(hard_constraints)) if hard_constraints else ""

    user_msg = (
        "## Customer requirement\n" + "\n".join(req_lines) +
        constraint_section +
        "\n\n## Candidate products (full specs)\n" + product_context +
        "\n\nApply the filter rules and return JSON."
    )

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    try:
        resp = client.chat.completions.create(
            model="gpt-5.5",
            messages=[
                {"role": "system", "content": SANITY_FILTER_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        perfect_raw = data.get("perfect", [])
        partial_raw = data.get("partial", [])
        removed = data.get("removed", [])
        # Legacy fallback: if model returned old "keep" format
        if not perfect_raw and not partial_raw and data.get("keep"):
            perfect_raw = data["keep"]
        if removed:
            import logging
            logging.getLogger(__name__).info(
                "Sanity filter removed %d products: %s",
                len(removed),
                [(r["sku"], r.get("reason", "")) for r in removed],
            )
        original_set = set(candidate_skus)
        perfect = [s for s in perfect_raw if s in original_set]
        partial = [s for s in partial_raw if s in original_set]
        # Never return empty — fall back to original if filter went wrong
        if not perfect and not partial:
            return candidate_skus, []

        # ── Python-level hard rules (override LLM classification) ──────────
        perfect, partial = _apply_hard_feature_rules(
            perfect, partial, answers, plan, conn_ref=None
        )

        return perfect, partial
    except Exception:
        return candidate_skus, []


def _apply_hard_feature_rules(
    perfect: list[str],
    partial: list[str],
    answers: dict,
    plan: dict,
    conn_ref=None,
) -> tuple[list[str], list[str]]:
    """
    Python-level post-processing after LLM filter.
    Checks explicit feature requirements against product names/descriptions.
    More reliable than LLM for simple keyword checks.
    """
    from api.db import get_conn, row_to_dict as _row_to_dict

    # Detect what the customer explicitly asked for
    req_text = " ".join([
        plan.get("scenario_summary", ""),
        plan.get("search_query", ""),
        " ".join(str(v) for v in answers.values()),
    ]).lower()

    # Feature → keywords that must appear in product name/description
    feature_checks = []
    if "multiview" in req_text or "multi-view" in req_text or "multi view" in req_text:
        feature_checks.append(("multiview", ["multiviewer", "multi-viewer", "multiview", "multi view"]))
    if "auto" in req_text and ("track" in req_text or "tracking" in req_text):
        feature_checks.append(("auto-tracking", ["auto track", "autotrack", "auto-track", "speaker track"]))
    if "ndi" in req_text and "no" not in req_text[:req_text.find("ndi")+5]:
        feature_checks.append(("ndi", ["ndi", "network device interface"]))

    if not feature_checks:
        return perfect, partial

    conn = get_conn()
    demoted = []
    for sku in list(perfect):
        row = conn.execute("SELECT name, what_it_does FROM products WHERE id=?", (sku,)).fetchone()
        if not row:
            continue
        product_text = ((row[0] or "") + " " + (row[1] or "")).lower()
        for feature_name, keywords in feature_checks:
            if not any(kw in product_text for kw in keywords):
                # Feature required but not found in product → demote to partial
                perfect.remove(sku)
                if sku not in partial:
                    partial.append(sku)
                demoted.append((sku, feature_name))
                break
    conn.close()

    if demoted:
        import logging
        logging.getLogger(__name__).info(
            "Hard feature rules demoted to partial: %s", demoted
        )

    return perfect, partial


FLOW_A_SYSTEM = f"""You are a BZB Gear product specialist helping a customer compare specific equipment options.

AV SIGNAL CHAIN RULES AND BEST PRACTICES
{AV_KNOWLEDGE}

YOUR TASK:
The customer asked about a specific product category. You are given TWO lists of products:
- PERFECT MATCHES: products that fully satisfy ALL customer requirements
- PARTIAL MATCHES: products in the right category but MISSING one or more requested features

CRITICAL: Your main analysis depends on which section you receive:
- If you receive "PERFECT MATCHES" → analyze ONLY those. Do NOT mention PARTIAL MATCHES in your text (they are shown separately in the UI).
- If you receive "CLOSEST MATCHES" (meaning no perfect matches exist) → analyze those honestly, make clear what each product is missing vs. what the customer asked for, and explain trade-offs. Do NOT pretend they are perfect.
- "PARTIAL MATCHES" section (when present alongside PERFECT MATCHES) → ignore entirely in your text output.

For each PERFECT MATCH product explain:
- What makes it different from the others in the list
- Which use case or scenario it is best suited for
- Key specs that match the customer's requirements
- Any trade-offs between the options
- Price tier (budget / mid / professional)

End with a clear "Best pick for your case" recommendation with a specific reason tied to what the customer told you.

OUTPUT FORMAT:

For each perfect match product:
**[SKU]** - [Short product name] ($[price])
Best for: [1-line ideal use case]
Pros: [2-3 bullet points]
Limitations: [1-2 bullet points only if relevant to this customer's case]

---

Best pick for your case: [SKU] - [1-sentence reason tied to what the customer told us]

RULES:
- Analyze ONLY products from the PERFECT MATCHES list — never mention partial matches in your text
- Base specs on the product data provided, not on general knowledge
- Never recommend products not in the provided list
- Do not use markdown heading syntax (no # or ## or ###)
- Do not use em dash or long dash characters
- Do not use backtick code formatting
- If a product has a color note (Black / White), mention the color options in one line - do not treat the alternate color as a separate product
- Never present accessories (SKUs containing "-ACC-") as main product recommendations

After the product comparison and best pick, add a short "You might also need:" section:
- If cameras were recommended: suggest PTZ controllers / joystick controllers and production switchers
- If matrix switchers were recommended: suggest cameras and control systems
- If encoders/decoders were recommended: suggest compatible cameras or switchers
Keep this section brief (2-3 bullet points max). Do not name specific SKUs - just suggest the categories."""


def get_flow_a_recommendation(
    question: str,
    candidate_skus: list[str],
    session: dict,
    requested_categories: list[str] | None = None,
    answers: dict | None = None,
    plan: dict | None = None,
) -> dict:
    """
    Flow A: SQL-filtered candidates → sanity filter → focused LLM comparison.
    LLM never sees the full catalog — only the pre-filtered products + their specs.
    """
    from api.db import get_conn, row_to_dict as _row_to_dict

    # 0. Sanity filter — split into perfect and partial matches
    perfect_skus, partial_skus = _sanity_filter_candidates(
        candidate_skus=candidate_skus,
        requested_categories=requested_categories or [],
        answers=answers or {},
        plan=plan or {},
    )

    all_skus = perfect_skus + [s for s in partial_skus if s not in perfect_skus]

    # 1. Fetch full product data for each candidate from DB
    conn = get_conn()
    def _fetch(skus):
        result = []
        for sku in skus:
            row = conn.execute(
                "SELECT * FROM products WHERE id=? AND (site_category IS NULL OR site_category != 'Discontinued') AND (stock_status IS NULL OR stock_status NOT IN ('Discontinued', 'Limited Stock'))",
                (sku,),
            ).fetchone()
            if row:
                result.append(_row_to_dict(row))
        return result

    perfect_products = _fetch(perfect_skus)
    partial_products = _fetch([s for s in partial_skus if s not in perfect_skus])
    conn.close()

    if not perfect_products and not partial_products:
        return {
            "answer": "No matching products found in our catalog for your specifications.",
            "selected_skus": [],
            "perfect_skus": [],
            "partial_skus": [],
        }

    # 2. Build focused mini-catalog
    perfect_ctx = _build_product_context(perfect_products) if perfect_products else ""
    partial_ctx = _build_product_context(partial_products) if partial_products else ""
    product_catalog = ""
    if perfect_ctx:
        product_catalog += f"## PERFECT MATCHES (fully meet all requirements)\n{perfect_ctx}\n"
        if partial_ctx:
            product_catalog += f"## PARTIAL MATCHES (right category, missing some features — do NOT analyze in main text)\n{partial_ctx}\n"
    elif partial_ctx:
        product_catalog += f"## CLOSEST MATCHES (none fully meet all requirements — analyze limitations honestly)\n{partial_ctx}\n"

    context = get_relevant_context(question, [p["id"] for p in perfect_products + partial_products])
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    lang_note = _detect_language(question)
    user_message = (
        f"{product_catalog}\n"
        f"## Customer requirements\n{question}"
        + (f"\n\n## Manual excerpts\n{context}" if context else "")
        + f"\n\n{lang_note}"
    )

    resp = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {"role": "system", "content": FLOW_A_SYSTEM},
            {"role": "user",   "content": user_message},
        ],
    )

    answer = resp.choices[0].message.content
    found_skus = sorted(set(_SKU_RE.findall(answer.upper())))
    return {
        "answer": answer,
        "selected_skus": found_skus,
        "perfect_skus": [p["id"] for p in perfect_products],
        "partial_skus": [p["id"] for p in partial_products],
    }


def stream_flow_a_recommendation(
    question: str,
    candidate_skus: list[str],
    session: dict,
    requested_categories: list[str] | None = None,
    answers: dict | None = None,
    plan: dict | None = None,
):
    """
    Streaming version of Flow A.
    Runs sanity filter (blocking), then streams LLM token by token.
    Yields tuples: ("product", sku, tier) | ("text", chunk) | ("done", "")
    tier = "perfect" | "partial"
    """
    import re
    from api.db import get_conn, row_to_dict as _row_to_dict

    # Sanity filter (blocking, before stream starts) — returns (perfect, partial)
    perfect_list, partial_list = _sanity_filter_candidates(
        candidate_skus=candidate_skus,
        requested_categories=requested_categories or [],
        answers=answers or {},
        plan=plan or {},
    )
    perfect_set = set(perfect_list)
    partial_set = set(partial_list) - perfect_set

    all_skus = list(perfect_set) + list(partial_set)

    # Fetch products
    conn = get_conn()
    def _fetch_p(skus):
        result = []
        for sku in skus:
            row = conn.execute(
                "SELECT * FROM products WHERE id=? AND (site_category IS NULL OR site_category != 'Discontinued') AND (stock_status IS NULL OR stock_status NOT IN ('Discontinued', 'Limited Stock'))",
                (sku,),
            ).fetchone()
            if row:
                result.append(_row_to_dict(row))
        return result

    perfect_products = _fetch_p(list(perfect_set))
    partial_products = _fetch_p(list(partial_set))
    conn.close()

    if not perfect_products and not partial_products:
        yield ("text", "No matching products found for your specifications.")
        yield ("done", "")
        return

    # Emit product cards immediately (before LLM starts) so cards appear while text streams
    for p in perfect_products:
        yield ("product", p["id"], "perfect")
    for p in partial_products:
        yield ("product", p["id"], "partial")

    # Build catalog sections for LLM
    # If perfect list is empty, pass partials to LLM labeled as closest matches
    perfect_ctx = _build_product_context(perfect_products) if perfect_products else ""
    partial_ctx = _build_product_context(partial_products) if partial_products else ""
    product_catalog = ""
    if perfect_ctx:
        product_catalog += f"## PERFECT MATCHES (fully meet all requirements)\n{perfect_ctx}\n"
    elif partial_ctx:
        # No perfect matches — show partials as closest options for LLM to analyze
        product_catalog += f"## CLOSEST MATCHES (none fully meet all requirements — analyze limitations honestly)\n{partial_ctx}\n"
    if perfect_ctx and partial_ctx:
        product_catalog += f"## PARTIAL MATCHES (right category, missing some features — do NOT analyze in main text, shown separately in UI)\n{partial_ctx}\n"

    context = get_relevant_context(question, [p["id"] for p in perfect_products + partial_products])
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    lang_note = _detect_language(question)

    # Build explicit constraint note from answers
    constraint_notes = []
    for q, a in (answers or {}).items():
        q_low, a_low = q.lower(), str(a).lower()
        if "ndi" in q_low and ("no" in a_low or "standard" in a_low or "hdmi" in a_low):
            constraint_notes.append("HARD CONSTRAINT: Customer does NOT want NDI. Do not recommend any NDI camera variants (SKUs containing 'ND').")
        if "dante" in q_low and ("no" in a_low or "standard" in a_low):
            constraint_notes.append("HARD CONSTRAINT: Customer does NOT want Dante. Do not recommend any Dante camera variants (SKUs containing 'DA').")
    constraint_block = ("\n\n## Customer constraints (MUST follow)\n" + "\n".join(constraint_notes)) if constraint_notes else ""

    user_message = (
        f"{product_catalog}\n"
        f"## Customer requirements\n{question}"
        + constraint_block
        + (f"\n\n## Manual excerpts\n{context}" if context else "")
        + f"\n\n{lang_note}"
    )

    stream = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {"role": "system", "content": FLOW_A_SYSTEM},
            {"role": "user",   "content": user_message},
        ],
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield ("text", delta)

    yield ("done", "")


def get_universal_recommendation(
    question: str,
    session: dict,
    candidate_skus: list[str] | None = None,
) -> dict:
    """
    Two-pass recommendation engine.

    Pass 1 (gpt-4o, fast): reads full catalog → selects SKUs
    Pass 2 (o4-mini, deep): catalog + AV rules + manual chunks for selected SKUs → full answer

    Returns: { answer: str, selected_skus: list[str] }
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    session_info = {k: v for k, v in session.items()
                    if v is not None and k not in ("session_id", "step")
                    and not str(k).startswith("_")}

    # ── PASS 1: identify SKUs ─────────────────────────────────────────────
    pass1_skus = _pass1_select_skus(question, session_info)

    # Merge with any semantic pre-search hints (deduplicated)
    all_hint_skus = list(dict.fromkeys((pass1_skus or []) + (candidate_skus or [])))

    # ── Fetch context for the SKUs LLM actually chose ─────────────────────
    # Website case studies + manual chunks keyed to pass1 selections
    context = get_relevant_context(question, all_hint_skus[:12])

    # ── PASS 2: full answer with manual context ───────────────────────────
    pass1_note = (
        f"\n\n### Pre-selected products from catalog scan\n"
        f"These SKUs were identified in a fast pre-scan — verify and refine:\n"
        + "\n".join(f"- {s}" for s in pass1_skus)
    ) if pass1_skus else ""

    user_message = f"""## Customer Requirements
{json.dumps(session_info, indent=2, default=str)}

## Customer Question
{question}{pass1_note}

{f"## Manual Excerpts & Case Studies (for selected products){chr(10)}{context}" if context else ""}

Design the optimal system. Use the pre-selected SKUs as a starting point — adjust if needed.
Verify signal compatibility at every link and show the complete chain.

{_detect_language(question)}"""

    resp = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
    )

    answer = resp.choices[0].message.content
    found_skus = sorted(set(_SKU_RE.findall(answer.upper())))

    return {
        "answer":        answer,
        "selected_skus": found_skus,
    }


def parse_approaches(recommendation: str) -> list[dict]:
    """
    Split the recommendation markdown into Option A / Option B sections.
    Returns list of {letter, name, text, skus} or [] if no dual-option structure found.
    """
    import re as _re
    pattern = _re.compile(r'^##\s+Option\s+([A-B])\s*[—–-]\s*(.+?)$', _re.MULTILINE)
    matches = list(pattern.finditer(recommendation))

    if len(matches) < 2:
        return []

    approaches = []
    for i, match in enumerate(matches):
        letter = match.group(1)
        name   = match.group(2).strip()
        start  = match.start()
        end    = matches[i + 1].start() if i + 1 < len(matches) else len(recommendation)
        section_text = recommendation[start:end].strip()
        skus = sorted(set(_SKU_RE.findall(section_text.upper())))
        approaches.append({
            "letter": letter,
            "name":   name,
            "text":   section_text,
            "skus":   skus,
        })

    return approaches
