import sys; sys.stdout.reconfigure(encoding='utf-8')
import truststore; truststore.inject_into_ssl()
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

r = requests.get("https://bzbgear.com/bg-4k-88ma/", headers=HEADERS, timeout=15)
print("Status:", r.status_code)
print("Content-Type:", r.headers.get("Content-Type"))
print("Content length:", len(r.content))
print()

# Check if it's HTML
if b"<html" in r.content[:500]:
    soup = BeautifulSoup(r.content, "lxml")
    print("Title:", soup.title.string if soup.title else "none")
    print()

    # Body classes
    body = soup.find("body")
    if body:
        print("Body classes:", " ".join(body.get("class", []))[:200])
    print()

    # JSON-LD scripts
    for i, script in enumerate(soup.find_all("script", type="application/ld+json")):
        print(f"JSON-LD #{i}:", (script.string or "")[:300])
        print()

    # Breadcrumbs
    for sel in [".woocommerce-breadcrumb", "nav.breadcrumb", ".breadcrumbs"]:
        el = soup.select_one(sel)
        if el:
            print(f"Breadcrumb ({sel}):", el.get_text(" > ", strip=True)[:200])

    # Price
    for sel in [".price", ".woocommerce-Price-amount", ".amount"]:
        el = soup.select_one(sel)
        if el:
            print(f"Price ({sel}):", el.get_text(strip=True)[:50])
            break
else:
    print("NOT HTML - first 200 bytes:", r.content[:200])
