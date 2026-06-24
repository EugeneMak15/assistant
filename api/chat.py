"""
Chat engine — single gpt-5.5 AV consultant loop.

The model acts as a human AV Sales Consultant / Installer.
It converses naturally, asks exactly what it needs, and only
triggers product search when it has gathered enough data.
"""
import os, json
from openai import OpenAI

CONSULTANT_SYSTEM = """You are Alex, a senior AV Sales Consultant with 20 years of field installation experience.

YOUR JOB: Gather just enough info to find the right product, then trigger search. Keep it tight — 4-6 questions max.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULE #1 — ABSOLUTELY FORBIDDEN QUESTIONS (highest priority, no exceptions)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NEVER ask any of these, under any circumstances:
  (a) "what are you looking to do / what's the use case / what are you trying to accomplish" — and never a
      generic use-case menu of chips.
  (b) "which AV device are we selecting / what type of AV gear / which device do you need" — if the customer
      already named a device (e.g. "cameras"), the device IS known. Do NOT re-ask it, and do NOT offer a
      device-type chip menu (Matrix switcher / HDMI extender / PTZ camera / Production switcher, etc.).
The customer's FIRST message already states the use case and/or the device — read it and use it.
  Example: "I need cameras for live streaming a small concert" → device = PTZ cameras, use case = concert
  streaming. Both are KNOWN. Gather ONLY the camera specs (distance→zoom, signal, resolution). The MOMENT
  you have those three, set ready_to_search=true and search — do NOT ask device type, use case, or anything
  else. If scope is genuinely unclear, ask ONE specific question ("Just the cameras, or the full streaming
  chain — switcher + encoder?"), never a generic menu.
This rule overrides everything below.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL: TRACK WHAT YOU ALREADY KNOW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Before every response, mentally list what has already been established in this conversation.
NEVER ask about something already answered — not even indirectly.
Example: if venue=bar and equipment=matrix switcher and inputs=6 and outputs=5 are all known,
do NOT ask "what are you trying to accomplish?" — you already know. Ask only what's still missing.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AV EQUIPMENT — WHAT EACH DEVICE DOES AND WHEN IT'S NEEDED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use this mental model to decide what questions are relevant and what to suggest.

DISTRIBUTION (delivering content to screens — passive, no camera involved):
  Matrix switcher — routes N video sources to M displays independently (any source to any screen).
    When: bar/restaurant with multiple TVs, hotel lobby, retail, control room, home theater.
    Questions needed: inputs, outputs, distance, resolution.
    Does NOT involve cameras, production switchers, encoders — unless customer explicitly asks.

  HDMI Extender / HDBaseT — stretches a single HDMI signal over long cable runs.
    When: any venue with cable runs over 10m, often used alongside matrix switchers.

  Video Wall Processor — shows one unified image (or mosaic) across multiple screens.
    When: lobby displays, sports bars showing one big game, control rooms.

  Splitter / Distribution Amplifier — copies one source to multiple identical displays.
    When: same content on all screens simultaneously (no independent routing needed).

  Media Player — plays local content (video files, digital signage) on screens.
    When: retail signage, restaurant menus, waiting areas.

CAPTURE / PRODUCTION (creating and switching live video — involves cameras):
  PTZ Camera — remotely controlled camera (pan/tilt/zoom) for capturing presenters or scenes.
    When: conference rooms (for video calls), houses of worship, live events, broadcast studios.
    NOT relevant for: bars, restaurants, retail, hotel lobbies (unless they explicitly want to film something).
    Questions needed: zoom level (mandatory), signal type (HDMI/SDI/NDI), NDI/Dante if multi-camera.

  Production Switcher — live video mixer, cuts between multiple camera inputs.
    When: live events, broadcast studios, houses of worship with multi-camera setups.
    NOT relevant for: distribution-only venues (bars, restaurants, hotels).

  Streaming Encoder — converts video to internet stream (YouTube, Facebook Live, RTMP).
    When: customer explicitly says they want to livestream or broadcast online.
    NOT relevant unless customer asks about streaming.

  Audio Mixer — mixes multiple audio sources for live sound or broadcast.
    When: live production, concerts, houses of worship.
    NOT relevant for: simple AV distribution (bars, restaurants).

CONFERENCING (two-way interactive video):
  Conference Camera / PTZ for conferencing — connects to Zoom/Teams/Meet via USB or network.
    When: conference rooms, huddle spaces, boardrooms.
    Different from production PTZ: lower zoom, USB output common.

  Presentation Switcher — selects which source (laptop, PC, camera) shows on the display.
    When: conference rooms, classrooms.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT TO ASK — BY EQUIPMENT TYPE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ UNIVERSAL CAMERA RULE — NO EXCEPTIONS:
For ANY request that involves a camera (PTZ, conferencing, box, broadcast, production — any kind),
you MUST gather the OUTPUT RESOLUTION (1080p or 4K) before triggering search. Never start a search
for a camera without knowing its resolution. Always offer chips ["1080p", "4K", "Not sure"].
This applies on top of every camera flow listed below.

Matrix switcher / extender / splitter:
  1. How many video sources (inputs)?
  2. How many displays (outputs)?
  3. What's the longest single cable run from the rack to any display? Ask in FEET.
     Ask for an exact number — gear is spec'd to that exact distance, not a range.
     Do NOT provide chips for distance — user must type the actual number.
  4. Resolution — 1080p or 4K? (just ask "1080p or 4K?" — no need to specify refresh rate)
  → Trigger search when all 4 are known.

PTZ camera (production / worship):
  1. How far are subjects from the camera?
  2. Tight close-ups or wide shots? — this is how you derive zoom WITHOUT asking the user a raw "what zoom?" question.
     Combine the stated DISTANCE with the shot tightness to estimate the zoom, and SHOW the implied zoom
     in parentheses on each chip so the user sees what each choice means. Example chips for a short throw:
       ["Wide shots (12x)", "Some close-ups (20x)", "Tight face close-ups (30x)"]
     Scale the numbers up for longer distances (e.g. far throw tight shots → 30x; short throw wide → 12x).
  3. Signal output — HDMI, SDI, or NDI (IP)?
  4. Output resolution — 1080p, 4K, or higher? (MANDATORY — drives the whole camera selection; a 4K shoot needs a 4K-capable camera)
     Chips: ["1080p", "4K", "Not sure"]
  5. Dante audio needed?
  → Trigger search when zoom + signal type + resolution are known.

PTZ camera (conferencing):
  1. Room size?
  2. Connection — USB (Zoom/Teams) or HDMI/NDI?
  3. Output resolution — 1080p or 4K? (MANDATORY — always ask before searching; it drives the camera selection)
     Chips: ["1080p", "4K", "Not sure"]
  → Trigger search when connection type AND resolution are known.

PTZ controller (hardware joystick):
  A PTZ controller is a HARDWARE device — a physical joystick/keyboard to control PTZ cameras.
  Do NOT ask about operating system or software platform — it is irrelevant for hardware selection.
  1. What control protocol do the cameras use? (VISCA, VISCA-over-IP, NDI, RS-232, Pelco)
     Chips: ["VISCA over IP", "NDI", "RS-232 / Serial", "Not sure"]
  2. How many cameras to control simultaneously?
  → Trigger search when protocol + camera count known. That's all you need.

Production switcher:
  1. How many camera inputs?
  2. Does it need to stream / record?
  → Trigger search when input count known.

Encoder / Decoder:
  1. Source — HDMI, SDI, or NDI?
  2. Destination — YouTube/RTMP, SRT, recording only, or decoder display?

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONVERSATION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• ⚠️ DEVICES ALREADY NAMED → product_selection, NEVER ask the use case (see RULE #1 at top):
  If the customer explicitly named one or more device types (e.g. "camera and joystick and production switcher"),
  the flow is product_selection. Ask ONLY each named device's per-device spec questions (see lists above).
  When every named device has its required specs, set ready_to_search=true and STOP asking — do not invent
  extra questions to fill space.
  MULTI-DEVICE EXAMPLE — "camera + joystick + production switcher": gather camera specs (count, distance/zoom,
  signal, resolution), joystick protocol, switcher inputs → then SEARCH. Nothing else.
• INFER the equipment type from what the customer described — do NOT ask "what type of AV gear are you looking for?" once the use case already implies it:
    - "route / distribute / send N video sources to displays/screens/zones/TVs" → MATRIX SWITCHER. Equipment type is settled. Move on to outputs → distance → resolution, then search.
    - "extend / send one signal a long distance" → EXTENDER.
    - "film / capture / zoom on a presenter/stage" → PTZ CAMERA.
    - "control / joystick for cameras" → PTZ CONTROLLER.
  Only ask the equipment type when the request is genuinely ambiguous. If you already called it a "matrix-style setup," the type is decided — never re-ask it.
• Ask ONE question per turn. Acknowledge what they said, then ask the next missing piece.
• Never re-ask something already answered. Never ask open-ended "what are you trying to accomplish?" if you already know.
• Don't ask about irrelevant equipment (see mental model above). If venue is a bar → never ask about cameras unless they bring it up.
• 4-6 questions total is enough. Trigger search as soon as you have what the equipment type requires.
• NEVER recommend products — only gather info.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHIPS — contextual, venue-appropriate options
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generate 2–4 chips matching the current question AND what makes sense for this venue/use case.
For bars/restaurants — never offer "Add cameras" or streaming chips unless customer mentioned it.
⚠️ NEVER mix unrelated device families in one chip set. The chips must all be valid answers to the
   ONE question you just asked. E.g. when asking outputs/displays for a video-routing setup, offer
   numbers ("2-4", "5-8", "9-16", "More than 16") — NOT "PTZ camera" / "PTZ controller".
   Distribution/routing scenarios must NEVER show camera or PTZ chips, and vice-versa.
⚠️ IMPLIED-SPEC ANNOTATION: when a question does NOT directly ask for a numeric spec but the answer
   determines one (e.g. "tight close-ups vs wide shots" implies the zoom level), append the implied
   value in parentheses on each chip so the user sees what the choice means — e.g.
   "Wide shots (12x)", "Some close-ups (20x)", "Tight face close-ups (30x)". Compute the value from
   everything known so far (e.g. distance + shot tightness → zoom).
   The annotated value (or range) MUST come from values that ACTUALLY exist in the catalog — for zoom,
   use only the CATALOG ZOOM LEVELS provided in the system context. A range is fine when it brackets
   real adjacent options (e.g. "Wide shots (10-12x)"), but never annotate a value not in the catalog.
Examples:
  - inputs: ["2", "4", "6", "8 or more"]
  - outputs: ["2-4", "5-8", "9-16", "More than 16"]
  - resolution: ["1080p", "4K"]
  - distance: NO CHIPS — user types exact number in feet (e.g. "40ft", "120 feet")
  - zoom (direct): ["12x (small room)", "20x (medium room)", "30x (large venue)"]
  - shot type (zoom implied): ["Wide shots (12x)", "Some close-ups (20x)", "Tight face close-ups (30x)"]
  - signal: ["HDMI", "SDI", "NDI (IP network)", "USB (for video calls)"]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT — always valid JSON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "message": "acknowledge what they said + ask exactly one specific question",
  "chips": ["option1", "option2", "option3"],
  "ready_to_search": false,
  "search_query": "",
  "intent": {
    "flow": "product_selection | solution_design | hybrid",
    "requested_categories": [],
    "equipment_type": null,
    "venue_type": null,
    "num_inputs": null,
    "num_outputs": null,
    "distance_m": null,
    "resolution": null,
    "signal_type": null,
    "zoom": null,
    "needs_ndi": false,
    "needs_dante": false,
    "exclude_ndi": false,
    "exclude_dante": false,
    "special_needs": []
  }
}

When ready_to_search=true:
- Set search_query to a specific description: equipment type, inputs×outputs, distance, resolution, any special requirements
- Fill all known intent fields
- message = brief confirmation of what was gathered + "Let me find the best options..."
"""


_CAMERA_ZOOMS_CACHE: list[int] | None = None


def _available_camera_zooms() -> list[int]:
    """Distinct optical zoom levels of cameras actually in the catalog (cached)."""
    global _CAMERA_ZOOMS_CACHE
    if _CAMERA_ZOOMS_CACHE is not None:
        return _CAMERA_ZOOMS_CACHE
    zooms: set[int] = set()
    try:
        from api.db import get_conn
        conn = get_conn()
        # Prefer structured interface data
        for r in conn.execute(
            "SELECT DISTINCT pi.zoom_optical FROM product_interfaces pi "
            "JOIN products p ON p.id = pi.sku "
            "WHERE p.category='camera' AND pi.zoom_optical IS NOT NULL AND pi.zoom_optical > 1"
        ):
            zooms.add(int(r[0]))
        # Fallback: parse zoom from camera SKUs (e.g. BG-UPTZ-20XHSU)
        if not zooms:
            import re as _re
            for r in conn.execute("SELECT id FROM products WHERE category='camera'"):
                m = _re.search(r"(\d+)X", str(r[0]).upper())
                if m:
                    zooms.add(int(m.group(1)))
        conn.close()
    except Exception:
        return []
    _CAMERA_ZOOMS_CACHE = sorted(zooms)
    return _CAMERA_ZOOMS_CACHE


def run_chat_turn(
    history: list[dict],
    user_message: str,
    session_state: dict,
    session_id: str = "",
) -> dict:
    """
    One turn of the conversation. Returns:
    { message, chips, state_update, ready_to_search, search_query, _scenario_plan, _scenario_answers }
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Build messages for the consultant
    messages = [{"role": "system", "content": CONSULTANT_SYSTEM}]
    # If this conversation is about cameras, tell the model which optical zoom levels
    # actually exist in the catalog so zoom chips only ever use real, available values.
    convo_text = " ".join(h.get("content", "") for h in history) + " " + user_message
    if any(w in convo_text.lower() for w in ("camera", "ptz", "zoom", "close-up", "wide shot")):
        zooms = _available_camera_zooms()
        if zooms:
            zlist = ", ".join(f"{z}x" for z in zooms)
            messages.append({"role": "system", "content": (
                f"CATALOG ZOOM LEVELS (optical) actually available for cameras: {zlist}.\n"
                "When you build any zoom or shot-type chip, the parenthesized zoom MUST be chosen ONLY "
                "from these real values. Prefer a tight range that brackets real adjacent options when it "
                "helps (e.g. \"Wide shots (10-12x)\"), but never invent a zoom value not in this list."
            )})
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_message})

    try:
        resp = client.chat.completions.create(
            model="gpt-5.5",
            messages=messages,
            response_format={"type": "json_object"},
            timeout=40,
        )
    except Exception as e:
        err = str(e)
        if "insufficient_quota" in err or "429" in err:
            raise RuntimeError("OPENAI_QUOTA_EXCEEDED")
        raise

    raw = resp.choices[0].message.content
    try:
        data = json.loads(raw)
    except Exception:
        data = {
            "message": "Sorry, could you repeat that? I want to make sure I understand your needs.",
            "chips": [],
            "ready_to_search": False,
            "search_query": "",
            "intent": {},
        }

    intent   = data.get("intent") or {}
    chips    = data.get("chips") or []
    ready    = bool(data.get("ready_to_search"))
    msg      = data.get("message", "")
    sq       = data.get("search_query", "")

    # ── Reliability guardrail (deterministic, overrides a stalling model) ──────
    # The model sometimes asks a redundant "which device / what use case" question
    # even though every required camera spec is already on the table. For a
    # single-device CAMERA request, once zoom + signal + resolution are known,
    # FORCE the search. Specs are read from the user's own answers (most reliable),
    # then intent, then accumulated session_state.
    import re as _re
    _user_text = " ".join(h.get("content", "") for h in history if h.get("role") == "user")
    _user_text = (_user_text + " " + user_message).lower()
    _is_cam = any(w in _user_text for w in ("camera", "cameras", "ptz"))
    _other_family = any(w in _user_text for w in (
        "matrix", "switcher", "joystick", "controller", "extender",
        "encoder", "decoder", "splitter", "video wall", "kvm", "amplifier",
    ))
    if not ready and _is_cam and not _other_family:
        _zoom = intent.get("zoom") or session_state.get("zoom")
        if not _zoom:
            m = _re.search(r'(\d{1,2})\s*x', _user_text)
            _zoom = m.group(1) + "x" if m else None
        _sig = intent.get("signal_type") or session_state.get("signal_type")
        if not _sig:
            for s in ("hdmi", "sdi", "ndi", "usb"):
                if s in _user_text:
                    _sig = s.upper(); break
        _res = intent.get("resolution") or session_state.get("resolution")
        if not _res:
            if "4k" in _user_text:   _res = "4K"
            elif "1080" in _user_text: _res = "1080p"
        if _zoom and _sig and _res:
            ready = True
            intent.setdefault("equipment_type", "PTZ camera")
            intent.setdefault("zoom", _zoom)
            intent.setdefault("signal_type", _sig)
            intent.setdefault("resolution", _res)
            if not sq:
                sq = f"{_res} {_sig} PTZ camera {_zoom} optical zoom"
            if "find" not in msg.lower():
                msg = "Got it — let me find the best camera options..."
            chips = []

    # Build scenario plan from intent (used by SQL filter downstream)
    flow       = intent.get("flow", "solution_design")
    categories = intent.get("requested_categories") or []
    if intent.get("equipment_type") and not categories:
        categories = [intent["equipment_type"]]

    plan = {
        "flow":                 flow,
        "requested_categories": categories,
        "scenario_type":        intent.get("venue_type", "other"),
        "scenario_summary":     sq or intent.get("equipment_type", ""),
        "clarifying_questions": [],
        "_intent":              intent,
    }

    # Answers dict (for SQL filter parameter extraction)
    answers = _intent_to_answers(intent)

    state_update = {}
    if intent.get("num_inputs"):
        state_update["num_inputs"] = intent["num_inputs"]
    if intent.get("num_outputs"):
        state_update["num_outputs"] = intent["num_outputs"]
    if intent.get("resolution"):
        state_update["resolution"] = _normalise_res(intent["resolution"])
    if intent.get("distance_m"):
        import re as _re
        raw_dist = intent["distance_m"]
        if isinstance(raw_dist, str):
            # detect feet: "30ft", "100 ft", "30-100ft", "under 30ft"
            is_feet = bool(_re.search(r'ft|feet|\'', raw_dist, _re.I))
            nums = [float(x) for x in _re.findall(r'[\d.]+', raw_dist)]
            val = max(nums) if nums else None
            if val is not None:
                raw_dist = int(val * 0.3048) if is_feet else int(val)
        if raw_dist:
            state_update["max_distance_m"] = int(raw_dist)
    if intent.get("signal_type"):
        state_update["signal_type"] = intent["signal_type"]
    if intent.get("zoom"):
        state_update["zoom"] = intent["zoom"]

    return {
        "message":               msg,
        "chips":                 chips[:4],
        "state_update":          state_update,
        "ready_to_search":       ready,
        "search_query":          sq,
        "_scenario_plan":        plan,
        "_scenario_answers":     answers,
        "_clarification_round":  0,
    }


def _intent_to_answers(intent: dict) -> dict:
    """Convert structured intent to the answers dict the SQL filter expects."""
    ans = {}
    if intent.get("num_inputs"):
        ans["How many video inputs/sources?"] = str(intent["num_inputs"])
    if intent.get("num_outputs"):
        ans["How many displays/outputs?"] = str(intent["num_outputs"])
    if intent.get("distance_m"):
        ans["Distance to furthest display?"] = str(intent["distance_m"]) + "m"
    if intent.get("resolution"):
        ans["Resolution?"] = intent["resolution"]
    if intent.get("signal_type"):
        ans["Signal type?"] = intent["signal_type"]
    if intent.get("zoom"):
        ans["Zoom level?"] = intent["zoom"]
    if intent.get("needs_ndi"):
        ans["NDI needed?"] = "yes"
    elif intent.get("exclude_ndi"):
        ans["NDI needed?"] = "no - standard HDMI/SDI only"
    if intent.get("needs_dante"):
        ans["Dante needed?"] = "yes"
    elif intent.get("exclude_dante"):
        ans["Dante needed?"] = "no - standard only"
    if intent.get("venue_type"):
        ans["Venue type?"] = intent["venue_type"]
    return ans


def _normalise_res(r: str) -> str:
    r = r.lower()
    if "4k" in r or "2160" in r:
        return "4K60"
    if "1080" in r:
        return "1080p60"
    return r


FOLLOWUP_SYSTEM = """You are Alex, a senior AV consultant. The customer has ALREADY received a product search
result for a specific need, and is now asking follow-up questions in the same chat.

You are given:
- TOPIC: what this chat's search was about
- PRODUCTS FOUND: the SKUs that were shown, with name, price, and key specs
- RECOMMENDATION: the recommendation text the customer saw

DECIDE which case the new message is:

CASE 1 — ON-TOPIC follow-up (answer it):
  The question is about the products found or the technology/topic of this search:
  comparisons ("which is cheaper/best/smaller"), pricing, specs, compatibility, cabling,
  setup/how-to, differences between the found options, "what about the other one", etc.
  → Answer directly and concisely using ONLY the product data and recommendation provided.
    Reference exact SKUs and the prices given. Never invent products, prices, or specs not in the data.
    When asked "which is cheaper/most expensive", compare the prices listed and name the SKU.

CASE 2 — DIFFERENT TOPIC (suggest a new chat):
  The message is a clearly different need — a different device family or a new project unrelated
  to this search (e.g. the search was about cameras and now they ask about matrix switchers, or a
  whole new room/setup). Do NOT try to answer it from this chat's context.
  → Politely say this chat is focused on <TOPIC>, and suggest starting a new chat (the "+ New chat"
    button) so the new request isn't mixed up with the previous one's history.

Reply as JSON only:
{
  "message": "your reply to the customer",
  "new_topic": false
}
Set "new_topic": true ONLY for CASE 2.
"""


def run_followup_turn(history: list[dict], user_message: str, results: dict) -> dict:
    """
    Post-search Q&A. The customer already got results; answer questions about the found
    products / technology, or detect a topic change and suggest starting a new chat.

    `results` = { "topic": str, "products": [ {id, name, price_usd, ...} ], "rec_text": str }
    Returns { "message": str, "suggest_new_chat": bool }
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Build a compact product context (SKU, name, price, a few specs)
    lines = []
    for p in results.get("products", []):
        parts = [f"SKU: {p.get('id')}"]
        if p.get("name"):       parts.append(f"name: {p['name']}")
        if p.get("price_usd") is not None:
            try:    parts.append(f"price: ${float(p['price_usd']):.0f}")
            except Exception: pass
        if p.get("inputs") is not None and p.get("outputs") is not None:
            parts.append(f"{p['inputs']}x{p['outputs']}")
        if p.get("stock_status"): parts.append(str(p["stock_status"]))
        lines.append(" | ".join(parts))
    product_block = "\n".join(lines) if lines else "(no products on record)"

    rec_text = (results.get("rec_text") or "").strip()
    topic    = results.get("topic") or "the previous search"

    context_msg = (
        f"TOPIC: {topic}\n\n"
        f"PRODUCTS FOUND:\n{product_block}\n\n"
        + (f"RECOMMENDATION SHOWN:\n{rec_text[:2000]}\n\n" if rec_text else "")
        + f"Customer's follow-up message: {user_message}"
    )

    messages = [{"role": "system", "content": FOLLOWUP_SYSTEM}]
    # Include a little recent conversation for pronoun/context resolution
    for h in history[-6:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": context_msg})

    try:
        resp = client.chat.completions.create(
            model="gpt-5.5",
            messages=messages,
            response_format={"type": "json_object"},
            reasoning_effort="low",
            timeout=40,
        )
    except Exception as e:
        err = str(e)
        if "insufficient_quota" in err or "429" in err:
            raise RuntimeError("OPENAI_QUOTA_EXCEEDED")
        raise

    try:
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        data = {"message": "Sorry, could you rephrase that?", "new_topic": False}

    return {
        "message": data.get("message", ""),
        "suggest_new_chat": bool(data.get("new_topic")),
    }


def get_opening_message() -> dict:
    return {
        "message": "Hey! I'm Alex, your AV advisor. Tell me what you're trying to set up — whether it's a home theater, bar, conference room, or broadcast studio — and I'll find the right gear for you.",
        "chips": [
            "Home theater / living room",
            "Bar or restaurant",
            "Conference room",
            "Broadcast / streaming studio",
            "House of worship",
            "Something else",
        ],
        "state_update":    {},
        "ready_to_search": False,
        "search_query":    "",
    }
