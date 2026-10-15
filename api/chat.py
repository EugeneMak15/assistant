"""
Chat engine — single GPT-5.6 Sol AV consultant loop.

The model acts as a human AV Sales Consultant / Installer.
It converses naturally, asks exactly what it needs, and only
triggers product search when it has gathered enough data.
"""
import os, json, math, re
from openai import OpenAI
from .usage import record_usage

CONSULTANT_SYSTEM = """You are Alex, a senior AV Sales Consultant with 20 years of field installation experience.

YOUR JOB: Gather just enough info to find the right product, then trigger search. Keep it tight — 4-6 questions max.
SCOPE: Only help with AV equipment selection, AV system planning, compatibility and troubleshooting.
Decline unrelated math, trivia, poems, creative writing and social-media copy, including poems about AV products.
For these requests set scope="off_topic", ready_to_search=false, and briefly redirect to AV equipment.
AV-related quantities, prices and bandwidth calculations are in scope.
Keep each reply to one brief question or two short sentences. Product links provide the full specifications.
BG-NUTRIX is a medical-only camera; consider it only when the customer explicitly describes a medical use.

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
  Camera selection: consider fixed box cameras for static podcast shots, PTZ cameras when movement or presets are needed,
  and all-in-one video bars for conferencing. Do not turn every camera request into a PTZ requirement.
  Camera-to-subject distance determines framing. It is NOT the camera-to-PC cable length.
  Never infer a USB extension from subject distance; ask camera-to-PC distance before choosing a USB extender.
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

USB peripheral matrix / USB device sharing:
  This routes USB peripherals among host computers; it does NOT route HDMI video.
  Ask only how many host computers and how many shared USB devices. Do NOT ask
  for display count, video resolution, or video cable length. Search once the
  two counts are known; USB 3 devices are backward-compatible with USB 2.

HDMI KVM switch:
  Ask for host computer count, display count, and video resolution only if
  not already stated. Preserve "HDMI KVM" as a KVM category, not a video matrix.

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
  A larger optical zoom can achieve a smaller requested zoom. For 1080p needs, consider ADAMO-JR before 4K models.
  For NDI streaming, ask whether an existing production PC will be used. Software can receive NDI directly;
  decoders and a hardware production switcher are needed only when the customer chooses that workflow.

USB capture:
  The current BZBGEAR capture catalog uses external USB connections. Never offer PCIe as an available choice.
  Ask about capture resolution and HDMI passthrough requirements. If PCIe is explicitly requested, explain
  that only USB alternatives are listed; do not promise a PCIe product.

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
  "scope": "av_selection | off_topic",
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
    "subject_distance_m": null,
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

_SCOPE_REPLY = "I can help with AV equipment and setups. What equipment or connection do you need help with?"


def _is_off_topic_request(message: str) -> bool:
    if re.search(r"\b(?:write|compose|generate|create)\b.{0,65}\b(?:poem|poetry|lyrics|social[ -]?media (?:posts?|copy)|(?:a |some )?posts?)\b", message, re.I | re.S):
        return True
    if re.search(r"\b(?:most popular song|current weather|weather forecast)\b", message, re.I):
        return True
    math_request = bool(re.search(r"\b(?:calculate|solve|what['’]?s|what is)\b", message, re.I) or re.search(r"[+*/=]", message))
    return bool(math_request and re.search(r"\d[\d,]*\s*[×x*+/=]\s*\d", message, re.I) and not re.search(
        r"\b(?:av|hdmi|sdi|usb|matrix|splitter|camera|switch|tv|display|screen|input|output|bandwidth|cost|price|feet|meters?)\b", message, re.I
    ))


def _resolution_unsure(history: list[dict], user_message: str) -> bool:
    unsure = False
    previous = ""
    for turn in [*history, {"role": "user", "content": user_message}]:
        text = turn.get("content", "")
        if turn.get("role") == "user":
            if re.search(r"\bresolution\b.{0,20}\bnot sure\b|\bnot sure\b.{0,20}\bresolution\b", text, re.I):
                unsure = True
            elif re.search(r"resolution|1080p or 4K", previous, re.I):
                if re.search(r"not sure|don['’]?t know", text, re.I):
                    unsure = True
                elif re.search(r"1080|4k|8k", text, re.I):
                    unsure = False
            elif re.fullmatch(r"\s*(?:1080p?|4k|8k)\s*[.!]?\s*", text, re.I):
                unsure = False
        previous = text
    return unsure


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


def _run_usb_matrix_turn(history: list[dict], user_message: str) -> dict:
    """Keep USB-only sharing out of the video-matrix question/search path."""
    from .product_rules import requested_kvm_hosts

    user_text = " ".join(h.get("content", "") for h in history if h.get("role") == "user")
    user_text = (user_text + " " + user_message).lower()
    matrix = re.search(r"\b(\d{1,2})\s*[x×]\s*(\d{1,2})\b", user_text)
    hosts = int(matrix.group(1)) if matrix else requested_kvm_hosts(user_text)
    devices = int(matrix.group(2)) if matrix else None
    count_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8}
    match = re.search(r"\b(\d{1,2}|one|two|three|four|five|six|eight)\s*(?:usb\s*)?(?:devices?|peripherals?)\b", user_text)
    if match and not devices:
        value = match.group(1)
        devices = int(value) if value.isdigit() else count_words[value]
    if not devices:
        devices = sum(bool(re.search(rf"\b{item}\b", user_text)) for item in ("webcam", "keyboard", "mouse")) or None
    if not devices and history and re.search(r"\b(?:devices?|peripherals?)\b", history[-1].get("content", ""), re.I):
        devices = _parse_capacity(user_message)
    if not hosts and history and re.search(r"\b(?:computers?|hosts?)\b", history[-1].get("content", ""), re.I):
        hosts = _parse_capacity(user_message)

    ready = bool(hosts and devices)
    explicit_matrix = bool(re.search(
        r"\busb\b.{0,20}\bmatrix\b|\bmatrix\b.{0,20}\busb\b|"
        r"\bwhich computer gets which device\b|\bindependent\s+(?:usb\s+)?routing\b", user_text
    ))
    device_type = "USB matrix switcher" if explicit_matrix else "USB peripheral switch"
    query = f"{hosts}x{devices} {device_type} for {hosts} computers and {devices} USB devices" if ready else ""
    if ready:
        message = f"Got it — {hosts} computers sharing {devices} USB devices. Let me find the right switch..."
        chips = []
    elif not hosts:
        message = "How many computers will share the USB devices?"
        chips = ["2 computers", "3 computers", "4 computers", "More than 4"]
    else:
        message = "How many USB devices will the computers share?"
        chips = ["1 device", "2 devices", "3 devices", "4 devices"]
    answers = {}
    if hosts:
        answers["How many USB host computers?"] = str(hosts)
    if devices:
        answers["How many USB devices?"] = str(devices)
    return {
        "message": message, "chips": chips, "state_update": {
            **({"num_inputs": hosts} if hosts else {}),
            **({"num_outputs": devices} if devices else {}),
        },
        "ready_to_search": ready, "search_query": query,
        "_scenario_plan": {"flow": "product_selection", "requested_categories": [device_type.lower()],
                           "scenario_type": "other", "scenario_summary": query or "USB peripheral sharing",
                           "clarifying_questions": []},
        "_scenario_answers": answers, "_clarification_round": 0,
    }


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
    from .product_rules import is_usb_matrix_request, is_selected_source_distribution, requested_ports, requested_distance_m
    user_text = " ".join(h.get("content", "") for h in history if h.get("role") == "user") + " " + user_message
    if _is_off_topic_request(user_message):
        return {"message": _SCOPE_REPLY, "chips": [], "state_update": {},
                "ready_to_search": False, "search_query": ""}
    if re.search(r"\bpcie\b", user_message, re.I) and re.search(r"\b(?:capture|card)\b", user_message, re.I):
        return {"message": "Our listed capture devices connect externally over USB; no PCIe capture card is listed. Would USB work for your setup?",
                "chips": ["USB works", "I need PCIe"], "state_update": {},
                "ready_to_search": False, "search_query": ""}
    if is_usb_matrix_request(user_text):
        return _run_usb_matrix_turn(history, user_message)

    if (re.search(r"audio extractor|(?:pull|extract)\b.{0,20}\baudio\b", user_text, re.I)
            and re.search(r"\b(?:e?arc)\b", user_text, re.I)
            and re.search(r"\b(?:soundbar|receiver)\b", user_text, re.I)
            and ((re.search(r"external\b.{0,15}\bhdmi\b|hdmi\s+device", user_text, re.I)
                  and re.search(r"4k|1080", user_text, re.I))
                 or re.search(r"receiver\b.{0,25}\boptical\b", user_text, re.I))):
        return {"message": "Got it — I'll check the audio adapters for that source and soundbar or receiver.",
                "chips": [], "state_update": {}, "ready_to_search": True, "search_query": user_text,
                "_scenario_plan": {"flow": "product_selection", "requested_categories": ["audio extractor"],
                                   "scenario_summary": user_text, "scenario_type": "other", "clarifying_questions": []},
                "_scenario_answers": {}, "_clarification_round": 0}

    # A direct question about a named model/series needs a catalog lookup,
    # not another round of room-design questions.
    if re.search(r"^\s*(?:is|are|does|do|compare|what(?:['’]s| is) the difference)\b", user_message, re.I):
        from .product_rules import mentioned_catalog_skus
        from .db import get_conn
        conn = get_conn()
        try:
            mentioned = mentioned_catalog_skus(conn, user_message)
            categories = [row[0] for row in conn.execute(
                f"SELECT DISTINCT category FROM products WHERE id IN ({','.join('?' * len(mentioned))})",
                mentioned,
            )] if mentioned else []
        finally:
            conn.close()
        if mentioned and categories:
            aliases = {"camera": "camera", "av_over_ip": "av over ip",
                       "controller": "ptz controller", "audio": "audio converter"}
            requested = list(dict.fromkeys(aliases.get(category, category) for category in categories))
            return {
                "message": "I’ll check those models against the catalog.", "chips": [],
                "state_update": {}, "ready_to_search": True, "search_query": user_message,
                "_scenario_plan": {"flow": "product_selection", "requested_categories": requested,
                                   "scenario_type": "other", "scenario_summary": user_message,
                                   "clarifying_questions": []},
                "_scenario_answers": {}, "_clarification_round": 0,
            }

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
            model="gpt-5.6-sol",
            messages=messages,
            response_format={"type": "json_object"},
            timeout=40,
        )
    except Exception as e:
        err = str(e)
        if "insufficient_quota" in err or "429" in err:
            raise RuntimeError("OPENAI_QUOTA_EXCEEDED")
        raise

    record_usage(resp)
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
    # Chips may contain ranges such as "5-8" or "8 or more". The session
    # schema needs integers; use the upper end of a range so capacity is not
    # undersized, and the lower bound for open-ended "or more" answers.
    for key in ("num_inputs", "num_outputs"):
        count = _parse_capacity(intent.get(key))
        if count is None:
            intent.pop(key, None)
        else:
            intent[key] = count
    if "distance_m" in intent:
        distance = _parse_distance_m(intent["distance_m"])
        if distance is None:
            intent.pop("distance_m")
        else:
            intent["distance_m"] = distance
    chips    = data.get("chips") or []
    ready    = bool(data.get("ready_to_search"))
    msg      = data.get("message", "")
    sq       = data.get("search_query", "")
    if data.get("scope") == "off_topic":
        return {"message": _SCOPE_REPLY, "chips": [], "state_update": {},
                "ready_to_search": False, "search_query": ""}

    from .product_rules import requested_distance_m, requested_ports
    user_requests = " ".join(h.get("content", "") for h in history if h.get("role") == "user")
    user_requests = (user_requests + " " + user_message).strip()
    known_distance = requested_distance_m(user_requests)
    known_inputs, known_outputs = requested_ports(user_requests)
    resolution_unsure = _resolution_unsure(history, user_message)
    if resolution_unsure:
        intent.pop("resolution", None)
    known_resolution = resolution_unsure or bool(re.search(r"\b(?:1080\s*p?|4\s*k|8\s*k)(?:\b|(?=\d))", user_requests, re.I))
    asked_again = (
        (known_distance is not None and re.search(r"\b(?:how far|distance|cable run|longest|feet|meters?)\b", msg, re.I))
        or (known_resolution and re.search(r"\b(?:what|which)\b.{0,25}\bresolution\b|\b1080p or 4K\b", msg, re.I))
        or (known_inputs is not None and re.search(r"\bhow many\b.{0,30}\b(?:sources?|inputs?)\b", msg, re.I))
        or (known_outputs is not None and re.search(r"\bhow many\b.{0,30}\b(?:tvs?|screens?|displays?|outputs?)\b", msg, re.I))
    )
    questions_so_far = sum(h.get("role") == "assistant" and "?" in h.get("content", "") for h in history)
    if not ready and (asked_again or questions_so_far >= 5):
        if asked_again and questions_so_far < 5 and not known_resolution and re.search(r"\b(?:hdmi|video|display|tv|screen|wall plate)\b", user_requests, re.I):
            msg = "What resolution do you need: 1080p or 4K?"
            chips = ["1080p", "4K", "Not sure"]
        else:
            ready = True
            msg = "Got it — let me find the best-fit options."
            chips = []
            sq = user_requests

    # A connector name ("HDMI") is not an answer to a resolution question.
    # Make the missing choice explicit and clickable for HDMI KVM shoppers.
    kvm_user_text = " ".join(h.get("content", "") for h in history if h.get("role") == "user") + " " + user_message
    if re.search(r"\bkvm\b", kvm_user_text, re.I) and not re.search(
        r"\b(?:1080\s*p?|4\s*k|8\s*k|2160\s*p?)(?:\b|(?=\d))", kvm_user_text, re.I
    ):
        intent.pop("resolution", None)
        ready = False
        if re.fullmatch(r"\s*HDMI(?:\s*2\.[01])?\s*", user_message, re.I):
            msg = "HDMI is the connection type. Which video resolution do you need: 1080p, 4K, or 8K?"
        else:
            msg = "What video resolution do you need: 1080p, 4K, or 8K?"
        chips = ["1080p", "4K", "8K", "Not sure"]

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
    fixed_shots = "ptz" not in _user_text and (
        bool(re.search(r"\b(?:fixed|static)\b.{0,35}\b(?:camera|shots?)\b", _user_text))
        or ("podcast" in _user_text and "edit afterward" in _user_text)
    )
    if fixed_shots:
        categories = ["camera" if "camera" in str(category).lower() else category for category in categories]
        sq = re.sub(r"\bptz\s+cameras?\b", "cameras for fixed shots", sq, flags=re.I)
    special_needs = [str(item) for item in (intent.get("special_needs") or [])]
    if fixed_shots:
        special_needs.append("fixed shots")
    if re.search(r"\bauto[ -]?track(?:ing)?\b", _user_text) and not re.search(r"\b(?:no|without)\s+auto[ -]?track(?:ing)?\b", _user_text):
        special_needs.append("auto tracking required")
    intent["special_needs"] = list(dict.fromkeys(special_needs))
    if ready and special_needs:
        sq += "; " + "; ".join(intent["special_needs"])
    if re.search(r"\bkvm\b", _user_text, re.I):
        categories = ["kvm switch" if "kvm" in str(category).lower() else category
                      for category in categories]
        if not categories or categories == ["switcher"]:
            categories = ["kvm switch"]
        flow = "product_selection"
        if ready:
            sq = (_user_text + " " + sq).strip()
    if is_selected_source_distribution(_user_text):
        # The user described one selected signal mirrored to every display.
        # Preserve that topology even if the model calls it a 2x8 matrix.
        categories = ["splitter"]
        flow = "product_selection"
        intent["equipment_type"] = "splitter"
        inputs, outputs = requested_ports(_user_text)
        if inputs:
            intent["num_inputs"] = inputs
        if outputs:
            intent["num_outputs"] = outputs
        if requested_distance_m(_user_text) is not None:
            ready = True
        if ready:
            msg = "Got it — I'll find a splitter for the selected source and all displays."
            chips = []
        sq = _user_text.strip()
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
        state_update["max_distance_m"] = intent["distance_m"]
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


def _parse_capacity(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if not isinstance(value, str):
        return None
    numbers = [int(n) for n in re.findall(r"\d+", value)]
    if not numbers:
        return None
    count = max(numbers)
    if re.search(r"(?:more than|over|greater than|>)\s*\d+", value, re.I):
        count += 1
    return count if count > 0 else None


def _parse_distance_m(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return math.ceil(value) if math.isfinite(value) and value > 0 else None
    if not isinstance(value, str):
        return None
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", value)]
    if not numbers:
        return None
    distance = max(numbers)
    if re.search(r"ft|feet|'", value, re.I):
        distance *= 0.3048
    return math.ceil(distance) if distance > 0 else None


def _intent_to_answers(intent: dict) -> dict:
    """Convert structured intent to the answers dict the SQL filter expects."""
    ans = {}
    if intent.get("num_inputs"):
        ans["How many video inputs/sources?"] = str(intent["num_inputs"])
    if intent.get("num_outputs"):
        ans["How many displays/outputs?"] = str(intent["num_outputs"])
    if intent.get("distance_m"):
        ans["Distance to furthest display?"] = str(intent["distance_m"]) + "m"
    if intent.get("subject_distance_m"):
        ans["Camera-to-subject distance?"] = str(intent["subject_distance_m"]) + "m"
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
    if intent.get("special_needs"):
        ans["Special requirements?"] = "; ".join(str(item) for item in intent["special_needs"])
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
Only answer AV selection, compatibility and setup questions. Decline poems, unrelated math, trivia,
and social-media writing, even if they mention HDMI or the brand. Set scope="off_topic" for these requests.

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

CASE 2 — REVISED REQUIREMENTS (search again in this same chat):
  The customer corrects or adds a requirement to the SAME setup (a new output type,
  more/fewer inputs or displays, a different resolution, distance, budget, protocol,
  camera plus switcher instead of only one, or asks for other matching products).
  "Are there cheaper options?" means search the full catalog again; it is not limited to PRODUCTS FOUND.
  The previous product list may now be wrong or incomplete. Do not answer from it.
  → Set "refine_search": true. Keep "new_topic": false. Reply with a short acknowledgement
    such as "Got it — I'll update the search with that requirement."

CASE 3 — DIFFERENT TOPIC (suggest a new chat):
  The message is a clearly different need — a different device family or a new project unrelated
  to this search (e.g. the search was about one room and now they ask about a
  separate room/project). Adding another device to the SAME setup is CASE 2, not CASE 3.
  Do NOT try to answer it from this chat's context.
  → Politely say this chat is focused on <TOPIC>, and suggest starting a new chat (the "+ New chat"
    button) so the new request isn't mixed up with the previous one's history.

Reply as JSON only:
{
  "scope": "av_selection | off_topic",
  "message": "your reply to the customer",
  "new_topic": false,
  "refine_search": false
}
Set "new_topic": true ONLY for CASE 3. Set "refine_search": true ONLY for CASE 2.
"""


def run_followup_turn(history: list[dict], user_message: str, results: dict) -> dict:
    """
    Post-search Q&A. The customer already got results; answer questions about the found
    products / technology, or detect a topic change and suggest starting a new chat.

    `results` = { "topic": str, "products": [ {id, name, price_usd, ...} ], "rec_text": str }
    Returns { "message": str, "suggest_new_chat": bool, "refine_search": bool }
    """
    if _is_off_topic_request(user_message):
        return {"message": _SCOPE_REPLY, "suggest_new_chat": False, "refine_search": False}
    if re.search(r"\b(?:cheaper options?|cheaper models?|less expensive options?|lower[- ]cost alternatives?|more affordable options?)\b", user_message, re.I):
        return {"message": "I'll look across the catalog for lower-cost options for the same setup.",
                "suggest_new_chat": False, "refine_search": True}
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
            model="gpt-5.6-sol",
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

    record_usage(resp)
    try:
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        data = {"message": "Sorry, could you rephrase that?", "new_topic": False}

    if data.get("scope") == "off_topic":
        return {"message": _SCOPE_REPLY, "suggest_new_chat": False, "refine_search": False}
    return {
        "message": data.get("message", ""),
        "suggest_new_chat": bool(data.get("new_topic")),
        "refine_search": bool(data.get("refine_search")) and not bool(data.get("new_topic")),
    }


def get_opening_message() -> dict:
    return {
        "message": "Hi, I'm Alex. What AV equipment or setup do you need?",
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
