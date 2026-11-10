"""Offline tests of safe, non-executing browser command handoff."""
import datetime as dt
import json
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import avito_trusted_ui_handoff as h
import avito_browser_operator as op

NOW = dt.datetime(2026, 11, 6, 12, 0, tzinfo=dt.timezone.utc)
RID = "b9f76dc1-68ea-4f10-89f7-6025acfb9b18"


def request(purpose="public-profile"):
    return {
        "schema": h.REQUEST_SCHEMA, "request_id": RID,
        "action": "inventory", "purpose": purpose,
        "issued_at": (NOW - dt.timedelta(minutes=1)).isoformat(),
        "expires_at": (NOW + dt.timedelta(minutes=5)).isoformat(),
    }


def owner_comment(req=None, user_id=h.OWNER_USER_ID, login=h.OWNER_LOGIN):
    return {
        "user": {"id": user_id, "login": login},
        "body": h.REQUEST_PREFIX + json.dumps(request() if req is None else req),
    }


def inventory():
    return op.inventory_controls([
        {"role": "button", "label": "Добавить альбом портфолио"},
        {"role": "textbox", "label": "Описание профиля"},
        {"role": "file", "label": "Загрузить фото"},
        {"role": "link", "label": "Секретный контакт user@example.com"},
    ])


class TrustedUiHandoffTests(unittest.TestCase):
    def test_only_inventory_command_allowed(self):
        h.validate_request(request(), NOW)
        for action in ("edit_profile", "click", "upload", "send", "shell", "delete"):
            x = request()
            x["action"] = action
            with self.assertRaises(h.InvalidTrustedRequest):
                h.validate_request(x, NOW)

    def test_only_two_known_screens_allowed(self):
        h.validate_request(request("portfolio"), NOW)
        with self.assertRaises(h.InvalidTrustedRequest):
            h.validate_request(request("messenger"), NOW)

    def test_rejects_url_selector_payload_and_secrets(self):
        for key, val in (
            ("target_url", "https://www.avito.ru/profile"),
            ("text", "private content"),
            ("cookie", "SECRET"),
            ("selector", "css"),
            ("ip_address", "PRIVATE_IP"),
        ):
            x = request()
            x[key] = val
            with self.assertRaises(h.InvalidTrustedRequest):
                h.validate_request(x, NOW)

    def test_rejects_noncanonical_uuid(self):
        for xval in ("bad", str(uuid.uuid1()), RID.upper(), "PRIVATE_TOKEN"):
            x = request()
            x["request_id"] = xval
            with self.assertRaises(h.InvalidTrustedRequest):
                h.validate_request(x, NOW)

    def test_rejects_expired_and_far_future(self):
        with self.assertRaises(h.InvalidTrustedRequest):
            h.validate_request(request(), NOW + dt.timedelta(hours=1))
        with self.assertRaises(h.InvalidTrustedRequest):
            h.validate_request(request(), NOW - dt.timedelta(hours=1))

    def test_rejects_large_ttl(self):
        x = request()
        x["expires_at"] = (NOW + dt.timedelta(hours=1)).isoformat()
        with self.assertRaises(h.InvalidTrustedRequest):
            h.validate_request(x, NOW)

    def test_rejects_naive_timestamps(self):
        x = request()
        x["issued_at"] = "2026-11-06T11:59:00"
        with self.assertRaises(h.InvalidTrustedRequest):
            h.validate_request(x, NOW)

    def test_requires_true_github_owner_metadata(self):
        self.assertIsNotNone(h.parse_owner_comment(owner_comment(), NOW))
        self.assertIsNone(h.parse_owner_comment(owner_comment(login="imposter"), NOW))
        self.assertIsNone(h.parse_owner_comment(owner_comment(user_id=111), NOW))
        self.assertIsNone(h.parse_owner_comment({"user": {"login": h.OWNER_LOGIN}, "body": "x"}, NOW))

    def test_rejects_body_with_extra_text_and_long_body(self):
        self.assertIsNone(h.parse_owner_comment({**owner_comment(), "body": "Hello\n" + owner_comment()["body"]}, NOW))
        self.assertIsNone(h.parse_owner_comment({**owner_comment(), "body": "x" * 2000}, NOW))

    def test_prepares_unexecuted_read_only_request(self):
        body = h.prepare_inventory_request("portfolio", NOW, RID)
        self.assertTrue(body.startswith(h.REQUEST_PREFIX))
        x = json.loads(body[len(h.REQUEST_PREFIX):])
        self.assertEqual(h.validate_request(x, NOW)["purpose"], "portfolio")
        self.assertEqual(x["action"], "inventory")
        self.assertEqual(set(x), {"schema", "request_id", "action", "purpose", "issued_at", "expires_at"})

    def test_filters_replays_and_foreign_comments(self):
        valid = owner_comment()
        result = h.fresh_requests([valid, valid, owner_comment(login="other")], set(), NOW)
        self.assertEqual(len(result), 1)
        self.assertEqual(h.fresh_requests([valid], {RID}, NOW), [])

    def test_safe_operator_inventory_compatibility(self):
        clean = h.sanitized_inventory(inventory())
        self.assertEqual(clean["categories"]["portfolio"], 1)
        self.assertEqual(clean["categories"]["profile"], 1)
        self.assertEqual(clean["control_types"]["file"], 1)
        self.assertNotIn("example.com", str(clean))

    def test_rejects_inventory_with_extra_fields(self):
        x = inventory()
        x["cookies"] = "SENSITIVE"
        with self.assertRaises(ValueError):
            h.sanitized_inventory(x)

    def test_rejects_unknown_inventory_keys_and_boolean_count(self):
        x = inventory()
        x["categories"]["IP_ADDRESS"] = 1
        with self.assertRaises(ValueError):
            h.sanitized_inventory(x)
        y = inventory()
        y["categories"]["profile"] = True
        with self.assertRaises(ValueError):
            h.sanitized_inventory(y)

    def test_default_result_is_blocked_and_no_effect_claim(self):
        body = h.make_public_result(request(), now=NOW)
        data = json.loads(body[len(h.RESULT_PREFIX):])
        self.assertEqual(data["status"], "blocked")
        self.assertEqual(data["reason"], "no_verified_session")
        self.assertFalse(data["public_profile_updated"])
        self.assertEqual(data["price_list_visible"], "unverified")

    def test_valid_counts_only_report(self):
        body = h.make_public_result(request("portfolio"), inventory(), session_verified=True, now=NOW)
        data = json.loads(body[len(h.RESULT_PREFIX):])
        self.assertEqual(data["status"], "observed_controls")
        self.assertEqual(data["inventory"]["categories"]["portfolio"], 1)
        self.assertNotIn("Добавить", body)
        self.assertNotIn("example.com", body)
        self.assertNotIn("IP_ADDRESS", body)
        self.assertFalse(data["public_profile_updated"])

    def test_invalid_report_stays_blocked(self):
        bad = inventory()
        bad["control_types"]["button"] = -2
        body = h.make_public_result(request(), bad, session_verified=True, now=NOW)
        data = json.loads(body[len(h.RESULT_PREFIX):])
        self.assertEqual(data["status"], "blocked")
        self.assertEqual(data["reason"], "invalid_inventory")
        self.assertNotIn("inventory", data)

    def test_result_rejects_arbitrary_unvalidated_correlation_id(self):
        bad_request = request()
        bad_request["request_id"] = "SENSITIVE_DO_NOT_PUBLISH"
        with self.assertRaises(h.InvalidTrustedRequest):
            h.make_public_result(bad_request, inventory(), session_verified=True, now=NOW)

    def test_result_does_not_accept_string_as_session_approval(self):
        body = h.make_public_result(request(), inventory(), session_verified="true", now=NOW)
        data = json.loads(body[len(h.RESULT_PREFIX):])
        self.assertEqual(data["reason"], "no_verified_session")
        self.assertEqual(data["status"], "blocked")

    def test_unknown_fields_never_echoed(self):
        bad = inventory()
        bad["private_notes"] = "NEVER_PUBLISH_ME"
        body = h.make_public_result(request(), bad, session_verified=True, now=NOW)
        self.assertNotIn("NEVER_PUBLISH_ME", body)
        self.assertNotIn("private_notes", body)


if __name__ == "__main__":
    unittest.main()
