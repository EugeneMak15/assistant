"""Read-only comparison of product rows against verified pre-audit backup."""
import sqlite3

before = sqlite3.connect("/opt/assistant/backups/products-before-new-products-20261105.db")
after = sqlite3.connect("/opt/assistant/products.db")
before.row_factory = after.row_factory = sqlite3.Row
assert before.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert after.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
old = {r["id"]: dict(r) for r in before.execute("SELECT * FROM products")}
new = {r["id"]: dict(r) for r in after.execute("SELECT * FROM products")}
assert old.keys() == new.keys()
for sku in sorted(old):
    fields = [field for field in old[sku] if old[sku][field] != new[sku][field]]
    if fields:
        print(sku, ",".join(fields))
print("product_count", len(new))
