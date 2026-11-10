"""Offline tests for the Wordstat chat bridge; no external requests."""
import datetime as dt
import json
import unittest
import uuid
from unittest.mock import patch

from tools import yandex_wordstat_bridge as w


class WordstatBridgeTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 11, 10, 3, 0, tzinfo=dt.timezone.utc)
        self.id = str(uuid.UUID("dd0ffca2-bef0-4137-b9ba-5a933a0e34ed"))

    def event(self, *, author=w.OWNER, action="regions", extras=None):
        data = {
            "schema": "wordstat.bridge.command.v1",
            "command_id": self.id,
            "action": action,
            "issued_at": "2026-11-10T02:58:00Z",
            "expires_at": "2026-11-10T03:02:00Z",
        }
        if extras:
            data.update(extras)
        return {
            "action": "created", "issue": {"number": w.ISSUE_NUMBER},
            "comment": {"user": {"login": author},
                        "body": w.COMMAND_PREFIX + json.dumps(data, ensure_ascii=False)}
        }

    def test_owner_command(self):
        cmd = w.parse_command(self.event(), self.now)
        self.assertEqual(cmd, {"command_id": self.id, "action": "regions"})

    def test_untrusted_actor_ignored(self):
        self.assertIsNone(w.parse_command(self.event(author="somebody-else"), self.now))

    def test_expired_rejected(self):
        with self.assertRaises(ValueError):
            w.parse_command(self.event(), self.now + dt.timedelta(minutes=5))

    def test_top_validation(self):
        cmd = w.parse_command(self.event(action="top",
                            extras={"phrase": "ИИ собеседник", "region": "225"}), self.now)
        self.assertEqual(cmd["device"], "DEVICE_ALL")
        self.assertEqual(cmd["phrase"], "ИИ собеседник")

    def test_invalid_device_rejected(self):
        with self.assertRaises(ValueError):
            w.parse_command(self.event(action="top",
                       extras={"phrase": "собеседник", "device": "UNKNOWN"}), self.now)

    def test_billable_operation_disabled_by_default(self):
        cmd = w.parse_command(self.event(action="top",
                            extras={"phrase": "ИИ собеседник"}), self.now)
        with patch.object(w, "request_json") as api:
            result = w.call_wordstat(cmd, "test-key", "test-folder", False)
            self.assertEqual(result["status"], "paid_requests_disabled")
            api.assert_not_called()

    def test_mock_regions(self):
        with patch.object(w, "request_json", return_value={
            "regions": [{"id": "225", "name": "Россия"}]
        }) as api:
            result = w.call_wordstat({"action": "regions"}, "fake-key", "folder", False)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["root_regions"][0]["id"], "225")
            self.assertFalse(result["billable"])
            self.assertIn("getRegionsTree", api.call_args.args[0])

    def test_free_regions_without_folder_id(self):
        with patch.object(w, "request_json", return_value={
            "regions": [{"id": "225", "label": "Россия"}]
        }) as api:
            result = w.call_wordstat({"action": "regions"}, "fake-key", "", False)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["root_regions"][0]["name"], "Россия")
            self.assertEqual(api.call_args.args[2], {})

    def test_mock_top(self):
        cmd = {"action": "top", "phrase": "ИИ собеседник",
               "region": "225", "device": "DEVICE_ALL"}
        with patch.object(w, "request_json", return_value={
            "totalCount": "120", "results": [{"phrase": "ии собеседник", "count": "120"}],
            "associations": []
        }) as api:
            result = w.call_wordstat(cmd, "fake-key", "folder", True)
            self.assertEqual(result["totalCount"], "120")
            self.assertEqual(result["results"][0]["count"], "120")
            self.assertIn("topRequests", api.call_args.args[0])

    def test_paid_daily_budget_counts_only_started_calls(self):
        records = [
            {"status": "started", "method": "GetTop",
             "checked_at": "2026-11-10T02:00:00+00:00"},
            {"status": "ok", "method": "GetTop",
             "checked_at": "2026-11-10T02:01:00+00:00"},
            {"status": "started", "method": "GetTop",
             "checked_at": "2026-11-09T23:59:00+00:00"},
            {"status": "started", "method": "GetRegionsTree",
             "checked_at": "2026-11-10T02:02:00+00:00"},
        ]
        self.assertEqual(w.count_daily_paid_reservations(records, self.now), 1)

    def test_paid_history_only_trusts_bot(self):
        history = [
            {"user": {"login": "outsider"}, "body":
             w.RESULT_PREFIX + json.dumps(
                 {"command_id": self.id, "status": "started", "method": "GetTop"})},
            {"user": {"login": "github-actions[bot]"}, "body":
             w.RESULT_PREFIX + json.dumps(
                 {"command_id": "bot", "status": "started", "method": "GetTop"})},
        ]
        with patch.object(w, "request_json", return_value=history):
            results = w.read_bot_results("test-token")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["command_id"], "bot")

    def test_paid_history_fails_closed_on_pagination_cap(self):
        page = [{"user": {"login": "outsider"}, "body": "x"}] * 100
        with patch.object(w, "request_json", return_value=page):
            with self.assertRaises(ValueError):
                w.read_bot_results("test-token")

    def test_paid_calls_require_folder_id(self):
        with patch.object(w, "request_json") as api:
            result = w.call_wordstat({"action": "top", "phrase": "ИИ собеседник",
                                      "region": "225", "device": "DEVICE_ALL"},
                                     "mock-key", "", True)
            self.assertEqual(result["status"], "not_configured")
            self.assertEqual(result["missing"], "folder_id")
            api.assert_not_called()

    def test_missing_credentials_never_calls_api(self):
        with patch.object(w, "request_json") as api:
            result = w.call_wordstat({"action": "regions"}, "", "", False)
            self.assertEqual(result["status"], "not_configured")
            api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
