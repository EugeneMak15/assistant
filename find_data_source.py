import sys; sys.stdout.reconfigure(encoding='utf-8')
import truststore; truststore.inject_into_ssl()
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
S = requests.Session(); S.headers.update(HEADERS)

urls_to_try = [
    # WooCommerce REST API
    "https://bzbgear.com/wp-json/wc/v3/products?per_page=10",
    "https://bzbgear.com/wp-json/wc/v3/products?per_page=5&consumer_key=&consumer_secret=",
    # Alternative feeds
    "https://bzbgear.com/?feed=products",
    "https://bzbgear.com/product-feed/?numberposts=-1",
    "https://bzbgear.com/product-feed/?posts_per_page=500",
    # Sitemap is XML - check if it has data
    "https://bzbgear.com/product-sitemap.xml",
    "https://bzbgear.com/product_cat-sitemap.xml",
    # Google shopping feed
    "https://bzbgear.com/google-product-feed/",
    "https://bzbgear.com/feed/products/",
]

for url in urls_to_try:
    try:
        r = S.get(url, timeout=8)
        ct = r.headers.get("Content-Type","")
        preview = r.content[:200]
        is_html = b"<html" in preview
        is_xml = b"<?xml" in preview or b"<rss" in preview
        is_json = preview.strip().startswith(b"[") or preview.strip().startswith(b"{")
        is_png = preview.startswith(b"\x89PNG")

        tag = "HTML" if is_html else "XML" if is_xml else "JSON" if is_json else "PNG" if is_png else "???"
        print(f"[{r.status_code}] {tag:5} {url[:70]}")
        if is_json or is_xml:
            print(f"       Preview: {r.text[:300]}")
    except Exception as e:
        print(f"[ERR] {url[:70]} -- {e}")
