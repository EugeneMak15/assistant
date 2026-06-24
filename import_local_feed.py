"""
Import BZB Gear products from local RSS feed file.
Correctly handles nested <categories><category> structure.
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import re, json, sqlite3
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import track

console = Console()
DB_PATH = "./products.db"
FEED_PATH = r"C:\Users\eugen\Downloads\download.rss"

# ─── Category mapping: site hierarchy -> system category ─────────────────────

# Maps site category strings (lowercase, partial match) -> system category
# Full mapping from actual feed category hierarchy
SITE_TO_SYSTEM = {
    # Signal Extenders
    "hdmi extenders over category cable":       "extender",
    "hdmi extenders over coax":                 "extender",
    "fiber optic extenders":                    "extender",
    "displayport extenders":                    "extender",
    "wall plate extenders":                     "extender",
    "wireless extenders":                       "extender",
    "audio extenders":                          "extender",
    "kvm/usb extenders over category cable":    "kvm_switch",
    "kvm extenders":                            "kvm_switch",
    "signal extenders":                         "extender",
    # Video Switchers
    "matrix switchers":                         "switcher",
    "standard switchers":                       "switcher",
    "production switchers":                     "switcher",
    "hdmi/usb mixers":                          "switcher",
    "long-range matrix kits":                   "switcher",
    "kvm switches":                             "kvm_switch",
    "wired presentation switchers":             "presentation_switcher",
    "wireless presentation switchers":          "presentation_switcher",
    "presentation switchers":                   "presentation_switcher",
    "video wall processors / switchers":        "multiviewer",
    "video switchers":                          "switcher",
    # 8K devices — map by subcategory
    "8k matrix switchers":                      "switcher",
    "8k standard switchers":                    "switcher",
    "8k extenders":                             "extender",
    "8k splitters / amplifiers":                "distribution_amp",
    "8k integration tools":                     "integration",
    "8k compatible devices":                    "other",   # parent only, skip
    # AV over IP
    "avoip":                                    "av_over_ip",
    "av over ip":                               "av_over_ip",
    "streaming encoders / decoders":            "encoder_decoder",
    # Audio
    "audio amplifiers":                         "audio",
    "audio converters":                         "sdi",
    "conference speakers/microphones":          "audio",
    "dsp":                                      "audio",
    "audio":                                    "audio",
    # Cameras
    "ptz cameras":                              "camera",
    "eptz cameras":                             "camera",
    "box cameras":                              "camera",
    "webcams":                                  "camera",
    "cameras":                                  "camera",
    # Capture / Converters
    "capture cards":                            "capture",
    "video converters / scalers":               "sdi",
    "capture cards / converters":               "capture",
    # Splitters
    "hdmi splitters":                           "distribution_amp",
    "long-range hdmi splitters":                "distribution_amp",
    "sdi splitters":                            "distribution_amp",
    "splitters / amplifiers":                   "distribution_amp",
    # Other
    "multiviewers":                             "multiviewer",
    "video wall processors":                    "multiviewer",
    "network switches":                         "network",
    "joystick controllers":                     "controller",
    "integration tools":                        "integration",
    "medical carts":                            "medical_cart",
    "mounts/adapters":                          "accessory",
    "cables":                                   "cable_kit",
    "videobars":                                "videobar",
}

SKIP_CATEGORIES = {"new arrivals", "discontinued", "discontinued products"}

# Title-based fallback for products without categories
TITLE_PATTERNS = [
    (r"medical cart",                               "medical_cart"),
    (r"video ?bar",                                 "videobar"),
    (r"network switch|managed switch|unmanaged.*switch|poe.*switch|ethernet switch", "network"),
    (r"joystick controller|ptz controller",         "controller"),
    (r"production bundle|studio bundle|camera bundle", "bundle"),
    (r"speakerphone|conference speak",              "audio"),
    (r"av.over.ip|ipgear|multicast transceiver",    "av_over_ip"),
    (r"streaming encoder|streaming decoder|encoder.*decoder|decoder.*encoder", "encoder_decoder"),
    (r"wireless.*extend|extend.*wireless|wireless.*hdmi.*kit|wireless hdmi", "extender"),
    (r"kvm",                                        "kvm_switch"),
    (r"matrix switcher|matrix switch",              "switcher"),
    (r"wired presentation|wireless presentation",   "presentation_switcher"),
    (r"presentation switcher|byod|collaboration",   "presentation_switcher"),
    (r"production switch|streaming switch|live.*switch", "switcher"),
    (r"video wall|wall processor|wall controller",  "multiviewer"),
    (r"multiview|quad.view",                        "multiviewer"),
    (r"splitter|distribution amp",                  "distribution_amp"),
    (r"extender|hdbaset|over cat|over fiber",       "extender"),
    (r"usb.*extend|extend.*usb",                    "usb_extender"),
    (r"ptz|pan.tilt|auto.track|eptz",               "camera"),
    (r"conference cam|streaming cam|broadcast cam|huddle.*cam|box cam|webcam|web cam|usb.*camera", "camera"),
    (r"capture card|capture box|capture device|video capture", "capture"),
    (r"sdi.*hdmi|hdmi.*sdi|format conv|3g.sdi|12g.sdi|converter|scaler", "sdi"),
    (r"microphone|ceiling mic|condenser mic",        "audio"),
    (r"amplifier|dsp\b|dante|audio.*mixer",         "audio"),
    (r"test generator|pattern generator|signal generator|tpg", "signal_generator"),
    (r"mount|adapter|bracket|grommet|rack\b",       "accessory"),
    (r"\bcable\b|fiber optic.*cable",               "cable_kit"),
    (r"sfp module",                                 "accessory"),
    (r"switch\b",                                   "switcher"),
]

def infer_from_title(title: str) -> str:
    t = title.lower()
    for pat, cat in TITLE_PATTERNS:
        if re.search(pat, t):
            return cat
    return "other"

def map_category(cats: list[str], title: str = "") -> tuple[str, str | None, str | None]:
    """
    Returns (system_category, site_category, site_subcategory).
    Tries site categories first (most specific subcategory wins), then title fallback.
    """
    real_cats = [c for c in cats if c.lower().strip() not in SKIP_CATEGORIES]

    best_cat = None
    best_parent = None
    best_child = None

    for cat_str in real_cats:
        parts = [p.strip() for p in cat_str.split(">")]
        parent = parts[0] if parts else ""
        # Try most specific (deepest) level first
        for part in reversed(parts):
            key = part.lower().strip()
            if key in SITE_TO_SYSTEM and SITE_TO_SYSTEM[key] != "other":
                best_cat    = SITE_TO_SYSTEM[key]
                best_parent = parent
                best_child  = parts[1] if len(parts) > 1 else None
                break
        if best_cat:
            break

    if best_cat:
        return best_cat, best_parent, best_child

    # Title-based fallback for products without useful site category
    site_cat = real_cats[0] if real_cats else (cats[0] if cats else None)
    return infer_from_title(title), site_cat, None


# ─── Spec/feature parsing ─────────────────────────────────────────────────────

def clean_html(html: str, max_len: int = 2000) -> str:
    if not html: return ""
    return BeautifulSoup(html, "lxml").get_text(" ", strip=True)[:max_len]

def parse_specs_html(html: str) -> dict:
    if not html: return {}
    soup = BeautifulSoup(html, "lxml")
    specs = {}
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2:
            k = cells[0].get_text(strip=True)
            v = cells[1].get_text(" ", strip=True)
            if k and v and "technical spec" not in k.lower() and "connectivity" not in k.lower():
                specs[k] = v
    return specs

def parse_features_html(html: str) -> list:
    if not html: return []
    soup = BeautifulSoup(html, "lxml")
    items = []
    for li in soup.find_all("li"):
        t = li.get_text(" ", strip=True)
        if t and len(t) > 5:
            items.append(t[:300])
    return items[:25]

def spec_val(specs: dict, keys: list) -> str | None:
    for key in keys:
        for k, v in specs.items():
            if key.lower() in k.lower():
                return v
    return None

def parse_price(text: str) -> float | None:
    if not text: return None
    # Handle "Original price was: $X. Current price is: $Y." — take current
    current = re.search(r"Current price is:?\s*\$?([\d,]+\.?\d*)", text)
    if current:
        return float(current.group(1).replace(",", ""))
    m = re.search(r"\$?([\d,]+\.?\d*)", text.replace(",", ""))
    return float(m.group(1)) if m else None

def parse_sale_price(text: str) -> float | None:
    """Returns sale price only if different from regular."""
    if not text: return None
    orig = re.search(r"Original price was:?\s*\$?([\d,]+\.?\d*)", text)
    curr = re.search(r"Current price is:?\s*\$?([\d,]+\.?\d*)", text)
    if orig and curr and orig.group(1) != curr.group(1):
        return float(curr.group(1).replace(",",""))
    return None

def parse_port_count(text: str | None) -> int | None:
    if not text: return None
    m = re.match(r"(\d+)\s*[xX]?\s", str(text).strip())
    return int(m.group(1)) if m else None

def parse_distance_m(text: str | None) -> int | None:
    if not text: return None
    # metres
    m = re.search(r"(\d+)\s*m(?:eters?|etres?)?\b", str(text), re.I)
    if m: return int(m.group(1))
    # feet
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
    if re.search(r"4k\s*@?\s*30|4k30|2160p30|2160p25|2160p24", all_text): found.add("4K30")
    if re.search(r"1080p60|1080p59|1080p50", all_text): found.add("1080p60")
    if re.search(r"1080[pi]", all_text): found.add("1080p")
    if re.search(r"720[pi]", all_text): found.add("720p")
    ORDER = ["720p","1080p","1080p60","4K30","4K60","4K120","8K30","8K60"]
    return [r for r in ORDER if r in found]

def parse_signals(specs: dict, features: list) -> list:
    all_text = " ".join(list(specs.values()) + features).lower()
    sigs = set()
    if "hdmi 2.1" in all_text: sigs.add("HDMI 2.1")
    elif "hdmi 2.0" in all_text: sigs.add("HDMI 2.0")
    elif "hdmi 1.4" in all_text: sigs.add("HDMI 1.4")
    elif "hdmi" in all_text: sigs.add("HDMI")
    if "hdbaset" in all_text: sigs.add("HDBaseT")
    if "displayport" in all_text: sigs.add("DisplayPort")
    if "12g-sdi" in all_text or "12gsdi" in all_text: sigs.add("12G-SDI")
    elif "3g-sdi" in all_text or "\bsdi\b" in all_text or "sdi" in all_text: sigs.add("SDI")
    if "usb-c" in all_text or "type-c" in all_text or "type c" in all_text: sigs.add("USB-C")
    if "fiber" in all_text or "optical fiber" in all_text: sigs.add("Fiber")
    if "dante" in all_text: sigs.add("Dante")
    if "ndi" in all_text: sigs.add("NDI")
    return sorted(sigs)

def parse_weight(text: str | None) -> float | None:
    if not text: return None
    m = re.search(r"([\d.]+)\s*lbs?", str(text), re.I)
    return float(m.group(1)) if m else None


# ─── DB ──────────────────────────────────────────────────────────────────────

def setup_db(conn):
    conn.executescript("""
    DROP TABLE IF EXISTS products;
    CREATE TABLE products (
        id                  TEXT PRIMARY KEY,
        name                TEXT NOT NULL,
        title               TEXT,
        category            TEXT NOT NULL DEFAULT 'other',
        -- Site categories (exact from feed)
        site_category       TEXT,
        site_subcategory    TEXT,
        site_categories_raw TEXT,       -- JSON array of all raw category strings
        -- Port specs
        inputs              INTEGER,
        outputs             INTEGER,
        input_signals       TEXT,       -- JSON array
        output_signals      TEXT,       -- JSON array
        resolutions         TEXT,       -- JSON array
        max_bandwidth_gbps  REAL,
        max_distance_m      INTEGER,
        -- Pricing
        price_usd           REAL,
        price_sale_usd      REAL,
        stock_status        TEXT,
        -- Content
        description         TEXT,
        features            TEXT,       -- JSON array of strings
        specs_json          TEXT,       -- JSON dict key->value
        -- Media & links
        product_url         TEXT,
        image_url           TEXT,
        additional_images   TEXT,       -- JSON array
        manual_url          TEXT,
        brochure_url        TEXT,
        youtube_videos      TEXT,       -- JSON array
        -- Physical
        weight_lbs          REAL,
        dim_width           TEXT,
        dim_height          TEXT,
        dim_length          TEXT,
        -- Meta
        manual_file         TEXT,       -- local DOCX file
        notes               TEXT,
        scraped             INTEGER DEFAULT 1
    );
    CREATE INDEX idx_products_cat  ON products(category);
    CREATE INDEX idx_products_price ON products(price_usd);
    """)
    conn.commit()


# ─── Parse one <item> ─────────────────────────────────────────────────────────

def parse_item(item: ET.Element) -> dict | None:
    pid = (item.findtext("id") or "").strip().upper()
    if not pid:
        return None

    title = item.findtext("title") or ""
    link  = item.findtext("link") or ""

    # --- Categories (nested <categories><category> elements) ---
    cats_el = item.find("categories")
    cats = []
    if cats_el is not None:
        for cat_el in cats_el.findall("category"):
            t = (cat_el.text or "").strip()
            if t:
                cats.append(t)

    system_cat, site_cat, site_subcat = map_category(cats, title)

    # --- Price ---
    price_str   = item.findtext("price") or ""
    price       = parse_price(price_str)
    sale_price  = parse_sale_price(price_str)

    # --- Status ---
    status = item.findtext("status") or ""

    # --- Description ---
    desc = clean_html(item.findtext("description") or "")

    # --- Features & Specs ---
    features = parse_features_html(item.findtext("features") or "")
    specs    = parse_specs_html(item.findtext("specifications") or "")

    # --- Derived technical specs ---
    inputs_raw  = spec_val(specs, ["input port", "inputs", "hdmi input", "hdmi in"])
    outputs_raw = spec_val(specs, ["output port", "outputs", "hdmi output", "hdmi out"])
    dist_raw    = spec_val(specs, ["transmission distance", "max distance", "range", "transmission"])
    bw_raw      = spec_val(specs, ["video bandwidth", "bandwidth", "maximum video bandwidth"])

    inputs     = parse_port_count(inputs_raw)
    outputs    = parse_port_count(outputs_raw)
    distance   = parse_distance_m(dist_raw)
    bandwidth  = parse_bandwidth(bw_raw)
    resolutions = parse_resolutions(specs, features, title)
    signals    = parse_signals(specs, features)

    # --- Images ---
    image_url   = item.findtext("image_link") or ""
    add_images  = [el.text.strip() for el in item.findall("additional_image_link") if el.text]

    # --- Manual / brochure ---
    manual  = item.findtext("manual") or ""
    brochure = item.findtext("brochure") or ""

    # --- YouTube ---
    yt_el = item.find("youtube-videos")
    yt_videos = []
    if yt_el is not None:
        yt_videos = [el.text.strip() for el in yt_el.findall("youtube-video") if el.text]

    # --- Weight / Dimensions ---
    weight = parse_weight(item.findtext("weight") or "")
    dims_el = item.find("dimensions")
    dim_w = dim_h = dim_l = None
    if dims_el is not None:
        dim_w = dims_el.findtext("width")
        dim_h = dims_el.findtext("height")
        dim_l = dims_el.findtext("length")

    return {
        "id":                  pid,
        "name":                title or pid,
        "title":               title,
        "category":            system_cat,
        "site_category":       site_cat,
        "site_subcategory":    site_subcat,
        "site_categories_raw": json.dumps(cats),
        "inputs":              inputs,
        "outputs":             outputs,
        "input_signals":       json.dumps(signals),
        "output_signals":      json.dumps(signals),
        "resolutions":         json.dumps(resolutions),
        "max_bandwidth_gbps":  bandwidth,
        "max_distance_m":      distance,
        "price_usd":           price,
        "price_sale_usd":      sale_price,
        "stock_status":        status,
        "description":         desc,
        "features":            json.dumps(features),
        "specs_json":          json.dumps(specs),
        "product_url":         link,
        "image_url":           image_url,
        "additional_images":   json.dumps(add_images),
        "manual_url":          manual,
        "brochure_url":        brochure,
        "youtube_videos":      json.dumps(yt_videos),
        "weight_lbs":          weight,
        "dim_width":           dim_w,
        "dim_height":          dim_h,
        "dim_length":          dim_l,
    }


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    console.print(f"Parsing local feed: {FEED_PATH}")
    tree = ET.parse(FEED_PATH)
    root = tree.getroot()

    items = root.findall(".//item")
    console.print(f"Items found: [bold]{len(items)}[/bold]\n")

    # Load existing manual_file mappings before dropping table
    conn_old = sqlite3.connect(DB_PATH)
    old_manual_files = {}
    try:
        for row in conn_old.execute("SELECT id, manual_file FROM products WHERE manual_file IS NOT NULL"):
            old_manual_files[row[0]] = row[1]
    except Exception:
        pass
    conn_old.close()
    console.print(f"Preserving {len(old_manual_files)} manual_file mappings from existing DB")

    conn = sqlite3.connect(DB_PATH)
    setup_db(conn)

    ok = err = 0
    for item in track(items, description="Importing..."):
        p = parse_item(item)
        if not p:
            err += 1
            continue

        # Restore manual_file mapping
        p["manual_file"] = old_manual_files.get(p["id"])

        cols = list(p.keys())
        placeholders = ",".join("?" * len(cols))
        conn.execute(
            f"INSERT OR REPLACE INTO products ({','.join(cols)}) VALUES ({placeholders})",
            [p[c] for c in cols]
        )
        ok += 1

    conn.commit()

    console.print(f"\n[bold green]Done! {ok} products imported, {err} skipped.[/bold green]")

    # Summary
    console.print("\n[bold]Category breakdown (with site categories):[/bold]")
    for row in conn.execute("""
        SELECT category, site_category, COUNT(*) n,
               ROUND(AVG(price_usd),0) avg_price
        FROM products
        GROUP BY category, site_category
        ORDER BY n DESC
        LIMIT 40
    """):
        sub = f" > {row[1]}" if row[1] else ""
        console.print(f"  {row[0]:<25}{sub:<40}  {row[2]:>4} products  avg ${row[3] or 0:>7,.0f}")

    console.print()
    no_cat = conn.execute("SELECT COUNT(*) FROM products WHERE category='other'").fetchone()[0]
    no_cat_site = conn.execute("SELECT COUNT(*) FROM products WHERE site_category IS NULL").fetchone()[0]
    console.print(f"'other' category: {no_cat}")
    console.print(f"No site_category:  {no_cat_site}")

    conn.close()


if __name__ == "__main__":
    main()
