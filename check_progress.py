import sqlite3
conn = sqlite3.connect("products.db")
total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
done = conn.execute("SELECT COUNT(*) FROM products WHERE what_it_does IS NOT NULL AND what_it_does != ''").fetchone()[0]
print(f"Enriched: {done}/{total} ({100*done//total}%)")
for r in conn.execute("SELECT id, what_it_does FROM products WHERE what_it_does IS NOT NULL ORDER BY rowid DESC LIMIT 5"):
    print(f"  {r[0]}: {(r[1] or '')[:80]}...")
conn.close()
