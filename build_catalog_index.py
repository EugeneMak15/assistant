"""
Build a compact, LLM-readable index of all 429 products.
Output: catalog_index.txt — fits in one LLM context window (~12k tokens).

Format per product:
  SKU | title | signals_in→signals_out | resolution | distance | I/O | one-line description

Grouped by category with headers.
Run: python build_catalog_index.py
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3, json
from pathlib import Path
from collections import defaultdict

DB_PATH  = "./products.db"
OUT_PATH = "./catalog_index.txt"

CATEGORY_HEADERS = {
    "camera":                "## PTZ & Video Cameras",
    "switcher":              "## Matrix & Video Switchers",
    "extender":              "## Signal Extenders (HDBaseT / Fiber / Wireless)",
    "distribution_amp":      "## Splitters & Distribution Amplifiers",
    "av_over_ip":            "## AV Over IP (Encoders/Decoders/Controllers)",
    "encoder_decoder":       "## Stream Encoders & Decoders",
    "sdi":                   "## SDI Equipment & Converters",
    "kvm_switch":            "## KVM Switches",
    "multiviewer":           "## Multiviewers & Video Walls",
    "presentation_switcher": "## Presentation Switchers",
    "controller":            "## PTZ Camera Controllers",
    "capture":               "## Capture Cards & Converters",
    "audio":                 "## Audio Equipment",
    "network":               "## Network Switches (AV-optimized)",
    "integration":           "## Integration & Control Tools",
    "usb_extender":          "## USB Extenders",
    "videobar":              "## Videobars (All-in-one conferencing)",
    "medical_cart":          "## Medical Carts",
    "signal_generator":      "## Signal Generators & Analyzers",
    "cable_kit":             "## Cables & Fiber Kits",
    "accessory":             "## Accessories & Mounts",
    "bundle":                "## Complete System Bundles",
}

CAT_ORDER = list(CATEGORY_HEADERS.keys())


def compact_signals(sigs: list[str]) -> str:
    if not sigs:
        return "—"
    # Shorten common signal names
    mapping = {
        "HDMI 2.1": "HDMI2.1", "HDMI 2.0": "HDMI2.0", "HDMI 1.4": "HDMI1.4",
        "HDMI": "HDMI", "12G-SDI": "12G-SDI", "SDI": "SDI", "NDI": "NDI",
        "HDBaseT": "HDBaseT", "DisplayPort": "DP", "USB-C": "USB-C",
        "Fiber": "Fiber", "Dante": "Dante", "USB": "USB",
    }
    return "+".join(mapping.get(s, s) for s in sigs[:4])


def compact_res(res: list[str]) -> str:
    if not res:
        return ""
    # Show highest resolution only
    order = ["8K60","8K30","4K120","4K60","4K30","1080p60","1080p","720p"]
    for r in order:
        if r in res:
            return r
    return res[-1]


# Keywords that signal a product covers multiple roles
MULTI_ROLE_SIGNALS = {
    "multiviewer":              "ROLES: multiviewer+monitor",
    "multi-viewer":             "ROLES: multiviewer+monitor",
    "production switcher":      "ROLES: production-switcher",
    "video switcher":           "ROLES: production-switcher",
    "switcher/joystick":        "ROLES: production-switcher+ptz-controller",
    "switcher and joystick":    "ROLES: production-switcher+ptz-controller",
    "switcher and ptz":         "ROLES: production-switcher+ptz-controller",
    "joystick controller combo":"ROLES: production-switcher+ptz-controller",
    "joystick":                 "ROLES: ptz-controller+joystick",
    "ptz controller":           "ROLES: ptz-controller",
    "preview":                  "ROLES: includes-preview",
    "tally":                    "ROLES: includes-tally",
    "encoder":                  "ROLES: encoder+streamer",
    "streaming":                "ROLES: includes-streaming",
    "record":                   "ROLES: includes-recording",
    "video wall":               "ROLES: switcher+videowall",
    "audio embed":              "ROLES: includes-audio-embed",
    "audio mix":                "ROLES: includes-audio-mix",
    "ndi":                      "ROLES: includes-ndi",
}


def detect_roles(p: dict) -> list[str]:
    """Detect which roles this product covers based on description and features."""
    text = " ".join([
        (p.get("what_it_does") or ""),
        (p.get("use_cases") or ""),
        (p.get("title") or ""),
        (p.get("name") or ""),
    ]).lower()

    found = set()
    for keyword, role in MULTI_ROLE_SIGNALS.items():
        if keyword in text:
            found.add(role)
    return sorted(found)


def product_line(p: dict) -> str:
    ins  = json.loads(p.get("input_signals")  or "[]")
    outs = json.loads(p.get("output_signals") or "[]")
    res  = json.loads(p.get("resolutions")    or "[]")

    sig_in  = compact_signals(ins)
    sig_out = compact_signals(outs)
    sig_str = sig_in if sig_in == sig_out else f"{sig_in}→{sig_out}"

    parts = [p["id"].ljust(32)]

    if p.get("inputs") and p.get("outputs"):
        parts.append(f"{p['inputs']}×{p['outputs']}")
    elif p.get("inputs"):
        parts.append(f"{p['inputs']}in")
    elif p.get("outputs"):
        parts.append(f"{p['outputs']}out")

    if sig_str and sig_str != "—":
        parts.append(sig_str)

    r = compact_res(res)
    if r:
        parts.append(r)

    if p.get("max_distance_m"):
        parts.append(f"{p['max_distance_m']}m")

    desc = p.get("what_it_does") or ""
    if desc:
        first = desc.split(".")[0].strip()
        if len(first) > 90:
            first = first[:90] + "…"
        parts.append(f"| {first}")

    # Multi-role tag — shown inline so LLM notices it immediately
    roles = detect_roles(p)
    if len(roles) >= 2:
        parts.append(f"[MULTI:{'+'.join(r.split(':')[1] for r in roles[:3])}]")

    return "  " + "  ".join(parts)


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM products WHERE (site_category IS NULL OR site_category != 'Discontinued') ORDER BY category, id"
    ).fetchall()
    conn.close()

    products = [dict(r) for r in rows]
    by_cat = defaultdict(list)
    for p in products:
        by_cat[p["category"]].append(p)

    lines = [
        "# BZB GEAR — COMPLETE PRODUCT CATALOG INDEX",
        f"# {len(products)} products across {len(by_cat)} categories",
        "# Format: SKU  [I/O]  [signals]  [max_res]  [distance]  | description",
        "",
    ]

    for cat in CAT_ORDER:
        prods = by_cat.get(cat, [])
        if not prods:
            continue
        header = CATEGORY_HEADERS.get(cat, f"## {cat}")
        lines.append(header)
        lines.append(f"# {len(prods)} products")
        for p in prods:
            lines.append(product_line(p))
        lines.append("")

    # Any categories not in CAT_ORDER
    for cat, prods in by_cat.items():
        if cat not in CAT_ORDER:
            lines.append(f"## {cat}")
            for p in prods:
                lines.append(product_line(p))
            lines.append("")

    text = "\n".join(lines)
    Path(OUT_PATH).write_text(text, encoding="utf-8")

    # Stats
    tokens_est = len(text) // 4
    print(f"Written: {OUT_PATH}")
    print(f"Lines:   {len(lines)}")
    print(f"Chars:   {len(text):,}")
    print(f"Tokens:  ~{tokens_est:,} (estimated)")
    print()
    print("Preview (first 20 lines):")
    for l in lines[:20]:
        print(l)


if __name__ == "__main__":
    main()
