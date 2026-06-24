"""
Signal chain assembly and compatibility checking.
Builds source->switcher->extender->display chains and verifies each link.
"""
import json
from .db import get_conn, row_to_dict
from .models import Product

# ─── Signal compatibility rules ───────────────────────────────────────────────

# Bandwidth each signal type can carry (Gbps)
SIGNAL_BANDWIDTH = {
    "HDMI 2.1": 48.0,
    "HDMI 2.0": 18.0,
    "HDMI 1.4": 10.2,
    "HDMI":     10.2,
    "HDBaseT":  10.2,
    "DisplayPort": 32.4,
    "USB-C":    40.0,
    "SDI":       3.0,
    "Fiber":    48.0,
    "Dante":     1.0,
}

# Minimum bandwidth needed for each resolution
RESOLUTION_BANDWIDTH = {
    "720p":    1.5,
    "1080p":   3.0,
    "1080p60": 6.0,
    "4K30":    9.0,
    "4K60":   18.0,
    "4K120":  40.0,
    "8K30":   24.0,
    "8K60":   48.0,
}

# Which signals can pass through each other (direct connection possible)
COMPATIBLE_PAIRS = {
    ("HDMI 2.1", "HDMI 2.0"), ("HDMI 2.1", "HDMI 1.4"), ("HDMI 2.1", "HDMI"),
    ("HDMI 2.0", "HDMI 1.4"), ("HDMI 2.0", "HDMI"),
    ("HDMI 1.4", "HDMI"),
    ("HDBaseT", "HDBaseT"),
    ("Fiber", "Fiber"),
    ("SDI", "SDI"),
    ("DisplayPort", "DisplayPort"),
    ("USB-C", "USB-C"),
}

def signals_compatible(out_signals: list[str], in_signals: list[str]) -> tuple[bool, list[str]]:
    """Check if any output signal can connect to any input signal. Returns (ok, matched_pairs)."""
    matches = []
    for o in out_signals:
        for i in in_signals:
            if o == i:
                matches.append(f"{o}")
            elif (o, i) in COMPATIBLE_PAIRS or (i, o) in COMPATIBLE_PAIRS:
                matches.append(f"{o}->{i}")
    return bool(matches), matches

def signal_bandwidth(signals: list[str]) -> float:
    """Max bandwidth supported by a list of signals."""
    return max((SIGNAL_BANDWIDTH.get(s, 0) for s in signals), default=0)

def check_resolution_support(signals: list[str], resolution: str) -> bool:
    needed = RESOLUTION_BANDWIDTH.get(resolution, 0)
    available = signal_bandwidth(signals)
    return available >= needed


# ─── Chain templates ──────────────────────────────────────────────────────────

CHAIN_TEMPLATES = {
    "switcher_direct": {
        "description": "Sources -> Matrix Switcher -> Displays (short runs, <5m)",
        "roles": ["switcher"],
        "use_when": "max_distance_m <= 5 or max_distance_m is None",
    },
    "switcher_extender": {
        "description": "Sources -> Matrix Switcher -> HDBaseT Extenders -> Displays (up to 150m)",
        "roles": ["switcher", "extender"],
        "use_when": "max_distance_m > 5",
    },
    "switcher_da": {
        "description": "Sources -> Switcher -> Distribution Amp -> Multiple Displays",
        "roles": ["switcher", "distribution_amp"],
        "use_when": "num_outputs > switcher.outputs",
    },
    "av_over_ip": {
        "description": "Sources -> Encoders -> IP Network -> Decoders -> Displays (unlimited distance)",
        "roles": ["av_over_ip"],
        "use_when": "max_distance_m > 150 or num_outputs > 16",
    },
    "da_only": {
        "description": "Single Source -> Distribution Amp -> Multiple Displays",
        "roles": ["distribution_amp"],
        "use_when": "num_inputs == 1",
    },
    "camera_system": {
        "description": "PTZ Cameras -> Switcher/Encoder -> Display/Stream",
        "roles": ["camera"],
        "use_when": "category_hint == camera",
    },
}


# ─── Chain builder ────────────────────────────────────────────────────────────

def build_chain(session: dict) -> dict:
    """
    Given session state, determine the right chain topology and find products for each role.
    Returns a chain dict with products per role and compatibility check results.
    """
    num_inputs   = session.get("num_inputs")
    num_outputs  = session.get("num_outputs")
    distance     = session.get("max_distance_m") or 0
    resolution   = session.get("resolution")
    category     = session.get("category_hint")
    signal_type  = (session.get("signal_type") or "").upper()

    # Pick template
    if category == "camera":
        template_key = "camera_system"
    elif category in ("av_over_ip",) or distance > 150 or (num_outputs and num_outputs > 16):
        template_key = "av_over_ip"
    elif distance > 5:
        template_key = "switcher_extender"
    elif num_inputs == 1:
        template_key = "da_only"
    else:
        template_key = "switcher_direct"

    template = CHAIN_TEMPLATES[template_key]
    chain = {
        "template": template_key,
        "description": template["description"],
        "roles": {},
        "links": [],
        "issues": [],
    }

    conn = get_conn()

    for role in template["roles"]:
        conditions = ["category = ?"]
        params = [role]

        if role == "switcher":
            if num_inputs:
                conditions.append("(inputs IS NULL OR inputs >= ?)")
                params.append(num_inputs)
            if num_outputs:
                conditions.append("(outputs IS NULL OR outputs >= ?)")
                params.append(num_outputs)
            if resolution:
                conditions.append('(resolutions LIKE ? OR resolutions IS NULL OR resolutions = "[]")')
                params.append(f'%"{resolution}"%')

        elif role == "extender":
            if distance:
                conditions.append("(max_distance_m IS NULL OR max_distance_m >= ?)")
                params.append(distance)
            if resolution:
                conditions.append('(resolutions LIKE ? OR resolutions IS NULL OR resolutions = "[]")')
                params.append(f'%"{resolution}"%')

        elif role == "distribution_amp":
            if num_outputs:
                conditions.append("(outputs IS NULL OR outputs >= ?)")
                params.append(num_outputs)

        elif role == "av_over_ip":
            if resolution:
                conditions.append('(resolutions LIKE ? OR resolutions IS NULL OR resolutions = "[]")')
                params.append(f'%"{resolution}"%')

        elif role == "camera":
            # Filter by signal type if specified (e.g. SDI, NDI, HDMI)
            if signal_type:
                conditions.append(
                    "(output_signals LIKE ? OR input_signals LIKE ? "
                    "OR output_signals IS NULL OR output_signals = '[]')"
                )
                params.extend([f'%{signal_type}%', f'%{signal_type}%'])
            if resolution:
                conditions.append('(resolutions LIKE ? OR resolutions IS NULL OR resolutions = "[]")')
                params.append(f'%"{resolution}"%')

        where = " AND ".join(conditions)
        rows = conn.execute(f"SELECT * FROM products WHERE {where} ORDER BY id LIMIT 4", params).fetchall()
        chain["roles"][role] = [Product(**row_to_dict(r)) for r in rows]

    conn.close()

    # Check signal compatibility between adjacent roles in chain
    roles = template["roles"]
    for i in range(len(roles) - 1):
        role_a = roles[i]
        role_b = roles[i + 1]
        products_a = chain["roles"].get(role_a, [])
        products_b = chain["roles"].get(role_b, [])

        if not products_a or not products_b:
            chain["issues"].append(f"No products found for role: {role_a if not products_a else role_b}")
            continue

        # Check first candidate of each role
        a = products_a[0]
        b = products_b[0]
        ok, matches = signals_compatible(a.output_signals, b.input_signals)

        chain["links"].append({
            "from": a.id,
            "to": b.id,
            "compatible": ok,
            "signal": matches[0] if matches else "unknown",
            "note": f"{a.id} output -> {b.id} input" + (f" via {matches[0]}" if matches else " — signal mismatch!"),
        })

        if not ok:
            chain["issues"].append(
                f"Signal mismatch: {a.id} outputs {a.output_signals} but {b.id} needs {b.input_signals}"
            )

    return chain


def chain_to_text(chain: dict) -> str:
    """Serialise chain for inclusion in LLM context."""
    lines = [f"Signal chain: {chain['description']}", ""]

    for role, products in chain["roles"].items():
        if products:
            p = products[0]
            specs = []
            if p.inputs and p.outputs: specs.append(f"{p.inputs}×{p.outputs}")
            if p.max_distance_m: specs.append(f"{p.max_distance_m}m")
            if p.resolutions: specs.append("/".join(p.resolutions[:2]))
            lines.append(f"  [{role.upper()}] {p.id}  ({', '.join(specs)})")
            for alt in products[1:]:
                lines.append(f"     alt: {alt.id}")

    if chain["links"]:
        lines.append("")
        lines.append("Compatibility checks:")
        for link in chain["links"]:
            icon = "OK" if link["compatible"] else "FAIL"
            lines.append(f"  [{icon}] {link['note']}")

    if chain["issues"]:
        lines.append("")
        lines.append("Issues:")
        for issue in chain["issues"]:
            lines.append(f"  WARNING: {issue}")

    return "\n".join(lines)
