import base64
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / "tools" / "avito_support_account_id_encrypted.py"
spec = importlib.util.spec_from_file_location("avito_support_account_id_encrypted", FILE)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class AvitoSupportProfileIdTests(unittest.TestCase):
    def test_extract_own_profile_id(self):
        self.assertEqual(m.identify({"id": 123456789, "email": "SECRET"}), "123456789")
        self.assertEqual(m.identify({"id": "123456789"}), "123456789")

    def test_reject_bad_or_ad_ids(self):
        for v in (None, 0, -1, True, "1", "secret", "00001", 2.7, []):
            with self.subTest(v=v):
                self.assertIsNone(m.identify({"id": v}))
        self.assertIsNone(m.identify({"item_id": 8347570435}))

    def test_only_oauth_post_and_self_get(self):
        with self.assertRaises(ValueError):
            m.call("/autoload/v1/upload", data=b"x")
        with self.assertRaises(ValueError):
            m.call("/messenger/v2/accounts/123/chats")
        with self.assertRaises(ValueError):
            m.call("/core/v1/accounts/self", data=b"x")
        with self.assertRaises(ValueError):
            m.call("/token/")

    def test_encrypt_no_plaintext_and_randomized(self):
        first = m.encrypt_numeric_id("123456789")
        second = m.encrypt_numeric_id("123456789")
        self.assertNotEqual(first, second)
        self.assertEqual(len(base64.b64decode(first)), 256)
        self.assertNotIn("123456789", first)

    def test_never_publishes_profile_id_if_missing(self):
        with patch.dict(os.environ, {"AVITO_CLIENT_ID": "TEST", "AVITO_CLIENT_SECRET": "TEST"}):
            with patch.object(m, "call", side_effect=[(200, {"access_token": "FAKE"}),
                                                      (200, {"other_id": 123456789})]):
                out = m.inspect()
        self.assertEqual(out["status"], "id_missing_or_unexpected")
        self.assertNotIn("encrypted_id", out)
        self.assertEqual(out["messages_read"], 0)

    def test_public_result_only_ciphertext(self):
        with patch.dict(os.environ, {"AVITO_CLIENT_ID": "TEST", "AVITO_CLIENT_SECRET": "TEST"}):
            with patch.object(m, "call", side_effect=[(200, {"access_token": "FAKE"}),
                                                      (200, {"id": 123456789, "email": "SECRET"})]):
                out = m.inspect()
        saved = json.dumps(out)
        self.assertEqual(out["status"], "encrypted_id_ready")
        self.assertNotIn("123456789", saved)
        self.assertNotIn("SECRET", saved)
        self.assertFalse(out["plaintext_logged"])
        self.assertFalse(out["plaintext_stored"])
        self.assertEqual(out["ads_changed"], 0)

if __name__ == "__main__":
    unittest.main()
