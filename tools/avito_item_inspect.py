#!/usr/bin/env python3
"""Read-only inspection of ONE existing Avito item. Never changes or removes anything.

The fixed target 449877076 comes from the owner's verified project history.
No personal profile data, bearer tokens or credential values are printed.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TARGET_ITEM_ID = 449877076
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
        if status == 404:
            return fail("item", status, "not_found_or_not_accessible")
        if status != 200:
            return fail("item", status, "item_read_failed")
        item = item_response
        for key in ("result", "item"):
            if isinstance(item.get(key), dict):
                item = item[key]
        actual_id = item.get("id", item.get("item_id"))
        if actual_id is not None and str(actual_id) != str(TARGET_ITEM_ID):
            return fail("item", status, "id_mismatch")
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
        "owned_item_found", "not_found_or_not_accessible"
    } else 1


if __name__ == "__main__":
    sys.exit(main())
