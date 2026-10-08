"""The shopping feed controls advisor catalog eligibility and displayed prices."""

import sqlite3
import unittest

from refresh_catalog_availability import plan_updates


class CatalogAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""CREATE TABLE products (
            id TEXT PRIMARY KEY, stock_status TEXT, site_category TEXT, price_usd REAL
        )""")
        self.conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", [
            ("BG-COMMANDER", "Out of Stock", "Joystick Controllers", 349.0),
            ("BG-DA-14", "In Stock", "Splitters / Amplifiers", 62.0),
        ])

    def tearDown(self):
        self.conn.close()

    def test_stocked_eol_stays_available_and_uses_feed_price(self):
        feed = {"BG-COMMANDER": {
            "availability": "in_stock", "product_type": "Joystick Controllers", "price": 599.0,
        }}
        changes = plan_updates(self.conn, feed)
        self.assertIn(("In Stock", "Joystick Controllers", 599.0, "BG-COMMANDER"), changes["updates"])

    def test_missing_from_feed_is_excluded_without_deletion(self):
        changes = plan_updates(self.conn, {})
        self.assertIn(("Not in Feed", "Splitters / Amplifiers", 62.0, "BG-DA-14"), changes["updates"])
        self.assertIn("BG-DA-14", changes["missing_from_feed"])

    def test_explicit_out_of_stock(self):
        feed = {"BG-DA-14": {
            "availability": "out_of_stock", "product_type": "Discontinued", "price": 62.0,
        }}
        changes = plan_updates(self.conn, feed)
        self.assertIn(("Out of Stock", "Discontinued", 62.0, "BG-DA-14"), changes["updates"])

    def test_new_sku_for_review(self):
        feed = {"NEW-SKU": {
            "availability": "in_stock", "product_type": "Cameras", "price": 100.0,
        }}
        self.assertEqual(plan_updates(self.conn, feed)["new_skus_for_review"], ["NEW-SKU"])


if __name__ == "__main__":
    unittest.main()
