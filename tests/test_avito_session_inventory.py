"""Offline tests. Never read real Avito cookies."""
import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "avito_session_inventory.py"
spec = importlib.util.spec_from_file_location("avito_session_inventory", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SessionInventoryTests(unittest.TestCase):
    def test_missing_state_is_not_authenticated(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = mod.inspect_profile(Path(tmp), current_time=10000)
        self.assertTrue(result["profile_present"])
        self.assertFalse(result["saved_state_present"])
        self.assertEqual(result["authenticated"], "unverified")

    def test_dummy_state_never_exposes_cookie_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "storage_state.json"
            state.write_text(json.dumps({"cookies": [
                {"domain": ".avito.ru", "name": "secret", "value": "DO_NOT_LEAK"},
                {"domain": ".other.example", "name": "other", "value": "ALSO_SECRET"}],
                "origins": [{"origin": "https://www.avito.ru/", "localStorage": [
                    {"name": "account", "value": "PERSONAL_INFO"}]}
                ]}))
            os.chmod(state, 0o600)
            report = mod.inspect_profile(root, current_time=state.stat().st_mtime + 100)
        self.assertTrue(report["saved_state_valid"])
        self.assertTrue(report["saved_state_owner_only"])
        self.assertTrue(report["avito_cookie_present"])
        self.assertEqual(report["saved_state_age"], "under_1h")
        self.assertEqual(report["authenticated"], "unverified")
        printed = json.dumps(report)
        for secret in ("DO_NOT_LEAK", "ALSO_SECRET", "PERSONAL_INFO", "secret", "account"):
            self.assertNotIn(secret, printed)

    def test_weak_permissions_are_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "storage_state.json"
            state.write_text('{"cookies":[]}')
            os.chmod(state, 0o644)
            result = mod.inspect_profile(Path(tmp))
            self.assertFalse(result["saved_state_owner_only"])
            self.assertTrue(result["saved_state_present"])

    def test_symlinked_state_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            external = root / "external.json"
            external.write_text('{"cookies":[{"domain":".avito.ru","value":"DO_NOT_LEAK"}]}')
            (root / "storage_state.json").symlink_to(external)
            result = mod.inspect_profile(root)
            self.assertFalse(result["saved_state_present"])
            self.assertFalse(result["avito_cookie_present"])

    def test_malformed_and_oversized_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "storage_state.json"
            state.write_text("not json")
            self.assertFalse(mod.inspect_profile(Path(tmp))["saved_state_valid"])
            state.write_bytes(b"x" * (mod.MAX_BYTES + 1))
            self.assertFalse(mod.inspect_profile(Path(tmp))["saved_state_present"])

    def test_status_classification_is_not_auth_confirmation(self):
        payload = {"ok": True, "url": "https://www.avito.ru/profile",
                   "title": "VERY_PRIVATE_USER", "startup_error": ""}
        flags = mod.status_flags(payload)
        self.assertTrue(flags["browser_ready"])
        self.assertTrue(flags["on_avito_public_origin"])
        self.assertNotIn("title", flags)
        self.assertNotIn("VERY_PRIVATE_USER", str(flags))
        self.assertFalse(mod.status_flags({"ok": False, "url": "about:blank"})["browser_ready"])
        self.assertFalse(mod.status_flags({})["on_avito_public_origin"])


if __name__ == "__main__":
    unittest.main()
