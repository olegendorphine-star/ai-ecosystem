#!/usr/bin/env python3
"""Read-only inspection of ONE existing Avito item. Never changes or removes anything.

The fixed target 8347570435 comes from the owner's verified project history.
No personal profile data, bearer tokens or credential values are printed.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TARGET_ITEM_ID = 8347570435
BASE = "https://api.avito.ru"
MAX_BYTES = 65536
TIMEOUT = 20


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def network(request):
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=TIMEOUT) as res:
            return res.status, res.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read(MAX_BYTES + 1)


def json_object(payload):
    if len(payload) > MAX_BYTES:
        raise ValueError("response_too_large")
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("not_object")
    return value


def get(request, transport):
    status, body = transport(request)
    return status, json_object(body) if body else {}


def fail(stage, status=None, code="unexpected_response"):
    return {"target_item_id": TARGET_ITEM_ID, "stage": stage,
            "http_status": status, "outcome": code, "changed": False}


def list_fallback(token, transport):
    """Scan own listings in supported statuses, without printing unrelated listings.

    At most 15 GETs (5 statuses, <=3 pages each) and no mutation.
    A failed or truncated scan is inconclusive, not proof of absence.
    """
    for state in ("active", "old", "removed", "blocked", "rejected"):
        for page in (1, 2, 3):
            qs = urllib.parse.urlencode({"status": state, "page": page, "per_page": 99})
            req = urllib.request.Request(BASE + "/core/v1/items?" + qs,
                method="GET", headers={
                    "Authorization": "Bearer " + token,
                    "Accept": "application/json",
                })
            try:
                status, payload = get(req, transport)
            except Exception:
                return fail("item_list", code="list_transport_or_parse_error")
            if status != 200:
                return fail("item_list", status, "list_status_unavailable")
            entries = payload.get("resources")
            if not isinstance(entries, list):
                return fail("item_list", status, "list_schema_unknown")
            for item in entries:
                if not isinstance(item, dict):
                    continue
                found_id = item.get("id", item.get("item_id"))
                if str(found_id) != str(TARGET_ITEM_ID):
                    continue
                title = item.get("title")
                match = (any(s in title.casefold() for s in
                    ("экосистем", "ассистент", "искусственн", "ии-"))
                    if isinstance(title, str) else None)
                return {"target_item_id": TARGET_ITEM_ID, "stage": "item_list",
                        "http_status": status, "outcome": "owned_item_found_in_list",
                        "item_status": state, "project_title_match": match,
                        "changed": False}
            if len(entries) < 99:
                break
        else:
            return fail("item_list", 200, "pagination_limit_inconclusive")
    return fail("item_list", 200, "not_found_in_scanned_statuses")


def inspect(client_id, client_secret, transport=network):
    if not client_id or not client_secret:
        return fail("token", code="credentials_missing")

    encoded = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")
    auth = urllib.request.Request(BASE + "/token/", data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"}, method="POST")
    try:
        status, token_doc = get(auth, transport)
        if status != 200:
            known = {"unauthorized_client", "invalid_client", "invalid_request"}
            raw_error = token_doc.get("error")
            return fail("token", status, raw_error if raw_error in known else "auth_failed")
        token = token_doc.get("access_token")
        if not isinstance(token, str) or not token:
            return fail("token", status, "token_absent")

        def auth_get(path):
            return urllib.request.Request(BASE + path, headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/json",
            }, method="GET")

        status, profile = get(auth_get("/core/v1/accounts/self"), transport)
        if status != 200:
            return fail("profile", status, "profile_unavailable")
        user_id = profile.get("id")
        if isinstance(user_id, bool) or not str(user_id).isdigit() or int(user_id) < 1:
            return fail("profile", status, "profile_id_invalid")
        path = f"/core/v1/accounts/{int(user_id)}/items/{TARGET_ITEM_ID}/"
        status, item_response = get(auth_get(path), transport)
        if status in (404, 422):
            return list_fallback(token, transport)
        if status != 200:
            return fail("item", status, "item_read_failed")
        item = item_response
        for key in ("result", "item"):
            if isinstance(item.get(key), dict):
                item = item[key]
        actual_id = item.get("id", item.get("item_id"))
        if str(actual_id) != str(TARGET_ITEM_ID):
            return fail("item", status, "id_missing_or_mismatch")
        title = item.get("title")
        if isinstance(title, str):
            title_matches = any(s in title.casefold() for s in
                ("экосистем", "ассистент", "искусственн", "ии-"))
        else:
            title_matches = None
        item_status = item.get("status")
        if not isinstance(item_status, str) or item_status not in {
            "active", "old", "removed", "blocked", "rejected", "archived",
            "closed", "inactive",
        }:
            item_status = "unknown"
        return {"target_item_id": TARGET_ITEM_ID, "stage": "item",
                "http_status": status, "outcome": "owned_item_found",
                "item_status": item_status,
                "project_title_match": title_matches,
                "changed": False}
    except Exception:
        # Do not log raw exception text: request, response and trace may expose keys.
        return fail("transport", code="error_without_secret_details")


def main():
    if os.environ.get("AVITO_INSPECT_ONE_ITEM") != "YES":
        print(json.dumps(fail("guard", code="explicit_opt_in_required")))
        return 2
    result = inspect(os.environ.get("AVITO_CLIENT_ID", ""),
                     os.environ.get("AVITO_CLIENT_SECRET", ""))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["outcome"] in {
        "owned_item_found", "owned_item_found_in_list", "not_found_in_scanned_statuses"
    } else 1


if __name__ == "__main__":
    sys.exit(main())
