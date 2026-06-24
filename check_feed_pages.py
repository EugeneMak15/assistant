import sys; sys.stdout.reconfigure(encoding='utf-8')
import truststore; truststore.inject_into_ssl()
import requests, xml.etree.ElementTree as ET, time

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

# Check how many pages the product feed has
all_ids = []
for page in range(1, 40):
    url = f"https://bzbgear.com/product-feed/?paged={page}"
    try:
        r = S.get(url, timeout=20)
        if r.status_code != 200 or len(r.content) < 500:
            print(f"Page {page}: stopped (status {r.status_code})")
            break
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
        if not items:
            print(f"Page {page}: no items - end of feed")
            break
        ids = []
        for item in items:
            pid = item.findtext("{http://base.google.com/ns/1.0}id") or item.findtext("id") or ""
            ids.append(pid)
        all_ids.extend(ids)
        print(f"Page {page}: {len(items)} products - {', '.join(ids[:3])}...")
        time.sleep(0.5)
    except Exception as e:
        print(f"Page {page}: ERROR {e}")
        break

print(f"\nTotal unique products: {len(set(all_ids))}")
