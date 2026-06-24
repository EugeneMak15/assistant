"""
Parse full BZB Gear product feed (429 products) and update products.db
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import re, json, sqlite3, time
import xml.etree.ElementTree as ET
from pathlib import Path
from bs4 import BeautifulSoup

import truststore; truststore.inject_into_ssl()
import requests
from rich.console import Console
from rich.progress import track

console = Console()
DB_PATH = "./products.db"

# ─── Fetch feed ──────────────────────────────────────────────────────────────

def fetch_feed() -> ET.Element:
    console.print("Fetching full product feed...")
    S = requests.Session()
    S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    r = S.get("https://bzbgear.com/product-feed/", timeout=30)
    console.print(f"Feed size: {len(r.content):,} bytes")
    return ET.fromstring(r.content)

# ─── Detect namespaces ───────────────────────────────────────────────────────

def find_namespaces(root: ET.Element) -> dict:
    """Find all namespace prefixes used in the feed."""
    ns = {}
    for el in root.iter():
        tag = el.tag
        if tag.startswith("{"):
            uri = tag[1:tag.index("}")]
            # Guess prefix
            if "google" in uri or "base.google" in uri:
                ns["g"] = uri
            elif "bzbgear" in uri or "bzb" in uri.lower():
                ns["bzb"] = uri
    return ns

# ─── Parse one item ──────────────────────────────────────────────────────────

def clean_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "lxml").get_text(" ", strip=True)

def parse_price(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
    return float(m.group()) if m else None

def parse_item(item: ET.Element, ns: dict) -> dict:
    G = ns.get("g", "http://base.google.com/ns/1.0")

    def g(local):
        el = item.find(f"{{{G}}}{local}")
        return el.text.strip() if el is not None and el.text else None

    def plain(tag):
        el = item.find(tag)
        return el.text.strip() if el is not None and el.text else None

    # ID — try various field names
    pid = g("id") or g("item_group_id") or plain("id")

    # Extract from link if ID not found
    link = plain("link") or g("link") or ""
    if not pid and link:
        slug = link.rstrip("/").split("/")[-1].upper()
        pid = slug

    # Categories — product_type has "Parent > Child" format
    cats = []
    for el in item.findall(f"{{{G}}}product_type"):
        if el.text:
            cats.append(el.text.strip())
    # Also check plain product_type
    for el in item.findall("product_type"):
        if el.text:
            cats.append(el.text.strip())

    # Parse first category into parent > sub
    site_category = None
    site_subcategory = None
    if cats:
        parts = [p.strip() for p in cats[0].split(">")]
        site_category = parts[0] if parts else None
        site_subcategory = parts[1] if len(parts) > 1 else None

    # Price
    price_str = g("price") or g("sale_price") or ""
    price = parse_price(price_str)
    sale_str = g("sale_price") or ""
    sale_price = parse_price(sale_str) if sale_str and sale_str != price_str else None

    # Features
    features_el = item.find(f"{{{G}}}features")
    if features_el is None:
        features_el = item.find("features")
    features_text = features_el.text if features_el is not None else ""
    features = [f.strip() for f in re.split(r"[•\n\r]+", features_text or "") if f.strip() and len(f.strip()) > 3]

    # Specifications — parse HTML table into dict
    specs_el = item.find(f"{{{G}}}specifications")
    if specs_el is None:
        specs_el = item.find("specifications")
    specs = {}
    if specs_el is not None and specs_el.text:
        soup = BeautifulSoup(specs_el.text, "lxml")
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                k = cells[0].get_text(strip=True)
                v = cells[1].get_text(strip=True)
                if k and v:
                    specs[k] = v

    # Extract specs we care about
    def spec(keys):
        for k in keys:
            for sk, sv in specs.items():
                if k.lower() in sk.lower():
                    return sv
        return None

    inputs_str  = spec(["inputs", "input port", "hdmi input"])
    outputs_str = spec(["outputs", "output port", "hdmi output"])
    dist_str    = spec(["distance", "range", "transmission"])
    bw_str      = spec(["bandwidth"])
    res_str     = spec(["resolution", "max resolution"])

    def parse_num(s):
        if not s: return None
        m = re.search(r"\d+", str(s))
        return int(m.group()) if m else None

    # Manual / brochure URLs
    manual_url = g("manual") or plain("manual")

    return {
        "id":               pid,
        "title":            plain("title") or g("title"),
        "link":             link,
        "site_category":    site_category,
        "site_subcategory": site_subcategory,
        "all_categories":   cats,
        "price_usd":        price,
        "price_sale_usd":   sale_price,
        "stock_status":     g("availability"),
        "description":      clean_html(plain("description") or "")[:1500],
        "features":         features,
        "specs":            specs,
        "image_url":        g("image_link"),
        "manual_url":       manual_url,
        "weight_str":       g("shipping_weight") or g("weight"),
        # Derived from specs
        "inputs_parsed":    parse_num(inputs_str),
        "outputs_parsed":   parse_num(outputs_str),
        "distance_parsed":  parse_num(dist_str),
        "bandwidth_parsed": parse_price(bw_str or ""),
    }

# ─── Category mapping ────────────────────────────────────────────────────────

SITE_TO_SYSTEM = {
    "signal extenders":           "extender",
    "hdmi extenders over cat":    "extender",
    "hdmi extenders over fiber":  "extender",
    "usb extenders":              "usb_extender",
    "video switchers":            "switcher",
    "matrix switchers":           "switcher",
    "presentation switchers":     "presentation_switcher",
    "multiviewers":               "multiviewer",
    "video wall":                 "multiviewer",
    "splitters":                  "distribution_amp",
    "amplifiers":                 "distribution_amp",
    "cameras":                    "camera",
    "ptz cameras":                "camera",
    "av over ip":                 "av_over_ip",
    "capture cards":              "capture",
    "converters":                 "sdi",
    "sdi":                        "sdi",
    "audio":                      "audio",
    "joystick controllers":       "controller",
    "integration tools":          "integration",
    "network switches":           "network",
    "medical carts":              "medical_cart",
    "cables":                     "cable_kit",
    "mounts":                     "accessory",
    "adapters":                   "accessory",
    "videobars":                  "videobar",
    "kvm":                        "kvm_switch",
    "test generators":            "signal_generator",
    "pattern generators":         "signal_generator",
    "new arrivals":               None,  # skip — not a real category
    "discontinued":               None,
}

def map_category(site_cat: str) -> str | None:
    if not site_cat:
        return None
    key = site_cat.lower().strip()
    for k, v in SITE_TO_SYSTEM.items():
        if k in key or key in k:
            return v
    return None

# ─── DB ──────────────────────────────────────────────────────────────────────

def migrate_db(conn):
    existing = {row[1] for row in conn.execute("PRAGMA table_info(products)")}
    cols = {
        "title":            "TEXT",
        "site_category":    "TEXT",
        "site_subcategory": "TEXT",
        "price_usd":        "REAL",
        "price_sale_usd":   "REAL",
        "stock_status":     "TEXT",
        "description":      "TEXT",
        "features":         "TEXT",
        "specs_json":       "TEXT",
        "product_url":      "TEXT",
        "image_url":        "TEXT",
        "manual_url":       "TEXT",
        "weight_lbs":       "REAL",
        "scraped":          "INTEGER DEFAULT 0",
    }
    for col, typ in cols.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} {typ}")
    conn.commit()

# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    conn = sqlite3.connect(DB_PATH)
    migrate_db(conn)

    root = fetch_feed()

    # Find namespaces
    ns = {}
    for el in root.iter():
        if "{" in el.tag:
            uri = el.tag[1:el.tag.index("}")]
            if "google" in uri: ns["g"] = uri

    console.print(f"Namespace: {ns}")

    items = root.findall(".//item")
    console.print(f"Total items in feed: [bold]{len(items)}[/bold]\n")

    updated = inserted = skipped = 0

    for item in track(items, description="Processing feed..."):
        p = parse_item(item, ns)

        pid = p.get("id")
        if not pid:
            skipped += 1
            continue

        pid = pid.upper().strip()

        # Skip non-product entries
        if not p.get("link") or not p.get("title"):
            skipped += 1
            continue

        # Determine system category
        site_cat = p.get("site_category") or ""
        mapped_cat = map_category(site_cat)

        # Skip if category maps to None (New Arrivals, Discontinued etc)
        # but keep in DB with site_category filled
        if mapped_cat is None and site_cat.lower() in ("new arrivals", "discontinued products", "discontinued"):
            # Still update non-category fields
            mapped_cat = None

        features_json = json.dumps(p["features"]) if p["features"] else None
        specs_json    = json.dumps(p["specs"])    if p["specs"]    else None

        # Check if product exists
        row = conn.execute("SELECT id FROM products WHERE id=?", (pid,)).fetchone()

        if row:
            # Update — category from site wins over our regex guesses
            fields = [
                ("title",            p.get("title")),
                ("site_category",    p.get("site_category")),
                ("site_subcategory", p.get("site_subcategory")),
                ("price_usd",        p.get("price_usd")),
                ("price_sale_usd",   p.get("price_sale_usd")),
                ("stock_status",     p.get("stock_status")),
                ("description",      p.get("description")),
                ("features",         features_json),
                ("specs_json",       specs_json),
                ("product_url",      p.get("link")),
                ("image_url",        p.get("image_url")),
                ("manual_url",       p.get("manual_url")),
                ("scraped",          1),
            ]
            if mapped_cat:
                fields.append(("category", mapped_cat))
            # Also update inputs/outputs from specs if currently NULL
            if p.get("inputs_parsed"):
                fields.append(("inputs", p["inputs_parsed"]))
            if p.get("outputs_parsed"):
                fields.append(("outputs", p["outputs_parsed"]))
            if p.get("distance_parsed"):
                fields.append(("max_distance_m", p["distance_parsed"]))

            set_clause = ", ".join(f"{k}=?" for k, _ in fields)
            conn.execute(
                f"UPDATE products SET {set_clause} WHERE id=?",
                [v for _, v in fields] + [pid]
            )
            updated += 1
        else:
            # Insert new product
            conn.execute("""
                INSERT OR IGNORE INTO products
                (id, name, category, site_category, site_subcategory,
                 title, price_usd, price_sale_usd, stock_status,
                 description, features, specs_json,
                 product_url, image_url, manual_url,
                 inputs, outputs, max_distance_m, scraped)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
            """, (
                pid, p.get("title", pid),
                mapped_cat or "other",
                p.get("site_category"), p.get("site_subcategory"),
                p.get("title"),
                p.get("price_usd"), p.get("price_sale_usd"),
                p.get("stock_status"),
                p.get("description"), features_json, specs_json,
                p.get("link"), p.get("image_url"), p.get("manual_url"),
                p.get("inputs_parsed"), p.get("outputs_parsed"),
                p.get("distance_parsed"),
            ))
            inserted += 1

    conn.commit()
    conn.close()

    console.print(f"\n[bold green]Done![/bold green]  Updated: {updated}  Inserted: {inserted}  Skipped: {skipped}")

    # Show result
    conn = sqlite3.connect(DB_PATH)
    console.print("\n[bold]Site categories in DB:[/bold]")
    for row in conn.execute("""
        SELECT site_category, category, COUNT(*) as n
        FROM products
        WHERE site_category IS NOT NULL
        GROUP BY site_category, category
        ORDER BY n DESC
    """):
        console.print(f"  {str(row[0]):<40} -> {str(row[1]):<25} ({row[2]})")

    total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    console.print(f"\nTotal products in DB: [bold]{total}[/bold]")
    conn.close()

if __name__ == "__main__":
    main()
