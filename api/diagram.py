"""
Extract a structured connection diagram from a recommendation text.
Returns nodes + connections that the frontend renders as SVG.
"""
import os, json
from openai import OpenAI

DIAGRAM_PROMPT = """You are extracting a signal-chain diagram from an AV system recommendation.

Return ONLY valid JSON in this exact structure:
{
  "nodes": [
    {
      "id": "unique_short_id",
      "sku": "BG-XXXXX or null if no SKU",
      "label": "short product name (3-5 words max)",
      "type": "camera|controller|switcher|encoder|extender|splitter|network|display|streaming|recorder|audio|pc|other",
      "quantity": 1
    }
  ],
  "connections": [
    {
      "from": "node_id",
      "to": "node_id",
      "cable": "HDMI 2.0",
      "signal": "HDMI"
    }
  ]
}

Signal type must be one of: HDMI | SDI | NDI | Ethernet | USB | Fiber | Audio | Power | HDBaseT

Rules:
- Include EVERY device mentioned in the recommendation
- For quantity > 1 (e.g. 3 cameras), set quantity field — don't create separate nodes
- Infer cable type from context (e.g. "Cat6" → Ethernet, "coax" → SDI, "RTMP" → Ethernet)
- Include streaming targets (YouTube, etc.) as type "streaming"
- Include internet/router as type "network" if mentioned
- Keep labels short and clear"""


def extract_diagram(recommendation: str) -> dict:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": DIAGRAM_PROMPT},
            {"role": "user",   "content": f"Extract diagram from this recommendation:\n\n{recommendation}"},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {"nodes": [], "connections": []}
