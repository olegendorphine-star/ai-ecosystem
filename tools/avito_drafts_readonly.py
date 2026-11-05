#!/usr/bin/env python3
"""One-time read-only check whether Avito Business API exposes own draft item.

No writes, no messaging, no purchase. Never print credentials, tokens, raw API
responses, identity fields, titles or URLs. Refuses live mode without opt-in.
"""
from __future__ import annotations
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error

BASE = "https://api.avito.ru"
TARGET = 449877076
LIMIT = 65536

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None

def request(method, path, data=None, token=None):
    assert method in ("GET", "POST")
    assert (method == "POST" and path == "/token/") or (
        method == "GET" and (path == "/core/v1/accounts/self" or
            path.startswith("/core/v1/items?status=draft&") or
            path.endswith("/items/%s/" % TARGET))
    )
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    body = None
    if data is not None:
        assert method == "POST"
        body = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=15) as response:
            status, raw = response.status, response.read(LIMIT + 1)
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read(LIMIT + 1)
    if len(raw) > LIMIT:
        return status, None
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception:
        value = None
    return status, value if isinstance(value, dict) else None

def out(stage, status=None, outcome=None, **attrs):
    result = {"stage": stage, "http_status": status,
              "outcome": outcome, "changed": False}
    result.update(attrs)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))

def main():
    if len(sys.argv) != 2 or sys.argv[1] != "--live":
        out("guard", outcome="offline_only")
        return 0
    if os.environ.get("AVITO_DRAFTS_READONLY_OPT_IN") != "YES":
        out("guard", outcome="opt_in_required")
        return 2
    client_id = os.environ.get("AVITO_CLIENT_ID", "")
    client_secret = os.environ.get("AVITO_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        out("guard", outcome="credentials_missing")
        return 2
    try:
        code, body = request("POST", "/token/", data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        })
        token = body.get("access_token") if body else None
        if code != 200 or not isinstance(token, str) or not token:
            out("authorization", code, "failed")
            return 1
        out("authorization", 200, "ok")
        code, body = request("GET", "/core/v1/accounts/self", token=token)
        user_id = body.get("id") if body else None
        if code != 200 or isinstance(user_id, bool) or not str(user_id).isdigit():
            out("own_profile", code, "unavailable")
            return 1
        out("own_profile", 200, "ok")
        code, body = request("GET", "/core/v1/items?status=draft&page=1&per_page=99", token=token)
        resources = body.get("resources") if body else None
        found = any(str(row.get("id", row.get("item_id"))) == str(TARGET)
                    for row in resources if isinstance(row, dict)) if isinstance(resources, list) else None
        out("draft_status_filter", code,
            "target_found" if found else ("target_not_in_first_page" if found is False else "no_item_array"),
            target_id=TARGET, target_found=found)
        code, body = request("GET",
            "/core/v1/accounts/%d/items/%d/" % (int(user_id), TARGET), token=token)
        item = body
        if isinstance(item, dict):
            for key in ("result", "item"):
                if isinstance(item.get(key), dict):
                    item = item[key]
        observed_id = item.get("id", item.get("item_id")) if isinstance(item, dict) else None
        status = item.get("status") if isinstance(item, dict) else None
        exact = str(observed_id) == str(TARGET) if observed_id is not None else None
        out("direct_draft_detail", code,
            "target_verified" if exact else "not_verified",
            target_id=TARGET, exact_id=exact,
            item_status=status if exact and status in ("draft","active","old","removed","blocked","rejected") else None)
        return 0
    except Exception:
        out("transport", outcome="error_no_sensitive_details")
        return 1

if __name__ == "__main__":
    sys.exit(main())
