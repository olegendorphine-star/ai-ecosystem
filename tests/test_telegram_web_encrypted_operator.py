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

    def test_self_note_owner_approval_and_no_recipient(self):
        with self.assertRaises(owner.Rejected):
            owner.validate(command("web_self_note", {"text":"Hi"}))
        with self.assertRaises(owner.Rejected):
            owner.validate(command("web_self_note", {"text":"Hi",
                                                     "approved_by_owner":False}))
        with self.assertRaises(owner.Rejected):
            owner.validate(command("web_self_note", {"text":"Hi",
                                                     "approved_by_owner":True,
                                                     "peer_id":12345}))
        with self.assertRaises(owner.Rejected):
            owner.validate(command("web_self_note", {"text":"a"*301,
                                                     "approved_by_owner":True}))
        c = command("web_self_note", {"text":"Test",
                                     "approved_by_owner":True})
        self.assertEqual(owner.validate(c)["action"], "web_self_note")

    def test_approved_phone_message_requires_e164_and_consent(self):
        params = {"phone": "+12025550123", "text": "Test", "approved_by_owner": True}
        self.assertEqual(owner.validate(command("web_phone_message", params))["action"],
                         "web_phone_message")
        for invalid in (
            {**params, "approved_by_owner": False},
            {**params, "phone": "not-phone"},
            {**params, "phone": "2025550123"},
            {**params, "phone": "+0"},
            {**params, "phone": "+12025550123", "text": ""},
            {**params, "text": "x"*301},
            {**params, "peer_id": 111},
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(owner.Rejected):
                    owner.validate(command("web_phone_message", invalid))

    def test_owner_contact_link_requires_no_recipient_or_arguments(self):
        self.assertEqual(owner.validate(command("web_owner_contact_link", {}))["action"],
                         "web_owner_contact_link")
        with self.assertRaises(owner.Rejected):
            owner.validate(command("web_owner_contact_link",
                                   {"phone": "+12025550123"}))
        with self.assertRaises(owner.Rejected):
            owner.validate(command("web_owner_contact_link", {"username": "someone"}))

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


class OwnContactLink(unittest.TestCase):
    def test_accepts_short_normalized_telegram_contact_token(self):
        page = mock.Mock()
        page.evaluate.return_value = {"status": "ok", "method": "contact_token",
                                      "url": "https://t.me/contact/abc_def-12",
                                      "expires": 1899999999}
        res = web.get_owner_contact_link(page)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["url"], "https://t.me/contact/abc_def-12")

    def test_canonicalizes_only_official_contact_token_shapes(self):
        source = path.read_text()
        body = source.split("def get_owner_contact_link(",1)[1].split(
            "def send_approved_phone_message(",1)[0]
        self.assertIn("tg://contact?token", body)
        self.assertIn("parsed.hostname === 'contact'", body)
        self.assertIn("url:'https://t.me/contact/'+encodeURIComponent(token)", body)
        self.assertIn("u?.username", body)
        self.assertIn('telegram_url', body)
        self.assertNotIn("return {status:'ok',method:'contact_token',url:rawUrl}", body)

    def test_returns_only_own_safe_username_url(self):
        page = mock.Mock()
        page.evaluate.return_value = {"status":"ok", "method":"username",
                                      "url":"https://t.me/OwnAccount_123"}
        res = web.get_owner_contact_link(page)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["url"], "https://t.me/OwnAccount_123")

    def test_rejects_external_or_unsafe_link(self):
        page = mock.Mock()
        for bad in ("https://evil.example/x", "http://t.me/OwnAccount_123",
                    "https://t.me/OwnAccount_123?token=secret"):
            page.evaluate.return_value = {"status":"ok", "method":"username",
                                          "url":bad}
            self.assertEqual(web.get_owner_contact_link(page)["status"],
                             "contact_link_invalid")

    def test_refuses_private_browser_failure(self):
        page = mock.Mock()
        page.evaluate.side_effect = RuntimeError("private-browser-detail")
        self.assertEqual(web.get_owner_contact_link(page),
                         {"status":"contact_link_unavailable"})


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

    def test_same_intent_different_uuid_does_not_resend(self):
        with tempfile.TemporaryDirectory() as td:
            os.chmod(td, 0o700)
            path = Path(td) / "reply.sqlite3"
            params = {"peer_id": 18, "reply_to_id": 99,
                      "text": "same text", "approved_by_owner": True}
            one = command("web_reply", params)
            two = command("web_reply", params)
            self.assertNotEqual(one["command_id"], two["command_id"])
            self.assertEqual(web.claim_reply_once(one, path), "claimed")
            self.assertEqual(web.claim_reply_once(two, path), "already_attempted")

    def test_same_self_note_different_uuid_does_not_resend(self):
        with tempfile.TemporaryDirectory() as td:
            os.chmod(td, 0o700)
            path = Path(td) / "reply.sqlite3"
            params = {"text": "single note", "approved_by_owner": True}
            one = command("web_self_note", params)
            two = command("web_self_note", params)
            self.assertEqual(web.claim_reply_once(one, path), "claimed")
            self.assertEqual(web.claim_reply_once(two, path), "already_attempted")
            web.complete_reply(one["command_id"], path)
            self.assertEqual(web.claim_reply_once(two, path), "already_attempted")

    def test_self_note_refuses_if_self_not_verified(self):
        page = mock.Mock()
        page.evaluate.return_value = False
        c = command("web_self_note", {"text":"hello",
                                       "approved_by_owner":True})
        with mock.patch.object(web, "claim_reply_once") as claim:
            result = web.send_owner_self_note(page, c)
            self.assertEqual(result["status"], "self_chat_unavailable")
            claim.assert_not_called()

    def test_self_note_does_not_send_if_already_attempted(self):
        page = mock.Mock()
        page.evaluate.return_value = True
        c = command("web_self_note", {"text":"hello",
                                       "approved_by_owner":True})
        with mock.patch.object(web, "claim_reply_once", return_value="already_attempted"):
            result = web.send_owner_self_note(page, c)
            self.assertEqual(result["status"], "already_attempted_no_resend")
            self.assertEqual(page.evaluate.call_count, 2)

    def test_phone_intent_is_deduplicated_across_command_ids(self):
        with tempfile.TemporaryDirectory() as td:
            os.chmod(td, 0o700)
            path = Path(td) / "reply.sqlite3"
            params = {"phone": "+12025550123", "text": "Test", "approved_by_owner": True}
            one, two = command("web_phone_message", params), command("web_phone_message", params)
            self.assertEqual(web.claim_reply_once(one, path), "claimed")
            self.assertEqual(web.claim_reply_once(two, path), "already_attempted")

    def test_contact_import_is_preferred_over_phone_resolution(self):
        source = path.read_text()
        block = source.split("def send_approved_phone_message(", 1)[1].split(
            "def normalize_messages(", 1)[0]
        assert "importContact(" in block
        assert "resolvePhone(" in block
        self.assertLess(block.index("importContact("), block.index("resolvePhone("))
        self.assertIn("resolved_contact_phone_mismatch", block)
        self.assertIn("contact_not_resolved_by_telegram", block)
        self.assertIn("error_code:code", block)
        self.assertIn("error_class:kind", block)
        self.assertIn("message_requires_payment_or_premium", block)

    def test_exact_contact_precheck_and_failure_types(self):
        source = path.read_text()
        block = source.split("def send_approved_phone_message(", 1)[1].split(
            "def normalize_messages(", 1)[0]
        self.assertIn("getContacts(", block)
        self.assertIn("contact_browser_type_error", block)
        self.assertIn("telegram_rate_limited", block)
        self.assertIn("telegram_contact_privacy_restricted", block)
        self.assertIn("contact_not_resolved_by_telegram", block)
        self.assertIn("resolved_contact_phone_mismatch", block)
        self.assertLess(block.index("getContacts("), block.index("importContact("))

    def test_imported_id_requires_server_user_verification(self):
        source = path.read_text()
        block = source.split("def send_approved_phone_message(", 1)[1].split(
            "def normalize_messages(", 1)[0]
        self.assertIn("getApiUsers([importedId])", block)
        self.assertIn("fresh.find(u => String(u?.id) === String(importedId))", block)
        self.assertIn("phone_user_not_verified_after_import", block)
        self.assertIn("resolved_contact_phone_mismatch", block)
        self.assertIn("message_requires_payment_or_premium", block)

    def test_phone_unresolved_never_calls_send_or_ledger(self):
        page = mock.Mock()
        page.evaluate.return_value = {"status": "phone_not_found"}
        request = command("web_phone_message", {"phone": "+12025550123",
                                 "text": "Test", "approved_by_owner": True})
        with mock.patch.object(web, "claim_reply_once") as claim:
            result = web.send_approved_phone_message(page, request)
            self.assertEqual(result["status"], "phone_not_found")
            claim.assert_not_called()

    def test_phone_paid_requirement_blocks_before_ledger(self):
        page = mock.Mock()
        page.evaluate.return_value = {"status": "message_requires_payment_or_premium"}
        request = command("web_phone_message", {"phone": "+12025550123",
                                 "text": "Test", "approved_by_owner": True})
        with mock.patch.object(web, "claim_reply_once") as claim:
            result = web.send_approved_phone_message(page, request)
            self.assertEqual(result["status"], "message_requires_payment_or_premium")
            claim.assert_not_called()

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
