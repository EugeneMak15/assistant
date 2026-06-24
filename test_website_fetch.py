import sys; sys.stdout.reconfigure(encoding='utf-8')
import truststore; truststore.inject_into_ssl()
from urllib.request import urlopen, Request
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

test_urls = [
    ("faq",            "https://bzbgear.com/blog/faq_item/what-is-a-capture-card-do-i-need-one/"),
    ("faq",            "https://bzbgear.com/blog/faq_item/which-type-of-video-output-should-i-use-on-my-camera/"),
    ("knowledge_base", "https://bzbgear.com/blog/knowledge_base/what-is-hdbaset/"),
    ("case_study",     "https://bzbgear.com/case-studies/"),
    ("blog",           "https://bzbgear.com/blog/how-to-set-up-a-multi-camera-live-streaming-studio/"),
]

for doc_type, url in test_urls:
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")

        if "cf-browser-verification" in html or "Just a moment" in html:
            print(f"  [BLOCKED] {url}")
            continue

        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script","style","nav","header","footer","aside"]):
            tag.decompose()

        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else "No H1"

        for sel in ["article", "main", ".entry-content", ".post-content", "body"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(separator=" ", strip=True)
                text = " ".join(text.split())
                break

        print(f"\n[{doc_type}] {url[-60:]}")
        print(f"  Title: {title}")
        print(f"  Text length: {len(text)} chars")
        print(f"  Preview: {text[:200]}")

    except Exception as e:
        print(f"  ERROR {url}: {e}")
