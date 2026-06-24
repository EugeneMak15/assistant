import sys; sys.stdout.reconfigure(encoding='utf-8')
import truststore; truststore.inject_into_ssl()
import requests

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0"})
r = S.get("https://bzbgear.com/product-feed/", timeout=30)

# Show first 3000 chars of raw XML
text = r.text
print(text[:3000])
print("\n...\n")
# Find first item and show its full content
start = text.find("<item>")
end = text.find("</item>") + 7
if start > 0:
    print("=== FIRST ITEM ===")
    print(text[start:end][:4000])
