"""Persist chat context and results so a page refresh can resume the same session."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from api import db


class ChatResumeTests(unittest.TestCase):
    def test_history_results_and_session_fields_survive_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(db, "DB_PATH", Path(tmp) / "advisor.db"):
                db.init_chat_state_table()
                db.save_chat_state("sid-1", {"_refining_search": False}, [
                    {"role": "user", "content": "Need 4K cameras"},
                    {"role": "assistant", "content": "Searching now"},
                ])
                db.save_session_fields("sid-1", {"session_id": "sid-1", "resolution": "4K60"})
                db.save_chat_result("sid-1", {
                    "history_index": 2, "skus": ["BG-CAMERA"], "rec_text": "First result",
                })
                db.save_chat_result("sid-1", {
                    "history_index": 4, "skus": ["BG-OTHER"], "rec_text": "Revised result",
                })

                scenario, history = db.load_chat_state("sid-1")
                self.assertFalse(scenario["_refining_search"])
                self.assertEqual(history[0]["content"], "Need 4K cameras")
                self.assertEqual(db.load_session_fields("sid-1")["resolution"], "4K60")
                results = db.load_chat_results("sid-1")
                self.assertEqual([r["history_index"] for r in results], [2, 4])
                self.assertEqual(results[-1]["skus"], ["BG-OTHER"])


if __name__ == "__main__":
    unittest.main()
