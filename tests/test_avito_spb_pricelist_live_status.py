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

    def test_skips_rate_limited_items_during_processing(self):
        xml = (Path(__file__).resolve().parents[1] / "docs" / "avito-feed.xml").read_bytes()
        requested = []
        def fake(url, auth=None, body=None):
            requested.append(url)
            if url == m.FEED:
                return 200, xml
            if url == m.API + "/token/":
                return 200, {"access_token": "TEST_ONLY"}
            if url.startswith(m.API + "/core/v1/items"):
                return 200, {"resources": []}
            if url == m.API + "/autoload/v4/uploads/current":
                return 200, {"upload_id": 628665408, "status": "processing"}
            raise AssertionError("Unexpected live route " + url)
        with patch.dict(m.os.environ, {"AVITO_CLIENT_ID": "test", "AVITO_CLIENT_SECRET": "test"}):
            with patch.object(m, "http", side_effect=fake):
                out = m.inspect()
        self.assertEqual(out["current_items_check"], "skipped_while_processing")
        self.assertNotIn("current_items", out["http"])
        self.assertTrue(all("/current/items" not in u for u in requested))
        self.assertEqual(out["autoload_posts"], 0)

    def test_calls_items_once_after_final_upload_status(self):
        xml = (Path(__file__).resolve().parents[1] / "docs" / "avito-feed.xml").read_bytes()
        called = []
        def fake(url, auth=None, body=None):
            called.append(url)
            if url == m.FEED:
                return 200, xml
            if url == m.API + "/token/":
                return 200, {"access_token": "TEST_ONLY"}
            if url.startswith(m.API + "/core/v1/items"):
                return 200, {"resources": []}
            if url == m.API + "/autoload/v4/uploads/current":
                return 200, {"upload_id": 628665408, "status": "completed"}
            if url == m.API + "/autoload/v4/uploads/current/items":
                return 429, None
            raise AssertionError("Unexpected route " + url)
        with patch.dict(m.os.environ, {"AVITO_CLIENT_ID": "test", "AVITO_CLIENT_SECRET": "test"}):
            with patch.object(m, "http", side_effect=fake):
                out = m.inspect()
        self.assertEqual(out["current_items_check"], "rate_limited")
        self.assertEqual(out["http"]["current_items"], 429)
        self.assertEqual(called.count(m.API + "/autoload/v4/uploads/current/items"), 1)

    def test_public_petersburg_id_and_url_without_tracking_params(self):
        rows = {"resources": [{"id": 8347570435, "status": "active", "price": 5000},
           {"id": 8347570999, "status": "active", "price": 5000,
            "url": "https://www.avito.ru/sankt-peterburg/predlozheniya_uslug/test_8347570999?contact=PRIVATE"}]}
        report = m.active_check(rows)
        self.assertEqual(report["spb_public_ad_id"], 8347570999)
        self.assertEqual(report["spb_public_url"],
                         "https://www.avito.ru/sankt-peterburg/predlozheniya_uslug/test_8347570999")
        self.assertNotIn("PRIVATE", json.dumps(report))

if __name__ == "__main__":
    unittest.main()
