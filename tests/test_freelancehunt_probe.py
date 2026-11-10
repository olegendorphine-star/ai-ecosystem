"""Offline tests: all API responses mocked, no network or real token."""
import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from tools import freelancehunt_probe as fh


class ProbeTests(unittest.TestCase):
    def test_successful_read_only_probe(self):
        paths = []
        def mocked_urlopen(request, timeout):
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.get_header("Authorization"), "Bearer dummy")
            paths.append(request.full_url)
            body = {"data": {"id": 1, "type": "profile"}} if "/my/profile" in request.full_url else {"data": [{"id": 42}]}
            return io.BytesIO(json.dumps(body).encode("utf-8"))
        with patch.object(fh, "urlopen", side_effect=mocked_urlopen):
            self.assertEqual(fh.probe("dummy"), 1)
        self.assertEqual(len(paths), 2)

    def test_http_error_is_sanitized(self):
        with patch.object(fh, "urlopen", side_effect=HTTPError("https://example.test", 401, "unauthorized", {}, None)):
            with self.assertRaisesRegex(fh.ProbeError, "http_401"):
                fh.probe("dummy")

    def test_missing_secret_no_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(fh, "urlopen") as network:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(fh.main(), 2)
            network.assert_not_called()
            self.assertEqual(json.loads(output.getvalue())["reason"], "secret_missing")

    def test_reject_external_path(self):
        with self.assertRaises(fh.ProbeError):
            fh.get_json("https://evil.example/", "dummy")


if __name__ == "__main__":
    unittest.main()
