import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "avito_profile_report_guard.py"
spec = importlib.util.spec_from_file_location("avito_profile_report_guard", SOURCE)
app = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = app
spec.loader.exec_module(app)


class ProfileReportGuardTests(unittest.TestCase):
    def sample(self):
        return {
            "oauth_http": 200, "oauth_ok": True,
            "http": {"account": 200, "autoload_profile": 200,
                     "active_items": 200, "category_tree": 200},
            "category_fields_http": 200, "category_fields_observed": ["PriceList"],
            "pricelist_observed_in_fields": True,
            "items": {"moscow_active": True, "petersburg_active_first_page": True,
                      "active_items_first_page_count": 2},
            "writes": 0, "messages_read": 0, "messages_sent": 0, "charges_rub": 0,
            "email": "PRIVATE_EMAIL", "token": "PRIVATE_TOKEN",
            "chat": "PRIVATE_MESSAGE",
            "profile": {"private": "PRIVATE_ACCOUNT"},
        }

    def test_normal_report_strips_every_unknown_or_private_field(self):
        data = app.validate(self.sample())
        text = json.dumps(data, ensure_ascii=False)
        for forbidden in ("PRIVATE", "token", "email", "chat", "profile"):
            self.assertNotIn(forbidden, text)
        self.assertTrue(data["pricelist_observed_in_fields"])
        self.assertEqual(data["http"]["category_tree"], 200)

    def test_unknown_name_in_public_fields_rejected(self):
        payload = self.sample()
        payload["category_fields_observed"].append("client_phone")
        with self.assertRaises(ValueError):
            app.validate(payload)

    def test_refuse_a_report_claiming_any_mutation(self):
        for key in ("writes", "messages_read", "messages_sent", "charges_rub"):
            payload = self.sample()
            payload[key] = 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                app.validate(payload)

    def test_http_rate_limit_is_not_success(self):
        payload = self.sample()
        payload["http"]["category_tree"] = 429
        payload.pop("category_fields_http")
        payload.pop("category_fields_observed")
        payload.pop("pricelist_observed_in_fields")
        result = app.validate(payload)
        self.assertEqual(result["http"]["category_tree"], 429)
        self.assertNotIn("pricelist_observed_in_fields", result)

    def test_reject_invented_or_malformed_status(self):
        for status in (True, 600, -2, "200", 1.2):
            payload = self.sample()
            payload["http"]["active_items"] = status
            with self.subTest(status=status), self.assertRaises(ValueError):
                app.validate(payload)

    def test_zero_is_not_allowed_as_missing_values(self):
        payload = self.sample()
        payload.pop("writes")
        with self.assertRaises(ValueError):
            app.validate(payload)

    def test_script_saves_only_sanitized_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "raw.json"
            dst = Path(tmp) / "report.json"
            src.write_text(json.dumps(self.sample()), encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = app.main([str(src), str(dst)])
            self.assertEqual(code, 0)
            data = json.loads(dst.read_text(encoding="utf-8"))
            self.assertEqual(data["schema"], "avito.profile.inventory.redacted.v1")
            self.assertNotIn("PRIVATE", dst.read_text(encoding="utf-8"))

    def test_script_rejects_raw_sensitive_field_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "raw.json"
            dst = Path(tmp) / "report.json"
            payload = self.sample()
            payload["category_fields_observed"] = ["PRIVATE_CUSTOMER_NAME"]
            src.write_text(json.dumps(payload), encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = app.main([str(src), str(dst)])
            self.assertEqual(code, 4)
            self.assertFalse(dst.exists())


if __name__ == "__main__":
    unittest.main()
