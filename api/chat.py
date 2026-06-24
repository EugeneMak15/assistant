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
Matrix switcher / extender / splitter:
  1. How many video sources (inputs)?
  2. How many displays (outputs)?
  3. What's the longest single cable run from the rack to any display? Ask in FEET.
     Always ask for the worst-case (longest) run — gear is selected for that distance.
     Chips: ["Under 30ft", "30–100ft", "100–200ft", "Over 200ft"]
  4. Resolution — 1080p or 4K?
  → Trigger search when all 4 are known.

PTZ camera (production / worship):
  1. How far are subjects from the camera?
  2. Tight close-ups or wide shots? (determines zoom: 12x / 20x / 30x)
  3. Signal output — HDMI, SDI, or NDI (IP)?
  4. Dante audio needed?
  → Trigger search when zoom + signal type known.

PTZ camera (conferencing):
  1. Room size?
  2. Connection — USB (Zoom/Teams) or HDMI/NDI?
  → Trigger search when connection type known.

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
Examples:
  - inputs: ["2", "4", "6", "8 or more"]
  - outputs: ["2-4", "5-8", "9-16", "More than 16"]
  - resolution: ["1080p is fine", "4K60 required"]
  - distance (always in feet): ["Under 30ft", "30–100ft", "100–200ft", "Over 200ft"]
  - zoom: ["12x (small room)", "20x (medium room)", "30x (large venue)"]
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
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_message})

    resp = client.chat.completions.create(
        model="gpt-5.5",
        messages=messages,
        response_format={"type": "json_object"},
    )

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
