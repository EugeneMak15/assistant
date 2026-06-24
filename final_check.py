import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3, json

conn = sqlite3.connect("products.db")

print("=== REMAINING OTHER ===")
for r in conn.execute("SELECT id, title FROM products WHERE category='other'"):
    print(f"  {r[0]}: {r[1][:70]}")

print("\n=== FINAL CATEGORY TOTALS ===")
for r in conn.execute("SELECT category, COUNT(*) n FROM products GROUP BY category ORDER BY n DESC"):
    print(f"  {r[0]:<25} {r[1]}")

print("\n=== SAMPLE DATA CHECK ===")
for pid in ["BG-4K-88MA", "BG-IPGEAR-XTREME-CORE", "BG-STUDIO-ELITE-N-B"]:
    r = conn.execute("SELECT id,category,site_category,site_subcategory,price_usd,stock_status,inputs,outputs,max_distance_m FROM products WHERE id=?", (pid,)).fetchone()
    if r:
        print(f"\n  {r[0]}")
        print(f"    category: {r[1]}  site: {r[2]} > {r[3]}")
        print(f"    price: ${r[4]}  status: {r[5]}")
        print(f"    ports: {r[6]}x{r[7]}  dist: {r[8]}m")

print("\n=== FIELDS WITH GOOD COVERAGE ===")
for col in ["price_usd","features","specs_json","image_url","manual_url","resolutions","input_signals"]:
    cnt = conn.execute(f"SELECT COUNT(*) FROM products WHERE {col} IS NOT NULL AND {col} != '' AND {col} != '[]' AND {col} != '{{}}'").fetchone()[0]
    print(f"  {col:<20} {cnt}/429")

conn.close()
