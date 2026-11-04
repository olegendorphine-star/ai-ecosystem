"""Offline-only tests for a bounded, read-only inspection of user's specified Avito item."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import avito_item_inspect as app


class InspectTests(unittest.TestCase):
    def fake_api(self, *, item_status=200, title="Персональная ИИ-экосистема",
                 item_id=app.TARGET_ITEM_ID, account_id=12345):
        requests = []

        def fake(request):
            requests.append(request)
            if len(requests) == 1:
                self.assertEqual(request.get_method(), "POST")
                self.assertEqual(request.full_url, app.BASE + "/token/")
                return 200, b'{"access_token":"TEST_TOKEN"}'
            if len(requests) == 2:
                self.assertEqual(request.get_method(), "GET")
                self.assertEqual(request.full_url, app.BASE + "/core/v1/accounts/self")
                return 200, json.dumps({"id": account_id}).encode()
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.full_url, (
                f"{app.BASE}/core/v1/accounts/{account_id}/items/{app.TARGET_ITEM_ID}/"))
            if item_status == 404:
                return 404, b'{"message":"not found"}'
            return item_status, json.dumps({"id": item_id, "title": title, "status": "active"}).encode()

        return fake, requests

    def test_found_exact_own_ad_no_writes_and_redacted(self):
        fake, requests = self.fake_api()
        result = app.inspect("testID", "testSECRET", fake)
        self.assertEqual(result["outcome"], "owned_item_found")
        self.assertTrue(result["project_title_match"])
        self.assertFalse(result["changed"])
        self.assertEqual(result["item_status"], "active")
        self.assertEqual([x.get_method() for x in requests], ["POST", "GET", "GET"])
        self.assertNotIn("testSECRET", json.dumps(result))
        self.assertNotIn("TEST_TOKEN", json.dumps(result))
        self.assertNotIn("12345", json.dumps(result))

    def test_missing_item_not_same_as_permanently_deleted(self):
        calls = []
        def fake(req):
            calls.append(req)
            if len(calls) == 1:
                return 200, b'{"access_token":"TEST_TOKEN"}'
            if len(calls) == 2:
                return 200, b'{"id":12345}'
            if len(calls) == 3:
                return 404, b'{"message":"not found"}'
            self.assertIn("status=", req.full_url)
            return 200, b'{"resources":[]}'
        result = app.inspect("id", "secret", fake)
        self.assertEqual(result["outcome"], "not_found_in_scanned_statuses")
        self.assertEqual(len(calls), 8)
        self.assertFalse(result["changed"])

    def test_422_fallback_lists_owned_item(self):
        calls = []
        def fake(req):
            calls.append(req)
            if len(calls) == 1:
                return 200, b'{"access_token":"TEST_TOKEN"}'
            if len(calls) == 2:
                return 200, b'{"id":12345}'
            if len(calls) == 3:
                return 422, b'{"error":"unprocessable"}'
            self.assertEqual(req.get_method(), "GET")
            self.assertIn("status=active", req.full_url)
            return 200, json.dumps({"resources":[
                {"id": app.TARGET_ITEM_ID, "title":"Персональная ИИ-экосистема"}]}).encode()
        result = app.inspect("id", "secret", fake)
        self.assertEqual(result["outcome"], "owned_item_found_in_list")
        self.assertTrue(result["project_title_match"])
        self.assertEqual(result["item_status"], "active")
        self.assertFalse(result["changed"])
        self.assertEqual(len(calls), 4)

    def test_422_fallback_failed_list_inconclusive(self):
        calls = []
        def fake(req):
            calls.append(req)
            if len(calls) == 1:
                return 200, b'{"access_token":"TEST_TOKEN"}'
            if len(calls) == 2:
                return 200, b'{"id":12345}'
            if len(calls) == 3:
                return 422, b'{"error":"unprocessable"}'
            return 403, b'{"error":"forbidden"}'
        result = app.inspect("id", "secret", fake)
        self.assertEqual(result["outcome"], "list_status_unavailable")
        self.assertEqual(result["http_status"], 403)
        self.assertEqual(len(calls), 4)

    def test_mismatch_item_id(self):
        fake, _ = self.fake_api(item_id=222)
        result = app.inspect("id", "secret", fake)
        self.assertEqual(result["outcome"], "id_mismatch")
        self.assertFalse(result["changed"])

    def test_detail_without_id_requires_list_membership(self):
        calls = []
        def fake(req):
            calls.append(req)
            if len(calls) == 1:
                return 200, b'{"access_token":"TEST_TOKEN"}'
            if len(calls) == 2:
                return 200, b'{"id":12345}'
            if len(calls) == 3:
                return 200, b'{"status":"active","stats":{}}'
            self.assertIn("status=active", req.full_url)
            return 200, json.dumps({"resources":[{
                "id":app.TARGET_ITEM_ID,
                "title":"Персональная ИИ-экосистема",
                "status":"active"
            }]}).encode()
        result = app.inspect("id", "secret", fake)
        self.assertEqual(result["outcome"], "owned_item_found_in_list")
        self.assertTrue(result["project_title_match"])
        self.assertEqual(len(calls), 4)

    def test_wrong_title_not_assumed(self):
        fake, _ = self.fake_api(title="Продам велосипед")
        result = app.inspect("id", "secret", fake)
        self.assertFalse(result["project_title_match"])

    def test_credentials_missing_no_http(self):
        fake, requests = self.fake_api()
        result = app.inspect("", "", fake)
        self.assertEqual(result["outcome"], "credentials_missing")
        self.assertFalse(requests)

    def test_auth_error_no_item_request(self):
        calls = []
        def fake(req):
            calls.append(req)
            return 400, b'{"error":"unauthorized_client","error_description":"PRIVATE"}'
        result = app.inspect("id", "secret", fake)
        self.assertEqual(result["outcome"], "unauthorized_client")
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertEqual(len(calls), 1)

    def test_profile_mismatch_fails_closed(self):
        calls = []
        def fake(req):
            calls.append(req)
            if len(calls) == 1:
                return 200, b'{"access_token":"secret"}'
            return 200, b'{"foo":"no id"}'
        result = app.inspect("id", "secret", fake)
        self.assertEqual(result["outcome"], "profile_id_invalid")
        self.assertEqual(len(calls), 2)

    def test_transport_failure_no_leak(self):
        def fake(req):
            raise RuntimeError("SUPERSECRET")
        result = app.inspect("id", "SUPERSECRET", fake)
        self.assertEqual(result["stage"], "transport")
        self.assertNotIn("SUPERSECRET", json.dumps(result))

    def test_guard_no_env_no_network(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertNotEqual(app.main(), 0)


if __name__ == "__main__":
    unittest.main()
