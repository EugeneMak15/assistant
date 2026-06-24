import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3, json

conn = sqlite3.connect("products.db")
conn.row_factory = sqlite3.Row

# Check specific products
for pid in ["BG-4K-88MA", "BG-EXH-70C4", "BG-ADAMO-4K", "BG-MC-8080M"]:
    row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if row:
        d = dict(row)
        print(f"\n{'='*60}")
        print(f"ID:          {d['id']}")
        print(f"Title:       {d['title'][:80]}")
        print(f"Category:    {d['category']}")
        print(f"Price:       ${d['price_usd']}")
        print(f"Status:      {d['stock_status']}")
        print(f"In x Out:    {d['inputs']} x {d['outputs']}")
        print(f"Resolutions: {d['resolutions']}")
        print(f"Bandwidth:   {d['max_bandwidth_gbps']} Gbps")
        print(f"Distance:    {d['max_distance_m']} m")
        specs = json.loads(d['specs_json'] or '{}')
        print(f"Specs keys:  {list(specs.keys())[:6]}")
        features = json.loads(d['features'] or '[]')
        print(f"Features:    {len(features)} items, first: {features[0][:60] if features else 'none'}")
        print(f"Manual:      {d['manual_url']}")
    else:
        print(f"\n{pid}: NOT FOUND")

# Show "other" category to fix
print("\n\n=== OTHER CATEGORY (need fixing) ===")
for row in conn.execute("SELECT id, title, category FROM products WHERE category='other' ORDER BY id"):
    print(f"  {row['id']:30} {row['title'][:60]}")

conn.close()
