"""
One-time batch extraction of structured interface data for all products.

Usage:
    python extract_interfaces.py [--sku BG-XXX] [--limit 10] [--overwrite]

Reads: products table (features, input_signals, output_signals, description, what_it_does)
Writes: product_interfaces table (flat booleans + JSON detail for LLM)
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

import openai

sys.path.insert(0, os.path.dirname(__file__))
from api.db import get_conn
from api.db_interfaces import init_interfaces_table, upsert_interface

# ── Chroma (optional — gracefully skip if dimension mismatch) ────────────────
try:
    import chromadb
    _chroma_client = chromadb.PersistentClient(path="./chroma_db")
    _chroma_col = _chroma_client.get_collection("products")
    CHROMA_OK = True
except Exception as e:
    print(f"[warn] Chroma unavailable: {e} — will extract from DB only")
    CHROMA_OK = False

client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# ────────────────────────────────────────────────────────────────────────────
EXTRACTION_SYSTEM = """You are a precise AV hardware specification parser.

Given product data (name, features, description, manual excerpts), extract a
structured JSON object with these exact fields. Follow the rules strictly.

OUTPUT — return ONLY valid JSON, no markdown fences, no commentary.

{
  "primary_fn": <string>,       // ONE of: matrix-switcher | encoder | decoder |
                                //   extender-tx | extender-rx | camera-ptz |
                                //   camera-box | camera-usb | production-switcher |
                                //   controller | splitter | converter | multiviewer |
                                //   amplifier | recorder | audio-processor | other
  "secondary_fns": [<string>],  // additional functions from the same list
  "form_factor": <string>,      // rack-1u | rack-2u | rack-4u | desktop | inline |
                                //   camera-ptz | camera-box | camera-usb | portable | kit

  "out_hdmi": 0|1,
  "out_hdmi_count": <int>,      // 0 if none
  "out_hdmi_ver": <string|null>, // "1.4" | "2.0" | "2.1" | null if unknown
  "out_sdi": 0|1,
  "out_sdi_count": <int>,
  "out_sdi_ver": <string|null>, // "3G" | "6G" | "12G" | null
  "out_ndi": 0|1,               // NDI or NDI|HX or NDI|HX3
  "out_usb_video": 0|1,         // USB video output (UVC device to PC)
  "out_dante": 0|1,
  "out_hdbaset": 0|1,
  "out_fiber": 0|1,
  "out_vga": 0|1,
  "out_displayport": 0|1,
  "out_ip_stream": 0|1,         // RTSP | RTMP | SRT | HLS output

  "in_hdmi": 0|1,
  "in_hdmi_count": <int>,
  "in_hdmi_ver": <string|null>,
  "in_sdi": 0|1,
  "in_sdi_count": <int>,
  "in_ndi": 0|1,
  "in_usb_video": 0|1,
  "in_dante": 0|1,
  "in_hdbaset": 0|1,
  "in_fiber": 0|1,
  "in_vga": 0|1,
  "in_displayport": 0|1,
  "in_ip_stream": 0|1,          // RTSP | RTMP | SRT input

  "max_res": <string>,          // highest supported output resolution:
                                //   "1080p60" | "4K30" | "4K60" | "8K30" | "8K60"
                                //   Use "1080p60" if only 1080p mentioned
  "supports_4k": 0|1,
  "supports_8k": 0|1,
  "supports_hdr": 0|1,          // HDR10 | HLG | Dolby Vision

  "audio_embed_in": 0|1,        // accepts embedded audio from video sources
  "audio_embed_out": 0|1,       // passes embedded audio to outputs
  "audio_analog_in": 0|1,       // analog audio inputs: XLR | RCA | 3.5mm
  "audio_deembed": 0|1,         // can strip audio from video signal

  "ctrl_ip": 0|1,               // IP control: web UI | Telnet | REST | TCP
  "ctrl_rs232": 0|1,
  "ctrl_rs422": 0|1,
  "ctrl_ir": 0|1,
  "ctrl_visca": 0|1,            // VISCA camera control protocol
  "ctrl_pelco": 0|1,            // Pelco-D or Pelco-P
  "ctrl_front": 0|1,            // physical front-panel buttons / joystick
  "ctrl_api": 0|1,              // published SDK or REST API

  "poe": 0|1,                   // device accepts PoE power
  "poe_out": 0|1,               // device provides PoE to connected device

  "zoom_optical": <int>,        // optical zoom (cameras only): 12|20|25|30|31, else 0
  "has_tally": 0|1,
  "has_autotrack": 0|1,
  "has_recording": 0|1,         // onboard SD / SSD / USB recording

  "use_case_tags": [<string>],  // e.g. ["broadcast","church","sports-bar","conference"]

  "ports_json": {               // detailed USB / Ethernet / audio port info
    "usb": [{"type":"USB-A|USB-C|USB-B|Micro","role":"power|data|video|audio|mixed",
              "note":"<brief>"}],
    "ethernet": [{"role":"control|streaming|poe|management","speed":"100M|1G|2.5G|10G"}],
    "audio": [{"connector":"XLR|RCA|3.5mm|Phoenix","dir":"in|out","count":<int>}]
  },
  "inputs_json": [              // one entry per physical input port type
    {"signal":"HDMI|SDI|NDI|VGA|DP|HDBaseT|USB|IP","count":<int>,
     "version":"<if known>","note":"<optional>"}
  ],
  "outputs_json": [             // one entry per physical output port type
    {"signal":"HDMI|SDI|NDI|IP|HDBaseT|USB","count":<int>,
     "version":"<if known>","note":"<optional>"}
  ],
  "notes": "<one sentence — anything unusual or uncertain about this product>",
  "confidence": <float>         // 0.0–1.0 extraction confidence based on data quality
}

Rules:
- If data is ambiguous or missing, set integers to 0 and strings to null.
- For matrix switchers: in_hdmi_count = number of video INPUTS; out_hdmi_count = outputs.
- NDI-only devices still have out_ndi=1 and out_ip_stream=1.
- Cameras output signals (HDMI, SDI, NDI, USB) — they have no video inputs.
- Encoders have video inputs; decoders have video outputs.
- A device can be both encoder and decoder (codec) — put one in primary_fn, other in secondary_fns.
"""


def get_chroma_chunks(sku: str, n: int = 5) -> str:
    if not CHROMA_OK:
        return ""
    try:
        # try both 'id' and 'sku' metadata keys
        for key in ("id", "sku"):
            results = _chroma_col.get(
                where={key: {"$eq": sku}},
                include=["documents"],
            )
            docs = results.get("documents", [])
            if docs:
                return "\n---\n".join(docs[:n])
        return ""
    except Exception:
        return ""


def extract_interfaces(product: dict) -> dict | None:
    sku = product["sku"]
    name = product.get("name", sku)
    features = json.loads(product.get("features") or "[]")
    in_sigs = json.loads(product.get("input_signals") or "[]")
    out_sigs = json.loads(product.get("output_signals") or "[]")
    description = product.get("description") or ""
    what_it_does = product.get("what_it_does") or ""
    chroma_chunks = get_chroma_chunks(sku)

    user_content = f"""Product: {name} (SKU: {sku})

What it does: {what_it_does}

Input signals (from DB): {in_sigs}
Output signals (from DB): {out_sigs}

Features:
{chr(10).join(f'- {f}' for f in features)}

Description:
{description[:2000]}

{"Manual/spec excerpts:" + chr(10) + chroma_chunks[:3000] if chroma_chunks else ""}
""".strip()

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw)
        return data
    except Exception as e:
        print(f"  [error] {sku}: {e}")
        return None


def flatten_for_db(sku: str, data: dict) -> dict:
    """Convert extracted JSON to flat DB row."""
    ports = data.get("ports_json", {})
    inputs = data.get("inputs_json", [])
    outputs = data.get("outputs_json", [])

    row = {
        "sku": sku,
        "primary_fn": data.get("primary_fn"),
        "secondary_fns": json.dumps(data.get("secondary_fns", [])),
        "form_factor": data.get("form_factor"),
        "use_case_tags": json.dumps(data.get("use_case_tags", [])),

        "out_hdmi": int(data.get("out_hdmi", 0)),
        "out_hdmi_count": int(data.get("out_hdmi_count", 0)),
        "out_hdmi_ver": data.get("out_hdmi_ver"),
        "out_sdi": int(data.get("out_sdi", 0)),
        "out_sdi_count": int(data.get("out_sdi_count", 0)),
        "out_sdi_ver": data.get("out_sdi_ver"),
        "out_ndi": int(data.get("out_ndi", 0)),
        "out_usb_video": int(data.get("out_usb_video", 0)),
        "out_dante": int(data.get("out_dante", 0)),
        "out_hdbaset": int(data.get("out_hdbaset", 0)),
        "out_fiber": int(data.get("out_fiber", 0)),
        "out_vga": int(data.get("out_vga", 0)),
        "out_displayport": int(data.get("out_displayport", 0)),
        "out_ip_stream": int(data.get("out_ip_stream", 0)),

        "in_hdmi": int(data.get("in_hdmi", 0)),
        "in_hdmi_count": int(data.get("in_hdmi_count", 0)),
        "in_hdmi_ver": data.get("in_hdmi_ver"),
        "in_sdi": int(data.get("in_sdi", 0)),
        "in_sdi_count": int(data.get("in_sdi_count", 0)),
        "in_ndi": int(data.get("in_ndi", 0)),
        "in_usb_video": int(data.get("in_usb_video", 0)),
        "in_dante": int(data.get("in_dante", 0)),
        "in_hdbaset": int(data.get("in_hdbaset", 0)),
        "in_fiber": int(data.get("in_fiber", 0)),
        "in_vga": int(data.get("in_vga", 0)),
        "in_displayport": int(data.get("in_displayport", 0)),
        "in_ip_stream": int(data.get("in_ip_stream", 0)),

        "max_res": data.get("max_res"),
        "supports_4k": int(data.get("supports_4k", 0)),
        "supports_8k": int(data.get("supports_8k", 0)),
        "supports_hdr": int(data.get("supports_hdr", 0)),

        "audio_embed_in": int(data.get("audio_embed_in", 0)),
        "audio_embed_out": int(data.get("audio_embed_out", 0)),
        "audio_analog_in": int(data.get("audio_analog_in", 0)),
        "audio_deembed": int(data.get("audio_deembed", 0)),

        "ctrl_ip": int(data.get("ctrl_ip", 0)),
        "ctrl_rs232": int(data.get("ctrl_rs232", 0)),
        "ctrl_rs422": int(data.get("ctrl_rs422", 0)),
        "ctrl_ir": int(data.get("ctrl_ir", 0)),
        "ctrl_visca": int(data.get("ctrl_visca", 0)),
        "ctrl_pelco": int(data.get("ctrl_pelco", 0)),
        "ctrl_front": int(data.get("ctrl_front", 0)),
        "ctrl_api": int(data.get("ctrl_api", 0)),

        "poe": int(data.get("poe", 0)),
        "poe_out": int(data.get("poe_out", 0)),

        "zoom_optical": int(data.get("zoom_optical", 0)),
        "has_tally": int(data.get("has_tally", 0)),
        "has_autotrack": int(data.get("has_autotrack", 0)),
        "has_recording": int(data.get("has_recording", 0)),

        "ports_json": json.dumps(ports),
        "inputs_json": json.dumps(inputs),
        "outputs_json": json.dumps(outputs),
        "notes": data.get("notes"),
        "confidence": float(data.get("confidence", 0.8)),
        "extracted_at": datetime.utcnow().isoformat(),
    }
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sku", help="Extract only this SKU")
    parser.add_argument("--limit", type=int, help="Max products to process")
    parser.add_argument("--overwrite", action="store_true",
                        help="Re-extract already processed SKUs")
    parser.add_argument("--category", help="Filter by product category")
    args = parser.parse_args()

    init_interfaces_table()

    conn = get_conn()
    conn.row_factory = None  # plain tuples
    if args.sku:
        cur = conn.execute(
            "SELECT * FROM products WHERE id=?", (args.sku,)
        )
    else:
        q = "SELECT * FROM products WHERE stock_status != 'Discontinued'"
        params = []
        if args.category:
            q += " AND category LIKE ?"
            params.append(f"%{args.category}%")
        if not args.overwrite:
            q += " AND id NOT IN (SELECT sku FROM product_interfaces)"
        if args.limit:
            q += f" LIMIT {args.limit}"
        cur = conn.execute(q, params)
    col_names = [d[0] for d in cur.description]
    rows = cur.fetchall()
    # normalize: expose 'sku' as alias for 'id'
    products = [dict(zip(col_names, r)) for r in rows]
    for p in products:
        p.setdefault("sku", p.get("id"))
    conn.close()

    print(f"Processing {len(products)} products...")
    ok = fail = 0

    for i, product in enumerate(products, 1):
        sku = product["sku"]
        name = product.get("name", sku)
        print(f"[{i}/{len(products)}] {sku} — {name[:60]}", end=" ... ", flush=True)

        extracted = extract_interfaces(product)
        if extracted is None:
            print("FAILED")
            fail += 1
            continue

        row = flatten_for_db(sku, extracted)
        upsert_interface(row)
        print(f"OK  ({extracted.get('primary_fn','?')}, conf={extracted.get('confidence',0):.2f})")
        ok += 1

        if i % 20 == 0:
            time.sleep(1)  # gentle rate limit

    print(f"\nDone: {ok} OK, {fail} failed out of {len(products)} total.")

    if args.sku and ok:
        conn2 = get_conn()
        conn2.row_factory = None
        cur2 = conn2.execute(
            "SELECT * FROM product_interfaces WHERE sku=?", (args.sku,)
        )
        row2 = cur2.fetchone()
        if row2:
            record = dict(zip([d[0] for d in cur2.description], row2))
            print("\nExtracted record:")
            for k, v in record.items():
                if v not in (None, 0, "[]", "{}"):
                    print(f"  {k}: {v}")
        conn2.close()


if __name__ == "__main__":
    main()
