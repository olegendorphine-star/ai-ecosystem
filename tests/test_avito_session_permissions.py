"""Permission repair tests use only temporary dummy files."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "avito_session_permissions.py"
spec = importlib.util.spec_from_file_location("session_permissions", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class PermissionsTests(unittest.TestCase):
    def test_secure_existing_session_no_content_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "profile"
            root.mkdir(mode=0o755)
            state = root / "storage_state.json"
            state.write_bytes(b'{"cookies":[{"domain":".avito.ru","value":"VERY_SECRET"}]}')
            os.chmod(state, 0o644)
            report = mod.secure_profile(root)
            self.assertTrue(report["ok"])
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)
            self.assertIn(b"VERY_SECRET", state.read_bytes())
            self.assertNotIn("VERY_SECRET", str(report))

    def test_profile_with_no_state_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "profile"
            root.mkdir()
            report = mod.secure_profile(root)
            self.assertTrue(report["ok"])
            self.assertFalse(report["session_file_owner_only"])

    def test_symlinked_state_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "profile"
            root.mkdir()
            target = Path(tmp) / "secret_file"
            target.write_text("never open")
            os.chmod(target, 0o644)
            (root / "storage_state.json").symlink_to(target)
            report = mod.secure_profile(root)
            self.assertFalse(report["ok"])
            self.assertEqual(target.stat().st_mode & 0o777, 0o644)

    def test_symlinked_profile_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "profile"
            root.mkdir()
            link = Path(tmp) / "alias"
            link.symlink_to(root, target_is_directory=True)
            report = mod.secure_profile(link)
            self.assertFalse(report["ok"])


if __name__ == "__main__":
    unittest.main()
