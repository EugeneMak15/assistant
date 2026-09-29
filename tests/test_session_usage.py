"""Per-session cost estimate regressions (no network calls)."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api import db
from api.usage import estimate_cost, get_session_usage, init_usage_table, record_usage, track_session


class SessionUsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = patch.object(db, "DB_PATH", Path(self.temp.name) / "usage.db")
        self.db_path.start()
        init_usage_table()

    def tearDown(self):
        self.db_path.stop()
        self.temp.cleanup()

    def test_cached_and_cache_write_tokens_use_their_own_rates(self):
        cost = estimate_cost("gpt-5.6-sol-2026-09-01", 1000, 200, 100, 300)
        expected = (700 * 4 + 200 * 0.4 + 100 * 5 + 300 * 20) / 1_000_000
        self.assertAlmostEqual(cost, expected)

    def test_usage_is_isolated_by_session_and_persisted(self):
        response = SimpleNamespace(
            model="gpt-5.6-sol",
            usage=SimpleNamespace(
                prompt_tokens=1000,
                completion_tokens=100,
                prompt_tokens_details=SimpleNamespace(cached_tokens=200, cache_write_tokens=0),
            ),
        )
        record_usage(response)  # No active session: do not attribute this call.
        with track_session("session-one"):
            record_usage(response)
        with track_session("session-two"):
            record_usage(response)
            record_usage(SimpleNamespace(
                model="text-embedding-3-small",
                usage=SimpleNamespace(prompt_tokens=500, total_tokens=500),
            ))

        first = get_session_usage("session-one")
        second = get_session_usage("session-two")
        self.assertEqual(first["requests"], 1)
        self.assertEqual(second["requests"], 2)
        self.assertEqual(first["input_tokens"], 1000)
        self.assertEqual(second["input_tokens"], 1500)
        self.assertGreater(second["estimated_cost_usd"], first["estimated_cost_usd"])
        self.assertEqual(get_session_usage("new-session")["estimated_cost_usd"], 0)

    def test_unknown_model_is_marked_as_unpriced(self):
        with track_session("test"):
            record_usage({"model": "new-model", "usage": {"prompt_tokens": 10, "completion_tokens": 5}})
        usage = get_session_usage("test")
        self.assertEqual(usage["unpriced_requests"], 1)
        self.assertEqual(usage["estimated_cost_usd"], 0)


if __name__ == "__main__":
    unittest.main()
