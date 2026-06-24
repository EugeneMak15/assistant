import sys; sys.stdout.reconfigure(encoding='utf-8')
import truststore; truststore.inject_into_ssl()
import requests, xml.etree.ElementTree as ET

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0"})
r = S.get("https://bzbgear.com/product-feed/", timeout=30)
root = ET.fromstring(r.content)
items = root.findall(".//item")

# Show ALL tags in first item
item = items[0]
print(f"=== ALL TAGS IN FIRST ITEM ({item.findtext('id')}) ===")
for child in item:
    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
    text = (child.text or "").strip()[:200]
    print(f"  <{tag}>: {text}")

# Find items with product_type
print("\n=== CATEGORY SAMPLE (first 15 with product_type) ===")
count = 0
for item in items:
    cat = item.findtext("product_type") or item.findtext("category")
    pid = item.findtext("id")
    if cat:
        print(f"  {pid}: {cat}")
        count += 1
    if count >= 15:
        break

# Count how many have each field
print("\n=== FIELD COVERAGE ===")
fields = ["id","title","price","product_type","features","specifications","availability","image_link","link","weight"]
for f in fields:
    cnt = sum(1 for item in items if item.findtext(f))
    print(f"  {f:20}: {cnt}/{len(items)}")
