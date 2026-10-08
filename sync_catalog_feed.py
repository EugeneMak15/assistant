"""Review and import newly approved BZBGEAR products from the public Woo feed.

Dry run by default. Apply inserts only reviewed SKUs, keeps existing products
untouched, and creates a consistent SQLite backup before writing.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET

from lxml import html


FEED_URL = "https://bzbgear.com/wp-content/uploads/woo-feed/google/xml/bzbgearshoppingfeed.xml"
G = "{http://base.google.com/ns/1.0}"
HEADERS = {"User-Agent": "BZBAdvisor/1.0 (catalog sync; sales@bzbgear.com)"}

# Site specifications were checked for these six new devices. Camera 31x
# variants inherit shared connectivity from their existing 25x family members.
PROFILES = {
    "BG-EXH-8K100U": ("extender", "8K60", 100, 48, "HDBaseT", True),
    "BG-EXH-8K50C": ("extender", "8K60", 50, 48, "HDBaseT", False),
    "BG-EXH-4KFE": ("extender", "4K60", 10000, 18, "Fiber", True),
    "BG-EXH-4KFH": ("extender", "4K60", 10000, 18, "Fiber", False),
    "BG-8KCH": ("capture", "4K60", None, 48, "USB-C", True),
    "BG-AVTPG-MINI-SE": ("integration", "4K60", None, 18, "HDMI", False),
    "BG-4K-VP-R": ("extender", "4K60", 70, 18, "HDMI", False),
    "BG-4K-VP1616PRO": ("switcher", "4K60", 70, 18, "HDMI", False),
}
CAMERA_31X = {
    f"BG-ADAMO-4K{technology}31X-{color}-31"
    for technology in ("", "DA", "ND") for color in ("B", "W")
}
APPROVED = set(PROFILES) | CAMERA_31X


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _page_data(url: str) -> dict:
    page = html.fromstring(_fetch(url))
    tabs = page.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' tab_content ')]")
    overview, features = "", []
    for tab in tabs:
        heading = _clean(" ".join(tab.xpath("./h2[1]//text()"))).lower()
        if heading == "overview" or _clean(tab.text_content()).lower().startswith("overview"):
            overview = _clean(" ".join(tab.xpath(".//p//text()")))[:1800]
        elif heading == "features":
            features = [_clean(" ".join(li.itertext()))[:300] for li in tab.xpath(".//li")]
    specs = {}
    for row in page.xpath("//table//tr"):
        cells = row.xpath("./th|./td")
        if len(cells) >= 2:
            key, value = (_clean(" ".join(c.itertext())) for c in cells[:2])
            if key and value and len(key) < 100 and key not in specs:
                specs[key] = value[:500]
    return {"description": overview, "features": features[:20], "specs": specs}


def _feed_items(feed_url: str) -> dict[str, ET.Element]:
    root = ET.fromstring(_fetch(feed_url))
    items = {}
    for item in root.findall(".//item"):
        sku = (item.findtext(G + "id") or "").strip().upper()
        if sku:
            if sku in items:
                raise ValueError(f"Duplicate feed SKU: {sku}")
            items[sku] = item
    return items


def _camera_alias(sku: str, existing: set[str]) -> bool:
    """The feed appends -31 to old 12x/25x variants already in the DB."""
    return bool(sku.endswith("-31") and re.search(r"(?:12|25)X-[BW]-31$", sku)
                and sku[:-3] in existing)


def _price(value: str | None) -> float | None:
    match = re.search(r"[\d,]+(?:\.\d+)?", value or "")
    return float(match.group().replace(",", "")) if match else None


def _base_product(sku: str, item: ET.Element, page: dict, profile: tuple) -> dict:
    category, max_res, distance, bandwidth, transport, usb = profile
    title = _clean(item.findtext(G + "title") or sku)
    site_category = item.findtext(G + "product_type") or ""
    parts = [part.strip() for part in site_category.split(">")]
    resolutions = ["4K60"] if max_res == "4K60" else ["4K60", "4K120", "8K60"]
    if sku == "BG-8KCH":
        resolutions = ["4K60", "8K60 input/loop-out"]
    signals = ["HDMI 2.1" if bandwidth == 48 else "HDMI 2.0"]
    if transport not in ("HDMI", "USB-C"):
        signals.append(transport)
    if usb:
        signals.append("USB")
    input_signals = ["HDMI 2.1"] if sku == "BG-8KCH" else signals
    output_signals = ["HDMI 2.1", "USB-C"] if sku == "BG-8KCH" else signals
    stock = (item.findtext(G + "availability") or "").lower()
    status = {"in_stock": "In Stock", "out_of_stock": "Out of Stock", "preorder": "Pre-Order"}.get(stock, stock)
    description = page["description"] or title
    features = page["features"] or [f"{key}: {value}" for key, value in list(page["specs"].items())[:12]]
    return {
        "id": sku, "name": title, "title": title, "category": category,
        "site_category": parts[0], "site_subcategory": parts[1] if len(parts) > 1 else None,
        "site_categories_raw": json.dumps([site_category]),
        "inputs": 1, "outputs": 2 if sku == "BG-8KCH" else 1,
        "input_signals": json.dumps(input_signals), "output_signals": json.dumps(output_signals),
        "resolutions": json.dumps(resolutions), "max_bandwidth_gbps": bandwidth,
        "max_distance_m": distance, "price_usd": _price(item.findtext(G + "price")),
        "stock_status": status, "description": description,
        "features": json.dumps(features), "specs_json": json.dumps(page["specs"]),
        "product_url": item.findtext("link"), "image_url": item.findtext(G + "image_link"),
        "additional_images": json.dumps([e.text for e in item.findall(G + "additional_image_link") if e.text]),
        "what_it_does": description[:600], "scraped": 1,
    }


def _base_interface(sku: str, profile: tuple) -> dict:
    category, max_res, _, bandwidth, transport, usb = profile
    interface = {
        "sku": sku, "max_res": max_res, "supports_4k": 1,
        "supports_8k": int(max_res == "8K60" or sku == "BG-8KCH"),
        "supports_hdr": 1 if sku != "BG-AVTPG-MINI-SE" else 0,
        "in_hdmi": 1, "in_hdmi_count": 1,
        "out_hdmi": 1, "out_hdmi_count": 1,
        "in_hdmi_ver": "2.1" if bandwidth == 48 else "2.0",
        "out_hdmi_ver": "2.1" if bandwidth == 48 else "2.0",
        "primary_fn": "extender-tx" if category == "extender" else "encoder" if category == "capture" else "converter",
        "secondary_fns": json.dumps(["extender-rx"] if category == "extender" else []),
        "confidence": 0.95, "extracted_at": datetime.now(timezone.utc).isoformat(),
    }
    if transport == "HDBaseT":
        interface.update(in_hdbaset=1, out_hdbaset=1)
    elif transport == "Fiber":
        interface.update(in_fiber=1, out_fiber=1)
    if usb and category == "extender":
        interface["notes"] = "Kit extends USB peripherals; USB is not a video capture output."
    if sku == "BG-8KCH":
        interface.update(out_usb_video=1, notes="8K60 HDMI input/loop-through; USB capture output is limited to 4K60.")
    if sku == "BG-AVTPG-MINI-SE":
        interface["notes"] = "HDMI 4K60 signal generator and EDID/HDCP emulator."
    if sku == "BG-4K-VP-R":
        interface.update(in_hdmi=0, in_hdmi_count=0,
                         primary_fn="extender-rx", secondary_fns="[]",
                         notes="Receiver for BG-4K-VP1616PRO; CAT input to HDMI output, up to 70 m. Not a standalone extender kit.")
    if sku == "BG-4K-VP1616PRO":
        interface.update(in_hdmi_count=16, out_hdmi_count=16,
                         primary_fn="matrix-switcher", secondary_fns=json.dumps(["video-wall", "multiview"]),
                         notes="16x16 matrix/video-wall/multiview kit with 16 receivers; 16 HDMI and 16 CAT output ports.")
    return interface


def _reviewed_product(sku: str, item: ET.Element, page: dict, profile: tuple) -> dict:
    product = _base_product(sku, item, page, profile)
    if sku == "BG-4K-VP-R":
        product.update(inputs=1, outputs=1,
                       input_signals=json.dumps(["CAT (VP series)"]),
                       output_signals=json.dumps(["HDMI 2.0"]),
                       what_it_does="Dedicated CAT receiver for the BG-4K-VP1616PRO system; 4K60 HDMI output up to 70 m.")
    elif sku == "BG-4K-VP1616PRO":
        product.update(inputs=16, outputs=16,
                       input_signals=json.dumps(["HDMI 2.0"]),
                       output_signals=json.dumps(["HDMI 2.0", "CAT (VP series)"]),
                       what_it_does="16x16 4K60 HDMI matrix, video-wall processor and multiviewer kit with 16 receivers.")
    return product


def _camera_variant(conn: sqlite3.Connection, sku: str, item: ET.Element, page: dict) -> tuple[dict, dict]:
    source_sku = sku.replace("31X", "25X")[:-3]
    source = conn.execute("SELECT * FROM products WHERE id=?", (source_sku,)).fetchone()
    source_interface = conn.execute("SELECT * FROM product_interfaces WHERE sku=?", (source_sku,)).fetchone()
    if not source or not source_interface:
        raise ValueError(f"Missing reviewed camera family member: {source_sku}")
    product, interface = dict(source), dict(source_interface)
    title = _clean(item.findtext(G + "title") or sku)
    inherited_features = [feature for feature in json.loads(product.get("features") or "[]")
                          if not re.search(r"25\s*x", feature, re.I)]
    inherited_specs = {key: value for key, value in json.loads(product.get("specs_json") or "{}").items()
                       if not re.search(r"25\s*x", key + " " + value, re.I)}
    inherited_specs["Optical zoom"] = "31x"
    description = f"4K auto-tracking PTZ camera with 31x optical zoom and {('NDI' if '4KND' in sku else 'Dante AV-H' if '4KDA' in sku else 'HDMI/SDI/USB')} connectivity."
    product.update(
        id=sku, name=title, title=title, price_usd=_price(item.findtext(G + "price")),
        stock_status=("Out of Stock" if (item.findtext(G + "availability") or "").lower() in {"out_of_stock", "out of stock"} else "In Stock"),
        product_url=item.findtext("link"),
        image_url=item.findtext(G + "image_link"),
        additional_images=json.dumps([e.text for e in item.findall(G + "additional_image_link") if e.text]),
        description=description,
        features=json.dumps(["31x optical zoom"] + (page["features"] or inherited_features)[:19]),
        specs_json=json.dumps(page["specs"] or inherited_specs),
        what_it_does=description,
        manual_file=None, scraped=1,
    )
    interface.update(sku=sku, zoom_optical=31, extracted_at=datetime.now(timezone.utc).isoformat())
    if interface.get("notes"):
        interface["notes"] = re.sub(r"25\s*x", "31x", interface["notes"], flags=re.I)
    return product, interface


def _insert(conn: sqlite3.Connection, table: str, data: dict) -> None:
    allowed = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    fields = [field for field in data if field in allowed]
    placeholders = ",".join("?" for _ in fields)
    conn.execute(f"INSERT INTO {table} ({','.join(fields)}) VALUES ({placeholders})", [data[field] for field in fields])


def sync(db_path: str, feed_url: str = FEED_URL, apply: bool = False, backup_dir: str | None = None) -> dict:
    items = _feed_items(feed_url)
    if len(items) < 200:
        raise ValueError(f"Shopping feed unexpectedly small: {len(items)} SKUs")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    existing = {row[0].upper() for row in conn.execute("SELECT id FROM products")}
    aliases = sorted(sku for sku in items if sku not in existing and _camera_alias(sku, existing))
    new = sorted(set(items) - existing - set(aliases))
    unreviewed = sorted(set(new) - APPROVED)
    approved = sorted(set(new) & APPROVED)
    result = {"feed_items": len(items), "new_reviewed": approved, "existing_variant_aliases": aliases,
              "unreviewed": unreviewed, "inserted": []}
    if not apply:
        conn.close()
        return result
    if not approved:
        conn.close()
        return result
    if not backup_dir:
        conn.close()
        raise ValueError("--backup-dir is required with --apply")

    # Gather and validate all source data before backing up or writing.
    pages = {}
    prepared = []
    for sku in approved:
        item = items[sku]
        url = item.findtext("link") or ""
        if not url.startswith("https://bzbgear.com/product/"):
            raise ValueError(f"Unexpected product URL for {sku}: {url}")
        page_key = url.split("?", 1)[0]
        if page_key not in pages:
            pages[page_key] = _page_data(url)
        page = pages[page_key]
        if sku not in CAMERA_31X and len(page["specs"]) < 5:
            raise ValueError(f"Insufficient website specifications for {sku}")
        if sku in CAMERA_31X:
            prepared.append(_camera_variant(conn, sku, item, page))
        else:
            prepared.append((_reviewed_product(sku, item, page, PROFILES[sku]), _base_interface(sku, PROFILES[sku])))

    backup_path = Path(backup_dir) / f"products-pre-sync-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.db"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup_path) as backup_conn:
        conn.backup(backup_conn)
    try:
        conn.execute("BEGIN IMMEDIATE")
        for product, interface in prepared:
            _insert(conn, "products", product)
            _insert(conn, "product_interfaces", interface)
            result["inserted"].append(product["id"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    result["backup"] = str(backup_path)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="products.db")
    parser.add_argument("--feed-url", default=FEED_URL)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir")
    args = parser.parse_args()
    print(json.dumps(sync(args.db, args.feed_url, args.apply, args.backup_dir), indent=2))
