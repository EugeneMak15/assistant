import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3, json

import truststore; truststore.inject_into_ssl()
from dotenv import load_dotenv; load_dotenv()

# Import functions from enrich_products
from enrich_products import build_prompt, call_gpt

conn = sqlite3.connect("products.db")
conn.row_factory = sqlite3.Row

# Test on 5 varied products
test_ids = ["BG-4K-88MA", "BG-EXH-70C4", "BG-ADAMO-4K", "BG-IPGEAR-ULTRA-ACC-RM2", "BG-COMMANDER-PRO"]

for pid in test_ids:
    row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not row:
        print(f"\n{pid}: NOT FOUND")
        continue

    p = dict(row)
    prompt = build_prompt(p)
    print(f"\n{'='*60}")
    print(f"PROMPT for {pid}:")
    print(prompt[:400])
    print("\n--- GPT RESPONSE ---")
    result = call_gpt(prompt)
    print(f"What it does:\n  {result.get('what_it_does','')}")
    print(f"\nUse Cases:")
    for uc in result.get("use_cases", []):
        print(f"  • {uc}")

conn.close()
