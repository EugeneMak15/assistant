"""Regressions from the September 2026 advisor review."""

import json
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
from api.product_rules import camera_family_key, camera_family_variants, hard_mismatch, requested_video
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
        self.assertEqual(skus[:2], ["BG-8K-HS41A", "BG-8K-HS41AR"])
        self.assertNotIn("BG-8K-HS41", skus)  # Absent from the authoritative feed.
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

    def test_usb_peripheral_matrix_does_not_search_hdmi_matrices(self):
        examples = [
            (["usb matrix switcher"], "4x4 USB matrix switcher"),
            (["matrix switcher"], "4x4 USB matrix switcher"),
            (["usb switch"], "Four computers need to share the same USB devices, four devices total"),
        ]
        for categories, question in examples:
            with self.subTest(question=question, categories=categories):
                self.assertEqual(_find_matching_skus_for_flow_a(categories, {}, question), ["BG-USM-44"])

    def test_hdmi_kvm_long_and_short_phrasings_find_video_kvm(self):
        for categories, question in (
            (["HDMI KVM switch"], "I need an HDMI KVM switch so I can control 4 computers from one keyboard, mouse and monitor."),
            (["KVM switch"], "4-port KVM switch, HDMI, 4K, USB keyboard and mouse, one monitor."),
        ):
            with self.subTest(question=question):
                skus = _find_matching_skus_for_flow_a(categories, {}, question)
                self.assertIn("BG-UHD-KVM41A", skus)
                self.assertNotIn("BG-USM-44", skus)
                self.assertNotIn("BG-8K-KVM21A", skus)

    def test_usb_matrix_chat_to_product_card_pipeline(self):
        from api.chat import run_chat_turn
        from api.universal_engine import stream_flow_a_recommendation

        turn = run_chat_turn([], "4x4 USB matrix switcher", {})
        plan = turn["_scenario_plan"]
        skus = _find_matching_skus_for_flow_a(
            plan["requested_categories"], turn["_scenario_answers"], turn["search_query"]
        )
        self.assertEqual(skus, ["BG-USM-44"])
        stream = stream_flow_a_recommendation(
            question=turn["search_query"], candidate_skus=skus, session={},
            requested_categories=plan["requested_categories"],
            answers=turn["_scenario_answers"], plan=plan,
        )
        self.assertEqual(next(stream), ("product", "BG-USM-44", "perfect"))
        stream.close()

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
        self.assertNotIn("BG-NUTRIX", medical)  # Medical-only, but currently absent from the feed.
        stocked = {"id": "BG-NUTRIX", "name": "medical PTZ camera", "category": "camera",
                   "stock_status": "In Stock"}
        self.assertEqual(hard_mismatch(stocked, {}, "conference room"),
                         "medical-only camera outside a medical scenario")
        self.assertIsNone(hard_mismatch(stocked, {}, "medical clinic"))

    def test_out_of_stock_is_never_a_recommendation(self):
        self.assertEqual(
            hard_mismatch(
                {"id": "BG-DA-14", "name": "HDMI splitter", "stock_status": "Out of Stock"},
                None, "one HDMI input and four displays", ["splitter"],
            ),
            "product is not available for purchase",
        )

    def test_sanity_filter_cannot_restore_hard_mismatch(self):
        from api.universal_engine import _sanity_filter_candidates

        perfect, partial = _sanity_filter_candidates(
            ["BG-UHD-42M", "BG-8K-HS41A"], ["switcher"], {}, {},
            "Need a 4x1 switcher with 8K compatibility.",
        )
        self.assertEqual(perfect + partial, ["BG-8K-HS41A"])

    def test_classifier_failure_does_not_restore_4k_products(self):
        from api import universal_engine

        with patch.object(universal_engine, "OpenAI", side_effect=RuntimeError("offline")):
            perfect, partial = universal_engine._sanity_filter_candidates(
                ["BG-UHD-42M", "BG-8K-HS41A", "BG-8K-HS41AR"],
                ["switcher"], {}, {}, "Need a 4x1 8K switcher.",
            )
        self.assertNotIn("BG-UHD-42M", perfect + partial)
        self.assertEqual(set(perfect + partial), {"BG-8K-HS41A", "BG-8K-HS41AR"})

    def test_camera_and_switcher_both_survive_multi_device_filter(self):
        from api import universal_engine

        question = "Four 4K HDMI PTZ cameras with 12x zoom and a four-input production switcher"
        candidates = ["BG-ADAMO-4K12X-B", "BG-QUADFUSION-4K", "BG-8K-HS41"]
        with patch.object(universal_engine, "OpenAI", side_effect=RuntimeError("offline")):
            perfect, partial = universal_engine._sanity_filter_candidates(
                candidates, ["PTZ cameras", "production switcher"], {}, {}, question,
            )
        self.assertIn("BG-ADAMO-4K12X-B", perfect + partial)
        self.assertIn("BG-QUADFUSION-4K", perfect + partial)

    def test_classifier_cannot_omit_requested_camera_category(self):
        from api import universal_engine

        response = types.SimpleNamespace(
            usage=None,
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps({
                "perfect": ["BG-QUADFUSION-4K"], "partial": [],
                "removed": [{"sku": "BG-ADAMO-4K12X-B", "rule": 1}],
            })))],
        )
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}), patch.object(universal_engine, "OpenAI") as client:
            client.return_value.chat.completions.create.return_value = response
            perfect, partial = universal_engine._sanity_filter_candidates(
                ["BG-ADAMO-4K12X-B", "BG-QUADFUSION-4K"],
                ["PTZ cameras", "production switcher"], {}, {},
                "Four 4K HDMI PTZ cameras with 12x zoom and a four-input production switcher",
            )
        self.assertEqual(perfect, ["BG-QUADFUSION-4K"])
        self.assertEqual(partial, ["BG-ADAMO-4K12X-B"])
        client.return_value.chat.completions.create.assert_called_once()

    def test_multi_device_response_instructions_include_each_category(self):
        from api.universal_engine import _build_flow_a_system

        prompt = _build_flow_a_system(multi_category=True)
        self.assertIn("Never omit an entire requested category", prompt)
        self.assertNotIn("PARTIAL MATCHES\" section (when present alongside PERFECT MATCHES) → ignore", prompt)

    def test_camera_family_keeps_signal_type_and_lists_colors(self):
        conn = db.get_conn()
        variants = camera_family_variants(conn, "BG-ADAMO-4KND12X-B")
        conn.close()
        skus = {item["id"] for item in variants}
        self.assertIn("BG-ADAMO-4KND12X-W", skus)
        self.assertIn("BG-ADAMO-4KND25X-B", skus)
        self.assertNotIn("BG-ADAMO-4KDA12X-B", skus)

    def test_new_31x_camera_joins_existing_family(self):
        self.assertEqual(
            camera_family_key("BG-ADAMO-4KND31X-W-31"),
            camera_family_key("BG-ADAMO-4KND25X-B"),
        )

    def test_feed_aliases_are_not_duplicate_products(self):
        from sync_catalog_feed import _camera_alias, _base_interface, PROFILES

        self.assertTrue(_camera_alias("BG-ADAMO-4KND25X-W-31", {"BG-ADAMO-4KND25X-W"}))
        self.assertFalse(_camera_alias("BG-ADAMO-4KND31X-W-31", {"BG-ADAMO-4KND25X-W"}))
        capture = _base_interface("BG-8KCH", PROFILES["BG-8KCH"])
        self.assertEqual(capture["max_res"], "4K60")
        self.assertIn("USB capture output is limited to 4K60", capture["notes"])
        product = {"id": "BG-8KCH", "name": "8K input / 4K capture card", "category": "capture"}
        self.assertEqual(
            hard_mismatch(product, capture, "Need an 8K capture card", ["capture"]),
            "capture output resolution is below the requested format",
        )

    def test_vp_receiver_and_kit_have_distinct_signal_roles(self):
        from sync_catalog_feed import _base_interface, PROFILES

        receiver = _base_interface("BG-4K-VP-R", PROFILES["BG-4K-VP-R"])
        kit = _base_interface("BG-4K-VP1616PRO", PROFILES["BG-4K-VP1616PRO"])
        self.assertEqual(receiver["primary_fn"], "extender-rx")
        self.assertEqual(receiver["in_hdmi"], 0)
        self.assertEqual(kit["in_hdmi_count"], 16)
        self.assertEqual(kit["out_hdmi_count"], 16)

    def test_matrix_with_multiview_feature_is_still_a_matrix(self):
        product = {"id": "BG-4K-VP1616", "name": "16x16 matrix video wall multiviewer",
                   "category": "switcher", "stock_status": "In Stock"}
        interface = {"primary_fn": "matrix-switcher", "in_hdmi_count": 16,
                     "out_hdmi_count": 16, "supports_4k": 1, "max_res": "4K60"}
        self.assertIsNone(hard_mismatch(product, interface, "16x16 seamless video wall matrix", ["switcher"]))

    def test_specific_generator_category_survives_db_alias_expansion(self):
        skus = _find_matching_skus_for_flow_a(
            ["test pattern generator"], {}, "Test pattern generator for 8K displays"
        )
        self.assertIn("BG-AVTPG-MINI-G2", skus)

    def test_earc_receiver_does_not_select_soundbar_only_adapter(self):
        self.assertIsNotNone(hard_mismatch(
            {"id": "BG-8K-SA", "name": "eARC Audio to Soundbar Adapter", "category": "audio"},
            {"primary_fn": "converter"}, "TV eARC to my older AV receiver", ["audio extractor"],
        ))
        self.assertIsNone(hard_mismatch(
            {"id": "BG-8K-AE", "name": "eARC Audio to AV Receiver Adapter", "category": "audio"},
            {"primary_fn": "converter"}, "TV eARC to my older AV receiver", ["audio extractor"],
        ))

    def test_8k60_and_extension_distance_are_hard_requirements(self):
        self.assertEqual(requested_video("Need 8K60 video"), (True, False))
        product = {"id": "BG-EXH-8K50C", "name": "8K60 HDMI extender", "category": "extender",
                   "features": '["8K60"]', "max_distance_m": 50}
        interface = {"supports_8k": 1, "supports_4k": 1, "max_res": "8K60"}
        self.assertEqual(
            hard_mismatch(product, interface, "need 8K60 over 100 meters", ["extender"]),
            "insufficient extension distance",
        )


if __name__ == "__main__":
    unittest.main()
