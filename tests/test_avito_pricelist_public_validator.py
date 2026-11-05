import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "avito_pricelist_public_validator.py"
spec = importlib.util.spec_from_file_location("avito_pricelist_public_validator", SCRIPT)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class AvitoPublicValidatorTests(unittest.TestCase):
    def test_allowlist_rejects_account_urls(self):
        with self.assertRaises(ValueError):
            v.fetch("https://api.avito.ru/autoload/v1/upload", data=b"{}")
        with self.assertRaises(ValueError):
            v.fetch("https://api.avito.ru/token/", data=b"{}")
        with self.assertRaises(ValueError):
            v.fetch("https://evil.example/test")

    def test_checker_id_explicit_data(self):
        self.assertEqual(v.extract_id({"data": {"id": "6aec2f3a135917229b21cf87"}}),
                         "6aec2f3a135917229b21cf87")
        self.assertIsNone(v.extract_id({"data": {"id": "../evil"}}))
        self.assertIsNone(v.extract_id({"status": "ok"}))

    def test_pending_cannot_pass(self):
        r = v.describe_result({"data": {"status": "processing", "message": "Отчёт в работе"}})
        self.assertEqual(r["state"], "pending")

    def test_errors_are_detected(self):
        r = v.describe_result({"data": {"status": "done",
                            "errors": [{"code": 1008}, {"code": "1316"}]}})
        self.assertEqual(r["state"], "errors_reported")
        self.assertEqual(r["error_count_at_least"], 2)
        self.assertEqual(r["reported_error_codes"], ["1008", "1316"])

    def test_unknown_never_means_passed(self):
        r = v.describe_result({"data": {"unexpected": {"arbitrary": "success"}}})
        self.assertEqual(r["state"], "unclassified_response")

    def test_sanitizer_does_not_output_untrusted_text(self):
        payload = {"private": "SECRET", "data": {"status": "error",
                           "error": {"code": "1008", "text": "PRIVATE_EMAIL"}}}
        s = json.dumps(v.describe_result(payload))
        self.assertNotIn("SECRET", s)
        self.assertNotIn("PRIVATE_EMAIL", s)

    def test_no_id_means_report_without_publication(self):
        calls = []
        def fake(url, data=None, content_type=None):
            calls.append((url, data))
            if url == v.CANDIDATE:
                return 200, b"<Ads><Ad></Ad><Ad></Ad><PriceList></PriceList></Ads>"
            if url == v.SUBMIT:
                return 200, {"data": {"other": 1}}
            raise AssertionError(url)
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "safe.json")
            with patch.object(v, "fetch", side_effect=fake), patch.object(v.time, "sleep"):
                self.assertEqual(v.main(dest), 0)
            output = json.loads(Path(dest).read_text())
            self.assertEqual(output["status"], "checker_id_missing")
            self.assertEqual(output["account_mutations"], 0)
            self.assertEqual(output["ad_upload_requests"], 0)
            self.assertFalse(output["validation_passed"])
            self.assertEqual(len(calls), 2)

    def test_final_report_is_not_automatically_valid(self):
        def fake(url, data=None, content_type=None):
            if url == v.CANDIDATE:
                return 200, b"<Ads><Ad></Ad><Ad></Ad><PriceList></PriceList></Ads>"
            if url == v.SUBMIT:
                return 200, {"data": {"id": "aaaaaaaaaaaaaaaa"}}
            if url.startswith(v.RESULT):
                return 200, {"data": {"status": "completed"}}
            raise AssertionError(url)
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "report.json")
            with patch.object(v, "fetch", side_effect=fake), patch.object(v.time, "sleep"):
                self.assertEqual(v.main(dest), 0)
            output = json.loads(Path(dest).read_text())
            self.assertEqual(output["status"], "final_report_returned")
            self.assertFalse(output["validation_passed"])
            self.assertEqual(output["charges_rub"], 0)

if __name__ == "__main__":
    unittest.main()
