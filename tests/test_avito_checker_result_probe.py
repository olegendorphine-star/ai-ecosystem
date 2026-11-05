import importlib.util
import json
import sys
import unittest
import gzip
from pathlib import Path
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / "tools" / "avito_checker_result_probe.py"
spec = importlib.util.spec_from_file_location("avito_checker_result_probe", FILE)
p = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = p
spec.loader.exec_module(p)


class AvitoResultProbeTests(unittest.TestCase):
    def test_json_object(self):
        r = p.classify(b'{"data":{"status":"processing"}}', "application/json")
        self.assertEqual(r["parse_type"], "json_object")
        self.assertIn("data", r["top_level_known_keys"])

    def test_gzip_json(self):
        r = p.classify(gzip.compress(b'{"data":{"status":"done"}}'), "application/json", "gzip")
        self.assertEqual(r["compression"], "gzip")
        self.assertEqual(r["parse_type"], "json_object")

    def test_utf8_bom_json(self):
        r = p.classify(b"\xef\xbb\xbf" + b'{"data":{}}')
        self.assertEqual(r["parse_type"], "json_object")

    def test_html_fragment_does_not_leak(self):
        r = p.classify(b'<div>PRIVATE CUSTOMER PHONE 79999999999 ERROR</div>', "text/html")
        self.assertEqual(r["parse_type"], "html_fragment_or_invalid_xml")
        self.assertTrue(r["body_markers"]["error_phrase"])
        self.assertNotIn("PRIVATE", json.dumps(r))
        self.assertNotIn("79999999999", json.dumps(r))

    def test_pending_text(self):
        r = p.classify("Отчёт в работе".encode("utf-8"), "text/plain")
        self.assertTrue(r["body_markers"]["pending_phrase"])

    def test_not_mistake_failure_for_success(self):
        r = p.classify("XML не соответствует формату".encode("utf-8"))
        self.assertTrue(r["body_markers"]["xml_formally_invalid_phrase"])
        self.assertFalse(r["body_markers"]["xml_formally_valid_phrase"])

    def test_only_public_get(self):
        with patch.object(p.urllib.request, "urlopen", side_effect=AssertionError("blocked")):
            with self.assertRaises(AssertionError):
                p.read_public_result()
        self.assertEqual(p.RESULT_URL.count("/result/"), 1)
        self.assertIn("/api/v2/public/xml_checker/result/", p.RESULT_URL)
        self.assertNotIn("/autoload/v1/upload", p.RESULT_URL)

    def test_malformed_gzip(self):
        r = p.classify(b"\x1f\x8bfoo", "text/plain")
        self.assertEqual(r["parse_type"], "gzip_invalid")

if __name__ == "__main__":
    unittest.main()
