"""
Final BZB Gear product import from product feed.
429 products with full specs, features, descriptions, prices.
Categories inferred from title + URL + category page mapping.
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import re, json, sqlite3
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

import truststore; truststore.inject_into_ssl()
import requests
from rich.console import Console
from rich.progress import track

console = Console()
DB_PATH = "./products.db"

# ─── Category inference from title + URL ─────────────────────────────────────

TITLE_PATTERNS = [
    # Most specific first
    (r"medical cart",                           "medical_cart"),
    (r"video ?bar",                             "videobar"),
    (r"network switch|managed switch",          "network"),
    (r"joystick controller|ptz controller",     "controller"),
    (r"av.over.ip|ipgear|multicast transceiver","av_over_ip"),
    (r"kvm",                                    "kvm_switch"),
    (r"matrix switcher|matrix switch",          "switcher"),
    (r"presentation switcher|scaler.switcher|hdmi switcher|video switcher", "switcher"),
    (r"\b(4x1|2x1|4x2|8x1|8x2)\b.*switch",    "switcher"),
    (r"video wall|wall processor|wall controller", "multiviewer"),
    (r"multiview|quad.view|multi.view",         "multiviewer"),
    (r"splitter|distribution amp|distributor",  "distribution_amp"),
    (r"extender|hdbaset|over cat|over fiber|over ip.*extend", "extender"),
    (r"usb.*extend|extend.*usb",                "usb_extender"),
    (r"ptz|pan.tilt|auto.track|conference cam|streaming cam|broadcast cam", "camera"),
    (r"capture card|capture box|capture device|video capture", "capture"),
    (r"converter|sdi.*hdmi|hdmi.*sdi|format conv|3g.sdi|12g.sdi", "sdi"),
    (r"amplifier|speakerphone|microphone|audio.*mixer|dsp|dante", "audio"),
    (r"test generator|pattern generator|signal generator|tpg", "signal_generator"),
    (r"mount|adapter|bracket|table grommet",    "accessory"),
    (r"cable|fiber optic.*cable|hdmi.*cable",   "cable_kit"),
    (r"bundle|kit\b",                           "bundle"),
    (r"integration|controller system",          "integration"),
]

URL_PATTERNS = [
    (r"/extenders?/",      "extender"),
    (r"/switchers?/",      "switcher"),
    (r"/cameras?/",        "camera"),
    (r"/splitters?/",      "distribution_amp"),
    (r"/multiviewers?/",   "multiviewer"),
    (r"/av-over-ip/",      "av_over_ip"),
    (r"/capture-cards?/",  "capture"),
    (r"/audio/",           "audio"),
    (r"/cables?/",         "cable_kit"),
    (r"/medical/",         "medical_cart"),
    (r"/videobars?/",      "videobar"),
    (r"/network/",         "network"),
    (r"/controllers?/",    "controller"),
    (r"/kvm/",             "kvm_switch"),
]

def infer_category(title: str, url: str = "") -> str:
    t = (title or "").lower()
    u = (url or "").lower()

    # Try URL first (more reliable)
    for pat, cat in URL_PATTERNS:
        if re.search(pat, u):
            return cat

    # Then title
    for pat, cat in TITLE_PATTERNS:
        if re.search(pat, t):
            return cat

    return "other"


# ─── Spec extraction from HTML table ─────────────────────────────────────────

def parse_specs(html: str) -> dict:
    if not html:
        return {}
    soup = BeautifulSoup(html, "lxml")
    specs = {}
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2:
            k = cells[0].get_text(strip=True)
            v = cells[1].get_text(" ", strip=True)
            if k and v and k.lower() != "technical specifications":
                specs[k] = v
    return specs

def parse_features(html: str) -> list:
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    items = []
    for li in soup.find_all("li"):
        t = li.get_text(" ", strip=True)
        # Feature items often have a bold label then description
        if t and len(t) > 5:
            items.append(t[:300])
    return items[:25]

def extract_from_specs(specs: dict, keys: list) -> str | None:
    for key in keys:
        for k, v in specs.items():
            if key.lower() in k.lower():
                return v
    return None

def parse_port_count(text: str | None) -> int | None:
    if not text: return None
    m = re.match(r"(\d+)x?\s", str(text))
    return int(m.group(1)) if m else None

def parse_distance_m(text: str | None) -> int | None:
    if not text: return None
    # Look for meters
    m = re.search(r"(\d+)\s*m(?:eters?|etres?)?\b", str(text), re.I)
    if m: return int(m.group(1))
    # Look for feet and convert
    m = re.search(r"(\d+)\s*(?:ft|feet)\b", str(text), re.I)
    if m: return int(int(m.group(1)) * 0.3048)
    return None

def parse_bandwidth(text: str | None) -> float | None:
    if not text: return None
    m = re.search(r"([\d.]+)\s*Gbps", str(text), re.I)
    return float(m.group(1)) if m else None

def parse_resolutions(specs: dict, features: list, title: str = "") -> list:
    all_text = " ".join([title] + list(specs.values()) + features).lower()
    found = set()
    if re.search(r"8k\s*@?\s*60|8k60", all_text): found.add("8K60")
    if re.search(r"8k\s*@?\s*30|8k30|8k(?!60)", all_text): found.add("8K30")
    if re.search(r"4k\s*@?\s*120|4k120", all_text): found.add("4K120")
    if re.search(r"4k\s*@?\s*60|4k60|2160p60|2160p59", all_text): found.add("4K60")
    if re.search(r"4k\s*@?\s*30|4k30|2160p30|2160p29|2160p25|2160p24", all_text): found.add("4K30")
    if re.search(r"1080p60|1080p59|1080p50", all_text): found.add("1080p60")
    if re.search(r"1080[pi]", all_text): found.add("1080p")
    if re.search(r"720[pi]", all_text): found.add("720p")
    ORDER = ["720p","1080p","1080p60","4K30","4K60","4K120","8K30","8K60"]
    return [r for r in ORDER if r in found]

def parse_signals(specs: dict, features: list) -> tuple[list, list]:
    all_text = " ".join(list(specs.values()) + features).lower()
    sigs = set()
    if "hdmi 2.1" in all_text: sigs.add("HDMI 2.1")
    elif "hdmi 2.0" in all_text: sigs.add("HDMI 2.0")
    elif "hdmi 1.4" in all_text: sigs.add("HDMI 1.4")
    elif "hdmi" in all_text: sigs.add("HDMI")
    if "hdbaset" in all_text: sigs.add("HDBaseT")
    if "displayport" in all_text or " dp " in all_text: sigs.add("DisplayPort")
    if "12g-sdi" in all_text or "12gsdi" in all_text: sigs.add("12G-SDI")
    elif "3g-sdi" in all_text or "sdi" in all_text: sigs.add("SDI")
    if "usb-c" in all_text or "type-c" in all_text or "type c" in all_text: sigs.add("USB-C")
    if "fiber" in all_text or "optical" in all_text: sigs.add("Fiber")
    if "dante" in all_text: sigs.add("Dante")
    if "ndi" in all_text: sigs.add("NDI")
    return sorted(sigs), sorted(sigs)

def parse_price(text: str) -> float | None:
    if not text: return None
    m = re.search(r"[\d,]+\.?\d*", text.replace(",",""))
    return float(m.group()) if m else None


# ─── DB setup ─────────────────────────────────────────────────────────────────

def setup_db(conn):
    # Drop and recreate with complete schema
    conn.executescript("""
    DROP TABLE IF EXISTS products_new;
    CREATE TABLE products_new (
        id                TEXT PRIMARY KEY,
        name              TEXT NOT NULL,
        title             TEXT,
        category          TEXT NOT NULL,
        site_category     TEXT,
        site_subcategory  TEXT,
        -- Port specs
        inputs            INTEGER,
        outputs           INTEGER,
        input_signals     TEXT,     -- JSON
        output_signals    TEXT,     -- JSON
        resolutions       TEXT,     -- JSON
        max_bandwidth_gbps REAL,
        max_distance_m    INTEGER,
        -- Product info
        price_usd         REAL,
        price_sale_usd    REAL,
        stock_status      TEXT,
        short_description TEXT,
        description       TEXT,
        features          TEXT,     -- JSON array
        specs_json        TEXT,     -- JSON dict
        -- Links
        product_url       TEXT,
        image_url         TEXT,
        manual_url        TEXT,
        -- Meta
        weight_lbs        REAL,
        manual_file       TEXT,     -- local DOCX file if any
        notes             TEXT,
        scraped           INTEGER DEFAULT 0
    );
    """)
    conn.commit()


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    console.print("Fetching product feed (429 products)...")
    S = requests.Session()
    S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    r = S.get("https://bzbgear.com/product-feed/", timeout=30)
    console.print(f"Feed: {len(r.content):,} bytes")

    root = ET.fromstring(r.content)
    items = root.findall(".//item")
    console.print(f"Items: {len(items)}\n")

    # Load existing DB to preserve manual_file mappings
    conn_old = sqlite3.connect(DB_PATH)
    conn_old.row_factory = sqlite3.Row
    old_products = {
        r["id"]: dict(r)
        for r in conn_old.execute("SELECT * FROM products").fetchall()
    }
    conn_old.close()
    console.print(f"Existing products in DB: {len(old_products)}")

    # Set up new table
    conn = sqlite3.connect(DB_PATH)
    setup_db(conn)

    processed = 0
    for item in track(items, description="Importing..."):
        pid = (item.findtext("id") or "").strip().upper()
        if not pid:
            continue

        title   = item.findtext("title") or ""
        link    = item.findtext("link") or ""
        price   = parse_price(item.findtext("price") or "")
        status  = item.findtext("status") or ""
        desc_html = item.findtext("description") or ""
        desc    = BeautifulSoup(desc_html, "lxml").get_text(" ", strip=True)[:2000]
        manual  = item.findtext("manual") or ""
        image   = item.findtext("image_link") or ""
        weight_str = item.findtext("weight") or ""
        weight  = float(re.search(r"[\d.]+", weight_str).group()) if re.search(r"[\d.]+", weight_str) else None

        # Parse specs and features
        specs    = parse_specs(item.findtext("specifications") or "")
        features = parse_features(item.findtext("features") or "")

        # Derive structured fields from specs
        inputs_str  = extract_from_specs(specs, ["input port", "inputs", "hdmi input", "hdmi in"])
        outputs_str = extract_from_specs(specs, ["output port", "outputs", "hdmi output", "hdmi out"])
        dist_str    = extract_from_specs(specs, ["transmission distance", "max distance", "range", "distance"])
        bw_str      = extract_from_specs(specs, ["video bandwidth", "bandwidth", "data rate"])

        inputs    = parse_port_count(inputs_str)
        outputs   = parse_port_count(outputs_str)
        distance  = parse_distance_m(dist_str)
        bandwidth = parse_bandwidth(bw_str)
        resolutions = parse_resolutions(specs, features, title)
        in_sigs, out_sigs = parse_signals(specs, features)

        # Category
        category = infer_category(title, link)

        # Preserve manual_file from old DB
        old = old_products.get(pid, {})
        manual_file = old.get("manual_file")
        notes       = old.get("notes")

        conn.execute("""
            INSERT OR REPLACE INTO products_new
            (id, name, title, category,
             inputs, outputs, input_signals, output_signals,
             resolutions, max_bandwidth_gbps, max_distance_m,
             price_usd, stock_status,
             description, features, specs_json,
             product_url, image_url, manual_url,
             weight_lbs, manual_file, notes, scraped)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
        """, (
            pid, title, title, category,
            inputs, outputs,
            json.dumps(in_sigs), json.dumps(out_sigs),
            json.dumps(resolutions), bandwidth, distance,
            price, status,
            desc[:2000], json.dumps(features), json.dumps(specs),
            link, image, manual,
            weight, manual_file, notes,
        ))
        processed += 1

    # Copy new table over old
    conn.executescript("""
        DROP TABLE IF EXISTS products;
        ALTER TABLE products_new RENAME TO products;
        CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
        CREATE INDEX IF NOT EXISTS idx_products_inputs   ON products(inputs);
        CREATE INDEX IF NOT EXISTS idx_products_outputs  ON products(outputs);
    """)
    conn.commit()

    console.print(f"\n[bold green]Done! {processed} products imported.[/bold green]")

    # Summary
    console.print("\n[bold]Category breakdown:[/bold]")
    for row in conn.execute("""
        SELECT category, COUNT(*) n,
               ROUND(AVG(price_usd),0) avg_price,
               SUM(CASE WHEN inputs IS NOT NULL THEN 1 ELSE 0 END) has_io
        FROM products GROUP BY category ORDER BY n DESC
    """):
        console.print(f"  {str(row[0]):<25} {row[1]:>4} products  "
                      f"avg ${row[2] or 0:>8,.0f}  "
                      f"io_parsed={row[3]}")

    conn.close()

if __name__ == "__main__":
    main()
