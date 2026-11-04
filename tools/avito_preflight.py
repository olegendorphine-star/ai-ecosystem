#!/usr/bin/env python3
"""Avito personal-account read-only preflight.

Default operation is an offline description; LIVE requires an explicit flag
and an opt-in environment variable. No advertising or messaging writes.
No credential or access token is printed or stored.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

TOKEN_URL = 'https://api.avito.ru/token/'
PROFILE_URL = 'https://api.avito.ru/core/v1/accounts/self'
TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 65536
GRANT = 'client_credentials'
OPT_IN = 'AVITO_ALLOW_READONLY_PREFLIGHT'


@dataclass(frozen=True)
class Result:
    stage: str
    success: bool
    status: int | None
    code: str

    def as_dict(self):
        return {'stage': self.stage, 'success': self.success,
                'http_status': self.status, 'code': self.code}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# Transport returns (status, response bytes). Injected in offline tests.
def default_transport(request: urllib.request.Request) -> tuple[int, bytes]:
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(MAX_RESPONSE_BYTES + 1)


def parse_json(payload: bytes) -> dict:
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError('response_too_large')
    try:
        obj = json.loads(payload.decode('utf-8'))
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError('invalid_json') from None
    if not isinstance(obj, dict):
        raise ValueError('invalid_json_type')
    return obj


def sanitize_error_code(payload: dict, status: int) -> str:
    # Never echo untrusted error_description, token-like data, or whole bodies.
    known = {'unauthorized_client', 'invalid_client', 'invalid_grant',
             'invalid_request', 'unsupported_grant_type', 'access_denied',
             'insufficient_scope', 'forbidden', 'rate_limited'}
    code = payload.get('error')
    if isinstance(code, str) and code in known:
        return code
    if status == 401:
        return 'http_401_auth_rejected'
    if status == 403:
        return 'http_403_access_denied'
    if status == 429:
        return 'http_429_rate_limited'
    if status >= 500:
        return 'http_5xx_provider_error'
    return 'http_error'


def diagnostics(client_id: str, client_secret: str,
                transport: Callable[[urllib.request.Request], tuple[int, bytes]] = default_transport
                ) -> list[Result]:
    if not client_id or not client_secret:
        raise ValueError('missing_credentials')
    # Validate nonempty credentials but never log, hash, return or persist them.
    body = urllib.parse.urlencode({'grant_type': GRANT, 'client_id': client_id,
                                   'client_secret': client_secret}).encode('utf-8')
    auth_req = urllib.request.Request(TOKEN_URL, method='POST', data=body,
                      headers={'Content-Type': 'application/x-www-form-urlencoded',
                               'Accept': 'application/json'})
    try:
        status, raw = transport(auth_req)
        auth_obj = parse_json(raw)
    except (urllib.error.URLError, OSError, ValueError) as err:
        # The exception object can include request details, so never show it.
        label = str(err) if isinstance(err, ValueError) and str(err) in (
            'response_too_large', 'invalid_json', 'invalid_json_type') else 'transport_error'
        return [Result('token', False, None, label)]
    if status != 200:
        return [Result('token', False, status, sanitize_error_code(auth_obj, status))]
    token = auth_obj.get('access_token')
    if not isinstance(token, str) or not token:
        return [Result('token', False, status, 'missing_access_token')]
    token_ok = Result('token', True, status, 'authorized')
    profile_req = urllib.request.Request(PROFILE_URL, method='GET',
                      headers={'Authorization': 'Bearer ' + token,
                               'Accept': 'application/json'})
    try:
        status, raw = transport(profile_req)
        profile_obj = parse_json(raw)
    except (urllib.error.URLError, OSError, ValueError) as err:
        label = str(err) if isinstance(err, ValueError) and str(err) in (
            'response_too_large', 'invalid_json', 'invalid_json_type') else 'transport_error'
        return [token_ok, Result('profile', False, None, label)]
    if status != 200:
        return [token_ok, Result('profile', False, status,
                                 sanitize_error_code(profile_obj, status))]
    # Don't expose personal profile fields, user_id, email, phone etc.
    return [token_ok, Result('profile', True, status, 'read_only_ok')]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--live', action='store_true', help='Run authenticated read-only checks')
    args = p.parse_args(argv)
    if not args.live:
        print(json.dumps({'status': 'DRY_RUN', 'network': False,
                          'steps': ['POST /token/', 'GET /core/v1/accounts/self'],
                          'writes': False, 'credentials_read': False}))
        return 0
    if os.environ.get(OPT_IN) != 'YES':
        print('LIVE_BLOCKED: set explicit read-only opt-in', file=sys.stderr)
        return 2
    client_id = os.environ.get('AVITO_CLIENT_ID', '')
    client_secret = os.environ.get('AVITO_CLIENT_SECRET', '')
    if not client_id or not client_secret:
        print('LIVE_BLOCKED: credentials unavailable in protected environment', file=sys.stderr)
        return 2
    results = diagnostics(client_id, client_secret)
    for x in results:
        print(json.dumps(x.as_dict(), sort_keys=True))
    return 0 if len(results) == 2 and all(x.success for x in results) else 1


if __name__ == '__main__':
    sys.exit(main())