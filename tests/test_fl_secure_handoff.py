"""Offline checks of one-time FL handoff. Never launches Chrome/tunnel."""
import importlib.util
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1]/"tools"/"fl_secure_handoff.py"
spec = importlib.util.spec_from_file_location("fl_secure_handoff", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SecurityTests(unittest.TestCase):
    def test_gateway_is_loopback_only_in_config(self):
        self.assertIn('("127.0.0.1", PORT)', SRC.read_text())

    def test_challenge_hostname_validation(self):
        self.assertTrue(mod.valid_host("abc.trycloudflare.com"))
        self.assertFalse(mod.valid_host("abc.trycloudflare.com.evil.test"))
        self.assertFalse(mod.valid_host("fl.example.com"))
        self.assertTrue(mod.valid_host("127.0.0.1:8990"))

    def test_browser_input_is_only_on_fl_https(self):
        self.assertTrue(mod.is_fl_url("https://www.fl.ru/account/login/"))
        self.assertTrue(mod.is_fl_url("https://fl.ru/profile/setup/main/"))
        self.assertFalse(mod.is_fl_url("http://www.fl.ru/account/login/"))
        self.assertFalse(mod.is_fl_url("https://www.fl.ru.phishing.example/account/login/"))
        self.assertFalse(mod.is_fl_url("https://login.google.com/"))
        self.assertFalse(mod.is_fl_url("not a url"))

    def test_all_navigation_routes_are_allowlisted(self):
        self.assertTrue(all(mod.is_fl_url(v) for v in mod.ALLOWED_PAGES.values()))
        self.assertIn("login", mod.ALLOWED_PAGES)
        self.assertEqual(mod.LOGIN, "olegendorphine")
        self.assertNotIn("olegendorphine2", mod.ALLOWED_PAGES.values())

    def test_session_file_saved_private_without_emitting_cookies(self):
        class Context:
            def storage_state(self):
                return {"cookies":[{"domain":".fl.ru","name":"SESSION",
                                    "value":"VERY_SECRET"}],"origins":[]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"profile"
            with patch.object(mod,"PROFILE",root),patch.object(mod,"STATE",root/"storage_state.json"):
                mod.save_state(Context())
                self.assertEqual(stat.S_IMODE(mod.STATE.stat().st_mode),0o600)
                self.assertEqual(stat.S_IMODE(root.stat().st_mode),0o700)
                self.assertIn("VERY_SECRET",mod.STATE.read_text())

    def test_symlinked_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"profile"
            root.mkdir()
            other=Path(tmp)/"secret"
            other.write_text("do not overwrite")
            (root/"storage_state.json").symlink_to(other)
            class Context:
                def storage_state(self):
                    return {"cookies":[]}
            with patch.object(mod,"PROFILE",root),patch.object(mod,"STATE",root/"storage_state.json"):
                with self.assertRaisesRegex(RuntimeError,"state_symlink_rejected"):
                    mod.save_state(Context())
            self.assertEqual(other.read_text(),"do not overwrite")

    def test_page_contains_no_external_script_or_remote_inclusions(self):
        self.assertNotIn("<script src",mod.PAGE)
        self.assertNotIn("<iframe",mod.PAGE)
        self.assertIn("__CSRF__",mod.PAGE)
        self.assertNotIn("https://www.fl.ru/account/login/",mod.PAGE)
        self.assertLessEqual(mod.TTL,1200)

    def test_credentials_never_in_unauthenticated_log(self):
        src=SRC.read_text()
        self.assertIn("def log_message(self, *args):",src)
        self.assertIn("HttpOnly; Secure; SameSite=Strict",src)
        self.assertIn('"x-fl-csrf":csrf',src)
        self.assertIn("not_on_fl_site",src)
        self.assertNotIn('print(self.server.secret)',src)


if __name__=="__main__":
    unittest.main()
