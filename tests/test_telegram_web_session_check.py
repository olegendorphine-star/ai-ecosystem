"""Offline tests: privacy-safe Telegram Web session classification."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/telegram_web_session_check.py"
spec = importlib.util.spec_from_file_location("tg_web_session_check", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SessionClassificationTests(unittest.TestCase):
    def test_chatlist_and_sidebar_confirm_login(self):
        self.assertEqual(mod.classify({"telegram_origin": True, "sidebar_visible": True,
                                       "chatlist_visible": True, "auth_ui_visible": False}),
                         "authenticated")

    def test_login_form_blocks_success(self):
        self.assertEqual(mod.classify({"telegram_origin": True, "sidebar_visible": True,
                                       "chatlist_visible": True, "auth_ui_visible": True}),
                         "auth_required")

    def test_no_false_positive_without_chatlist(self):
        self.assertEqual(mod.classify({"telegram_origin": True, "sidebar_visible": True,
                                       "chatlist_visible": False, "auth_ui_visible": False}),
                         "inconclusive")

    def test_wrong_origin_blocks_success(self):
        self.assertEqual(mod.classify({"telegram_origin": False, "sidebar_visible": True,
                                       "chatlist_visible": True, "auth_ui_visible": False}),
                         "inconclusive")

    def test_malformed_input_not_authenticated(self):
        for obj in (None, "", [], {}, {"telegram_origin": True}):
            self.assertEqual(mod.classify(obj), "inconclusive")

    def test_no_private_browser_content_or_network_export(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("innerText", source[source.index("UI_SIGNALS_JS"):source.index("def profile_safe")])
        self.assertNotIn("storage_state()", source)
        self.assertNotIn("page.screenshot(", source)
        self.assertNotIn("get_attribute(", source)
        self.assertNotIn("input.value", source)
        self.assertIn("LOCK_EX | fcntl.LOCK_NB", source)

    def test_missing_profile_is_not_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing"
            self.assertFalse(mod.profile_safe(path))


if __name__ == "__main__":
    unittest.main()
