import sqlite3

conn = sqlite3.connect("products.db")
cur = conn.cursor()

print("=== OTHER category ===")
for row in cur.execute("SELECT id, inputs, outputs, resolutions FROM products WHERE category='other' ORDER BY id"):
    print(row)

print("\n=== EXTENDERS sample ===")
for row in cur.execute("SELECT id, inputs, outputs, max_distance_m, resolutions FROM products WHERE category='extender' ORDER BY id LIMIT 10"):
    print(row)

print("\n=== Switchers missing inputs/outputs ===")
for row in cur.execute("SELECT id FROM products WHERE category='switcher' AND (inputs IS NULL OR outputs IS NULL) LIMIT 10"):
    print(row)

print("\n=== Total with inputs+outputs parsed ===")
cur.execute("SELECT COUNT(*) FROM products WHERE inputs IS NOT NULL AND outputs IS NOT NULL")
print(cur.fetchone())

conn.close()
