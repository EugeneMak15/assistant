"""
Scenario Planner — Step 1 of the new chat flow.

Uses LLM general AV industry knowledge (NOT the BZB catalog) to:
1. Classify intent: product_selection (Flow A) vs solution_design (Flow B)
2. List equipment roles relevant to the request
3. Generate targeted clarifying questions

Flow A — "product_selection":
  Customer named specific device categories (matrix switcher, cameras, encoder…).
  System asks only about specs for those categories.
  Universal Engine recommends ONLY those categories.

Flow B — "solution_design":
  Customer described a room, venue, or full setup task.
  System designs the complete solution.

Hybrid — "hybrid":
  Customer named specific categories AND a venue/context.
  Treated as Flow A, venue used only as context for specs.
"""
import os, json
from openai import OpenAI

PLANNER_SYSTEM = """You are a senior AV systems consultant with 20 years of experience.
Analyze the customer's request, classify their intent, and generate appropriate equipment roles.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1 — CLASSIFY INTENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Classify into one of three flows:

FLOW A — "product_selection"
  Trigger: customer named specific EQUIPMENT TYPES or DEVICE CATEGORIES.
  Keywords: camera, PTZ, matrix switcher, video switcher, encoder, decoder, amplifier,
            extender, converter, controller, multiviewer, splitter, capture card,
            HDBaseT, KVM, KVM switch, videobar, video bar, presentation switcher,
            distribution amplifier, video wall, video wall processor,
            AV over IP, AVoIP, audio processor, audio matrix, network switch,
            studio bundle, production bundle
  Rule: required_roles = ONLY the categories customer mentioned. Do NOT add extras.
  Set requested_categories = list of the specific device types the customer mentioned.

FLOW B — "solution_design"
  Trigger: customer described a ROOM, VENUE, or OVERALL TASK without naming device types.
  Phrases: "set up a", "equip a", "conference room", "sports bar", "live studio",
           "broadcast studio", "classroom", "house of worship", "streaming setup",
           "AV system for", "what do I need for"
  Rule: required_roles = all standard roles for the scenario type (see below).
  Set requested_categories = [].

HYBRID — "hybrid"
  Trigger: customer named BOTH a venue/task AND specific device categories.
  Example: "I need cameras and a switcher for my live studio"
  Rule: required_roles = ONLY the categories the customer mentioned.
        Use the venue only as context for specs (it will help pick the right size/signal type).
  Set requested_categories = the specific device types mentioned.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2 — GENERATE REQUIRED ROLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For FLOW A / HYBRID: required_roles = only the categories the customer asked about.

For FLOW B — use these standard roles per scenario type:

  Bars, restaurants, lobbies, hotels, multi-screen sports venues (av_distribution):
    Signal Source Hub, Video Matrix / Extenders, Audio System, Control System

  Conference rooms, meeting rooms (conference_room):
    Camera, Video Conferencing System, Presentation Switcher, Display, Audio System

  Live production, concerts, events, broadcast studios (live_production / broadcast_studio):
    PTZ Cameras, Production Switcher, PTZ Controller, Streaming Encoder, Audio Mixer

  Houses of worship (house_of_worship):
    PTZ Cameras, Production Switcher, Streaming Encoder, Audio System, Confidence Monitors

  Classrooms, training rooms (education):
    Display, Source Switcher, Audio System

  Digital signage (digital_signage):
    Media Player, Video Distribution System, Display Management

CONDITIONAL — add to FLOW B ONLY when customer's message explicitly mentions the keyword:
  "Streaming encoder" in bars/restaurants → only if customer says "stream" or "broadcast"
  "Backup/Redundancy" → only if customer says "backup" or "failover"
  "Recording" → only if customer says "record" or "capture"
  "Audio Mixer" → NEVER for bars/restaurants; only for live_production/broadcast_studio

IMPORTANT: Do NOT include the scenario_type name as a role. Keep 2–7 roles. No brand names.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT — valid JSON only:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "flow": "product_selection|solution_design|hybrid",
  "requested_categories": ["matrix switcher"],
  "scenario_type": "live_production|conference_room|broadcast_studio|av_distribution|digital_signage|house_of_worship|education|other",
  "scenario_summary": "one sentence",
  "required_roles": [{"role": "name", "purpose": "≤8 words", "quantity_hint": "1", "critical": true}],
  "assumed_defaults": ["brief assumption"]
}"""


QUESTIONS_SYSTEM = """You are a senior AV consultant. Given a scenario and its flow type, return 2–3 targeted clarifying questions.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IF flow = "product_selection" OR "hybrid":
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ask ONLY about specs needed to select the right product(s) from the requested_categories.
Do NOT ask about equipment the customer did not mention.

Questions by category:

"matrix switcher" / "video matrix" / "matrix":
  1. How many video sources (inputs)? options: ["1","2","4","More than 4"]
  2. How many displays (outputs)? options: ["2–4","5–8","9–16","More than 16"]
  3. What resolution? options: ["1080p is fine","4K60 required"]

"camera" / "PTZ camera" / "PTZ":
  1. What signal output do you need? options: ["HDMI","SDI","NDI/IP","USB (for conferencing)"]
  2. What zoom level? options: ["12x (small room / huddle)","20x (medium room)","30x (large venue / auditorium)","Any / not sure"]
  3. Resolution? options: ["1080p60 is fine","4K required"]

"encoder" / "streaming encoder":
  1. Video source type? options: ["HDMI from computer/camera","SDI from broadcast camera","NDI over network","Multiple mixed sources"]
  2. Stream destination? options: ["YouTube / Facebook Live","Custom RTMP server","SRT destination","Recording only"]
  3. Resolution? options: ["1080p60","4K30","4K60"]

"extender" / "HDBaseT" / "HDMI extender":
  1. Signal type to extend? options: ["HDMI","SDI","USB with video","VGA / analog"]
  2. Distance needed? options: ["Under 30m","30–70m","70–100m","Over 100m"]
  3. How many endpoints? options: ["1","2–4","5+"]

"video wall" / "video wall processor":
  1. How many screens make up the video wall? options: ["2×2 (4 screens)","3×3 (9 screens)","4×4 (16 screens)","Custom layout"]
  2. How many video sources (inputs)? options: ["1","2–4","5–8","More than 8"]
  3. Resolution? options: ["1080p is fine","4K60 required"]

"decoder" / "AV-over-IP decoder":
  1. Video source type? options: ["BZB AV-over-IP encoder","NDI stream","RTSP/H.264 stream","Unknown"]
  2. How many decoders (display endpoints)? options: ["1","2–4","5–10","More than 10"]

"switcher" / "production switcher" / "video switcher":
  1. How many video inputs? options: ["2","4","6–8","More than 8"]
  2. Signal type? options: ["HDMI","SDI","NDI/IP","Mixed"]
  3. Streaming output needed? options: ["Yes — live stream","No — switching only","Both streaming and recording"]

"amplifier" / "audio amplifier":
  1. How many audio zones? options: ["1","2–4","5–8","More than 8"]
  2. Speaker type? options: ["8-ohm passive speakers","70V/100V distributed","Powered speakers (no amp needed)"]
  3. Audio input? options: ["HDMI audio extract","Analog (XLR/RCA)","Digital (AES/EBU / optical)"]

"controller" / "PTZ controller":
  1. How many cameras to control? options: ["1–2","3–4","5–8","More than 8"]
  2. Camera protocol? options: ["NDI","VISCA over IP","VISCA RS-232/RS-422","Pelco-D"]
  3. Control preference? options: ["Joystick hardware controller","Software/tablet control","Both"]

GENERAL: If the category is not listed above, ask: (a) quantity needed, (b) key technical spec
(signal type, resolution, or distance), (c) any specific requirement or constraint.
NEVER ask about equipment the customer did not mention.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IF flow = "solution_design":
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use the standard scenario-based questions.

av_distribution / digital_signage (sports bar, restaurant, lobby, hotel, retail):
  1. Distance from source rack to the FARTHEST display? options: ["Under 5m","5–30m","30–70m","Over 70m"]
  2. Same content on all screens or independent zones? options: ["Same content on all","Independent zones","Mix of both"]
  3. Resolution? options: ["1080p is fine","4K60 required","Mix depending on location"]

conference_room:
  1. Room size / participants? options: ["Small (≤6 people)","Medium (6–12)","Large boardroom (12+)","Multiple rooms"]
  2. Video conferencing (Zoom/Teams/WebEx)? options: ["Yes — required","No — in-room presentation only","Both"]
  3. Distance from source to display? options: ["Under 5m","5–15m","Over 15m"]

live_production / broadcast_studio / house_of_worship:
  1. How many cameras? options: ["1","2–3","4–6","More than 6"]
  2. Primary output goal? options: ["Live stream (YouTube/Facebook)","Recording only","Both streaming and recording","In-venue display only"]
  3. Distance from cameras to production desk? options: ["Under 10m (HDMI)","10–100m (SDI or fiber)","Different floors or buildings"]

education:
  1. Fixed installation or portable/mobile? options: ["Fixed (wall/ceiling mounted)","Mobile (cart-based)","Both"]
  2. Independent room control? options: ["Central control for all rooms","Each room independently controlled","Both"]

Return JSON: {"clarifying_questions": [{"question":"...","why":"...","options":["A","B","C"]}]}"""


_PLAN_CACHE: dict[str, dict] = {
    "live streaming / concert": {
        "flow": "solution_design",
        "requested_categories": [],
        "scenario_type": "live_production",
        "scenario_summary": "The customer wants to set up a live streaming production for a concert.",
        "required_roles": [
            {"role": "PTZ Cameras", "purpose": "Capture video from multiple angles", "quantity_hint": "2–4", "critical": True},
            {"role": "Production Switcher", "purpose": "Switch between camera feeds live", "quantity_hint": "1", "critical": True},
            {"role": "Streaming Encoder", "purpose": "Encode and send video to streaming platform", "quantity_hint": "1", "critical": True},
            {"role": "PTZ Controller", "purpose": "Operate cameras remotely", "quantity_hint": "1", "critical": True},
            {"role": "Audio Mixer", "purpose": "Mix audio from multiple sources", "quantity_hint": "1", "critical": True},
        ],
        "assumed_defaults": ["Live stream to YouTube or similar platform"],
        "clarifying_questions": [],
    },
    "conference room": {
        "flow": "solution_design",
        "requested_categories": [],
        "scenario_type": "conference_room",
        "scenario_summary": "The customer wants to set up a conference room for meetings and presentations.",
        "required_roles": [
            {"role": "Camera", "purpose": "Capture video of meeting participants", "quantity_hint": "1–2", "critical": True},
            {"role": "Video Conferencing System", "purpose": "Connect remote participants via Zoom/Teams", "quantity_hint": "1", "critical": True},
            {"role": "Presentation Switcher", "purpose": "Switch between laptop and camera sources", "quantity_hint": "1", "critical": True},
            {"role": "Display", "purpose": "Show content and video feeds", "quantity_hint": "1–2", "critical": True},
            {"role": "Audio System", "purpose": "Amplify sound for participants", "quantity_hint": "1", "critical": True},
        ],
        "assumed_defaults": ["Video conferencing required", "Single display"],
        "clarifying_questions": [],
    },
    "broadcast studio": {
        "flow": "solution_design",
        "requested_categories": [],
        "scenario_type": "broadcast_studio",
        "scenario_summary": "The customer wants to set up a broadcast studio for professional production.",
        "required_roles": [
            {"role": "PTZ Cameras", "purpose": "Capture studio footage from fixed positions", "quantity_hint": "2–4", "critical": True},
            {"role": "Production Switcher", "purpose": "Switch and mix video sources live", "quantity_hint": "1", "critical": True},
            {"role": "Streaming Encoder", "purpose": "Encode for live broadcast or recording", "quantity_hint": "1", "critical": True},
            {"role": "PTZ Controller", "purpose": "Remotely control camera position and zoom", "quantity_hint": "1", "critical": True},
            {"role": "Audio Mixer", "purpose": "Mix broadcast audio from all sources", "quantity_hint": "1", "critical": True},
        ],
        "assumed_defaults": ["Professional broadcast workflow"],
        "clarifying_questions": [],
    },
    "video distribution": {
        "flow": "solution_design",
        "requested_categories": [],
        "scenario_type": "av_distribution",
        "scenario_summary": "The customer wants to distribute video from one or more sources to multiple displays.",
        "required_roles": [
            {"role": "Video Matrix Switcher", "purpose": "Route any source to any display", "quantity_hint": "1", "critical": True},
            {"role": "HDMI/HDBaseT Extender", "purpose": "Send video over long cable runs", "quantity_hint": "1 per zone", "critical": True},
            {"role": "AV-over-IP System", "purpose": "Distribute video over network infrastructure", "quantity_hint": "1 per source + 1 per display", "critical": False},
        ],
        "assumed_defaults": ["Multiple display zones"],
        "clarifying_questions": [],
    },
    "ptz cameras": {
        "flow": "product_selection",
        "requested_categories": ["PTZ cameras"],
        "scenario_type": "live_production",
        "scenario_summary": "The customer needs PTZ cameras for their production setup.",
        "required_roles": [
            {"role": "PTZ Cameras", "purpose": "Pan/tilt/zoom cameras for remote control", "quantity_hint": "2–6", "critical": True},
        ],
        "assumed_defaults": ["Remote controlled cameras needed"],
        "clarifying_questions": [],
    },
}


def analyze_scenario(user_message: str, conversation_history: list[dict] = None) -> dict:
    """
    Phase 1a: classify intent + generate roles.
    Returns instantly for common chip-click scenarios; calls LLM for custom descriptions.
    """
    key = user_message.strip().lower()
    if key in _PLAN_CACHE and not conversation_history:
        plan = dict(_PLAN_CACHE[key])
        plan["required_roles"] = [dict(r) for r in plan["required_roles"]]
        _fill_bzb_availability(plan)
        return plan

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    messages = [{"role": "system", "content": PLANNER_SYSTEM}]
    if conversation_history:
        messages.extend(conversation_history[-4:])
    messages.append({"role": "user", "content": user_message})

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0,
    )

    try:
        plan = json.loads(resp.choices[0].message.content)
        plan.setdefault("flow", "solution_design")
        plan.setdefault("requested_categories", [])
        plan.setdefault("clarifying_questions", [])
        _remove_scenario_type_echo(plan)
        _fill_bzb_availability(plan)
        return plan
    except Exception:
        return {
            "flow": "solution_design",
            "requested_categories": [],
            "scenario_type": "other",
            "scenario_summary": user_message[:100],
            "required_roles": [],
            "clarifying_questions": [],
            "assumed_defaults": [],
        }


def fetch_questions(plan: dict, user_message: str) -> list[dict]:
    """Fetch clarifying questions for a plan. Flow-aware: Flow A asks about specs only."""
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    flow = plan.get("flow", "solution_design")
    scenario_type = plan.get("scenario_type", "other")
    requested_categories = plan.get("requested_categories", [])
    roles = ", ".join(r["role"] for r in plan.get("required_roles", []))

    context = (
        f"Flow: {flow}\n"
        f"Requested categories: {', '.join(requested_categories) if requested_categories else 'none'}\n"
        f"Scenario type: {scenario_type}\n"
        f"Roles: {roles}\n"
        f"User said: {user_message}"
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": QUESTIONS_SYSTEM},
            {"role": "user", "content": context},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    try:
        return json.loads(resp.choices[0].message.content).get("clarifying_questions", [])
    except Exception:
        return []


def _remove_scenario_type_echo(plan: dict) -> None:
    """Remove artifact role where LLM echoes the scenario_type as the first role name."""
    stype = plan.get("scenario_type", "").lower().replace("_", " ")
    roles = plan.get("required_roles", [])
    plan["required_roles"] = [
        r for r in roles
        if r.get("role", "").lower().replace("_", " ") != stype
        and r.get("role", "").lower().replace("_", "/") not in (stype, stype.replace(" ", "_"))
    ]


# Keywords that BZB carries (role name must contain at least one)
_BZB_CAN = {
    "camera", "ptz", "switcher", "switch", "encoder", "decoder",
    "extender", "transmitter", "receiver", "distribution", "splitter",
    "amplifier", "multiviewer", "capture", "controller", "scaler",
    "converter", "kvm", "av-over-ip", "av over ip", "videobar", "video bar",
    "sdi", "fiber", "streaming", "network", "signal generator",
    "presentation system", "presentation switcher", "tally",
}
# Keywords that BZB does NOT carry — checked first (higher priority)
_BZB_CANNOT = {
    "microphone", " mic ", "audio mixer", "mixing board", "mixing console",
    "display", " monitor ", "screen", "projector", "projection",
    "laptop", " pc ", "computer", "tablet", "software", "platform",
    "lighting", "light ", "furniture", "subscription", "license",
    "confidence monitor", "tally light",
    "backup power", " ups ", "rack unit", "rack enclosure",
}


def _fill_bzb_availability(plan: dict) -> None:
    """Determine bzb_available for each role via keyword matching."""
    for role in plan.get("required_roles", []):
        name = " " + role.get("role", "").lower() + " "
        combined = name + " " + role.get("purpose", "").lower()
        if any(kw in name for kw in _BZB_CANNOT):
            role["bzb_available"] = False
        elif any(kw in combined for kw in _BZB_CAN):
            role["bzb_available"] = True
        else:
            role["bzb_available"] = True


def format_clarification_message(plan: dict, question_index: int = 0) -> tuple[str, list[str]]:
    summary   = plan.get("scenario_summary", "")
    roles     = plan.get("required_roles", [])
    questions = plan.get("clarifying_questions", [])
    defaults  = plan.get("assumed_defaults", [])

    lines = []

    if question_index == 0:
        lines.append(f"Got it — **{summary}**")
        lines.append("")
        lines.append("A typical setup like this requires:")
        for r in roles:
            qty     = r.get("quantity_hint", "")
            qty_str = f" ({qty})" if qty and qty != "1" else ""
            crit    = " ✦" if r.get("critical") else ""
            lines.append(f"• **{r['role']}**{qty_str}{crit} — {r['purpose']}")

        if defaults:
            lines.append("")
            lines.append("*Assuming: " + "; ".join(defaults) + "*")

    chips = []
    if question_index < len(questions):
        q = questions[question_index]
        lines.append("")
        lines.append(f"**{q['question']}**")
        if q.get("why"):
            lines.append(f"*(affects: {q['why']})*")
        chips = q.get("options", [])[:4]

    return "\n".join(lines), chips


def merge_answers_into_session(plan: dict, answers: dict, session: dict) -> dict:
    updated = dict(session)

    for key, val in answers.items():
        key_lower = str(key).lower()
        val_str = str(val).lower()

        if "camera" in key_lower or "камер" in key_lower:
            try:
                updated["num_inputs"] = int("".join(c for c in val_str if c.isdigit()) or "3")
            except Exception:
                pass

        if "resolution" in key_lower or "разреш" in key_lower:
            if "4k" in val_str:
                updated["resolution"] = "4K60"
            elif "1080" in val_str:
                updated["resolution"] = "1080p60"

        if "signal" in key_lower or "сигнал" in key_lower:
            if "ndi" in val_str:
                updated["signal_type"] = "NDI"
            elif "sdi" in val_str:
                updated["signal_type"] = "SDI"
            elif "hdmi" in val_str:
                updated["signal_type"] = "HDMI"

    updated["_scenario_plan"] = plan
    updated["_scenario_answers"] = answers
    return updated


def extract_answers_from_freetext(text: str, questions: list[dict]) -> dict[int, str]:
    """Extract answers to questions from free-text user input."""
    if not questions:
        return {}

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    qs_lines = "\n".join(
        f"{i}: {q['question']} [options: {', '.join(q.get('options', []))}]"
        for i, q in enumerate(questions)
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": (
                f'User said: "{text}"\n\n'
                f"Does this message answer any of these questions? "
                f"Extract the best matching answer for each that is clearly addressed.\n\n"
                f"{qs_lines}\n\n"
                f'Return JSON: {{"answered": [{{"index": 0, "answer": "extracted short answer"}}]}}\n'
                f"Only include questions that are genuinely answered. Be lenient — "
                f"if user says '10 телеков' that answers a question about number of displays."
            ),
        }],
        response_format={"type": "json_object"},
        temperature=0,
    )

    try:
        data = json.loads(resp.choices[0].message.content)
        return {int(item["index"]): item["answer"] for item in data.get("answered", [])}
    except Exception:
        return {}


def _interfaces_table_ready() -> bool:
    """Return True if product_interfaces is populated (extraction has run)."""
    try:
        from api.db import get_conn
        conn = get_conn()
        count = conn.execute("SELECT COUNT(*) FROM product_interfaces").fetchone()[0]
        conn.close()
        return count >= 50
    except Exception:
        return False


def _find_matching_skus_via_interfaces(
    requested_categories: list[str],
    answers: dict,
    min_inputs: int | None,
    max_inputs: int | None,
    min_outputs: int | None,
    max_outputs: int | None,
    signal_filter: str | None,
    zoom_filter: str | None,
    resolution_filter: str | None,
    is_matrix: bool,
    is_camera: bool,
    needs_ndi: bool = False,
    needs_dante: bool = False,
) -> list[str]:
    """
    Structured query using product_interfaces JOIN products.
    More precise than the legacy products-only query.
    """
    # Map requested categories → primary_fn values in product_interfaces
    FN_MAP = {
        "matrix switcher":       ["matrix-switcher"],
        "video matrix":          ["matrix-switcher"],
        "switcher":              ["matrix-switcher", "production-switcher"],
        "production switcher":   ["production-switcher"],
        "presentation switcher": ["matrix-switcher", "production-switcher"],
        "video wall":            ["matrix-switcher"],
        "video wall processor":  ["matrix-switcher"],
        "videowall":             ["matrix-switcher"],
        "camera":                ["camera-ptz", "camera-box", "camera-usb"],
        "cameras":               ["camera-ptz", "camera-box", "camera-usb"],
        "ptz camera":            ["camera-ptz"],
        "ptz cameras":           ["camera-ptz"],
        "encoder":               ["encoder"],
        "streaming encoder":     ["encoder"],
        "decoder":               ["decoder"],
        "extender":              ["extender-tx", "extender-rx"],
        "hdbaset":               ["extender-tx", "extender-rx"],
        "amplifier":             ["amplifier"],
        "audio amplifier":       ["amplifier"],
        "controller":            ["controller"],
        "ptz controller":        ["controller"],
        "multiviewer":           ["multiviewer"],
        "splitter":              ["splitter"],
        "distribution amp":      ["splitter"],
        "da":                    ["splitter"],
        "converter":             ["converter"],
        "sdi converter":         ["converter"],
        "audio":                 ["audio-processor", "amplifier"],
        "audio processor":       ["audio-processor"],
        "audio matrix":          ["audio-processor"],
    }

    # Categories best searched directly by products.category (not via primary_fn)
    CATEGORY_DIRECT_MAP = {
        "capture card":    ["capture"],
        "capture":         ["capture"],
        "capture cards":   ["capture"],
        "kvm":             ["kvm_switch"],
        "kvm switch":      ["kvm_switch"],
        "kvm switcher":    ["kvm_switch"],
        "videobar":        ["videobar"],
        "video bar":       ["videobar"],
        "conferencing bar": ["videobar"],
        "av over ip":      ["av_over_ip", "encoder_decoder"],
        "av-over-ip":      ["av_over_ip", "encoder_decoder"],
        "av_over_ip":      ["av_over_ip"],   # internal supplement — only dedicated AV over IP products, not encoders
        "avoip":           ["av_over_ip", "encoder_decoder"],
        "ip distribution": ["av_over_ip", "encoder_decoder"],
        "transceiver":     ["av_over_ip", "encoder_decoder"],
        "network switch":  ["network"],
        "network":         ["network"],
        "managed switch":  ["network"],
        "poe switch":      ["network"],
        "bundle":          ["bundle"],
        "studio bundle":   ["bundle"],
        "multiviewer":     ["multiviewer"],
        "multi viewer":    ["multiviewer"],
        "quad viewer":     ["multiviewer"],
    }


    fn_values: set[str] = set()
    direct_cats: set[str] = set()
    is_video_wall = any(
        "video wall" in c.lower() or "videowall" in c.lower()
        for c in requested_categories
    )
    for cat in requested_categories:
        cat_low = cat.lower()
        # Check direct category map first (exact match)
        if cat_low in CATEGORY_DIRECT_MAP:
            direct_cats.update(CATEGORY_DIRECT_MAP[cat_low])
            continue
        cat_words = set(cat_low.split())
        # Sort by specificity (more words = more specific) and take first match only
        for key, fns in sorted(FN_MAP.items(), key=lambda kv: len(kv[0].split()), reverse=True):
            key_words = set(key.split())
            if key_words <= cat_words:  # all key words must appear in category
                fn_values.update(fns)
                break  # take most specific match only

    if not fn_values and not direct_cats:
        return []

    from api.db import get_conn as _get_conn2
    conn = _get_conn2()

    # If only direct_cats (no fn_values), do a category-based search without JOIN
    if direct_cats and not fn_values:
        dph = ",".join("?" * len(direct_cats))
        direct_sql = (
            "SELECT p.id FROM products p "
            f"WHERE p.category IN ({dph}) "
            "AND (p.stock_status IS NULL OR p.stock_status NOT IN ('Discontinued', 'Limited Stock')) "
            "AND (p.site_category IS NULL OR p.site_category != 'Discontinued') "
            "AND p.category != 'accessory'"
        )
        rows = conn.execute(direct_sql, list(direct_cats)).fetchall()
        conn.close()
        return _deduplicate_color_variants([r[0] for r in rows])

    placeholders = ",".join("?" * len(fn_values))
    params: list = list(fn_values)

    # For video wall queries: restrict to products that explicitly mention Video Wall,
    # and also include the BG-UHD-VW series (category='multiviewer' but these ARE video wall processors)
    vw_name_filter = ""
    if is_video_wall:
        vw_name_filter = (
            " AND (p.name LIKE '%Video Wall%' OR p.name LIKE '%video wall%' "
            "OR p.name LIKE '%VideoWall%' OR p.category = 'multiviewer')"
        )

    # If both fn_values and direct_cats, we'll merge results after main SQL
    sql = (
        "SELECT p.id FROM products p "
        "JOIN product_interfaces pi ON pi.sku = p.id "
        f"WHERE pi.primary_fn IN ({placeholders}) "
        "AND (p.stock_status IS NULL OR p.stock_status NOT IN ('Discontinued', 'Limited Stock')) "
        "AND (p.site_category IS NULL OR p.site_category != 'Discontinued') "
        f"{vw_name_filter}"
        "AND p.category != 'accessory' "
    )

    # Matrix input/output count filters (with proximity ceiling)
    if is_matrix and min_inputs:
        sql += " AND pi.in_hdmi_count >= ?"
        params.append(min_inputs)
        if max_inputs:
            sql += " AND pi.in_hdmi_count <= ?"
            params.append(max_inputs)
        # Matrix must have at least 2 outputs (exclude 4x1 selectors)
        sql += " AND pi.out_hdmi_count >= 2"
    elif min_inputs and not is_camera:
        sql += " AND (p.inputs IS NULL OR p.inputs >= ?)"
        params.append(min_inputs)

    if is_matrix and min_outputs:
        sql += " AND pi.out_hdmi_count >= ?"
        params.append(min_outputs)
        if max_outputs:
            sql += " AND pi.out_hdmi_count <= ?"
            params.append(max_outputs)
    elif is_matrix and not min_outputs:
        # Even without explicit output request, exclude 1-output "switchers"
        sql += " AND pi.out_hdmi_count >= 2"

    # Camera-specific filters
    if is_camera:
        if signal_filter:
            col_map = {
                "SDI": "pi.out_sdi = 1",
                "NDI": "pi.out_ndi = 1",
                "HDMI": "pi.out_hdmi = 1",
                "USB": "pi.out_usb_video = 1",
            }
            if signal_filter in col_map:
                sql += f" AND {col_map[signal_filter]}"

        if resolution_filter:
            if "4K60" in resolution_filter:
                sql += " AND pi.max_res = '4K60'"
            elif "4K" in resolution_filter:
                sql += " AND pi.supports_4k = 1"

        if zoom_filter:
            zf = zoom_filter.replace("x", "")
            if "-" in zf:
                # Range like "25-30" → match the whole span with a little tolerance
                lo, hi = zf.split("-", 1)
                zmin, zmax = int(lo) - 1, int(hi) + 1
            else:
                zoom_n = int(zf)
                # single value: allow a small upper tolerance
                zmin, zmax = zoom_n - 1, zoom_n + 3
            sql += " AND pi.zoom_optical >= ? AND pi.zoom_optical <= ?"
            params.append(zmin)
            params.append(zmax)

        if needs_ndi:
            sql += " AND pi.out_ndi = 1"
        elif is_camera and not needs_ndi and not needs_dante:
            # Customer didn't ask for NDI — exclude NDI-only/Dante-only camera variants
            # Keep cameras where NDI/Dante is not the defining feature
            sql += " AND pi.out_ndi = 0"
        if needs_dante:
            sql += " AND pi.out_dante = 1"
        elif is_camera and not needs_dante and not needs_ndi:
            sql += " AND pi.out_dante = 0"

    rows = conn.execute(sql, params).fetchall()
    iface_skus = {row[0] for row in rows}

    # Supplement with products not yet in product_interfaces (transitional period).
    CAT_MAP_LEGACY = {
        "matrix-switcher":     ["switcher"],
        "production-switcher": ["switcher"],
        "camera-ptz":          ["camera"],
        "camera-box":          ["camera"],
        "camera-usb":          ["camera"],
        "encoder":             ["encoder"],
        "decoder":             ["decoder"],
        "extender-tx":         ["extender"],
        "extender-rx":         ["extender"],
        "amplifier":           ["amplifier"],
        "controller":          ["controller"],
        "multiviewer":         ["multiviewer"],
        "splitter":            ["splitter"],
        "converter":           ["converter"],
    }
    legacy_cats: set[str] = set()
    for fn in fn_values:
        legacy_cats.update(CAT_MAP_LEGACY.get(fn, []))

    if legacy_cats:
        lph = ",".join("?" * len(legacy_cats))
        legacy_params: list = list(legacy_cats)
        legacy_sql = (
            f"SELECT p.id FROM products p "
            f"WHERE p.category IN ({lph}) "
            f"AND (p.stock_status IS NULL OR p.stock_status != 'Discontinued') "
            f"AND p.category != 'accessory' "
            f"AND p.id NOT IN (SELECT sku FROM product_interfaces)"
        )
        if is_matrix and min_inputs:
            # Use explicit inputs count OR name patterns for products with NULL inputs
            if min_inputs <= 8:
                name_pats = (
                    "p.name LIKE '%8x8%' OR p.name LIKE '%8X8%' "
                    "OR p.name LIKE '%8x6%' OR p.name LIKE '%8X6%' "  # e.g. BG-M88-H2A
                    "OR p.name LIKE '%16x16%' OR p.name LIKE '%16X16%' "
                    "OR p.name LIKE '%12x12%'"
                )
            else:
                name_pats = "p.name LIKE '%16x16%' OR p.name LIKE '%16X16%'"
            legacy_sql += f" AND (p.inputs >= ? OR (p.inputs IS NULL AND ({name_pats})))"
            legacy_params.append(min_inputs)
        if min_outputs and is_matrix:
            if min_outputs <= 8:
                out_pats = "p.name LIKE '%8x8%' OR p.name LIKE '%8X8%' OR p.name LIKE '%16x16%'"
            else:
                out_pats = "p.name LIKE '%16x16%'"
            legacy_sql += f" AND (p.outputs >= ? OR (p.outputs IS NULL AND ({out_pats})))"
            legacy_params.append(min_outputs)
            # Apply max_outputs ceiling (exclude grossly oversized switchers)
            if max_outputs:
                legacy_sql += " AND (p.outputs IS NULL OR p.outputs <= ?)"
                legacy_params.append(max_outputs)
            # For large scale (>16 outputs), require known capacity — exclude NULL-output small switchers
            if min_outputs > 16:
                legacy_sql += " AND p.outputs IS NOT NULL"
        if is_camera and signal_filter:
            legacy_sql += " AND p.output_signals LIKE ?"
            legacy_params.append(f"%{signal_filter}%")
        if is_camera and zoom_filter:
            if "-" in zoom_filter:
                lo, hi = zoom_filter.replace("x", "").split("-", 1)
                legacy_sql += " AND (p.name LIKE ? OR p.name LIKE ?)"
                legacy_params.append(f"%{lo}X%"); legacy_params.append(f"%{hi}X%")
            else:
                legacy_sql += " AND p.name LIKE ?"
                legacy_params.append(f"%{zoom_filter}%")
        legacy_rows = conn.execute(legacy_sql, legacy_params).fetchall()
        iface_skus.update(row[0] for row in legacy_rows)

    # If direct_cats were also requested, merge those results
    if direct_cats:
        dph = ",".join("?" * len(direct_cats))
        direct_sql_extra = ""
        direct_extra_params: list = []
        # When matrix search adds av_over_ip, exclude controllers (only want TX/RX/transceivers)
        if "av_over_ip" in direct_cats and is_matrix:
            direct_sql_extra = (
                " AND NOT (p.category = 'av_over_ip' AND "
                "(p.title LIKE '%Controller%' OR p.title LIKE '%Smart Controller%'))"
            )
        direct_rows = conn.execute(
            f"SELECT p.id FROM products p WHERE p.category IN ({dph}) "
            "AND (p.stock_status IS NULL OR p.stock_status NOT IN ('Discontinued', 'Limited Stock')) "
            "AND (p.site_category IS NULL OR p.site_category != 'Discontinued') "
            f"AND p.category != 'accessory'{direct_sql_extra}",
            list(direct_cats) + direct_extra_params
        ).fetchall()
        iface_skus.update(r[0] for r in direct_rows)

    conn.close()
    return _deduplicate_color_variants(list(iface_skus))


def _find_matching_skus_for_flow_a(requested_categories: list[str], answers: dict) -> list[str]:
    """
    For Flow A: SQL-query ALL non-discontinued products that match the requested category
    and the customer's specs. These SKUs will be passed as mandatory to the LLM so it can't
    silently omit any of them.
    """
    # Multi-category requests (e.g. "PTZ camera + joystick + production switcher") MUST be
    # searched one category at a time and then unioned. If searched together, the device-type
    # flags (is_matrix / is_camera / is_ptz_controller) all turn on at once and their
    # type-specific filters get ANDed into a single impossible query → zero results, even
    # though the catalog has each product. Each category gets its own correctly-flagged search.
    if len(requested_categories) > 1:
        merged: list[str] = []
        seen: set[str] = set()
        for cat in requested_categories:
            for sku in _find_matching_skus_for_flow_a([cat], answers):
                if sku not in seen:
                    seen.add(sku)
                    merged.append(sku)
        return merged

    CAT_MAP = {
        "matrix switcher": ["switcher"],
        "video matrix":    ["switcher"],
        "switcher":        ["switcher"],
        "production switcher": ["switcher"],
        "presentation switcher": ["switcher"],
        "video wall":      ["switcher", "multiviewer"],
        "video wall processor": ["switcher", "multiviewer"],
        "videowall":       ["switcher", "multiviewer"],
        "camera":          ["camera"],
        "cameras":         ["camera"],
        "ptz camera":      ["camera"],
        "ptz cameras":     ["camera"],
        "capture card":    ["capture"],
        "capture cards":   ["capture"],
        "capture":         ["capture"],
        "kvm":             ["kvm_switch"],
        "kvm switch":      ["kvm_switch"],
        "kvm switcher":    ["kvm_switch"],
        "videobar":        ["videobar"],
        "video bar":       ["videobar"],
        "conferencing bar": ["videobar"],
        "av over ip":      ["av_over_ip", "encoder_decoder"],
        "av-over-ip":      ["av_over_ip", "encoder_decoder"],
        "avoip":           ["av_over_ip", "encoder_decoder"],
        "transceiver":     ["av_over_ip", "encoder_decoder"],
        "audio":           ["audio"],
        "audio processor": ["audio"],
        "audio amplifier": ["audio"],
        "audio matrix":    ["audio"],
        "network switch":  ["network"],
        "network":         ["network"],
        "poe switch":      ["network"],
        "bundle":          ["bundle"],
        "studio bundle":   ["bundle"],
        "encoder":         ["encoder"],
        "streaming encoder": ["encoder"],
        "decoder":         ["decoder"],
        "extender":        ["extender"],
        "hdbaset":         ["extender"],
        "amplifier":       ["amplifier"],
        "audio amplifier": ["amplifier"],
        "controller":      ["controller"],
        "ptz controller":  ["controller"],
        "joystick":        ["controller"],
        "joystick controller": ["controller"],
        "multiviewer":     ["multiviewer"],
        "splitter":        ["splitter"],
        "converter":       ["converter"],
    }

    db_cats: set[str] = set()
    for cat in requested_categories:
        cat_low = cat.lower()
        for key, vals in CAT_MAP.items():
            if key in cat_low or cat_low in key:
                db_cats.update(vals)

    if not db_cats:
        return []

    # Derive min/max inputs/outputs from chip answers
    min_inputs = None
    max_inputs = None   # None = no upper bound
    min_outputs = None
    max_outputs = None
    for q, a in answers.items():
        q_low = q.lower()
        a_low = str(a).lower().strip()
        if any(w in q_low for w in ("source", "input", "camera", "источник")):
            if   "more than 16" in a_low: min_inputs = 17
            elif "more than 8"  in a_low: min_inputs = 9; max_inputs = 32
            elif "more than 6"  in a_low: min_inputs = 7; max_inputs = 16
            elif "more than 4"  in a_low: min_inputs = 5; max_inputs = 16
            elif "–" in a_low or "-" in a_low:
                # Parse range like "2–4" or "5-8"
                parts = [p.strip() for p in a_low.replace("–", "-").split("-") if p.strip().isdigit()]
                if len(parts) >= 2:
                    min_inputs = int(parts[0]); max_inputs = int(parts[-1]) * 2
            elif a_low.isdigit():
                min_inputs = int(a_low)
                # Exact request: proximity ceiling = 2× requested (min 8)
                max_inputs = max(int(a_low) * 2, 8)
        if any(w in q_low for w in ("display", "output", "screen", "monitor", "экран")):
            if   "more than 16" in a_low: min_outputs = 17
            elif "more than 8"  in a_low: min_outputs = 9; max_outputs = 32
            elif "more than 4"  in a_low: min_outputs = 5; max_outputs = 16
            elif "–" in a_low or "-" in a_low:
                parts = [p.strip() for p in a_low.replace("–", "-").split("-") if p.strip().isdigit()]
                if len(parts) >= 2:
                    min_outputs = int(parts[0]); max_outputs = int(parts[-1]) * 2
            elif a_low.isdigit():
                min_outputs = int(a_low)
                max_outputs = max(int(a_low) * 2, 8)

    # Detect category type for specialised filtering
    is_matrix = any("matrix" in c or "switcher" in c for c in requested_categories)
    is_camera = any("camera" in c for c in requested_categories)
    is_ptz_controller = any("controller" in c or "joystick" in c for c in requested_categories)

    # For large-scale distribution, include AV over IP alternatives alongside switchers
    # 9+ outputs or explicit av_over_ip request → show IPGEAR / MC-Series options too
    if is_matrix and (min_outputs is not None and min_outputs > 8):
        db_cats.update(["av_over_ip"])

    # Extract signal type / zoom / resolution from answers (cameras, encoders, extenders)
    signal_filter:     str | None = None
    zoom_filter:       str | None = None
    resolution_filter: str | None = None
    needs_ndi:   bool = False
    needs_dante: bool = False
    for q, a in answers.items():
        q_low, a_low = q.lower(), str(a).lower()
        if any(w in q_low for w in ("signal", "сигнал", "output", "interface", "type")):
            if   "sdi"  in a_low: signal_filter = "SDI"
            elif "ndi"  in a_low: signal_filter = "NDI"
            elif "hdmi" in a_low: signal_filter = "HDMI"
            elif "usb"  in a_low: signal_filter = "USB"
        if any(w in q_low for w in ("ndi", "needed", "network")):
            if a_low in ("yes", "true", "1"): needs_ndi = True
            elif "no" in a_low or "standard" in a_low or "hdmi" in a_low or "sdi" in a_low: needs_ndi = False
        if any(w in q_low for w in ("dante",)):
            if a_low in ("yes", "true", "1"): needs_dante = True
            elif "no" in a_low or "standard" in a_low: needs_dante = False
        # Detect from signal answer
        if "ndi" in a_low and any(w in q_low for w in ("signal", "network", "ndi", "output", "technology", "needed")):
            needs_ndi = True
        if "dante" in a_low and any(w in q_low for w in ("signal", "dante", "audio", "technology", "needed")):
            needs_dante = True
        # Detect explicit "standard / no NDI" choice
        if any(w in q_low for w in ("ndi", "dante", "network", "technology")):
            if any(w in a_low for w in ("standard", "hdmi", "sdi", "regular", "normal", "no ndi", "without ndi")):
                needs_ndi = False
                needs_dante = False
        if any(w in q_low for w in ("zoom", "зум", "magnif")) or "x)" in a_low or "x " in a_low:
            import re as _re
            # Range first, e.g. "25-30x" / "10-12x" → keep as "MIN-MAXx"
            rng = _re.search(r'(\d{1,2})\s*[-–]\s*(\d{1,2})\s*x', a_low)
            if rng:
                zoom_filter = f"{rng.group(1)}-{rng.group(2)}x"
            else:
                for z in ("31x", "30x", "25x", "20x", "12x", "10x"):
                    if z in a_low:
                        zoom_filter = z
                        break
                # Also parse plain numbers like "20" or "around 20"
                if not zoom_filter:
                    m = _re.search(r'\b(10|12|20|25|30|31)\b', a_low)
                    if m:
                        zoom_filter = m.group(1) + "x"
        if any(w in q_low for w in ("resolution", "разреш")) and not resolution_filter:
            if   "4k60" in a_low: resolution_filter = "4K60"
            elif "4k"   in a_low: resolution_filter = "4K"
            elif "1080" in a_low: resolution_filter = "1080"

    try:
        # ── Fast path: use structured product_interfaces table if ready ───────
        if _interfaces_table_ready():
            # Pass expanded db_cats so fast path also includes av_over_ip when needed
            expanded_cats = list(db_cats)
            return _find_matching_skus_via_interfaces(
                requested_categories=expanded_cats,
                answers=answers,
                min_inputs=min_inputs,
                max_inputs=max_inputs,
                min_outputs=min_outputs,
                max_outputs=max_outputs,
                signal_filter=signal_filter,
                zoom_filter=zoom_filter,
                resolution_filter=resolution_filter,
                is_matrix=is_matrix,
                is_camera=is_camera,
                needs_ndi=needs_ndi,
                needs_dante=needs_dante,
            )

        # ── Legacy fallback: plain products table query ────────────────────────
        from api.db import get_conn
        conn = get_conn()
        placeholders = ",".join("?" * len(db_cats))
        params: list = list(db_cats)

        sql = (
            f"SELECT id, name FROM products "
            f"WHERE category IN ({placeholders}) "
            f"AND (site_category IS NULL OR site_category != 'Discontinued') "
            f"AND (stock_status IS NULL OR stock_status NOT IN ('Discontinued', 'Limited Stock')) "
            f"AND category != 'accessory'"
        )
        # PTZ controller search must not include AV-over-IP "controller" devices
        if is_ptz_controller:
            sql += " AND category != 'av_over_ip'"

        if is_matrix and min_inputs:
            # av_over_ip products are scalable (no fixed input count) — exempt from matrix/size filters
            # Check both name and title for 'atrix' since name field may just be the SKU
            sql += " AND (category = 'av_over_ip' OR ((name LIKE '%atrix%' OR title LIKE '%atrix%') AND (inputs IS NULL OR inputs >= ?)))"
            params.append(min_inputs)
        elif min_inputs:
            sql += " AND (inputs IS NULL OR inputs >= ?)"
            params.append(min_inputs)

        if min_outputs:
            # av_over_ip: scalable, no fixed output count — always passes
            # switchers: require enough outputs OR unknown (NULL)
            sql += " AND (category = 'av_over_ip' OR outputs IS NULL OR outputs >= ?)"
            params.append(min_outputs)

        # Exclude grossly oversized switchers (outputs > 2× needed)
        # av_over_ip is scalable so always exempt; unknown-capacity switchers also pass
        if min_outputs and max_outputs:
            sql += " AND (category = 'av_over_ip' OR outputs IS NULL OR outputs <= ?)"
            params.append(max_outputs)

        # For large matrix searches, exclude AV over IP controllers (only want transceivers/transmitters/receivers)
        if is_matrix and min_outputs and min_outputs > 8:
            sql += " AND NOT (category = 'av_over_ip' AND (title LIKE '%Controller%' OR title LIKE '%Smart Controller%'))"

        # For large-scale systems (>16 outputs), only include switchers with known capacity
        # (prevents small 4x4/8x8 products with NULL outputs from appearing)
        if is_matrix and min_outputs and min_outputs > 16:
            sql += " AND (category = 'av_over_ip' OR outputs IS NOT NULL)"

        if is_camera:
            if signal_filter:
                sql += " AND output_signals LIKE ?"
                params.append(f"%{signal_filter}%")
            if resolution_filter:
                sql += " AND resolutions LIKE ?"
                params.append(f"%{resolution_filter}%")
            if zoom_filter:
                if "-" in zoom_filter:
                    lo, hi = zoom_filter.replace("x", "").split("-", 1)
                    sql += " AND (name LIKE ? OR name LIKE ?)"
                    params.append(f"%{lo}X%"); params.append(f"%{hi}X%")
                else:
                    sql += " AND name LIKE ?"
                    params.append(f"%{zoom_filter}%")

        rows = conn.execute(sql, params).fetchall()
        conn.close()

        skus = [row[0] for row in rows]
        return _deduplicate_color_variants(skus)

    except Exception:
        return []


def _deduplicate_color_variants(skus: list[str]) -> list[str]:
    """
    Products ending in -B / -W / -S / -G are the same model in different colors.
    Keep only one per base SKU — prefer -B, otherwise first found.
    """
    COLOR_SUFFIXES = ("-B", "-W", "-S", "-G")
    seen_bases: dict[str, str] = {}
    result: list[str] = []

    for sku in skus:
        upper = sku.upper()
        base = upper
        is_color = False
        for suffix in COLOR_SUFFIXES:
            if upper.endswith(suffix):
                base = upper[: -len(suffix)]
                is_color = True
                break

        if not is_color:
            result.append(sku)
        elif base not in seen_bases:
            seen_bases[base] = sku
            result.append(sku)
        elif upper.endswith("-B") and not seen_bases[base].upper().endswith("-B"):
            # Upgrade to -B variant
            result = [s for s in result if s != seen_bases[base]]
            seen_bases[base] = sku
            result.append(sku)

    return result


def _interpret_answers(answers: dict) -> str:
    """
    Convert chip-answer text (e.g. 'More than 4') into explicit technical requirements.
    Returns extra context lines to append to the enriched question.
    """
    notes = []
    for q, a in answers.items():
        q_low = q.lower()
        a_low = str(a).lower()

        # Source / input count interpretation
        if any(w in q_low for w in ["source", "input", "camera", "источник"]):
            if "more than 4" in a_low or "больше 4" in a_low:
                notes.append("⚠️ Customer needs MORE THAN 4 inputs → minimum 8×8 matrix required. Do NOT recommend 4×4.")
            elif "more than 8" in a_low or "больше 8" in a_low:
                notes.append("⚠️ Customer needs MORE THAN 8 inputs → minimum 16×16 matrix required.")
            elif "more than 6" in a_low or "больше 6" in a_low:
                notes.append("⚠️ Customer needs MORE THAN 6 inputs → minimum 8×8 or 9×9 matrix required.")
            elif "more than 16" in a_low or "больше 16" in a_low:
                notes.append("⚠️ Customer needs MORE THAN 16 inputs → recommend largest available matrix.")

        # Display / output count interpretation
        if any(w in q_low for w in ["display", "output", "screen", "monitor", "экран", "дисплей"]):
            if "more than 4" in a_low:
                notes.append("⚠️ Customer needs MORE THAN 4 outputs → minimum 8×8 matrix required.")
            elif "more than 8" in a_low:
                notes.append("⚠️ Customer needs MORE THAN 8 outputs → minimum 16×16 matrix required.")

        # Resolution interpretation
        if "resolution" in q_low or "разреш" in q_low:
            if "4k60" in a_low or "4k" in a_low:
                notes.append("Resolution: 4K60 required → only recommend HDMI 2.0 or HDMI 2.1 products.")
            elif "8k" in a_low:
                notes.append("Resolution: 8K required → only recommend HDMI 2.1 products.")

        # Distance interpretation
        if "distance" in q_low or "расстоян" in q_low or "far" in q_low:
            if "over 70" in a_low or "70m" in a_low:
                notes.append("⚠️ Distance over 70m → HDBaseT extenders NOT sufficient. Use AV-over-IP or fiber.")
            elif "30–70" in a_low or "30-70" in a_low:
                notes.append("Distance 30–70m → recommend HDBaseT Cat6 extenders (BG-EXH-70C4).")
            elif "70–100" in a_low or "70-100" in a_low:
                notes.append("Distance 70–100m → recommend HDBaseT Cat6A extenders (BG-EXH-100C4).")

    return "\n".join(notes)


def build_enriched_question(plan: dict, answers: dict, original_question: str, selected_roles: list[str] = None) -> str:
    """
    Build a rich question for the Universal Engine.
    Includes flow type so the engine knows whether to focus on specific categories only (Flow A)
    or design the complete solution (Flow B).
    """
    flow = plan.get("flow", "solution_design")
    requested_categories = plan.get("requested_categories", [])

    all_roles = plan.get("required_roles", [])
    if selected_roles:
        roles = [r for r in all_roles if r["role"] in selected_roles]
        skipped = [r["role"] for r in all_roles if r["role"] not in selected_roles]
    else:
        roles = all_roles
        skipped = []

    roles_text = "\n".join(
        f"  - {r['role']} ({r.get('quantity_hint','1')}): {r['purpose']}"
        for r in roles
    )

    answers_text = "\n".join(f"  - {k}: {v}" for k, v in answers.items()) if answers else "  (none yet)"

    skipped_note = (
        f"\nRoles the customer already has / does not need:\n"
        + "\n".join(f"  - {r}" for r in skipped)
        if skipped else ""
    )

    interpreted = _interpret_answers(answers)
    interpreted_block = f"\nTechnical requirements (interpreted from answers):\n{interpreted}" if interpreted else ""

    if flow in ("product_selection", "hybrid"):
        cats_str = ", ".join(requested_categories) if requested_categories else "the specific device types mentioned"

        # SQL pre-fetch: ALL matching non-discontinued SKUs — LLM must cover all of them
        mandatory_skus = _find_matching_skus_for_flow_a(requested_categories, answers)
        if mandatory_skus:
            mandatory_block = (
                "\n⚠️ MANDATORY — the following products exist in our catalog and match the specs. "
                "You MUST include and compare ALL of them (do NOT omit any):\n"
                + "\n".join(f"  - {s}" for s in mandatory_skus)
            )
        else:
            mandatory_block = ""

        flow_instruction = f"""
⚠️ FLOW TYPE: product_selection
The customer asked specifically about: {cats_str}
DO NOT recommend other equipment categories.
Start your response: "You're looking for {cats_str} — here are all the options from our catalog that match your specs:"
{mandatory_block}
"""
    else:
        flow_instruction = """
⚠️ FLOW TYPE: solution_design
Design the complete system for this scenario.
Identify and recommend ALL required equipment categories for the workflow to function.
"""

    return f"""Scenario: {plan.get('scenario_summary', original_question)}
Type: {plan.get('scenario_type', 'unknown')}
{flow_instruction}
Equipment roles:
{roles_text}
{skipped_note}
Customer answers:
{answers_text}
{interpreted_block}
Original request: {original_question}"""
