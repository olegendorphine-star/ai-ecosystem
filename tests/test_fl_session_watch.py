#!/usr/bin/env python3
"""Offline deterministic tests for FL session watchdog; never contact FL.ru."""
from __future__ import annotations
import inspect
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fl_session_watch as monitor


class FLWatchTests(unittest.TestCase):
    def test_healthy_requires_exact_owner_and_settings(self):
        yes = dict(settings_visible=True, owner_visible=True,
                   login_visible=False, captcha_visible=False)
        self.assertEqual(monitor.classify_owner_page(
            "https://www.fl.ru/profile/setup/main/", 200, **yes), "healthy")
        # FL settings can redirect, so do not require a fixed profile URL.
        self.assertEqual(monitor.classify_owner_page(
            "https://www.fl.ru/users/olegendorphine/", 200, **yes), "healthy")
        self.assertEqual(monitor.classify_owner_page(
            "https://www.fl.ru/profile/setup/main/", 200,
            **{**yes, "owner_visible": False}), "technical_error")

    def test_fail_closed_for_login_captcha_rate_limits_and_bad_domains(self):
        kw = dict(settings_visible=False, owner_visible=False,
                  login_visible=False, captcha_visible=False)
        self.assertEqual(monitor.classify_owner_page(
            "https://www.fl.ru/account/login/", 200, **kw), "auth_required")
        self.assertEqual(monitor.classify_owner_page(
            "https://www.fl.ru/profile/setup/main/", 200,
            **{**kw, "captcha_visible": True}), "captcha_required")
        self.assertEqual(monitor.classify_owner_page(
            "https://fl.ru/profile/setup/main/", 429, **kw), "access_restricted")
        self.assertEqual(monitor.classify_owner_page(
            "https://fl.ru.attacker.example/profile/setup/main/", 200, **kw),
            "technical_error")

    def test_transition_alerts_only_on_changes(self):
        self.assertEqual(monitor.transition(None, "healthy"), "none")
        self.assertEqual(monitor.transition(None, "auth_required"), "failure")
        self.assertEqual(monitor.transition("healthy", "healthy"), "none")
        self.assertEqual(monitor.transition("healthy", "auth_required"), "failure")
        self.assertEqual(monitor.transition("auth_required", "healthy"), "recovered")
        self.assertEqual(monitor.transition("auth_required", "auth_required"), "none")
        self.assertEqual(monitor.transition("healthy", "already_running"), "none")

    def test_no_automated_account_actions(self):
        src = inspect.getsource(monitor)
        self.assertIn("browser.open(Path(tmp))", src)
        self.assertIn("browser.close()", src)
        self.assertIn("page.goto(portal.ALLOWED_PAGES[\"settings\"]", src)
        self.assertNotIn("page.mouse.click(", src)
        self.assertNotIn("page.keyboard.", src)
        self.assertNotIn("storage_state(path=", src)
        self.assertNotIn("new_cdp_session", src)
        self.assertNotIn("cloudflared", src)
        self.assertNotIn("login.submit", src)
        self.assertNotIn("captcha.solve", src)
        self.assertEqual(len(monitor.ALLOWED_STATUSES), 7)


if __name__ == "__main__":
    unittest.main()
