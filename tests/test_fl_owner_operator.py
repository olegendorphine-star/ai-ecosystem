"""FL owner integration tests. No network, account, browser or real cookies."""
import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1] / "tools"

def load(name):
    spec = importlib.util.spec_from_file_location(name, BASE / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

fl = load("fl_browser_probe")
policy = load("fl_operator_policy")
NOW = dt.datetime(2026, 11, 8, 12, 0, tzinfo=dt.timezone.utc)


class FLBrowserProbeTests(unittest.TestCase):
    def test_only_fl_https_domains_accepted(self):
        self.assertTrue(fl.safe_hostname("https://www.fl.ru/projects/"))
        self.assertFalse(fl.safe_hostname("http://www.fl.ru/projects/"))
        self.assertFalse(fl.safe_hostname("https://www.fl.ru.evil.example/"))
        self.assertFalse(fl.safe_hostname("https://other.example/"))

    def test_private_redirect_is_auth_required(self):
        r = fl.classify_response(
            200, "https://www.fl.ru/account/login/", "/profile/setup/main/"
        )
        self.assertEqual(r["state"], "auth_required")
        self.assertFalse(r["expected_route"])

    def test_public_route_200_is_reachable(self):
        r = fl.classify_response(
            200, "https://www.fl.ru/projects/", "/projects/"
        )
        self.assertEqual(r["state"], "reachable")
        self.assertTrue(r["expected_route"])

    def test_site_403_and_429_are_not_login(self):
        a = fl.classify_response(403, "https://www.fl.ru/projects/", "/projects/")
        b = fl.classify_response(429, "https://www.fl.ru/projects/", "/projects/")
        self.assertEqual(a["state"], "access_restricted")
        self.assertEqual(b["state"], "rate_limited")

    def test_saved_state_is_not_auth_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            file = profile / "storage_state.json"
            file.write_text('{"cookies":[{"name":"SECRET","value":"TOKEN"}]}')
            file.chmod(0o600)
            with patch.object(fl, "PROFILE_DIR", profile), patch.object(fl, "STATE_FILE", file):
                r = fl.safe_state_inventory()
        self.assertTrue(r["saved_session_present"])
        self.assertTrue(r["saved_state_owner_only"])
        self.assertEqual(r["authentication"], "unverified")
        self.assertNotIn("SECRET", str(r))
        self.assertNotIn("TOKEN", str(r))

    def test_symlinked_state_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            secret = profile / "other.json"
            secret.write_text('{"secret":"TOKEN"}')
            state = profile / "storage_state.json"
            state.symlink_to(secret)
            with patch.object(fl, "PROFILE_DIR", profile), patch.object(fl, "STATE_FILE", state):
                r = fl.safe_state_inventory()
        self.assertFalse(r["saved_session_present"])

    def test_no_saved_session_fails_closed_without_launching_chrome(self):
        with tempfile.TemporaryDirectory() as tmp:
            dir = Path(tmp)
            with patch.object(fl, "AGENT_DIR", dir), patch.object(fl, "PROFILE_DIR", dir/"profile"), patch.object(fl, "STATE_FILE", dir/"profile"/"storage_state.json"):
                r = fl.probe_routes("session_probe")
        self.assertEqual(r["auth_state"], "auth_required")
        self.assertFalse(r["browser_ready"])
        self.assertFalse(r["write_actions"])


class FLOperatorPolicyTests(unittest.TestCase):
    def req(self, action, **kwargs):
        return {"login": "olegendorphine", "action": action, **kwargs}

    def test_public_scan(self):
        r = policy.evaluate(self.req("scan_public"), now=NOW)
        self.assertEqual(r["decision"], "read_only_allowed")
        self.assertFalse(r["send_performed"])

    def test_refuse_wrong_account(self):
        r = policy.evaluate({"login": "olegendorphine2", "action": "scan_public"}, now=NOW)
        self.assertEqual(r["decision"], "blocked")

    def test_valid_project_url(self):
        self.assertTrue(policy.valid_fl_project(
            "https://www.fl.ru/projects/5528311/infografika-dlya-ozon-wb.html"
        ))
        self.assertFalse(policy.valid_fl_project(
            "https://www.fl.ru.evil.net/projects/5528311/a.html"
        ))

    def test_draft_is_safe_without_login(self):
        r = policy.evaluate(self.req(
            "draft_bid", project_url="https://www.fl.ru/projects/5528311/a.html"
        ), now=NOW)
        self.assertEqual(r["decision"], "draft_allowed")

    def test_no_bid_without_verified_owner(self):
        r = policy.evaluate(self.req("submit_bid", project_url="https://www.fl.ru/projects/5528311/a.html", session_state="unverified"), now=NOW)
        self.assertEqual(r["decision"], "manual_only")

    def test_no_bid_with_unknown_free_badge(self):
        r = policy.evaluate(self.req("submit_bid", project_url="https://www.fl.ru/projects/5528311/a.html",
            session_state="verified_owner", paid=False, free_badge_verified=False,
            approval={"expires_at": "2026-11-08T13:00:00Z"}),
            now=NOW)
        self.assertEqual(r["decision"], "manual_only")

    def test_block_paid_bid_even_with_approval(self):
        r = policy.evaluate(self.req("submit_bid", session_state="verified_owner",
            paid=True, fee_rub=80, approval={"allow_send": True, "expires_at": "2026-11-08T13:00:00Z"}),
            now=NOW)
        self.assertEqual(r["decision"], "manual_only")
        self.assertFalse(r["payment_performed"])

    def test_known_bid_is_duplicate(self):
        r = policy.evaluate(self.req("submit_bid", project_url="https://www.fl.ru/projects/5528311/a.html",
            session_state="verified_owner", paid=False, free_badge_verified=True,
            approval={"expires_at": "2026-11-08T13:00:00Z"}),
            now=NOW, already_sent={"5528311"})
        self.assertEqual(r["decision"], "manual_only")

    def test_exact_approval_required_to_prepare_submission(self):
        proposal = "Изучил требования к обработке товаров. Предлагаю сверить 2 примера и затем сделать весь объём с проверкой."
        base = self.req("submit_bid",
            project_url="https://www.fl.ru/projects/5528400/a.html",
            session_state="verified_owner", paid=False, free_badge_verified=True,
            proposal=proposal)
        base["approval"] = {"allow_send": True, "sha256": "wrong", "expires_at": "2026-11-08T13:00:00Z"}
        self.assertEqual(policy.evaluate(base, now=NOW)["decision"], "manual_only")
        base["approval"]["sha256"] = policy.digest(proposal)
        result = policy.evaluate(base, now=NOW)
        self.assertEqual(result["decision"], "manual_only")
        self.assertFalse(result["send_performed"])

    def test_profile_edit_rejects_sensitive_changes(self):
        change = {"password": "topsecret"}
        r = policy.evaluate(self.req("update_profile", session_state="verified_owner", paid=False,
            changes=change, approval={"allow_profile_edit": True, "expires_at": "2026-11-08T13:00:00Z"}),
            now=NOW)
        self.assertEqual(r["decision"], "manual_only")
        self.assertNotIn("topsecret", json.dumps(r))

    def test_profile_edit_only_with_exact_diff_approval(self):
        change = {"headline": "ИИ-ассистенты и автоматизация"}
        canonical = json.dumps(change, ensure_ascii=False, sort_keys=True)
        r = policy.evaluate(self.req("update_profile", session_state="verified_owner", paid=False,
            changes=change, approval={"allow_profile_edit": True, "sha256": policy.digest(canonical),
                "expires_at": "2026-11-08T13:00:00Z"}), now=NOW)
        self.assertEqual(r["decision"], "manual_only")
        self.assertFalse(r["profile_changed"])


    def test_all_account_actions_manual_even_with_valid_approval(self):
        for action in ("submit_bid", "update_profile", "inspect_profile"):
            request = self.req(action, session_state="verified_owner",
                paid=False, fee_rub=0, free_badge_verified=True,
                project_url="https://www.fl.ru/projects/5528400/a.html",
                proposal="Реальный текст отклика, согласованный владельцем и подходящий для отправки на FL.ru.",
                changes={"headline": "Новая специализация"},
                approval={"allow_send": True, "allow_profile_edit": True,
                    "expires_at": "2026-11-08T13:00:00Z"})
            result = policy.evaluate(request, now=NOW)
            self.assertEqual(result["decision"], "manual_only", action)
            self.assertEqual(result["next_action"], "open_official_fl_site_for_owner")
            self.assertFalse(result["send_performed"])
            self.assertFalse(result["profile_changed"])
            self.assertFalse(result["payment_performed"])



if __name__ == "__main__":
    unittest.main()
