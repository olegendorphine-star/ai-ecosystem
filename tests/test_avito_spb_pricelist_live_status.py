import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "tools" / "avito_spb_pricelist_live_status.py"
spec = importlib.util.spec_from_file_location("avito_spb_pricelist_live_status", PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class AvitoLiveStatusTests(unittest.TestCase):
    def test_public_feed_two_ad_integrity(self):
        xml = (Path(__file__).resolve().parents[1] / "docs" / "avito-feed.xml").read_bytes()
        s = m.feed_check(xml)
        self.assertTrue(all(s.values()))

    def test_api_no_write_except_oauth(self):
        with self.assertRaises(ValueError):
            m.http(m.API + "/autoload/v1/upload", body=b"{}")
        with self.assertRaises(ValueError):
            m.http(m.API + "/messenger/v2/accounts/1/chats")
        with self.assertRaises(ValueError):
            m.http(m.API + "/core/v2/items/1/vas/", body=b"{}")

    def test_active_status_no_private_fields(self):
        rows = {"resources": [
            {"id": 8347570435, "status": "active", "price": 5000, "phone": "SECRET"},
            {"id": 123, "status": "active", "price": 5000, "url": "https://www.avito.ru/sankt-peterburg/x", "email": "SECRET"},
        ]}
        s = m.active_check(rows)
        self.assertTrue(s["moscow_active"])
        self.assertTrue(s["spb_active"])
        self.assertNotIn("SECRET", json.dumps(s))

    def test_upload_section_and_status(self):
        s = m.upload_check({"upload_id": 628659811, "status": "processing"},
                           {"items": [{"id": "ai-assistant-memory-spb-001",
                                       "section": {"slug": "success_published"}}]})
        self.assertTrue(s["spb_in_current_items"])
        self.assertEqual(s["spb_section"], "success_published")

    def test_upload_unknown_status_not_claimed_success(self):
        s = m.upload_check({"upload_id": "private", "status": "weird"},
                           {"items": []})
        self.assertIsNone(s["upload_id"])
        self.assertEqual(s["spb_section"], "unknown")

    def test_no_oauth_if_public_xml_not_ready(self):
        with patch.object(m, "http", return_value=(404, None)) as request:
            result = m.inspect()
        self.assertEqual(request.call_count, 1)
        self.assertEqual(result["public_feed_http"], 404)
        self.assertNotIn("oauth_ok", result)
        self.assertEqual(result["autoload_posts"], 0)

if __name__ == "__main__":
    unittest.main()
