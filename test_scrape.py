import sys; sys.stdout.reconfigure(encoding='utf-8')
import truststore; truststore.inject_into_ssl()
from scrape_catalog import scrape_product_page, pid_from_url

test_urls = [
    "https://bzbgear.com/bg-4k-88ma/",
    "https://bzbgear.com/bg-exh-70c4/",
    "https://bzbgear.com/bg-adamo-4k/",
]

for url in test_urls:
    print(f"\n{'='*60}")
    print(f"URL: {url}")
    data = scrape_product_page(url)
    for k, v in data.items():
        if v:
            val = str(v)[:120]
            print(f"  {k:20} = {val}")
