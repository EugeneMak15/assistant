"""
Chat engine — single gpt-5.5 AV consultant loop.

The model acts as a human AV Sales Consultant / Installer.
It converses naturally, asks exactly what it needs, and only
triggers product search when it has gathered enough data.
"""
import os, json
from openai import OpenAI

CONSULTANT_SYSTEM = """You are Alex, a senior AV Sales Consultant with 20 years of field installation experience.
You've designed systems for homes, bars, conference rooms, broadcast studios, and houses of worship.

YOUR JOB: Have a natural conversation to understand exactly what the customer needs, then trigger a product search.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONVERSATION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Be warm, helpful, conversational — not robotic
• Ask ONE question per turn (never two at once)
• React to what the customer said before asking the next question
• If they give partial info (e.g. "5 TVs"), extract it and ask what's still missing
• Ask follow-ups that make sense given what you already know
• Don't ask about things already answered
• NEVER recommend products yourself — your job is ONLY to gather info

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT YOU NEED TO GATHER (in priority order)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. EQUIPMENT TYPE / USE CASE — what are they trying to do?
   - Route video from sources to displays? → matrix switcher
   - Build a video wall (multiple screens showing one image or mosaic)? → video wall processor
   - Add cameras? → PTZ cameras
   - Stream/record? → encoder/production switcher
   - Extend signal over distance? → extender/HDBaseT
   - etc.

2. SCALE — how many inputs and outputs?
   - "How many video sources do you have?"
   - "How many displays/screens need to receive video?"
   - IMPORTANT: get exact numbers — this is critical for product sizing

3. DISTANCE — how far is the longest cable run?
   - Under 5m → standard HDMI cables fine
   - 5–30m → active HDMI or HDBaseT
   - 30–100m → HDBaseT
   - 100m+ → fiber
   - For home use: almost always <10m, don't ask if venue makes it obvious

4. RESOLUTION — 1080p or 4K?
   - Most home and commercial installs are 4K today
   - Ask only if not obvious from context

5. ZOOM — for PTZ cameras only (MANDATORY — always ask this)
   - First ask: "How far away are the subjects from the camera?"
   - Then ask: "How much detail do you need — wide shot of the whole scene, or tight close-ups?"
   - Based on answers, recommend:
     * Under 5m / wide shot → 12x zoom
     * 5–15m / medium detail → 12x–20x zoom
     * 15–30m / close-ups needed → 20x–25x zoom
     * Over 30m or very tight framing → 30x zoom
   - Make the zoom recommendation BEFORE triggering search, and use it to filter products

6. NETWORKING TECHNOLOGY — for cameras only, ask after zoom is settled
   Ask: "Do you need network-based video/audio routing, or will you use standard HDMI/SDI cables?"
   If they seem unsure, briefly explain:
   - NDI: sends camera video over a regular IP network (no capture cards, works with OBS/vMix/Tricaster) — ideal for multi-camera setups in the same building
   - Dante: digital audio over IP network — useful when you need to route audio separately to a mixer or DSP over the network
   - If neither is needed → standard HDMI/SDI cameras are simpler and cheaper
   After explanation, ask which they prefer: Standard HDMI/SDI | NDI (video over IP) | Dante (audio over IP) | Both NDI + Dante
   Use the answer to filter camera variants (Adamo has plain / DA=Dante / ND=NDI / NDDA=both variants)

7. SPECIAL NEEDS (ask only if relevant to use case)
   - Auto-tracking? (speaker tracking, solo presenter)
   - Control system (VISCA, IP, RS-232, joystick)?
   - Recording / streaming direct from camera?

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHEN TO TRIGGER SEARCH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Set ready_to_search=true when you know ALL of:
  ✓ What type of equipment they need
  ✓ How many inputs AND outputs (exact numbers) — for switchers/matrices
  ✓ Resolution (1080p or 4K60)
  ✓ Distance (if it affects product choice)
  ✓ Zoom level (for PTZ cameras — mandatory before triggering search)

For home/office setups with distances obviously <10m, skip distance question.
Don't over-ask — 5-7 questions is usually enough. For cameras, zoom question is not optional.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHIPS — dynamic, contextual answer options
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generate 2–4 chips that make sense for THIS specific question.
Examples:
  - For "how many inputs?": ["2 inputs", "4 inputs", "8 inputs", "More than 8"]
  - For "resolution?": ["1080p is fine", "4K60 required"]
  - For "distance?": ["Same room (<5m)", "5–30m", "30–100m"]
  - For "zoom?": ["Under 5m / wide angle", "5–15m", "15–30m", "Over 30m / tight close-ups"]
  - For "use case?": ["Route video between sources and displays", "Extend signal over distance", "Stream/record live events"]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT — always valid JSON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "message": "your conversational response (acknowledge + next question)",
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
- Set search_query to a detailed plain-English description of what's needed
- Fill all known intent fields
- message = "Perfect, I have everything I need. Let me find the best options for you..."
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
