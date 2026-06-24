import sys; sys.stdout.reconfigure(encoding='utf-8')
import truststore; truststore.inject_into_ssl()
from dotenv import load_dotenv; load_dotenv()
from api.layer2 import semantic_search_products

queries = [
    "PTZ camera SDI 4K broadcast studio",
    "conference room presentation switcher HDMI laptop",
    "HDMI extender 70 meters Cat6 4K60",
    "video wall 4 displays multiviewer",
    "PTZ camera controller joystick NDI",
]

for q in queries:
    results = semantic_search_products(q, n=5)
    print(f"\nQuery: {q}")
    for r in results:
        pid = r['id']
        score = r['score']
        cat = r['category']
        sigs = r['input_signals']
        print(f"  {pid:<38} score={score:.3f}  cat={cat}  sigs={sigs}")
