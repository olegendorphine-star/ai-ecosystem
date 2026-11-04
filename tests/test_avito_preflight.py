"""Offline-only tests. No network or real Avito credentials."""
import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import avito_preflight as app


class AvitoPreflightTest(unittest.TestCase):
    def test_dry_run_no_network_or_credential_read(self):
        with patch.object(app, 'default_transport', side_effect=AssertionError('network')):
            with patch.dict(os.environ, {}, clear=True):
                with contextlib.redirect_stdout(io.StringIO()) as o:
                    self.assertEqual(app.main([]), 0)
        obj = json.loads(o.getvalue())
        self.assertIs(obj['network'], False)
        self.assertIs(obj['credentials_read'], False)

    def test_live_without_explicit_optin_refused(self):
        with patch.dict(os.environ, {'AVITO_CLIENT_ID': 'dummy', 'AVITO_CLIENT_SECRET': 'dummy'}, clear=True):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(app.main(['--live']), 2)

    def test_live_without_secrets_refused(self):
        with patch.dict(os.environ, {app.OPT_IN: 'YES'}, clear=True):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(app.main(['--live']), 2)

    def test_success_two_requests_and_no_leak(self):
        requests = []
        def fake(req):
            requests.append(req)
            if len(requests) == 1:
                self.assertEqual(req.get_method(), 'POST')
                self.assertEqual(req.full_url, app.TOKEN_URL)
                form = parse_qs(req.data.decode())
                self.assertEqual(form['grant_type'], ['client_credentials'])
                self.assertEqual(form['client_secret'], ['secret-test-only'])
                return 200, b'{"access_token":"token-test-only","expires_in":86400}'
            self.assertEqual(req.full_url, app.PROFILE_URL)
            self.assertEqual(req.get_method(), 'GET')
            self.assertEqual(req.get_header('Authorization'), 'Bearer token-test-only')
            return 200, b'{"id":1234,"email":"private@example.test"}'
        result = app.diagnostics('id-test-only', 'secret-test-only', fake)
        self.assertEqual([r.code for r in result], ['authorized', 'read_only_ok'])
        printable = json.dumps([x.as_dict() for x in result])
        for secret in ('secret-test-only', 'token-test-only', 'private@example.test', '1234'):
            self.assertNotIn(secret, printable)
        self.assertEqual(len(requests), 2)

    def test_unauthorized_client_stops_without_profile(self):
        calls = []
        def fake(req):
            calls.append(req)
            return 400, b'{"error":"unauthorized_client","error_description":"NEVER ECHO SECRET"}'
        result = app.diagnostics('id', 'secret', fake)
        self.assertEqual(len(calls), 1)
        self.assertEqual([(v.stage, v.code) for v in result], [('token', 'unauthorized_client')])
        self.assertNotIn('NEVER ECHO SECRET', json.dumps([x.as_dict() for x in result]))

    def test_invalid_client_stops(self):
        result = app.diagnostics('id', 'secret', lambda req:(401,b'{"error":"invalid_client"}'))
        self.assertEqual(result[0].code, 'invalid_client')

    def test_403_stops(self):
        calls = []
        def fake(req):
            calls.append(req)
            return (200, b'{"access_token":"TOKEN"}') if len(calls) == 1 else (403, b'{"error":"forbidden"}')
        result = app.diagnostics('id', 'secret', fake)
        self.assertEqual([x.success for x in result], [True, False])
        self.assertEqual(result[1].status, 403)

    def test_429_stops_no_retry(self):
        calls = []
        def fake(req):
            calls.append(req)
            return 429, b'{"error":"overloaded"}'
        result = app.diagnostics('id', 'secret', fake)
        self.assertEqual(result[0].code, 'http_429_rate_limited')
        self.assertEqual(len(calls), 1)

    def test_invalid_json_stops(self):
        result = app.diagnostics('id', 'secret', lambda req:(200,b'not-json'))
        self.assertEqual(result[0].code, 'invalid_json')

    def test_token_missing_stops(self):
        result = app.diagnostics('id', 'secret', lambda req:(200,b'{"token_type":"Bearer"}'))
        self.assertEqual(result[0].code, 'missing_access_token')

    def test_response_too_large(self):
        result = app.diagnostics('id', 'secret', lambda req:(200,b'x'*(app.MAX_RESPONSE_BYTES+1)))
        self.assertEqual(result[0].code, 'response_too_large')

    def test_oserror_does_not_echo_secret(self):
        def fake(req):
            raise OSError('secret-test-only leaked by transport')
        result = app.diagnostics('id', 'secret-test-only', fake)
        self.assertEqual(result[0].code, 'transport_error')
        self.assertNotIn('secret-test-only', str(result))


if __name__ == '__main__':
    unittest.main()