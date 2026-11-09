#!/usr/bin/env python3
"""Offline security regressions for the manual FL VPS remote desktop."""
import inspect
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fl_rootless_owner_desktop as m


class FLOwnerDesktopSecurity(unittest.TestCase):
    def test_original_gateway_not_used(self):
        self.assertEqual(m.LOGIN, "olegendorphine")
        self.assertNotIn('<input', m.PAGE.lower())
        self.assertNotIn('typeText()', m.PAGE)
        self.assertNotIn('/start?token=', m.PAGE)
        self.assertIn('location.hash', m.PAGE)
        self.assertIn('/api/claim', m.PAGE)
        self.assertIn('history.replaceState', m.PAGE)

    def test_no_automated_login_captcha_or_bids(self):
        self.assertNotIn('/api/type', inspect.getsource(m.HandoffHandler))
        self.assertNotIn('page.keyboard.type(', inspect.getsource(m.HandoffHandler))
        self.assertIn('"/api/char"', inspect.getsource(m.HandoffHandler))
        self.assertIn('page.keyboard.insert_text(char)', inspect.getsource(m.HandoffHandler))
        self.assertIn('login_not_verified', inspect.getsource(m.HandoffHandler))
        self.assertNotIn('submit_bid', inspect.getsource(m.HandoffHandler))
        self.assertNotIn('captcha.solve', inspect.getsource(m.HandoffHandler).lower())

    def test_url_gate(self):
        self.assertTrue(m.is_fl_url("https://www.fl.ru/account/login/"))
        self.assertTrue(m.is_fl_url("https://fl.ru/profile/setup/main/"))
        for url in ("http://fl.ru", "https://evil-fl.ru", "https://fl.ru.evil.com",
                    "https://evil.com", "javascript:alert(1)"):
            self.assertFalse(m.is_fl_url(url))

    def test_rootless_no_system_writes(self):
        src = inspect.getsource(m.Browser.open)
        self.assertIn('executable.write_bytes(image.replace(old, replacement))', src)
        self.assertIn('headless=False', src)
        self.assertIn('runpath / "Xvfb"', src)
        self.assertNotIn('sudo', src)
        self.assertNotIn('apt-get', src)
        self.assertIn('127.0.0.1', inspect.getsource(m.main))

    def test_token_owner_only_and_expiry(self):
        src = inspect.getsource(m.HandoffHandler.do_POST)
        self.assertIn('hmac.compare_digest', src)
        self.assertIn('"Origin"', src)
        self.assertIn('HttpOnly; Secure; SameSite=Strict', src)
        self.assertTrue(180 <= m.TTL <= 900)


if __name__ == "__main__":
    unittest.main()
