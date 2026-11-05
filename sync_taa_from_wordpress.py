"""Synchronize the advisor's TAA flag from the WooCommerce product admin field."""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path


APP_DIR = Path("/opt/assistant")
WP_DIR = Path("/var/www/bzbprod/data/www/bzbgear.com")
DB_PATH = APP_DIR / "products.db"

# Hex literals keep this safe to pass through wp-cli without shell quoting.
TAA_SKU_SQL = """
SELECT DISTINCT sku.meta_value
FROM wp_posts p
JOIN wp_postmeta taa
  ON taa.post_id=p.ID
 AND taa.meta_key=0x7461615f636f6d706c69616e74
 AND taa.meta_value=0x31
JOIN wp_postmeta sku
  ON sku.post_id=p.ID
 AND sku.meta_key=0x5f736b75
WHERE p.post_type=0x70726f64756374
  AND p.post_status=0x7075626c697368
  AND sku.meta_value<>''
""".strip()


def wordpress_taa_skus() -> set[str]:
    proc = subprocess.run(
        ["wp", "db", "query", TAA_SKU_SQL, "--skip-column-names", "--allow-root"],
        cwd=WP_DIR,
        text=True,
        capture_output=True,
        check=True,
    )
    return {line.strip().upper() for line in proc.stdout.splitlines() if line.strip()}


def sync() -> tuple[int, int, list[str]]:
    admin_skus = wordpress_taa_skus()
    if len(admin_skus) < 40:
        raise RuntimeError(f"Refusing suspicious TAA sync: only {len(admin_skus)} admin SKUs")

    conn = sqlite3.connect(DB_PATH)
    try:
        catalog_skus = {row[0].upper() for row in conn.execute("SELECT id FROM products")}
        matched = sorted(admin_skus & catalog_skus)
        missing = sorted(admin_skus - catalog_skus)
        if len(matched) < 40:
            raise RuntimeError(f"Refusing suspicious TAA sync: only {len(matched)} catalog matches")
        with conn:
            conn.execute("UPDATE products SET taa_compliant=0")
            conn.executemany(
                "UPDATE products SET taa_compliant=1 WHERE UPPER(id)=?",
                [(sku,) for sku in matched],
            )
    finally:
        conn.close()
    return len(admin_skus), len(matched), missing


if __name__ == "__main__":
    total, matched, missing = sync()
    print(f"TAA admin SKUs: {total}; indexed: {matched}; absent from advisor catalog: {len(missing)}")
    if missing:
        print("Missing: " + ", ".join(missing))
