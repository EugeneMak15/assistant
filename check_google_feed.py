import sys; sys.stdout.reconfigure(encoding='utf-8')
import truststore; truststore.inject_into_ssl()
import requests, xml.etree.ElementTree as ET

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0"})

r = S.get("https://bzbgear.com/google-product-feed/", timeout=30)
print("Status:", r.status_code, "  Size:", len(r.content), "bytes")

root = ET.fromstring(r.content)
items = root.findall(".//item")
print(f"Products in feed: {len(items)}")
print()

# Show namespaces
ns_map = {}
for k, v in root.attrib.items():
    if "xmlns" in k:
        ns_map[k] = v
print("Namespaces:", list(root.attrib.keys())[:5])
print()

# Show first item fields
if items:
    item = items[0]
    print("=== First product fields ===")
    for child in item:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        val = (child.text or "").strip()[:120]
        if val:
            print(f"  {tag:25} = {val}")
    print()
    print("=== Sample categories ===")
    cats = set()
    for item in items[:50]:
        for el in item:
            tag = el.tag.split("}")[-1]
            if tag in ("product_type", "google_product_category"):
                if el.text:
                    cats.add(el.text.strip()[:80])
    for c in sorted(cats):
        print(f"  {c}")
