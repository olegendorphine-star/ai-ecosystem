import importlib.util
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "avito_session_guardian.py"
spec = importlib.util.spec_from_file_location("avito_session_guardian", SOURCE)
guardian = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guardian)


class GuardianDecisionTests(unittest.TestCase):
    def test_live_403_is_access_restricted_not_expired_auth(self):
        result = guardian.classify_owner_probe({
            "browser_ready": True, "profile_route_reached": True,
            "auth_state": "unverified", "site_http_status": 403
        })
        self.assertEqual(result["state"], "access_restricted")
        self.assertEqual(result["next_action"], "stop_and_request_support_review")
        self.assertFalse(result["retry_blocked_page"])
        self.assertFalse(result["automatic_login_allowed"])
        self.assertFalse(result["browser_write_actions_allowed"])

    def test_rate_limit_never_retries(self):
        result = guardian.classify_owner_probe({
            "browser_ready": True, "site_http_status": 429
        })
        self.assertEqual(result["state"], "rate_limited")
        self.assertFalse(result["retry_blocked_page"])

    def test_explicit_auth_required_owner_only(self):
        result = guardian.classify_owner_probe({
            "browser_ready": True, "auth_challenge_visible": True,
            "site_http_status": 200
        })
        self.assertEqual(result["state"], "auth_required")
        self.assertEqual(result["next_action"], "request_owner_login")
        self.assertFalse(result["automatic_login_allowed"])

    def test_likely_active_is_not_verified(self):
        result = guardian.classify_owner_probe({
            "browser_ready": True, "profile_route_reached": True,
            "auth_state": "likely_active", "site_http_status": 200
        })
        self.assertEqual(result["state"], "likely_active_unverified")
        self.assertFalse(result["browser_write_actions_allowed"])

    def test_unrecognized_probes_fail_closed_without_pii(self):
        for item in (None, {}, [], "private", {
            "browser_ready": True, "username": "SECRET",
            "cookies": ["SECRET_COOKIE"], "site_http_status": 200
        }):
            report = guardian.classify_owner_probe(item)
            self.assertFalse(report["browser_write_actions_allowed"])
            self.assertNotIn("SECRET", str(report))

    def test_down_browser_does_not_attempt_login(self):
        report = guardian.classify_owner_probe({"browser_ready": False})
        self.assertEqual(report["state"], "browser_unavailable")
        self.assertFalse(report["automatic_login_allowed"])


if __name__ == "__main__":
    unittest.main()
