import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

WORKER_PATH = Path(__file__).resolve().parents[1] / "tools" / "avito_server_worker.py"
spec = importlib.util.spec_from_file_location("worker", WORKER_PATH)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WorkerTests(unittest.TestCase):
    def test_health_is_read_only_shape(self):
        result = worker.health()
        self.assertEqual(result["action"], "health")
        self.assertTrue(result["ok"])
        self.assertIn("disk_free_bytes", result)

    def test_browser_health_does_not_require_profile(self):
        os.environ.pop("AVITO_BROWSER_PROFILE_DIR", None)
        result = worker.browser_health()
        self.assertFalse(result["profile_configured"])

    def test_connect_status_has_no_write_action(self):
        worker.http_status = lambda url: 200
        result = worker.connect_status()
        self.assertFalse(result["write_actions"])


    def test_classifies_missing_libatk_without_exposing_private_error(self):
        err = "Chrome exited: libatk-1.0.so.0 from /home/private/SECRET"
        result = worker._safe_browser_status({"ok": False, "url": "", "startup_error": err})
        self.assertFalse(result["ok"])
        self.assertEqual(result["startup_error_category"], "missing_libatk")
        self.assertNotIn("SECRET", str(result))

    def test_classifies_generic_browser_failure(self):
        result = worker._safe_browser_status({
            "ok": False, "url": "", "startup_error": "RuntimeError: unknown private detail"
        })
        self.assertEqual(result["startup_error_category"], "browser_start_failed")
        self.assertNotIn("unknown private detail", str(result))

    def test_handoff_status_ready_sanitizes_private_fields(self):
        result = worker._safe_browser_status({
            "ok": True, "url": "https://www.avito.ru/private",
            "title": "PRIVATE ACCOUNT", "profile": "/home/user/private/profile",
            "startup_error": ""
        })
        self.assertTrue(result["ok"])
        self.assertTrue(result["browser_ready"])
        self.assertFalse(result["write_actions"])
        self.assertNotIn("url", result)
        self.assertNotIn("title", result)
        self.assertNotIn("profile", result)
        self.assertNotIn("private", str(result).lower())

    def test_handoff_status_never_exposes_startup_error(self):
        result = worker._safe_browser_status({
            "ok": False, "url": "", "startup_error": "SECRET_PATH"
        })
        self.assertFalse(result["ok"])
        self.assertTrue(result["startup_failed"])
        self.assertNotIn("SECRET_PATH", str(result))

    def test_handoff_status_malformed_fails_closed(self):
        for data in (None, [], "OK", {}, {"ok": True, "url": 500},
                     {"ok": True, "url": ""}):
            self.assertFalse(worker._safe_browser_status(data)["ok"])

    def test_handoff_health_readonly_loopback(self):
        import json
        from unittest.mock import patch
        seen = []
        class Response:
            status = 200
            headers = {"Content-Type": "application/json; charset=utf-8"}
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def read(self, n):
                seen.append(("read", n))
                return json.dumps({"ok": True, "url": "about:blank", "startup_error": ""}).encode()
        class Opener:
            def open(self, request, timeout=None):
                seen.append(("request", request.full_url, request.get_method(), timeout))
                return Response()
        with patch.object(worker.urllib.request, "build_opener", return_value=Opener()):
            result = worker.handoff_health()
        self.assertTrue(result["ok"])
        self.assertEqual(seen[0], ("request", "http://127.0.0.1:8787/api/status", "GET", 3))
        self.assertEqual(seen[1], ("read", 4097))
        self.assertFalse(result["write_actions"])
        self.assertNotIn("url", result)

    def test_handoff_health_connection_failure_fails_closed(self):
        from unittest.mock import patch
        class Opener:
            def open(self, request, timeout=None):
                raise OSError("cannot reach local server")
        with patch.object(worker.urllib.request, "build_opener", return_value=Opener()):
            result = worker.handoff_health()
        self.assertFalse(result["ok"])
        self.assertFalse(result["local_http_ok"])
        self.assertNotIn("cannot reach", str(result))

    def test_handoff_health_rejects_redirect_and_non_json(self):
        from unittest.mock import patch
        class Response:
            status = 302
            headers = {"Content-Type": "text/html"}
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
        class Opener:
            def open(self, request, timeout=None):
                return Response()
        with patch.object(worker.urllib.request, "build_opener", return_value=Opener()):
            result = worker.handoff_health()
        self.assertFalse(result["ok"])

    def test_handoff_health_rejects_oversized_response(self):
        from unittest.mock import patch
        class Response:
            status = 200
            headers = {"Content-Type": "application/json"}
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def read(self, n):
                return b"X" * n
        class Opener:
            def open(self, request, timeout=None):
                return Response()
        with patch.object(worker.urllib.request, "build_opener", return_value=Opener()):
            result = worker.handoff_health()
        self.assertFalse(result["ok"])



    def test_avito_navigation_smoke_only_fixed_public_url_and_no_data_leak(self):
        import json
        from unittest.mock import patch
        requests = []
        pre = {"ok": True, "url": "about:blank", "startup_error": ""}
        post = {"ok": True, "url": "https://www.avito.ru/",
                "startup_error": "", "last_navigation_http_status": 200,
                "last_navigation_ip_blocked": False, "title": "PRIVATE"}
        seq = [pre, {"ok": True}, post]
        class Response:
            def __init__(self, payload):
                self.status = 200
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def read(self, limit):
                return json.dumps(self.payload).encode()
        class Opener:
            def open(self, request, timeout=None):
                requests.append((request.full_url, request.get_method(), request.data))
                return Response(seq.pop(0))
        with patch.object(worker.urllib.request, "build_opener", return_value=Opener()):
            result = worker.avito_navigation_smoke()
        self.assertTrue(result["ok"])
        self.assertEqual(result["site_http_status"], 200)
        self.assertNotIn("url", result)
        self.assertNotIn("title", result)
        self.assertNotIn("PRIVATE", str(result))
        self.assertEqual(len(requests), 3)
        self.assertEqual(requests[1][0], "http://127.0.0.1:8787/api/navigate")
        self.assertEqual(requests[1][1], "POST")
        self.assertEqual(requests[1][2], b'{"url":"https://www.avito.ru/"}')

    def test_avito_navigation_smoke_detects_ip_blocked_page(self):
        import json
        from unittest.mock import patch
        seq = [
            {"ok": True, "url": "about:blank", "startup_error": ""},
            {"ok": True},
            {"ok": True, "url": "https://www.avito.ru/", "startup_error": "",
             "last_navigation_http_status": 200, "last_navigation_ip_blocked": True}
        ]
        class Response:
            status = 200
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def read(self, limit):
                return json.dumps(self.payload).encode()
        class Opener:
            def open(self, request, timeout=None):
                return Response(seq.pop(0))
        with patch.object(worker.urllib.request, "build_opener", return_value=Opener()):
            result = worker.avito_navigation_smoke()
        self.assertFalse(result["ok"])
        self.assertTrue(result["avito_ip_blocked"])
        self.assertTrue(result["reached_avito_origin"])

    def test_avito_navigation_smoke_rejects_http_403(self):
        import json
        from unittest.mock import patch
        seq = [
            {"ok": True, "url": "about:blank", "startup_error": ""},
            {"ok": True},
            {"ok": True, "url": "https://www.avito.ru/", "startup_error": "",
             "last_navigation_http_status": 403, "last_navigation_ip_blocked": False}
        ]
        class Response:
            status = 200
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def read(self, limit):
                return json.dumps(self.payload).encode()
        class Opener:
            def open(self, request, timeout=None):
                return Response(seq.pop(0))
        with patch.object(worker.urllib.request, "build_opener", return_value=Opener()):
            result = worker.avito_navigation_smoke()
        self.assertFalse(result["ok"])
        self.assertEqual(result["site_http_status"], 403)

    def test_avito_navigation_smoke_does_not_navigate_if_chromium_not_ready(self):
        import json
        from unittest.mock import patch
        requests = []
        class Response:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def read(self, limit):
                return json.dumps({"ok": False, "url": "",
                                   "startup_error": "missing_libatk"}).encode()
        class Opener:
            def open(self, request, timeout=None):
                requests.append(request.get_method())
                return Response()
        with patch.object(worker.urllib.request, "build_opener", return_value=Opener()):
            result = worker.avito_navigation_smoke()
        self.assertFalse(result["ok"])
        self.assertEqual(requests, ["GET"])
        self.assertEqual(result["startup_error_category"], "missing_libatk")


    def test_navigation_timeout_category_is_reported_without_raw_error(self):
        import json
        from unittest.mock import patch
        seq = [
            {"ok": True, "url": "about:blank", "startup_error": ""},
            {"ok": False},
            {"ok": True, "url": "https://www.avito.ru/", "startup_error": "",
             "last_navigation_http_status": None, "last_navigation_ip_blocked": False,
             "last_navigation_error_category": "navigation_timeout"},
        ]
        class Response:
            status = 200
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def read(self, limit):
                return json.dumps(self.payload).encode()
        class Opener:
            def open(self, request, timeout=None):
                return Response(seq.pop(0))
        with patch.object(worker.urllib.request, "build_opener", return_value=Opener()):
            result = worker.avito_navigation_smoke()
        self.assertFalse(result["ok"])
        self.assertEqual(result["navigation_error_category"], "navigation_timeout")
        self.assertNotIn("url", result)
        self.assertNotIn("private", str(result))


    def test_owner_session_probe_filters_private_data(self):
        import json
        from unittest.mock import patch
        seen = []
        class Response:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def read(self, limit):
                return json.dumps({
                    "ok": True,
                    "browser_ready": True,
                    "profile_route_reached": True,
                    "account_controls_seen": True,
                    "auth_challenge_visible": False,
                    "auth_state": "likely_active",
                    "site_http_status": 200,
                    "navigation_error_category": "none",
                    "url": "https://www.avito.ru/profile",
                    "name": "PRIVATE OWNER",
                    "cookies": ["SECRET SESSION"],
                }).encode()
        class Opener:
            def open(self, request, timeout=None):
                seen.append((request.full_url, request.get_method(), request.data))
                return Response()
        with patch.object(worker.urllib.request, "build_opener", return_value=Opener()):
            result = worker.avito_owner_session_probe()
        self.assertTrue(result["ok"])
        self.assertEqual(result["auth_state"], "likely_active")
        self.assertTrue(result["account_controls_seen"])
        self.assertNotIn("PRIVATE OWNER", str(result))
        self.assertNotIn("SECRET SESSION", str(result))
        self.assertNotIn("url", result)
        self.assertEqual(seen, [(
            "http://127.0.0.1:8787/api/owner-session-probe", "POST", b"{}"
        )])
        self.assertFalse(result["write_actions"])

    def test_owner_session_probe_rejects_invalid_state(self):
        import json
        from unittest.mock import patch
        class Response:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def read(self, limit):
                return json.dumps({"ok": True, "auth_state": "user_SECRET"}).encode()
        class Opener:
            def open(self, request, timeout=None):
                return Response()
        with patch.object(worker.urllib.request, "build_opener", return_value=Opener()):
            result = worker.avito_owner_session_probe()
        self.assertEqual(result["auth_state"], "unverified")
        self.assertNotIn("user_SECRET", str(result))



if __name__ == "__main__":
    unittest.main()
