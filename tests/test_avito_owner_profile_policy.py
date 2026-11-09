import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "avito_owner_profile_policy.py"
spec = importlib.util.spec_from_file_location("avito_owner_profile_policy", SOURCE)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
F = "a" * 64

def intent(action="profile_edit"):
    return {"schema": p.SCHEMA, "action": action, "target_fingerprint": F,
            "payload_sha256": "b" * 64}

def env(action="profile_edit"):
    return {"browser_ready": True, "site_http_status": 200,
            "owner_session_verified": True, "owner_identity_verified": True,
            "ui_supported_actions": [action], "unique_target_count": 1,
            "target_fingerprint": F, "private_backup_verified": True}

def approval(i, delete=False, secs=600):
    return {"owner_authorized": True, "intent_sha256": p.fingerprint(i),
            "expires_at": (NOW + timedelta(seconds=secs)).isoformat(),
            "confirm_delete": delete}

class PolicyTests(unittest.TestCase):
    def check(self, i, e, a, expected):
        r = p.assess(i, e, a, NOW)
        self.assertEqual(r["decision"], expected)
        self.assertIs(r["live_change_performed"], False)
        self.assertNotIn(F, str(r))
    def test_unsupported(self):
        self.check({"schema": p.SCHEMA, "action": "send_message"}, {}, None, "unsupported_action")
    def test_invalid_fields(self):
        self.check({"schema": p.SCHEMA, "action": "profile_edit"}, env(), None, "invalid_request")
    def test_access_controls(self):
        for status, expected in [(403, "access_restricted"), (451, "access_restricted"), (429, "rate_limited")]:
            e = env()
            e["site_http_status"] = status
            i = intent()
            self.check(i, e, approval(i), expected)
    def test_owner_identity(self):
        for field in ("owner_session_verified", "owner_identity_verified"):
            e = env()
            e[field] = False
            i = intent()
            self.check(i, e, approval(i), "auth_unverified")
    def test_target_capability(self):
        i = intent()
        e = env()
        e["ui_supported_actions"] = []
        self.check(i, e, approval(i), "capability_unverified")
        e = env()
        e["unique_target_count"] = 2
        self.check(i, e, approval(i), "target_unverified")
    def test_authorization(self):
        i = intent()
        self.check(i, env(), None, "approval_required")
        a = approval(i)
        a["intent_sha256"] = "0" * 64
        self.check(i, env(), a, "approval_mismatch")
    def test_expiry(self):
        i = intent()
        self.check(i, env(), approval(i, secs=-1), "approval_expired_or_too_long")
        self.check(i, env(), approval(i, secs=1801), "approval_expired_or_too_long")
    def test_edits_only_preflight(self):
        i = intent()
        self.check(i, env(), approval(i), "preflight_approved")
    def test_delete_backup_and_confirmation(self):
        for action in p.DELETE:
            i = intent(action)
            e = env(action)
            e["private_backup_verified"] = False
            self.check(i, e, approval(i, delete=True), "backup_required")
            e["private_backup_verified"] = True
            self.check(i, e, approval(i), "deletion_confirmation_required")
            self.check(i, e, approval(i, delete=True), "preflight_approved")
    def test_doc_capability_unknown(self):
        i = intent("portfolio_add_document")
        self.check(i, env(), approval(i), "capability_unverified")
    def test_read_only_requires_login(self):
        i = {"schema": p.SCHEMA, "action": "profile_inspect"}
        self.check(i, env(), None, "read_only_ready")
        e = env()
        e["owner_session_verified"] = False
        self.check(i, e, None, "auth_unverified")

if __name__ == "__main__":
    unittest.main()
