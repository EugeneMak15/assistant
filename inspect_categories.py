import sys; sys.stdout.reconfigure(encoding='utf-8')
import truststore; truststore.inject_into_ssl()
import requests, xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0"})
r = S.get("https://bzbgear.com/product-feed/", timeout=30)
root = ET.fromstring(r.content)
items = root.findall(".//item")

print(f"Total items: {len(items)}")
print()

# Find items WITH categories
print("=== ITEMS WITH <categories> CONTENT ===")
found = 0
for item in items:
    cat_el = item.find("categories")
    cat = (cat_el.text or "").strip() if cat_el is not None else ""
    if cat:
        pid = item.findtext("id")
        print(f"  {pid}: {cat[:100]}")
        found += 1
    if found >= 20:
        break

print(f"\nTotal with categories: {sum(1 for i in items if (i.findtext('categories') or '').strip())}")

# Check status field
print("\n=== STATUS FIELD SAMPLES ===")
statuses = set()
for item in items[:50]:
    s = item.findtext("status") or ""
    if s: statuses.add(s)
print(statuses)

# Check specs of a few products to understand what data is there
print("\n=== SPECS SAMPLE (BG-4K-88MA) ===")
for item in items:
    if item.findtext("id") == "BG-4K-88MA":
        specs_html = item.findtext("specifications") or ""
        soup = BeautifulSoup(specs_html, "lxml")
        for row in soup.find_all("tr")[:15]:
            cells = row.find_all(["td","th"])
            if len(cells) >= 2:
                print(f"  {cells[0].get_text(strip=True):35} = {cells[1].get_text(strip=True)}")
        break

# Show features sample
print("\n=== FEATURES SAMPLE (BG-4K-88MA) ===")
for item in items:
    if item.findtext("id") == "BG-4K-88MA":
        feat_html = item.findtext("features") or ""
        soup = BeautifulSoup(feat_html, "lxml")
        for li in soup.find_all("li")[:10]:
            print(f"  • {li.get_text(strip=True)[:100]}")
        break
