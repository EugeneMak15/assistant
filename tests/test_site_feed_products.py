"""The reviewed full-site feed is an explicit exception to Shopping XML."""

import sqlite3
import tempfile
from pathlib import Path
import unittest

from site_feed_products import parse_site_feed
from sync_site_products import sync
from api.product_rules import hard_mismatch


class SiteFeedProductTests(unittest.TestCase):
    def test_parse_reviewed_items_and_ignore_trailing_script(self):
        filler = "<item><id>OTHER</id></item>" * 200
        reviewed = "".join(
            f"<item><id>{sku}</id><title>{sku}</title>"
            f"<link>https://bzbgear.com/product/{sku.lower()}/</link>"
            f"<price>$599.00</price><status>{status}</status>"
            "<categories><category>Video Switchers &gt; KVM Switches</category></categories>"
            "<features><![CDATA[<ul><li>USB switching</li></ul>]]></features>"
            "<specifications><![CDATA[<table>"
            + "".join(f"<tr><td>Spec {n}</td><td>Value {n}</td></tr>" for n in range(5))
            + "</table>]]></specifications></item>"
            for sku, status in (("BG-8K-KVM21A", "Available"),
                                ("BG-USM-44", "Pre-Order"), ("BG-8K-28A", "Pre-Order"))
        )
        products = parse_site_feed(("<rss><channel>" + filler + reviewed + "</channel></rss><script/>").encode())
        self.assertEqual(set(products), {"BG-8K-KVM21A", "BG-USM-44", "BG-8K-28A"})
        self.assertEqual(products["BG-USM-44"]["status"], "Pre-Order")
        self.assertEqual(len(products["BG-8K-28A"]["specs"]), 5)

    def test_sync_inserts_two_and_repairs_existing_kvm(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "products.db")
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE products (id TEXT PRIMARY KEY, category TEXT, stock_status TEXT, inputs INTEGER, outputs INTEGER, price_usd REAL, site_category TEXT, product_url TEXT)")
                conn.execute("CREATE TABLE product_interfaces (sku TEXT PRIMARY KEY, max_res TEXT, primary_fn TEXT, in_hdmi_count INTEGER, out_hdmi_count INTEGER, ctrl_ip INTEGER)")
                conn.execute("INSERT INTO products(id, stock_status) VALUES ('BG-8K-KVM21A', 'Not in Feed')")
                conn.execute("INSERT INTO product_interfaces(sku,max_res,primary_fn,ctrl_ip) VALUES ('BG-8K-KVM21A','8K30','splitter',1)")
                conn.commit()
            finally:
                conn.close()

            products = {}
            for sku, status, category in (
                ("BG-8K-KVM21A", "Available", "Video Switchers > KVM Switches"),
                ("BG-USM-44", "Pre-Order", "Video Switchers > Matrix Switchers"),
                ("BG-8K-28A", "Pre-Order", "Splitters / Amplifiers > HDMI Splitters"),
            ):
                products[sku] = {"title": sku, "link": f"https://bzbgear.com/product/{sku.lower()}/",
                                 "price": 599.0, "status": status, "categories": [category],
                                 "features": ["Reviewed"], "specs": {"Bandwidth": "48Gbps"},
                                 "image_url": None, "additional_images": [], "manual_url": None,
                                 "brochure_url": None}
            result = sync(db_path, apply=True, backup_dir=directory, site_products=products)
            self.assertEqual(result["insert"], ["BG-8K-28A", "BG-USM-44"])
            self.assertTrue(Path(result["backup"]).exists())
            conn = sqlite3.connect(db_path)
            try:
                self.assertEqual(conn.execute("SELECT count(*) FROM products").fetchone()[0], 3)
                self.assertEqual(conn.execute("SELECT stock_status FROM products WHERE id='BG-USM-44'").fetchone()[0], "Pre-Order")
                self.assertEqual(conn.execute("SELECT max_res,primary_fn,ctrl_ip FROM product_interfaces WHERE sku='BG-8K-KVM21A'").fetchone(), ("8K60", "kvm-switcher", 0))
            finally:
                conn.close()

    def test_usb_matrix_is_not_a_video_kvm(self):
        product = {"id": "BG-USM-44", "name": "USB 3.2 matrix", "category": "kvm_switch",
                   "stock_status": "Pre-Order"}
        self.assertEqual(hard_mismatch(product, {}, "Need HDMI KVM for two monitors"),
                         "USB-only matrix does not route video")
        self.assertIsNone(hard_mismatch(product, {}, "Share USB peripherals between computers"))


if __name__ == "__main__":
    unittest.main()
