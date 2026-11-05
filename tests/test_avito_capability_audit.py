import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "tools" / "avito_capability_audit.py"
spec = importlib.util.spec_from_file_location("avito_capability_audit", MODULE)
m = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class AuditTests(TestCase):
    def test_offline_has_zero_network_calls(self):
        with patch.object(m, "request_json", side_effect=AssertionError("network")):
            out = io.StringIO()
            with redirect_stdout(out):
                status = m.main([])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out.getvalue())["network_calls"], 0)

    def test_live_gate_requires_explicit_yes(self):
        with patch.dict(m.os.environ, {"AVITO_ALLOW_CAPABILITY_AUDIT": "NO"}):
            with patch.object(m, "request_json", side_effect=AssertionError("network")):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(m.main(["--live", "--approve-readonly"]), 2)

    def test_reject_non_whitelisted_methods(self):
        with self.assertRaises(ValueError):
            m.request_json("/core/v2/items/1/vas/", form=b"{}")
        with self.assertRaises(ValueError):
            m.request_json("/messenger/v1/accounts/1/chats/x/messages", form=b"{}")
        with self.assertRaises(ValueError):
            m.request_json("/core/v1/accounts/1/balance/")

    def test_multicity_summary(self):
        active = {"resources": [{"id": 8347570435, "status": "active", "price": 5000},
                                {"id": 2345, "status": "active", "price": 5000,
                                 "url": "https://www.avito.ru/sankt-peterburg/predlozheniya_uslug/x_2345"}]}
        items = {"items": [{"id": "ai-assistant-memory-spb-001",
                            "section": {"slug": "success_published"}}]}
        result = m.derive_summary(active, items)
        self.assertTrue(result["moscow_active_in_first_page"])
        self.assertTrue(result["spb_active_in_first_page"])
        self.assertEqual(result["spb_import_section"], "success_published")
        self.assertNotIn("url", str(result))

    def test_does_not_invent_active_from_empty_list(self):
        result = m.derive_summary({}, {"items": []})
        self.assertFalse(result["spb_active_in_first_page"])
        self.assertFalse(result["spb_in_latest_import"])
        self.assertEqual(result["spb_import_section"], "unknown")

    def test_redacted_messenger_probe(self):
        p = m.Probe
        def fake(path, *, token=None, form=None):
            if path == "/token/":
                return p(path, 200, {"access_token": "SECRET"})
            if path == "/core/v1/accounts/self":
                return p(path, 200, {"id": 123, "email": "private@test.invalid"})
            if path.startswith("/messenger/"):
                return p(path, 200, {"chats": [{"messages": [{"text": "PRIVATE"}]}]})
            return p(path, 200, {"resources": [], "items": []})
        with patch.dict(m.os.environ, {"AVITO_CLIENT_ID": "fake", "AVITO_CLIENT_SECRET": "fake"}):
            with patch.object(m, "request_json", side_effect=fake):
                result = m.audit(messenger=True)
        output = json.dumps(result)
        self.assertTrue(result["messenger_read_supported"])
        self.assertNotIn("SECRET", output)
        self.assertNotIn("PRIVATE", output)
        self.assertNotIn("private@test.invalid", output)
        self.assertNotIn("123", output)

    def test_no_messenger_probe_by_default(self):
        with patch.dict(m.os.environ, {"AVITO_CLIENT_ID": "fake", "AVITO_CLIENT_SECRET": "fake"}):
            with patch.object(m, "request_json", side_effect=lambda path, **kw: m.Probe(path, 200, {"access_token": "x", "id": 1, "resources": [], "items": []})) as req:
                result = m.audit(messenger=False)
        self.assertNotIn("messenger_metadata_http", result)
        self.assertEqual(req.call_count, 6)

    def test_network_errors_are_redacted(self):
        with patch("urllib.request.urlopen", side_effect=m.urllib.error.URLError("private full url secret")):
            probe = m.request_json("/core/v1/accounts/self", token="TOKEN")
        self.assertIsNone(probe.status)
        self.assertIsNone(probe.payload)
