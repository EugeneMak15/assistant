"""Regression for numeric chip answers breaking an in-progress chat."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from api.chat import _parse_capacity, _parse_distance_m, run_chat_turn


class ChatContextTests(unittest.TestCase):
    def test_capacity_chips_are_safe_integer_requirements(self):
        self.assertEqual(_parse_capacity("8 or more"), 8)
        self.assertEqual(_parse_capacity("5-8"), 8)
        self.assertEqual(_parse_capacity("More than 16"), 17)
        self.assertIsNone(_parse_capacity("Not sure"))

    def test_distance_is_converted_without_truncating_feet(self):
        self.assertEqual(_parse_distance_m("20 feet"), 7)
        self.assertIsNone(_parse_distance_m("Not sure"))

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
