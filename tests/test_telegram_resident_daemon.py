"""Offline safety tests for resident Telegram browser and private IPC."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
name = ROOT / "tools" / "telegram_resident_daemon.py"
spec = importlib.util.spec_from_file_location("resident_telegram", name)
resident = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resident)

class MonitorTests(unittest.TestCase):
    def test_only_aggregates_visible_unread_no_private_content(self):
        rows = [
            {"peer_id": 135, "title": "private person", "unread_label": "3",
             "text": "do not store"},
            {"peer_id": 99, "title": "secret", "unread_label": "2"},
            {"peer_id": -100, "title": "group", "unread_label": "wrong"},
        ]
        result = resident.monitor_snapshot(rows)
        self.assertEqual(result, {"unread_total_visible": 5,
                                  "unread_chats_visible": 2})
        self.assertNotIn("secret", str(result))
        self.assertNotIn("person", str(result))
        self.assertNotIn("135", str(result))

    def test_badges_bounded(self):
        rows = [{"unread_label": "999999999"}] * 30
        result = resident.monitor_snapshot(rows)
        self.assertEqual(result["unread_total_visible"], 99999)
        self.assertEqual(result["unread_chats_visible"], 20)

    def test_non_ascii_badges_rejected(self):
        self.assertEqual(resident.monitor_snapshot(
            [{"unread_label": "١٢"}, {"unread_label": "-1"}]),
            {"unread_total_visible": 0, "unread_chats_visible": 0})

    def test_file_writes_do_not_store_usernames_or_contacts(self):
        with tempfile.TemporaryDirectory() as temp:
            old = resident.RUNTIME
            resident.RUNTIME = Path(temp)
            try:
                resident.write_private_state({"status": "running",
                         **resident.monitor_snapshot([
                            {"title": "PRIVATE", "peer_id": 123,
                             "unread_label": "1"}])})
                data = (resident.RUNTIME / "monitor.json").read_text()
                self.assertNotIn("PRIVATE", data)
                self.assertNotIn("peer_id", data)
                self.assertEqual((resident.RUNTIME / "monitor.json").stat().st_mode & 0o077, 0)
            finally:
                resident.RUNTIME = old

    def test_socket_insecure_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            original = resident.SOCKET
            target = Path(temp) / "hidden"
            target.write_text("private")
            link = Path(temp) / "operator.sock"
            link.symlink_to(target)
            resident.SOCKET = link
            try:
                self.assertEqual(resident.request_socket(
                    {"internal_control": "status"})["status"],
                    "resident_not_running")
            finally:
                resident.SOCKET = original

    def test_status_contains_metadata_only(self):
        agent = resident.Agent()
        d = agent.state()
        for key in ("unread_chats_visible", "unread_total_visible", "browser_alive"):
            self.assertIn(key, d)
        self.assertNotIn("peer_id", d)
        self.assertNotIn("dialogs", d)

if __name__ == "__main__":
    unittest.main()
