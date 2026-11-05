#!/usr/bin/env python3
"""One-shot read-only Avito account capability audit.

Only requests explicitly designated read-only in the Avito Business API
specification (snapshot 2026-10-03). No ads, prices, profile fields or paid
services are changed. No Messenger endpoint is contacted.
No credentials, tokens, response bodies or personal/financial fields are
logged or saved. Live network access requires an explicit environment guard.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.avito.ru"
ITEM_ID = 8347570435
MAX_BYTES = 65536
TIMEOUT = 12
GUARD = "AVITO_ALLOW_READONLY_AUDIT"

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None

def transport(request):
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=TIMEOUT) as result:
            return result.status, result.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as result:
        return result.code, result.read(MAX_BYTES + 1)

def decode(body):
    if len(body) > MAX_BYTES:
        raise ValueError("response_too_large")
    value = json.loads(body.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("non_object_json")
    return value

def call(method, path, token=None, data=None):
    assert method in ("GET", "POST")
    assert path.startswith("/")
    # POSTs below are data retrieval, not service activation or modification.
    if method == "POST":
        assert path in {
            "/token/",
            "/stats/v1/accounts/{user_id}/items",
            "/stats/v2/accounts/{user_id}/items",
            "/stats/v2/accounts/{user_id}/spendings",
            "/promotion/v2/items/services/get",
            "/promotion/v1/items/services/bbip/suggests/get",
        } or path.startswith("/stats/v1/accounts/") and path.endswith("/items") or (
            path.startswith("/stats/v2/accounts/") and (
                path.endswith("/items") or path.endswith("/spendings")
            )
        )
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    body = None
    if data is not None:
        if path == "/token/":
            body = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, headers=headers, data=body, method=method)
    return transport(req)

def classification(status):
    if status == 200:
        return "http_200"
    if status in (401, 403):
        return "auth_or_permission_denied"
    if status in (400, 404, 405, 422):
        return "unsupported_or_request_invalid"
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return "provider_error"
    return "other"

def summary(name, status, payload=None, parse_issue=False):
    result = {"check": name, "http_status": status,
              "result": classification(status), "changed": False}
    if status == 200 and parse_issue:
        result["result"] = "http_200_payload_invalid"
    if status == 200 and isinstance(payload, dict):
        if name == "items":
            entries = payload.get("resources")
            result["target_listed"] = (
                any(str(item.get("id", item.get("item_id"))) == str(ITEM_ID)
                    for item in entries if isinstance(item, dict))
                if isinstance(entries, list) else None
            )
        if name == "promotion_active_services":
            flag = payload.get("degraded")
            result["degraded"] = flag if isinstance(flag, bool) else None
            items = payload.get("items")
            result["items_count"] = len(items) if isinstance(items, list) else None
        if name == "bbip_offers":
            values = payload.get("items")
            result["items_count"] = len(values) if isinstance(values, list) else None
        if name == "autoload_profile":
            flag = payload.get("autoload_enabled")
            result["autoload_enabled"] = flag if isinstance(flag, bool) else None
        if name in ("stats_v1", "stats_v2", "promotion_active_services", "bbip_offers"):
            result["structured_data"] = bool(payload)
    return result

def main():
    if len(sys.argv) != 2 or sys.argv[1] != "--live":
        print(json.dumps({"mode": "OFFLINE_ONLY", "network": False,
                          "checks": 9, "writes": False}))
        return 0
    if os.getenv(GUARD) != "YES":
        print(json.dumps({"mode": "BLOCKED", "reason": "explicit_guard_required"}))
        return 2
    client_id = os.getenv("AVITO_CLIENT_ID", "")
    secret = os.getenv("AVITO_CLIENT_SECRET", "")
    if not client_id or not secret:
        print(json.dumps({"mode": "BLOCKED", "reason": "missing_protected_credentials"}))
        return 2

    try:
        code, raw = call("POST", "/token/", data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
        })
        if code != 200:
            print(json.dumps(summary("token", code), sort_keys=True))
            return 1
        token_data = decode(raw)
        access_token = token_data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            print(json.dumps({"check":"token","result":"no_token","changed":False}))
            return 1
        print(json.dumps(summary("token", 200), sort_keys=True))

        code, raw = call("GET", "/core/v1/accounts/self", token=access_token)
        if code != 200:
            print(json.dumps(summary("profile", code), sort_keys=True))
            return 1
        profile = decode(raw)
        user_id = profile.get("id")
        if isinstance(user_id, bool) or not str(user_id).isdigit() or int(user_id) < 1:
            print(json.dumps({"check":"profile","result":"invalid_id","changed":False}))
            return 1
        user_id = int(user_id)
        print(json.dumps(summary("profile", 200), sort_keys=True))

        end = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
        start = end - dt.timedelta(days=6)
        date_from, date_to = start.isoformat(), end.isoformat()

        # All following methods are read-only, even where the API uses POST.
        checks = [
            ("items", "GET", "/core/v1/items?status=active&page=1&per_page=30", None),
            ("wallet_balance", "GET", f"/core/v1/accounts/{user_id}/balance/", None),
            ("stats_v1", "POST", f"/stats/v1/accounts/{user_id}/items", {
                "itemIds": [ITEM_ID], "dateFrom": date_from, "dateTo": date_to,
                "fields": ["views", "contacts", "favorites"], "periodGrouping": "day"
            }),
            ("stats_v2", "POST", f"/stats/v2/accounts/{user_id}/items", {
                "dateFrom": date_from, "dateTo": date_to,
                "metrics": ["views", "contacts"], "grouping": "totals",
                "limit": 1, "offset": 0
            }),
            ("spendings", "POST", f"/stats/v2/accounts/{user_id}/spendings", {
                "dateFrom": date_from, "dateTo": date_to,
                "spendingTypes": ["promotion"], "grouping": "day"
            }),
            ("promotion_active_services", "POST",
             "/promotion/v2/items/services/get", {"itemIds": [ITEM_ID]}),
            ("bbip_offers", "POST",
             "/promotion/v1/items/services/bbip/suggests/get", {"itemIds": [ITEM_ID]}),
            ("autoload_profile", "GET", "/autoload/v2/profile", None),
        ]
        for name, method, path, request_data in checks:
            try:
                status, raw = call(method, path, token=access_token, data=request_data)
                parsed, invalid = None, False
                if status == 200:
                    try:
                        parsed = decode(raw)
                    except (ValueError, UnicodeError, json.JSONDecodeError):
                        invalid = True
                result = summary(name, status, parsed, invalid)
            except Exception:
                # Do not echo exception details: request or body might include secrets.
                result = {"check":name,"result":"transport_or_parse_error","changed":False}
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"check":"bootstrap","result":"error_without_secrets","changed":False}))
        return 1

if __name__ == "__main__":
    sys.exit(main())
