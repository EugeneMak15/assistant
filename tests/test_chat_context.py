"""Regression for numeric chip answers breaking an in-progress chat."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from api.chat import _parse_capacity, _parse_distance_m, run_chat_turn, run_followup_turn


class ChatContextTests(unittest.TestCase):
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("api.chat.OpenAI")
    def test_followup_can_request_same_chat_research(self, mock_openai):
        payload = {"message": "I'll update the search.", "new_topic": False, "refine_search": True}
        mock_openai.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
        )
        result = run_followup_turn(
            [{"role": "user", "content": "I need a 4-input matrix"}],
            "Actually, it needs 8 inputs", {"topic": "matrix", "products": [], "rec_text": ""},
        )
        self.assertTrue(result["refine_search"])
        self.assertFalse(result["suggest_new_chat"])

    def test_capacity_chips_are_safe_integer_requirements(self):
        self.assertEqual(_parse_capacity("8 or more"), 8)
        self.assertEqual(_parse_capacity("5-8"), 8)
        self.assertEqual(_parse_capacity("More than 16"), 17)
        self.assertIsNone(_parse_capacity("Not sure"))

    def test_distance_is_converted_without_truncating_feet(self):
        self.assertEqual(_parse_distance_m("20 feet"), 7)
        self.assertIsNone(_parse_distance_m("Not sure"))

    @patch("api.chat.OpenAI")
    def test_usb_peripheral_sharing_asks_only_device_count_then_searches(self, mock_openai):
        opening = "Four computers need to share the same USB devices, and I want to pick which computer gets which device."
        first = run_chat_turn([], opening, {})
        self.assertFalse(first["ready_to_search"])
        self.assertIn("How many USB devices", first["message"])
        self.assertNotIn("resolution", first["message"].lower())
        second = run_chat_turn([{"role": "user", "content": opening},
                                {"role": "assistant", "content": first["message"]}], "4 devices", {})
        self.assertTrue(second["ready_to_search"])
        self.assertEqual(second["_scenario_plan"]["requested_categories"], ["usb matrix switcher"])
        self.assertIn("4x4 USB matrix", second["search_query"])
        mock_openai.assert_not_called()

    @patch("api.chat.OpenAI")
    def test_exact_usb_matrix_request_needs_no_video_questions(self, mock_openai):
        result = run_chat_turn([], "4x4 USB matrix switcher", {})
        self.assertTrue(result["ready_to_search"])
        self.assertEqual(result["chips"], [])
        mock_openai.assert_not_called()

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("api.chat.OpenAI")
    def test_hdmi_kvm_category_is_normalized(self, mock_openai):
        payload = {"message": "Let me search.", "chips": [], "ready_to_search": True,
                   "search_query": "4x1 HDMI KVM 4K", "intent": {"flow": "product_selection",
                   "requested_categories": ["HDMI KVM switch"], "num_inputs": 4,
                   "num_outputs": 1, "resolution": "4K", "signal_type": "HDMI"}}
        mock_openai.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
        result = run_chat_turn([], "I need a 4K HDMI KVM switch for 4 computers and one monitor", {})
        self.assertEqual(result["_scenario_plan"]["requested_categories"], ["kvm switch"])
        self.assertIn("4 computers", result["search_query"])

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("api.chat.OpenAI")
    def test_kvm_resolution_question_has_explicit_choices_after_hdmi_answer(self, mock_openai):
        payload = {"message": "What resolution?", "chips": [], "ready_to_search": False,
                   "intent": {"flow": "product_selection", "requested_categories": ["kvm switch"],
                              "resolution": "4K"}}
        mock_openai.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
        opening = "I need an HDMI KVM switch so I can control 4 computers from one keyboard, mouse and monitor."
        result = run_chat_turn([], opening, {})
        self.assertEqual(result["chips"][:3], ["1080p", "4K", "8K"])
        self.assertIn("resolution", result["message"].lower())
        self.assertNotIn("Resolution?", result["_scenario_answers"])
        payload["ready_to_search"] = True
        payload["search_query"] = "4-port HDMI KVM 4K"
        mock_openai.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
        followup = run_chat_turn([
            {"role": "user", "content": opening},
            {"role": "assistant", "content": result["message"]},
            {"role": "user", "content": "HDMI"},
            {"role": "assistant", "content": result["message"]},
        ], "4K", {})
        self.assertTrue(followup["ready_to_search"])

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("api.chat.OpenAI")
    def test_selected_source_distribution_survives_matrix_rephrasing(self, mock_openai):
        opening = "I have two 8K HDMI sources and need to send one of them to eight displays."
        for wrong_category in ("matrix switcher", "switcher"):
            with self.subTest(wrong_category=wrong_category):
                payload = {
                    "message": "Let me find a 2x8 HDMI matrix.", "chips": [],
                    "ready_to_search": True, "search_query": "2x8 HDMI matrix for 8K signals",
                    "intent": {"flow": "product_selection", "requested_categories": [wrong_category],
                               "num_inputs": 2, "num_outputs": 8, "resolution": "8K"},
                }
                mock_openai.return_value.chat.completions.create.return_value = SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
                result = run_chat_turn(
                    [{"role": "user", "content": opening},
                     {"role": "assistant", "content": "How far is the longest run?"}],
                    "15 feet", {},
                )
                self.assertTrue(result["ready_to_search"])
                self.assertEqual(result["_scenario_plan"]["requested_categories"], ["splitter"])
                self.assertIn("one of them to eight displays", result["search_query"])
                self.assertNotIn("matrix", result["message"].lower())

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("api.chat.OpenAI")
    def test_range_intent_does_not_break_session_update(self, mock_openai):
        payload = {
            "message": "Got it — how far is the furthest display?",
            "chips": [],
            "ready_to_search": False,
            "intent": {
                "equipment_type": "matrix switcher",
                "num_inputs": "8 or more",
                "num_outputs": "5-8",
                "distance_m": "20 feet",
            },
        }
        mock_openai.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        )
        result = run_chat_turn([], "20", {}, "test-session")
        self.assertEqual(result["state_update"]["num_inputs"], 8)
        self.assertEqual(result["state_update"]["num_outputs"], 8)
        self.assertEqual(result["state_update"]["max_distance_m"], 7)
        self.assertEqual(result["_scenario_answers"]["How many displays/outputs?"], "8")


if __name__ == "__main__":
    unittest.main()
