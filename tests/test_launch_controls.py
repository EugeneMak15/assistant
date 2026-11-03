"""Launch access and alert accounting without external email or HTTP calls."""
import base64
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api import db
from api.launch_controls import client_ip, init_launch_tables, is_admin, check_daily_budget, count_request
from api.usage import init_usage_table


class LaunchControlsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(db, "DB_PATH", Path(self.temp.name) / "test.db")
        self.path_patch.start()
        init_launch_tables()
        init_usage_table()

    def tearDown(self):
        self.path_patch.stop()
        self.temp.cleanup()

    def test_admin_requires_separate_password(self):
        header = "Basic " + base64.b64encode(b"admin:unique-admin-password").decode()
        request = SimpleNamespace(headers={"authorization": header})
        with patch.dict("os.environ", {"ADVISOR_ADMIN_PASSWORD": "unique-admin-password"}):
            self.assertTrue(is_admin(request))
        with patch.dict("os.environ", {"ADVISOR_ADMIN_PASSWORD": ""}):
            self.assertFalse(is_admin(request))

    def test_only_local_reverse_proxy_can_supply_real_ip(self):
        request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.10"),
                                  headers={"x-real-ip": "198.51.100.1"})
        self.assertEqual(client_ip(request), "203.0.113.10")
        request.client.host = "127.0.0.1"
        self.assertEqual(client_ip(request), "198.51.100.1")
        request.headers["x-real-ip"] = "bad-ip"
        self.assertEqual(client_ip(request), "127.0.0.1")

    def test_budget_alert_triggers_only_over_ten_dollars(self):
        with closing(db.get_conn()) as conn, conn:
            conn.execute("INSERT INTO chat_usage(session_id,model,prompt_tokens,cached_tokens,cache_write_tokens,completion_tokens,estimated_cost_usd) VALUES ('s','test',1,0,0,0,10.01)")
        with patch("api.launch_controls.alert_once") as alert:
            check_daily_budget()
            self.assertEqual(alert.call_count, 1)

    def test_daily_count_is_per_ip_and_persists(self):
        for count in range(1, 102):
            self.assertEqual(count_request("2026-11-03", "198.51.100.4"), count)
        self.assertEqual(count_request("2026-11-03", "198.51.100.5"), 1)
        self.assertEqual(count_request("2026-11-04", "198.51.100.4"), 1)


if __name__ == "__main__":
    unittest.main()
