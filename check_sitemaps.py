import sys; sys.stdout.reconfigure(encoding='utf-8')
import truststore; truststore.inject_into_ssl()
import urllib.request
import xml.etree.ElementTree as ET

sitemaps = [
    ("FAQ",          "https://bzbgear.com/faq_item-sitemap.xml"),
    ("Case Studies", "https://bzbgear.com/case-sitemap.xml"),
    ("Knowledge Base","https://bzbgear.com/knowledge_base-sitemap.xml"),
    ("Solutions",    "https://bzbgear.com/solution-sitemap.xml"),
    ("Blog Posts",   "https://bzbgear.com/post-sitemap.xml"),
]

total = 0
all_urls = []
for name, url in sitemaps:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            xml = r.read()
        root = ET.fromstring(xml)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [loc.text for loc in root.findall(".//sm:loc", ns)]
        print(f"  {name:20s}: {len(urls)} URLs")
        total += len(urls)
        all_urls.extend([(name, u) for u in urls])
    except Exception as e:
        print(f"  {name:20s}: ERROR — {e}")

print(f"\nTotal: {total} URLs")
print("\nSamples:")
for name, url in all_urls[:3]:
    print(f"  [{name}] {url}")
