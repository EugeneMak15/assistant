"""Reviewed products present in BZBGEAR's full product feed, not Shopping XML."""

import re
import logging
import urllib.request
import xml.etree.ElementTree as ET

from lxml import html


SITE_FEED_URL = "https://bzbgear.com/product-feed/"
REVIEWED_SITE_SKUS = {
    "BG-8K-KVM21A", "BG-USM-44", "BG-8K-28A", "BG-8K-24A",
    "BG-PSC51-4K", "BG-UHD-VWP110L", "BG-USW-24",
    "BG-USX-B100BC", "BG-USX-B100CH", "BG-USX-WP100BC", "BG-USX-WP150HC",
}


def _feed_root(data: bytes) -> ET.Element:
    # The site sometimes appends a Cloudflare script after the RSS document.
    end = data.find(b"</rss>")
    if end < 0:
        raise ValueError("Full product feed has no closing RSS tag")
    root = ET.fromstring(data[:end + len(b"</rss>")])
    if len(root.findall(".//item")) < 200:
        raise ValueError("Full product feed unexpectedly small")
    return root


def _site_price(value: str) -> float | None:
    # Sale markup contains both original and current prices; the last amount
    # is the current price on the public product page.
    amounts = re.findall(r"\$\s*([\d,]+(?:\.\d+)?)", value or "")
    if not amounts:
        amounts = re.findall(r"[\d,]+(?:\.\d+)?", value or "")
    return float(amounts[-1].replace(",", "")) if amounts else None


def parse_site_availability(data: bytes) -> dict[str, dict]:
    """Use the complete site feed for eligibility, including mixed-case SKUs."""
    products = {}
    status_map = {
        "Available": "in_stock", "In Stock": "in_stock", "Limited Stock": "in_stock",
        "Pre-Order": "preorder", "Shipping Soon": "preorder", "Backordered": "preorder",
        "Out of Stock": "out_of_stock", "Discontinued": "discontinued",
    }
    for item in _feed_root(data).findall(".//item"):
        sku = (item.findtext("id") or "").strip().upper()
        status = (item.findtext("status") or "").strip()
        if not sku or sku in products or status not in status_map:
            raise ValueError(f"Invalid full-feed SKU/status: {sku}: {status!r}")
        categories = [(node.text or "").strip() for node in item.findall("./categories/category")]
        category = next((path for path in categories if path != "New Arrivals"), "")
        products[sku] = {
            "availability": status_map[status],
            "price": _site_price(item.findtext("price") or ""),
            "product_type": category,
            "description": item.findtext("description") or "",
            "link": item.findtext("link") or "",
        }
    return products


def parse_shipping_estimate(page_data: bytes) -> str | None:
    """Read only the product-page shipping badge, never infer an ETA."""
    page = html.fromstring(page_data)
    for badge in page.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' mark_label ')]"):
        label = " ".join(badge.text_content().split())
        if re.fullmatch(r"Shipping\s+[A-Za-z0-9 ,/-]{2,60}", label, re.I):
            return label
    return None


def parse_site_feed(data: bytes, skus: set[str] = REVIEWED_SITE_SKUS) -> dict[str, dict]:
    items = _feed_root(data).findall(".//item")
    found = {}
    for item in items:
        sku = (item.findtext("id") or "").strip().upper()
        if sku not in skus:
            continue
        if sku in found:
            raise ValueError(f"Duplicate full-feed SKU: {sku}")
        link = (item.findtext("link") or "").strip()
        if not link.startswith("https://bzbgear.com/product/"):
            raise ValueError(f"Unexpected product URL for {sku}: {link}")
        status = (item.findtext("status") or "").strip()
        if status not in {"Available", "Pre-Order", "Out of Stock", "Discontinued"}:
            raise ValueError(f"Unknown full-feed status for {sku}: {status!r}")
        category_paths = [(node.text or "").strip() for node in item.findall("./categories/category")]
        features_html = html.fromstring("<div>" + (item.findtext("features") or "") + "</div>")
        features = [" ".join(node.text_content().split()) for node in features_html.xpath(".//li")]
        specs_html = html.fromstring("<div>" + (item.findtext("specifications") or "") + "</div>")
        specs = {}
        for row in specs_html.xpath(".//tr"):
            cells = row.xpath("./th|./td")
            if len(cells) >= 2:
                key, value = (" ".join(cell.text_content().split()) for cell in cells[:2])
                if key and value:
                    specs[key] = value
        price = _site_price(item.findtext("price") or "")
        if price is None or len(specs) < 5:
            raise ValueError(f"Incomplete full-feed product: {sku}")
        found[sku] = {
            "sku": sku,
            "title": (item.findtext("title") or "").strip(),
            "link": link,
            "price": price,
            "status": status,
            "categories": category_paths,
            "features": features,
            "specs": specs,
            "image_url": item.findtext("image_link"),
            "additional_images": [node.text for node in item.findall("additional_image_link") if node.text],
            "manual_url": item.findtext("manual"),
            "brochure_url": item.findtext("brochure"),
        }
    missing = skus - found.keys()
    if missing:
        raise ValueError(f"Reviewed SKU missing from full product feed: {sorted(missing)}")
    return found


def fetch_site_products() -> dict[str, dict]:
    request = urllib.request.Request(SITE_FEED_URL, headers={"User-Agent": "BZBAdvisor/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        products = parse_site_feed(response.read())
    for product in products.values():
        product["shipping_estimate"] = None
        if product["status"] != "Pre-Order":
            continue
        try:
            page_request = urllib.request.Request(product["link"], headers={"User-Agent": "BZBAdvisor/1.0"})
            with urllib.request.urlopen(page_request, timeout=12) as response:
                product["shipping_estimate"] = parse_shipping_estimate(response.read())
        except Exception as exc:
            logging.getLogger(__name__).warning("Could not verify shipping estimate for %s: %s", product["sku"], exc)
    return products
