"""Offline tests for user-authorized, encrypted Telegram Web browser operations."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import telegram_owner_operator as owner
import telegram_secure_bridge as bridge

path = ROOT / "tools" / "telegram_web_encrypted_operator.py"
spec = importlib.util.spec_from_file_location("telegram_web_encrypted_operator", path)
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)


def command(action="web_status", params=None):
    now = dt.datetime.now(dt.timezone.utc)
    return {
        "schema": "tg.owner.command.v1",
        "command_id": str(uuid.uuid4()),
        "action": action,
        "issued_at": now.isoformat(),
        "expires_at": (now + dt.timedelta(minutes=4)).isoformat(),
        "params": params or {},
    }


class Validation(unittest.TestCase):
    def test_web_status_only_empty_params(self):
        owner.validate(command())
        with self.assertRaises(owner.Rejected):
            owner.validate(command("web_status", {"url": "https://evil.example"}))

    def test_dialogs_bounded(self):
        owner.validate(command("web_dialogs", {"limit": 20}))
        for val in (-1, 0, 21, "10", True):
            with self.assertRaises(owner.Rejected):
                owner.validate(command("web_dialogs", {"limit": val}))

    def test_read_requires_peer_from_known_list(self):
        owner.validate(command("web_read", {"peer_id": 123456, "limit": 8}))
        for val in (None, "", True, 0, 2**54):
            with self.assertRaises(owner.Rejected):
                owner.validate(command("web_read", {"peer_id": val}))
        with self.assertRaises(owner.Rejected):
            owner.validate(command("web_read", {"peer_id": 123, "limit": 13}))

    def test_no_browser_send_or_arbitrary_actions(self):
        for action in ("web_reply", "web_send", "web_delete", "web_navigate",
                       "web_js", "web_screenshot", "web_export_cookies"):
            with self.assertRaises(owner.Rejected):
                owner.validate(command(action))


class UIHelpers(unittest.TestCase):
    def test_authenticated_requires_correct_origin_and_chat_list(self):
        self.assertEqual(web.classify_ui("https://web.telegram.org/k/",
                            {"sidebar": True, "chatlist": True,
                             "login_form": False}), "authorized")
        self.assertEqual(web.classify_ui("https://web.telegram.org/k/",
                            {"sidebar": True, "chatlist": True,
                             "login_form": True}), "auth_required")
        self.assertEqual(web.classify_ui("https://evil.example",
                            {"sidebar": True, "chatlist": True}), "unknown")
        self.assertEqual(web.classify_ui("https://web.telegram.org/k/",
                            {"sidebar": True, "chatlist": False}), "unknown")

    def test_dialogs_filtered_and_bounded(self):
        rows = [{"peer_id": 22, "title": "  Demo  ", "unread_label": "2"},
                {"peer_id": 22, "title": "duplicate"},
                {"peer_id": 0, "title": "invalid"},
                {"peer_id": 35, "title": "Case", "unread_label": "<script>"}]
        self.assertEqual(web.normalize_dialogs(rows, 10),
                         [{"peer_id": 22, "title": "Demo", "unread_label": "2"},
                          {"peer_id": 35, "title": "Case", "unread_label": ""}])

    def test_bounded_message_projection(self):
        rows = [{"message_id": 10, "incoming": True, "text": "a" * 2000},
                {"message_id": 11, "incoming": False, "text": "out"},
                {"message_id": "x", "text": "bad"}]
        out = web.normalize_messages(rows, 4)
        self.assertEqual(len(out), 2)
        self.assertEqual(len(out[0]["text"]), 1200)
        self.assertTrue(out[0]["incoming"])
        self.assertFalse(out[1]["incoming"])

    def test_private_commands_never_emit_raw_logs_or_read_cookies(self):
        source = path.read_text()
        self.assertNotIn("print(page", source)
        self.assertNotIn("storage_state(", source)
        self.assertNotIn("page.screenshot(", source)
        self.assertNotIn("os.system(", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("web_reply", source.split("ALLOWED =")[1].split("\n")[0])
        self.assertIn("LOCK_EX | fcntl.LOCK_NB", source)
        self.assertIn("browser.close()", source)


class BridgeRouting(unittest.TestCase):
    def test_web_status_without_telethon_credentials(self):
        fake = mock.Mock(returncode=0,
                         stdout='{"status":"authorized","action":"web_status"}',
                         stderr="")
        with mock.patch.object(owner.subprocess, "run", return_value=fake) as run, \
             mock.patch.object(owner.Path, "is_file", return_value=True), \
             mock.patch.object(owner.Path, "is_symlink", return_value=False):
            actual = owner._run_private_web_adapter(command())
            self.assertEqual(actual["status"], "authorized")
            self.assertNotIn("shell", run.call_args.kwargs)
            self.assertIsNone(run.call_args.kwargs.get("env"))

    def test_bridge_end_to_end_encrypted_owner_action(self):
        with tempfile.TemporaryDirectory() as td:
            os.chmod(td, 0o700)
            folder = Path(td)
            private = folder / "server.pem"
            public = bridge.generate_private_key(private)
            key = folder / "command.pem"
            req = command("web_dialogs", {"limit": 3})
            envelope = bridge.encrypt_request(req, public, key)
            self.assertNotIn("web_dialogs", json.dumps(envelope))
            decoded, shared = bridge.decrypt_request(envelope, bridge.load_key(private))
            self.assertEqual(decoded["action"], "web_dialogs")
            secret_name = "PRIVATE USER MOCK"
            reply = bridge.encrypt_result(
                {"status": "ok", "dialogs": [{"peer_id": 6, "title": secret_name}]},
                shared, envelope["sender_pub"])
            self.assertNotIn(secret_name, json.dumps(reply))
            result = bridge.decrypt_result(reply, bridge.load_key(key), public)
            self.assertEqual(result["dialogs"][0]["title"], secret_name)


if __name__ == "__main__":
    unittest.main()
