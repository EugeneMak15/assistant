import sqlite3
conn = sqlite3.connect("products.db")
fixes = [
    ("BG-STREAM-E",   "encoder_decoder"),
    ("BG-STREAM-NE",  "encoder_decoder"),
    ("BG-STREAM-D",   "encoder_decoder"),
    ("BG-STREAM-ND",  "encoder_decoder"),
    ("BG-EXM-SM5",    "audio"),
    ("BG-AVOIP1080D", "encoder_decoder"),
]
for pid, cat in fixes:
    conn.execute("UPDATE products SET category=? WHERE id=?", (cat, pid))
    print(f"  {pid} -> {cat}")
conn.commit()
remaining = conn.execute("SELECT COUNT(*) FROM products WHERE category='other'").fetchone()[0]
print(f"\nRemaining other: {remaining}")
conn.close()
