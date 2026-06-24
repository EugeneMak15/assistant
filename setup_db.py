"""
BZB Gear Products Database Setup
Parses 223 DOCX manuals -> extracts product specs via regex -> stores in SQLite
No API key required.
"""

import re
import sqlite3
from pathlib import Path
from docx import Document
from rich.console import Console
from rich.table import Table
from rich.progress import track

console = Console()
MANUALS_DIR = Path("./manuals")
DB_PATH = "./products.db"

# ─── Category detection from filename / content ───────────────────────────────

def detect_category(product_id: str, text: str = "") -> str:
    """Classify product by ID first (reliable), then fall back to text hints."""
    pid = product_id.upper()

    # AV over IP — check first (IPGEAR contains no other ambiguity)
    if re.search(r"IPGEAR", pid): return "av_over_ip"

    # Cables / fiber kits
    if re.search(r"(UM44|UM88|UM-88|SMB-[45]M)", pid): return "cable_kit"

    # USB extenders
    if re.search(r"USB", pid): return "usb_extender"

    # Extenders / HDBaseT / fiber (before switcher — EXH comes before xMA)
    if re.search(r"(EXH|EXD|EXHD|EXUF|EXHKVM|EXT-H|UDA-E\d|HDA-E\d|UDAIC)", pid): return "extender"

    # Distribution amplifiers / splitters
    if re.search(r"(-DA-|-DA[0-9]|DA1X|DA2X|8K-DA|3GS1[0-9]|12GCS|FES12|H3GS)", pid): return "distribution_amp"

    # PTZ Cameras
    if re.search(r"(PTZ|CYCLOPS|ADAMO|PACKSHOT|BPTZ|UPTZ|EPTZ|VPTZ)", pid): return "camera"

    # KVM switches
    if re.search(r"KVM", pid): return "kvm_switch"

    # Video wall controllers / multiviewers
    if re.search(r"(VW[P0-9]|-VWP|-QVP|QUADFUSION|MVS[0-9]|MV41|BZ-MVS|BZ-MVS)", pid): return "multiviewer"

    # Presentation switchers / scalers
    if re.search(r"(PSC[0-9]|PS[24][15]|PSB|HDVS|MFVS|BYOD)", pid): return "presentation_switcher"

    # Encoders / streamers
    if re.search(r"(STREAM|AIR4KAST|AVENTO)", pid): return "encoder_decoder"

    # Pattern / test generators
    if re.search(r"(AVTPG|SDITPG)", pid): return "signal_generator"

    # Audio
    if re.search(r"(AMP[0-9C]|AU88|AUD-|OMNITALK|MIC-|SPEAKP|AMPC)", pid): return "audio"

    # SDI / capture
    if re.search(r"(3GS[0-9]|12GCS|CSA|BSHA|BSHAN|BG-CHA|C2HA|AEE|SAVS|HAVS|CAP-|CAPTURE)", pid, re.IGNORECASE): return "sdi"

    # Matrix switchers — explicit MA/MX suffix or known switcher models
    if re.search(r"(-[0-9]+MA$|-[0-9]+M$|MX44|MX88|A88M|A1616|4K-VP|8K-VP|UHD-SC|4K-HS|8K-HS|4KSH|4KHS|8K-SA|8K-AA|8K-AD|8K-AE|MKVM|HDVS42|AU88-MA|-44M$|-88M$)", pid): return "switcher"

    # Fallback: scan first 300 chars of text
    snippet = text[:300].lower()
    if "matrix" in snippet or "switcher" in snippet: return "switcher"
    if "extender" in snippet or "hdbaset" in snippet: return "extender"
    if "camera" in snippet or "ptz" in snippet: return "camera"
    if "distribution" in snippet or "splitter" in snippet: return "distribution_amp"

    return "other"


# ─── Spec extraction from DOCX text ──────────────────────────────────────────

def extract_text(path: Path) -> str:
    try:
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        console.print(f"[red]Error reading {path.name}: {e}[/red]")
        return ""


def parse_int_list(patterns: list[str], text: str) -> list[int]:
    results = set()
    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            try:
                results.add(int(m.group(1)))
            except (IndexError, ValueError):
                pass
    return sorted(results)


SANE_PORT_RANGE = (1, 64)  # realistic for AV gear

def parse_nx_inputs(text: str) -> list[int]:
    """Extract N from NxM patterns like '8x8', '4x4', '16x16'."""
    results = []
    for m in re.finditer(r"\b(\d{1,2})\s*[xX×]\s*\d{1,2}\b", text):
        n = int(m.group(1))
        if SANE_PORT_RANGE[0] <= n <= SANE_PORT_RANGE[1]:
            results.append(n)
    return results

def parse_nx_outputs(text: str) -> list[int]:
    """Extract M from NxM patterns."""
    results = []
    for m in re.finditer(r"\b\d{1,2}\s*[xX×]\s*(\d{1,2})\b", text):
        n = int(m.group(1))
        if SANE_PORT_RANGE[0] <= n <= SANE_PORT_RANGE[1]:
            results.append(n)
    return results


def parse_inputs(text: str) -> int | None:
    # NxM format is most reliable for AV gear (e.g. "8x8 matrix", "4x4 switcher")
    nx = parse_nx_inputs(text)
    explicit = parse_int_list([
        r"(\d+)\s*HDMI\s+inputs?",
        r"(\d+)\s*input\s+ports?",
        r"(?:^|\n|\r)[ \t]*inputs?\s*[:\-]\s*(\d+)",
        r"(\d+)\s*[-–]\s*in\b",
        r"(\d+)\s*input\s+channels?",
        r"up\s+to\s+(\d+)\s+(?:HDMI\s+)?sources?",
    ], text)
    explicit = [n for n in explicit if SANE_PORT_RANGE[0] <= n <= SANE_PORT_RANGE[1]]
    all_nums = nx + explicit
    return max(all_nums) if all_nums else None


def parse_outputs(text: str) -> int | None:
    nx = parse_nx_outputs(text)
    explicit = parse_int_list([
        r"(\d+)\s*HDMI\s+outputs?",
        r"(\d+)\s*output\s+ports?",
        r"(?:^|\n|\r)[ \t]*outputs?\s*[:\-]\s*(\d+)",
        r"(\d+)\s*[-–]\s*out\b",
        r"(\d+)\s*output\s+channels?",
        r"up\s+to\s+(\d+)\s+(?:HDMI\s+)?displays?",
    ], text)
    explicit = [n for n in explicit if SANE_PORT_RANGE[0] <= n <= SANE_PORT_RANGE[1]]
    all_nums = nx + explicit
    return max(all_nums) if all_nums else None


def parse_resolutions(text: str) -> list[str]:
    found = set()
    patterns = [
        (r"8K\s*(?:@\s*)?(?:60|30)", lambda m: "8K60" if "60" in m.group() else "8K30"),
        (r"8K(?!\d)", lambda m: "8K30"),
        (r"4K\s*(?:@\s*)?120", lambda m: "4K120"),
        (r"4K\s*(?:@\s*)?60", lambda m: "4K60"),
        (r"4K\s*(?:@\s*)?30", lambda m: "4K30"),
        (r"4K(?!\d)", lambda m: "4K30"),
        (r"1080[pi]?\s*(?:@\s*)?(?:60|50)", lambda m: "1080p60"),
        (r"1080[pi](?!\d)", lambda m: "1080p"),
        (r"720[pi]", lambda m: "720p"),
    ]
    for pattern, label_fn in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            found.add(label_fn(m))
    return sorted(found, key=lambda x: ["720p","1080p","1080p60","4K30","4K60","4K120","8K30","8K60"].index(x) if x in ["720p","1080p","1080p60","4K30","4K60","4K120","8K30","8K60"] else 99)


def parse_signals(text: str) -> tuple[list[str], list[str]]:
    signal_map = {
        "HDMI 2.1": r"HDMI\s*2\.1",
        "HDMI 2.0": r"HDMI\s*2\.0",
        "HDMI 1.4": r"HDMI\s*1\.4",
        "HDMI": r"\bHDMI\b",
        "HDBaseT": r"HDBaseT",
        "DisplayPort": r"DisplayPort|DP\b",
        "SDI": r"\bSDI\b",
        "VGA": r"\bVGA\b",
        "USB-C": r"USB[-\s]?C\b|Type[-\s]C",
        "Fiber": r"\bfiber\b|\boptical\b",
        "Dante": r"\bDante\b",
    }
    inputs_found = set()
    outputs_found = set()

    for sig, pattern in signal_map.items():
        if re.search(pattern, text, re.IGNORECASE):
            inputs_found.add(sig)
            outputs_found.add(sig)

    # Simplify: if HDMI 2.0 found, drop generic HDMI
    for spec in ["HDMI 2.1", "HDMI 2.0", "HDMI 1.4"]:
        if spec in inputs_found and "HDMI" in inputs_found:
            inputs_found.discard("HDMI")
            outputs_found.discard("HDMI")

    return sorted(inputs_found), sorted(outputs_found)


def parse_max_distance(text: str) -> int | None:
    nums = []
    for m in re.finditer(r"(\d+)\s*m(?:eters?|etres?)?\b", text, re.IGNORECASE):
        v = int(m.group(1))
        if 10 <= v <= 500:
            nums.append(v)
    # Also look for feet and convert
    for m in re.finditer(r"(\d+)\s*(?:ft|feet)\b", text, re.IGNORECASE):
        v = int(int(m.group(1)) * 0.3048)
        if 10 <= v <= 500:
            nums.append(v)
    return max(nums) if nums else None


def parse_bandwidth(text: str) -> float | None:
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*Gbps", text, re.IGNORECASE):
        v = float(m.group(1))
        if 1 <= v <= 200:
            return v
    return None


def extract_product_id(filename: str) -> str:
    name = Path(filename).stem
    # Remove common suffixes
    name = re.sub(r"\s*(User\s+)?Manual.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*(User\s+)?Guide.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+Manual_.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+v\d+.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"^Copy of\s+", "", name, flags=re.IGNORECASE)
    name = re.sub(r"^V\.\d+\s+", "", name, flags=re.IGNORECASE)
    # Extract BG-XXX or BZ-XXX or BZB-XXX pattern
    m = re.match(r"(B[GZB][-\w]+)", name, re.IGNORECASE)
    if m:
        return m.group(1).strip().upper()
    # Fallback: use cleaned name
    return name.strip().upper()


# ─── Database setup ───────────────────────────────────────────────────────────

def create_db(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        inputs INTEGER,
        outputs INTEGER,
        input_signals TEXT,      -- JSON array
        output_signals TEXT,     -- JSON array
        resolutions TEXT,        -- JSON array
        max_bandwidth_gbps REAL,
        max_distance_m INTEGER,
        manual_file TEXT,
        notes TEXT
    );
    """)
    conn.commit()


# SKUs that must never be imported or re-added to the catalog
_PRODUCT_BLACKLIST = {
    # Adamo-31 (31x zoom variant discontinued by BZB)
    "BG-ADAMO-4K12X-B-31", "BG-ADAMO-4K12X-W-31",
    "BG-ADAMO-4K25X-B-31", "BG-ADAMO-4K25X-W-31",
    "BG-ADAMO-4K31X-B-31", "BG-ADAMO-4K31X-W-31",
    "BG-ADAMO-4KDA12X-B-31", "BG-ADAMO-4KDA12X-W-31",
    "BG-ADAMO-4KDA25X-B-31", "BG-ADAMO-4KDA25X-W-31",
    "BG-ADAMO-4KDA31X-B-31", "BG-ADAMO-4KDA31X-W-31",
    "BG-ADAMO-4KND12X-B-31", "BG-ADAMO-4KND12X-W-31",
    "BG-ADAMO-4KND25X-B-31", "BG-ADAMO-4KND25X-W-31",
    "BG-ADAMO-4KND31X-B-31", "BG-ADAMO-4KND31X-W-31",
}


def upsert_product(conn: sqlite3.Connection, data: dict):
    if data.get("id", "").upper() in _PRODUCT_BLACKLIST:
        return  # silently skip blacklisted products
    import json
    conn.execute("""
    INSERT INTO products (id, name, category, inputs, outputs,
        input_signals, output_signals, resolutions,
        max_bandwidth_gbps, max_distance_m, manual_file, notes)
    VALUES (:id, :name, :category, :inputs, :outputs,
        :input_signals, :output_signals, :resolutions,
        :max_bandwidth_gbps, :max_distance_m, :manual_file, :notes)
    ON CONFLICT(id) DO UPDATE SET
        category=excluded.category,
        inputs=excluded.inputs,
        outputs=excluded.outputs,
        input_signals=excluded.input_signals,
        output_signals=excluded.output_signals,
        resolutions=excluded.resolutions,
        max_bandwidth_gbps=excluded.max_bandwidth_gbps,
        max_distance_m=excluded.max_distance_m,
        manual_file=excluded.manual_file,
        notes=excluded.notes
    """, {
        **data,
        "input_signals": json.dumps(data.get("input_signals", [])),
        "output_signals": json.dumps(data.get("output_signals", [])),
        "resolutions": json.dumps(data.get("resolutions", [])),
    })


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    import json

    console.print("[bold green]BZB Gear — Products DB Setup[/bold green]")
    console.print(f"Scanning: {MANUALS_DIR.resolve()}\n")

    conn = sqlite3.connect(DB_PATH)
    create_db(conn)

    files = sorted(MANUALS_DIR.glob("*.docx"))
    # Skip duplicates
    files = [f for f in files if not re.search(r"\(\d+\)", f.name) and not f.name.startswith("Copy of")]

    parsed = []
    skipped = []

    for path in track(files, description="Parsing manuals..."):
        product_id = extract_product_id(path.name)
        text = extract_text(path)

        if not text:
            skipped.append(path.name)
            continue

        inputs = parse_inputs(text)
        outputs = parse_outputs(text)
        resolutions = parse_resolutions(text)
        in_sigs, out_sigs = parse_signals(text)
        distance = parse_max_distance(text)
        bandwidth = parse_bandwidth(text)
        category = detect_category(product_id, text)

        # Extenders are always 1-in / 1-out point-to-point by design
        if category == "extender":
            inputs = inputs or 1
            outputs = outputs or 1

        data = {
            "id": product_id,
            "name": product_id,
            "category": category,
            "inputs": inputs,
            "outputs": outputs,
            "input_signals": in_sigs,
            "output_signals": out_sigs,
            "resolutions": resolutions,
            "max_bandwidth_gbps": bandwidth,
            "max_distance_m": distance,
            "manual_file": path.name,
            "notes": None,
        }
        upsert_product(conn, data)
        parsed.append(data)

    conn.commit()
    conn.close()

    console.print(f"\n[bold green]Done! {len(parsed)} products inserted, {len(skipped)} skipped[/bold green]")
    console.print(f"Database: {DB_PATH}\n")

    # Summary table
    from collections import Counter
    cats = Counter(p["category"] for p in parsed)
    t = Table(title="Products by category")
    t.add_column("Category"); t.add_column("Count", justify="right")
    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
        t.add_row(cat, str(cnt))
    console.print(t)

    # Spot-check a few
    console.print("\n[bold]Sample parsed specs:[/bold]")
    sample = [p for p in parsed if p["inputs"] and p["outputs"]][:8]
    t2 = Table()
    t2.add_column("Product"); t2.add_column("Cat"); t2.add_column("In"); t2.add_column("Out"); t2.add_column("Resolutions"); t2.add_column("Dist m")
    for p in sample:
        t2.add_row(
            p["id"], p["category"],
            str(p["inputs"] or ""), str(p["outputs"] or ""),
            ", ".join(json.loads(p["resolutions"]) if isinstance(p["resolutions"], str) else p["resolutions"]),
            str(p["max_distance_m"] or ""),
        )
    console.print(t2)


if __name__ == "__main__":
    main()
