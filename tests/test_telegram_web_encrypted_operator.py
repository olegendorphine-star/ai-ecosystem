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

    def test_owner_approval_mandatory_for_reply(self):
        data = {"peer_id": 123, "reply_to_id": 99, "text": "Approved reply"}
        with self.assertRaises(owner.Rejected):
            owner.validate(command("web_reply", data))
        with self.assertRaises(owner.Rejected):
            owner.validate(command("web_reply", {**data, "approved_by_owner": False}))
        with self.assertRaises(owner.Rejected):
            owner.validate(command("web_reply", {**data, "approved_by_owner": True,
                                                 "arbitrary_javascript": "x"}))
        self.assertEqual(owner.validate(command(
            "web_reply", {**data, "approved_by_owner": True}))["action"], "web_reply")

    def test_arbitrary_actions_forbidden(self):
        for action in ("web_send", "web_delete", "web_navigate",
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
        self.assertIn("send_approved_reply", source)
        self.assertIn("claim_reply_once", source)
        self.assertIn("inbound_message_not_verified", source)
        self.assertIn("LOCK_EX | fcntl.LOCK_NB", source)
        self.assertIn("browser.close()", source)


class ReplyLedger(unittest.TestCase):
    def test_attempted_once_no_replay(self):
        with tempfile.TemporaryDirectory() as td:
            os.chmod(td, 0o700)
            path = Path(td) / "reply.sqlite3"
            cmd = command("web_reply", {"peer_id": 18, "reply_to_id": 99,
                                         "text": "approved", "approved_by_owner": True})
            self.assertEqual(web.claim_reply_once(cmd, path), "claimed")
            self.assertEqual(web.claim_reply_once(cmd, path), "already_attempted")
            self.assertEqual(path.stat().st_mode & 0o077, 0)
            web.complete_reply(cmd["command_id"], path)
            self.assertEqual(web.claim_reply_once(cmd, path), "already_attempted")

    def test_conflicting_reuse_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            os.chmod(td, 0o700)
            path = Path(td) / "reply.sqlite3"
            cmd = command("web_reply", {"peer_id": 18, "reply_to_id": 99,
                                         "text": "one", "approved_by_owner": True})
            self.assertEqual(web.claim_reply_once(cmd, path), "claimed")
            cmd["params"]["text"] = "two"
            with self.assertRaises(ValueError):
                web.claim_reply_once(cmd, path)

    def test_inbound_required_before_ledger(self):
        fake_page = mock.Mock()
        fake_page.evaluate.return_value = False
        cmd = command("web_reply", {"peer_id": 18, "reply_to_id": 99,
                                     "text": "owner approved", "approved_by_owner": True})
        with mock.patch.object(web, "claim_reply_once") as claim:
            result = web.send_approved_reply(fake_page, 18, cmd["params"], cmd)
            self.assertEqual(result["status"], "inbound_message_not_verified")
            claim.assert_not_called()

    def test_no_send_after_existing_attempt(self):
        fake_page = mock.Mock()
        fake_page.evaluate.return_value = True
        cmd = command("web_reply", {"peer_id": 18, "reply_to_id": 99,
                                     "text": "owner approved", "approved_by_owner": True})
        with mock.patch.object(web, "claim_reply_once", return_value="already_attempted"):
            result = web.send_approved_reply(fake_page, 18, cmd["params"], cmd)
            self.assertEqual(result["status"], "already_attempted_no_resend")
            self.assertEqual(fake_page.evaluate.call_count, 1)


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
