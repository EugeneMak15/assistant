"""The shopping feed controls advisor catalog eligibility and displayed prices."""

import sqlite3
import unittest
import xml.etree.ElementTree as ET

from refresh_catalog_availability import plan_updates
from sync_catalog_feed import G, _feed_price


class CatalogAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""CREATE TABLE products (
            id TEXT PRIMARY KEY, category TEXT, stock_status TEXT, site_category TEXT, price_usd REAL,
            inputs INTEGER, outputs INTEGER, max_distance_m INTEGER, what_it_does TEXT
        )""")
        self.conn.executemany("INSERT INTO products (id, stock_status, site_category, price_usd) VALUES (?, ?, ?, ?)", [
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

    def test_sale_price_takes_priority_over_regular_feed_price(self):
        item = ET.fromstring(
            '<item xmlns:g="http://base.google.com/ns/1.0">'
            '<g:price>599.00 USD</g:price><g:sale_price>349.00 USD</g:sale_price></item>'
        )
        self.assertEqual(_feed_price(item), 349.0)

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

    def test_feed_supported_spec_repair(self):
        self.conn.execute("INSERT INTO products (id, stock_status, max_distance_m) VALUES (?, ?, ?)",
                          ("BG-EXH-8KF", "In Stock", 40))
        feed = {"BG-EXH-8KF": {
            "availability": "in_stock", "product_type": "Signal Extenders", "price": 999.0,
            "description": "Long Distance Extend your 8K signal up to 300M",
        }}
        result = plan_updates(self.conn, feed)
        self.assertEqual(result["corrected_specs"], ["BG-EXH-8KF"])
        self.assertEqual(result["spec_updates"][0][2], 300)

    def test_audio_converter_misclassified_as_sdi_is_corrected(self):
        self.conn.execute("INSERT INTO products (id, category, stock_status) VALUES (?, ?, ?)",
                          ("BG-8K-AE", "sdi", "In Stock"))
        feed = {"BG-8K-AE": {
            "availability": "in_stock", "product_type": "Audio > Audio Converters", "price": 199.0,
        }}
        self.assertEqual(plan_updates(self.conn, feed)["category_updates"], [("audio", "BG-8K-AE")])


if __name__ == "__main__":
    unittest.main()
