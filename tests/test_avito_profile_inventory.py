import importlib.util
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "tools" / "avito_profile_inventory.py"
spec = importlib.util.spec_from_file_location("avito_profile_inventory", PATH)
app = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = app
spec.loader.exec_module(app)


class TestAvitoProfileInventory(unittest.TestCase):
    def test_default_offline_does_not_touch_network(self):
        with patch.object(app, "call", side_effect=AssertionError("network forbidden")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(app.main([]), 0)
        self.assertEqual(json.loads(buf.getvalue())["network_calls"], 0)

    def test_live_gate_requires_opt_in(self):
        with patch.dict(os.environ, {"AVITO_ALLOW_PROFILE_INVENTORY": "NO"}):
            with patch.object(app, "call", side_effect=AssertionError("network forbidden")):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(app.main(["--live", "--approve-readonly"]), 2)

    def test_mutations_and_messages_are_rejected(self):
        for path in ("/messenger/v2/accounts/123/chats",
                     "/autoload/v1/upload",
                     "/core/v2/items/123/vas/",
                     "/core/v1/accounts/123/balance/",
                     "https://evil.example/path"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    app.call(path)
        with self.assertRaises(ValueError):
            app.call("/autoload/v2/profile", oauth_form=b"x")

    def test_category_slug_prefers_specific_leaf(self):
        tree = {"nodes": [
            {"name": "Деловые услуги", "slug": "business-services"},
            {"name": "IT, дизайн, тексты", "slug": "it-design"},
            {"name": "Программирование, настройка CRM", "slug": "programming-crm"},
        ]}
        self.assertEqual(app.find_category_slug(tree), "programming-crm")
        self.assertIsNone(app.find_category_slug([{"name": "Other", "slug": "other"}]))

    def test_public_fields_whitelist_never_leaks_contact(self):
        data = {"fields": [
            {"name": "PriceList", "email": "private@example.com"},
            {"name": "ServicePriceType", "values": ["private client name"]},
            {"name": "SomeSecret", "value": "token"},
        ]}
        result = app.allowed_field_names(data)
        self.assertEqual(result, ["PriceList", "ServicePriceType"])
        self.assertNotIn("private", str(result))
        self.assertNotIn("token", str(result))

    def test_safe_items(self):
        response = {"resources": [
            {"id": 8347570435, "price": 5000, "status": "active", "phone": "SECRET"},
            {"id": 123, "status": "active", "url": "https://www.avito.ru/sankt-peterburg/a"},
        ]}
        result = app.summarize_items(response)
        self.assertTrue(result["moscow_active"])
        self.assertTrue(result["petersburg_active_first_page"])
        self.assertEqual(result["active_items_first_page_count"], 2)
        self.assertNotIn("SECRET", json.dumps(result))

    def test_inventory_redacted_and_four_gets_plus_field_probe(self):
        def fake(path, token=None, oauth_form=None):
            if path == "/token/":
                return app.Result(200, {"access_token": "PRIVATE_TOKEN"})
            if path == "/autoload/v1/user-docs/tree":
                return app.Result(200, {"children": [
                    {"name": "Программирование, настройка CRM", "slug": "programming-crm"}
                ]})
            if path.endswith("/fields"):
                return app.Result(200, {"fields": [{"name": "PriceList"}]})
            if path == "/autoload/v2/profile":
                return app.Result(200, {"autoload_enabled": True,
                                        "feed_url": "https://private"})
            if path.startswith("/core/v1/items"):
                return app.Result(200, {"resources": [{"id": 8347570435,
                                      "status": "active", "phone": "9999"}]})
            if path == "/core/v1/accounts/self":
                return app.Result(200, {"email": "secret@example.com"})
            raise AssertionError(path)
        with patch.dict(os.environ, {"AVITO_CLIENT_ID": "client", "AVITO_CLIENT_SECRET": "private"}):
            with patch.object(app, "call", side_effect=fake) as calls:
                report = app.inventory()
        self.assertTrue(report["pricelist_observed_in_fields"])
        self.assertEqual(calls.call_count, 6)
        out = json.dumps(report)
        for secret in ("PRIVATE_TOKEN", "secret@example.com", "https://private", "9999"):
            self.assertNotIn(secret, out)
        self.assertEqual(report["messages_read"], 0)
        self.assertEqual(report["writes"], 0)

    def test_rate_limit_is_not_false_success(self):
        def fake(path, token=None, oauth_form=None):
            if path == "/token/":
                return app.Result(200, {"access_token": "secret"})
            if path == "/autoload/v1/user-docs/tree":
                return app.Result(429)
            if path == "/core/v1/items?status=active&per_page=99&page=1":
                return app.Result(429)
            return app.Result(200, {})
        with patch.dict(os.environ, {"AVITO_CLIENT_ID": "x", "AVITO_CLIENT_SECRET": "y"}):
            with patch.object(app, "call", side_effect=fake):
                report = app.inventory()
        self.assertEqual(report["http"]["category_tree"], 429)
        self.assertNotIn("pricelist_observed_in_fields", report)
        self.assertNotIn("items", report)


if __name__ == "__main__":
    unittest.main()
