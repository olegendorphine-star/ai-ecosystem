"""Offline mocks for one-shot exact-ID Avito archive. No network or secrets."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import avito_remove_once as app


class RemoveOnceTests(unittest.TestCase):
    def make_send(self, title="Персональная ИИ-экосистема", item_id=app.ITEM_ID,
                  delete_status=204, after_empty=True):
        methods = []
        counter = {"listing": 0}
        def send(req):
            methods.append(req.get_method())
            if req.full_url == app.API + "/token/":
                return 200, b'{"access_token":"FAKE-TOKEN"}'
            if req.full_url == app.API + "/core/v1/accounts/self":
                return 200, b'{"id":123}'
            if req.get_method() == "DELETE":
                self.assertEqual(req.full_url, app.API + f"/core/v1/accounts/123/items/{app.ITEM_ID}/")
                return delete_status, b''
            self.assertEqual(req.get_method(), "GET")
            self.assertIn("/core/v1/items?", req.full_url)
            counter["listing"] += 1
            if counter["listing"] > 1 and after_empty:
                return 200, b'{"resources":[]}'
            return 200, json.dumps({"resources": [{"id":item_id,"title":title}]}).encode()
        return send, methods

    def test_success_exact_id_once_then_readback(self):
        send, methods = self.make_send()
        result = app.remove_once("FAKE-ID", "FAKE-SECRET", send)
        self.assertEqual(result["outcome"], "not_in_active_list_after_archive_request")
        self.assertTrue(result["no_longer_active"])
        self.assertEqual(methods, ["POST", "GET", "GET", "DELETE", "GET"])
        self.assertNotIn("FAKE-SECRET", json.dumps(result))
        self.assertNotIn("FAKE-TOKEN", json.dumps(result))

    def test_title_mismatch_blocks_delete(self):
        send, methods = self.make_send(title="Продам велосипед")
        result = app.remove_once("id", "secret", send)
        self.assertEqual(result["outcome"], "project_title_mismatch_or_missing")
        self.assertNotIn("DELETE", methods)

    def test_missing_item_blocks_delete(self):
        send, methods = self.make_send(item_id=111111)
        result = app.remove_once("id", "secret", send)
        self.assertEqual(result["outcome"], "item_missing_or_check_inconclusive")
        self.assertNotIn("DELETE", methods)

    def test_rejected_delete_never_retries(self):
        send, methods = self.make_send(delete_status=405)
        result = app.remove_once("id", "secret", send)
        self.assertEqual(result["outcome"], "api_rejected_or_unsupported")
        self.assertEqual(methods.count("DELETE"), 1)

    def test_postcheck_active_does_not_claim_success(self):
        send, methods = self.make_send(after_empty=False)
        result = app.remove_once("id", "secret", send)
        self.assertEqual(result["outcome"], "postcheck_inconclusive_or_still_active")
        self.assertEqual(result["no_longer_active"], False)
        self.assertEqual(methods.count("DELETE"), 1)

    def test_no_credentials_no_http(self):
        send, methods = self.make_send()
        result = app.remove_once("", "", send)
        self.assertEqual(result["outcome"], "credentials_unavailable")
        self.assertEqual(methods, [])

    def test_transport_error_is_redacted(self):
        def bad(req):
            raise RuntimeError("FAKE-SECRET")
        result = app.remove_once("id", "FAKE-SECRET", bad)
        self.assertEqual(result["outcome"], "precheck_error_no_mutation")
        self.assertNotIn("FAKE-SECRET", json.dumps(result))

    def test_uncertain_delete_no_retry(self):
        send, _ = self.make_send()
        methods = []
        def fail_delete(req):
            methods.append(req.get_method())
            if req.get_method() == "DELETE":
                raise OSError("connection lost after send")
            return send(req)
        result = app.remove_once("id", "secret", fail_delete)
        self.assertEqual(result["outcome"], "unknown_outcome_no_retry")
        self.assertEqual(methods.count("DELETE"), 1)


if __name__ == "__main__":
    unittest.main()
