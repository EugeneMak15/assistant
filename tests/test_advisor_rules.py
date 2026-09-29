"""Regressions from the September 2026 advisor review."""

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


try:
    import openai  # noqa: F401
except ImportError:
    sys.modules["openai"] = types.SimpleNamespace(OpenAI=object)

from api.scenario_planner import _find_matching_skus_for_flow_a
from api.product_rules import camera_family_variants
from api import db


class AdvisorRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.DB_PATH = Path(__file__).resolve().parents[1] / "products.db"

    def test_8k_four_sources_one_tv(self):
        skus = _find_matching_skus_for_flow_a(
            ["switcher"], {},
            "I have four HDMI sources, two at 8K/4K120, and 1 TV. Need a switcher.",
        )
        self.assertEqual(skus[:3], ["BG-8K-HS41", "BG-8K-HS41A", "BG-8K-HS41AR"])
        self.assertIn("BG-8K-42MA", skus)
        self.assertNotIn("BG-UHD-MVS42MA", skus)
        self.assertNotIn("BG-PSC7X2", skus)
        self.assertNotIn("BG-8K-HS21A", skus)

    def test_explicit_8k_excludes_4k_partial_cards(self):
        skus = _find_matching_skus_for_flow_a(
            ["switcher"], {}, "Need a 4x1 switcher with 8K compatibility."
        )
        self.assertTrue(skus)
        self.assertTrue(all("8K" in sku for sku in skus))

    def test_ndi_variant_of_streaming_encoder(self):
        skus = _find_matching_skus_for_flow_a(
            ["streaming encoder"], {}, "Need a 1080p60 streaming encoder with NDI output."
        )
        self.assertIn("BG-STREAM-NE", skus)
        self.assertNotIn("BG-STREAM-E", skus)

    def test_4k_ndi_excludes_1080p_encoder(self):
        skus = _find_matching_skus_for_flow_a(
            ["streaming encoder"], {}, "Need 4K HDMI to NDI streaming encoder."
        )
        self.assertNotIn("BG-STREAM-NE", skus)

    def test_nutrix_is_medical_only(self):
        general = _find_matching_skus_for_flow_a(
            ["ptz camera"], {}, "Need a PTZ camera for a conference room."
        )
        medical = _find_matching_skus_for_flow_a(
            ["ptz camera"], {}, "Need a PTZ camera for a medical clinic."
        )
        self.assertNotIn("BG-NUTRIX", general)
        self.assertIn("BG-NUTRIX", medical)

    def test_sanity_filter_cannot_restore_hard_mismatch(self):
        from api.universal_engine import _sanity_filter_candidates

        perfect, partial = _sanity_filter_candidates(
            ["BG-UHD-42M", "BG-8K-HS41"], ["switcher"], {}, {},
            "Need a 4x1 switcher with 8K compatibility.",
        )
        self.assertEqual(perfect + partial, ["BG-8K-HS41"])

    def test_classifier_failure_does_not_restore_4k_products(self):
        from api import universal_engine

        with patch.object(universal_engine, "OpenAI", side_effect=RuntimeError("offline")):
            perfect, partial = universal_engine._sanity_filter_candidates(
                ["BG-UHD-42M", "BG-8K-HS41", "BG-8K-HS41A"],
                ["switcher"], {}, {}, "Need a 4x1 8K switcher.",
            )
        self.assertNotIn("BG-UHD-42M", perfect + partial)
        self.assertEqual(set(perfect + partial), {"BG-8K-HS41", "BG-8K-HS41A"})

    def test_camera_family_keeps_signal_type_and_lists_colors(self):
        conn = db.get_conn()
        variants = camera_family_variants(conn, "BG-ADAMO-4KND12X-B")
        conn.close()
        skus = {item["id"] for item in variants}
        self.assertIn("BG-ADAMO-4KND12X-W", skus)
        self.assertIn("BG-ADAMO-4KND25X-B", skus)
        self.assertNotIn("BG-ADAMO-4KDA12X-B", skus)


if __name__ == "__main__":
    unittest.main()
