"""
BZB Gear Product Catalog Scraper
1. Fetches product sitemap -> gets all product URLs
2. Also parses product-feed XML for structured data
3. Scrapes each product page for categories, price, description, features, specs
4. Updates products.db with correct data
"""
import re
import json
import time
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import truststore; truststore.inject_into_ssl()
import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import track

console = Console()

DB_PATH = "./products.db"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ─── DB Schema Migration ──────────────────────────────────────────────────────

def migrate_db(conn):
    """Add new columns to products table if they don't exist."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(products)")}
    new_cols = {
        "title":           "TEXT",
        "site_category":   "TEXT",      # exact category from website
        "site_subcategory":"TEXT",
        "price_usd":       "REAL",
        "price_sale_usd":  "REAL",
        "stock_status":    "TEXT",
        "short_description": "TEXT",
        "description":     "TEXT",
        "features":        "TEXT",      # JSON array of feature strings
        "product_url":     "TEXT",
        "image_url":       "TEXT",
        "sku":             "TEXT",
        "weight_lbs":      "REAL",
        "scraped":         "INTEGER DEFAULT 0",
    }
    for col, typ in new_cols.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} {typ}")
    conn.commit()
    console.print(f"[dim]DB schema updated[/dim]")


# ─── Sitemap fetch ────────────────────────────────────────────────────────────

def get_sitemap_urls():
    """Fetch product URLs from product-sitemap.xml."""
    console.print("Fetching product sitemap...")
    r = SESSION.get("https://bzbgear.com/product-sitemap.xml", timeout=15)
    root = ET.fromstring(r.content)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [loc.text for loc in root.findall(".//sm:loc", ns)]
    console.print(f"Found [bold]{len(urls)}[/bold] product URLs in sitemap")
    return urls


# ─── Product feed parse (structured data for ~10 newest) ─────────────────────

def parse_product_feed():
    """Parse the RSS product feed for structured data."""
    console.print("Fetching product feed XML...")
    r = SESSION.get("https://bzbgear.com/product-feed/", timeout=15)
    root = ET.fromstring(r.content)

    ns = {
        "g":    "http://base.google.com/ns/1.0",
        "bzbg": "https://bzbgear.com",
    }

    products = {}
    for item in root.findall(".//item"):
        def g(tag):
            el = item.find(tag)
            return el.text.strip() if el is not None and el.text else None

        pid = g("g:id") or g("id")
        if not pid:
            continue

        # Parse price
        price_str = g("g:price") or ""
        price = None
        m = re.search(r"[\d,]+\.?\d*", price_str.replace(",",""))
        if m:
            price = float(m.group())

        # Features
        features_el = item.find("g:features", ns)
        features_text = features_el.text if features_el is not None else ""
        features = [f.strip() for f in re.split(r"[•\n]+", features_text or "") if f.strip()]

        # Categories
        cats = [el.text.strip() for el in item.findall("g:product_type", ns) if el.text]

        products[pid.upper()] = {
            "title": g("title"),
            "price": price,
            "features": features,
            "categories": cats,
            "product_url": g("link"),
            "image_url": g("g:image_link"),
            "status": g("g:availability"),
            "description": BeautifulSoup(g("description") or "", "lxml").get_text(" ", strip=True)[:1000],
        }

    console.print(f"Feed parsed: [bold]{len(products)}[/bold] products with structured data")
    return products


# ─── Page scraper ─────────────────────────────────────────────────────────────

def scrape_product_page(url: str) -> dict:
    """Scrape a single product page. Returns dict of extracted data."""
    try:
        r = SESSION.get(url, timeout=12)
        if r.status_code != 200:
            return {}
        soup = BeautifulSoup(r.content, "lxml")
    except Exception as e:
        return {}

    data = {"product_url": url}

    # 1. JSON-LD schema.org Product
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            jd = json.loads(script.string or "")
            items = jd if isinstance(jd, list) else [jd]
            for item in items:
                if item.get("@type") == "Product":
                    data["title"] = item.get("name", "")
                    data["sku"] = item.get("sku", "")
                    data["image_url"] = (item.get("image") or [""])[0] if isinstance(item.get("image"), list) else item.get("image", "")
                    desc = item.get("description", "")
                    data["short_description"] = BeautifulSoup(desc, "lxml").get_text(" ", strip=True)[:500]

                    # Price from offers
                    offers = item.get("offers", {})
                    if isinstance(offers, list): offers = offers[0]
                    if offers:
                        data["price_usd"] = _parse_price(str(offers.get("price", "")))
                        data["stock_status"] = offers.get("availability", "").split("/")[-1]
        except Exception:
            pass

    # 2. Breadcrumbs -> site_category
    crumbs = []
    for el in soup.select(".woocommerce-breadcrumb a, nav.woocommerce-breadcrumb a, .breadcrumb a"):
        t = el.get_text(strip=True)
        if t and t.lower() not in ("home", "shop"):
            crumbs.append(t)
    if crumbs:
        data["site_category"] = crumbs[0] if crumbs else None
        data["site_subcategory"] = crumbs[1] if len(crumbs) > 1 else None

    # Also try product_cat from body class
    body = soup.find("body")
    if body:
        classes = body.get("class", [])
        for cls in classes:
            m = re.match(r"product_cat-([\w-]+)", cls)
            if m and not data.get("site_category"):
                data["site_category"] = m.group(1).replace("-", " ").title()

    # 3. Price (WooCommerce)
    if not data.get("price_usd"):
        for sel in (".price ins .amount", ".price .amount", ".woocommerce-Price-amount"):
            el = soup.select_one(sel)
            if el:
                data["price_usd"] = _parse_price(el.get_text())
                break

    # 4. Sale price
    sale_el = soup.select_one(".price ins .amount")
    if sale_el:
        data["price_sale_usd"] = _parse_price(sale_el.get_text())

    # 5. SKU
    if not data.get("sku"):
        sku_el = soup.select_one(".sku")
        if sku_el:
            data["sku"] = sku_el.get_text(strip=True)

    # 6. Stock status
    if not data.get("stock_status"):
        stock_el = soup.select_one(".stock")
        if stock_el:
            data["stock_status"] = stock_el.get_text(strip=True)

    # 7. Features list
    features = []
    for sel in (".product-features li", ".features li", ".wc-tab ul li", ".product-description li"):
        for li in soup.select(sel)[:20]:
            t = li.get_text(strip=True)
            if t and len(t) > 5:
                features.append(t)
        if features:
            break
    if features:
        data["features"] = json.dumps(features[:20])

    # 8. Full description
    if not data.get("description"):
        for sel in (".woocommerce-product-details__short-description", ".product-short-description", "#tab-description"):
            el = soup.select_one(sel)
            if el:
                data["description"] = el.get_text(" ", strip=True)[:2000]
                break

    # 9. Weight
    weight_el = soup.find(string=re.compile(r"\d+\.?\d*\s*lbs?", re.I))
    if weight_el:
        m = re.search(r"([\d.]+)\s*lbs?", str(weight_el), re.I)
        if m:
            data["weight_lbs"] = float(m.group(1))

    return data


def _parse_price(text: str) -> float | None:
    m = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
    return float(m.group()) if m else None


# ─── Product ID from URL ──────────────────────────────────────────────────────

def pid_from_url(url: str) -> str:
    """Extract product ID from URL slug."""
    slug = url.rstrip("/").split("/")[-1].upper()
    # Remove common suffixes that aren't part of the ID
    return slug


# ─── Category mapping: website -> our system ─────────────────────────────────

SITE_CATEGORY_MAP = {
    "signal extenders":         "extender",
    "hdmi extenders":           "extender",
    "extenders":                "extender",
    "video switchers":          "switcher",
    "switchers":                "switcher",
    "cameras":                  "camera",
    "splitters":                "distribution_amp",
    "splitters / amplifiers":   "distribution_amp",
    "amplifiers":               "distribution_amp",
    "multiviewers":             "multiviewer",
    "av over ip":               "av_over_ip",
    "capture cards":            "capture",
    "capture cards / converters": "capture",
    "converters":               "sdi",
    "audio":                    "audio",
    "joystick controllers":     "controller",
    "integration tools":        "integration",
    "network switches":         "network",
    "medical carts":            "medical_cart",
    "video wall processors":    "multiviewer",
    "video walls":              "multiviewer",
    "mounts/adapters":          "accessory",
    "mounts":                   "accessory",
    "cables":                   "cable_kit",
    "videobars":                "videobar",
    "kvm":                      "kvm_switch",
}

def map_category(site_cat: str | None) -> str | None:
    if not site_cat:
        return None
    key = site_cat.lower().strip()
    for k, v in SITE_CATEGORY_MAP.items():
        if k in key:
            return v
    return None


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    conn = sqlite3.connect(DB_PATH)
    migrate_db(conn)

    # Get feed data (10 newest products, richly structured)
    feed_data = parse_product_feed()

    # Get all product URLs from sitemap
    urls = get_sitemap_urls()

    console.print(f"\nScraping [bold]{len(urls)}[/bold] product pages...\n")

    updated = 0
    inserted = 0
    errors = 0

    for url in track(urls, description="Scraping..."):
        pid_slug = pid_from_url(url)

        # Try to find existing product in DB by URL slug or ID variations
        row = conn.execute(
            "SELECT id FROM products WHERE id = ? OR product_url = ? OR id LIKE ?",
            (pid_slug, url, f"%{pid_slug}%")
        ).fetchone()
        product_id = row[0] if row else pid_slug

        # Start with feed data if available
        data = dict(feed_data.get(product_id, {}))

        # Scrape the page
        page_data = scrape_product_page(url)
        # Page data wins for most fields, feed data wins for features/description
        for k, v in page_data.items():
            if v and not data.get(k):
                data[k] = v

        if not data:
            errors += 1
            continue

        # Map site category to our system
        site_cat = data.get("site_category") or ""
        mapped_cat = map_category(site_cat)

        # Determine if product exists in DB
        exists = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()

        if exists:
            # Update existing product
            fields = {
                "title":            data.get("title"),
                "site_category":    data.get("site_category"),
                "site_subcategory": data.get("site_subcategory"),
                "price_usd":        data.get("price_usd"),
                "price_sale_usd":   data.get("price_sale_usd"),
                "stock_status":     data.get("stock_status"),
                "short_description":data.get("short_description"),
                "description":      data.get("description"),
                "features":         data.get("features"),
                "product_url":      url,
                "image_url":        data.get("image_url"),
                "sku":              data.get("sku"),
                "weight_lbs":       data.get("weight_lbs"),
                "scraped":          1,
            }
            # Also update category if we got a better one from the site
            if mapped_cat:
                fields["category"] = mapped_cat

            set_clause = ", ".join(f"{k}=?" for k in fields)
            conn.execute(
                f"UPDATE products SET {set_clause} WHERE id=?",
                list(fields.values()) + [product_id]
            )
            updated += 1
        else:
            # Insert new product not in our DB
            conn.execute("""
                INSERT OR IGNORE INTO products
                (id, name, category, site_category, site_subcategory,
                 title, price_usd, price_sale_usd, stock_status,
                 short_description, description, features,
                 product_url, image_url, sku, weight_lbs, scraped)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
            """, (
                product_id, data.get("title", product_id),
                mapped_cat or "other",
                data.get("site_category"), data.get("site_subcategory"),
                data.get("title"),
                data.get("price_usd"), data.get("price_sale_usd"),
                data.get("stock_status"),
                data.get("short_description"), data.get("description"),
                data.get("features"),
                url, data.get("image_url"), data.get("sku"),
                data.get("weight_lbs"),
            ))
            inserted += 1

        conn.commit()
        time.sleep(0.3)  # polite delay

    conn.close()

    console.print(f"\n[bold green]Done![/bold green]")
    console.print(f"  Updated:  {updated}")
    console.print(f"  Inserted: {inserted}")
    console.print(f"  Errors:   {errors}")

    # Show category breakdown
    conn = sqlite3.connect(DB_PATH)
    console.print("\n[bold]Categories after scraping:[/bold]")
    for row in conn.execute("SELECT site_category, COUNT(*) FROM products WHERE site_category IS NOT NULL GROUP BY site_category ORDER BY 2 DESC"):
        console.print(f"  {row[0]}: {row[1]}")
    conn.close()


if __name__ == "__main__":
    main()
