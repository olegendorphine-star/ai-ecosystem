#!/usr/bin/env python3
"""One-shot Avito archive request for exactly one owner-verified item.

No automatic retry. Exact-ID and title guard. Never logs secrets, personal
details, access tokens, unrelated listings, or raw API responses.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.avito.ru"
ITEM_ID = 8347570435
TITLE_MARKER = "экосистем"
MAX_PAGES = 3
PAGE_SIZE = 99
MAX_BYTES = 65536
TIMEOUT = 15


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def transport(request):
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            return response.status, response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        return error.code, error.read(MAX_BYTES + 1)


def json_dict(data):
    if len(data) > MAX_BYTES:
        raise ValueError("response_too_large")
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("unexpected_json")
    return value


def result(stage, outcome, *, http_status=None, request_sent=False, no_longer_active=None):
    return {"target_item_id": ITEM_ID, "stage": stage, "outcome": outcome,
            "http_status": http_status, "delete_request_sent": request_sent,
            "no_longer_active": no_longer_active}


def active_listing(token, send):
    """Return ('found', match_bool), ('missing', None), or inconclusive."""
    for page in range(1, MAX_PAGES + 1):
        query = urllib.parse.urlencode({"status": "active", "page": page,
                                        "per_page": PAGE_SIZE})
        req = urllib.request.Request(API + "/core/v1/items?" + query,
            method="GET", headers={"Authorization": "Bearer " + token,
                                    "Accept": "application/json"})
        status, raw = send(req)
        if status != 200:
            return "inconclusive", None
        obj = json_dict(raw)
        items = obj.get("resources")
        if not isinstance(items, list):
            return "inconclusive", None
        for item in items:
            if not isinstance(item, dict) or str(item.get("id")) != str(ITEM_ID):
                continue
            title = item.get("title")
            if not isinstance(title, str):
                return "found", False
            return "found", TITLE_MARKER in title.casefold()
        if len(items) < PAGE_SIZE:
            return "missing", None
    return "inconclusive", None


def remove_once(client_id, client_secret, send=transport):
    if not client_id or not client_secret:
        return result("guard", "credentials_unavailable")
    body = urllib.parse.urlencode({"grant_type": "client_credentials",
        "client_id": client_id, "client_secret": client_secret}).encode("utf-8")
    token_req = urllib.request.Request(API + "/token/", method="POST", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"})
    try:
        status, raw = send(token_req)
        if status != 200:
            return result("token", "authorization_failed", http_status=status)
        token = json_dict(raw).get("access_token")
        if not isinstance(token, str) or not token:
            return result("token", "access_token_missing", http_status=status)
        auth = {"Authorization": "Bearer " + token, "Accept": "application/json"}
        profile_req = urllib.request.Request(API + "/core/v1/accounts/self",
            method="GET", headers=auth)
        status, raw = send(profile_req)
        if status != 200:
            return result("profile", "profile_failed", http_status=status)
        account_id = json_dict(raw).get("id")
        if isinstance(account_id, bool) or not str(account_id).isdigit() or int(account_id) < 1:
            return result("profile", "invalid_account_id")
        found, title_matches = active_listing(token, send)
        if found != "found":
            return result("pre_delete", "item_missing_or_check_inconclusive")
        if title_matches is not True:
            return result("pre_delete", "project_title_mismatch_or_missing")
        # Exactly one user-authorized DELETE for exact verified account + item ID.
        delete_req = urllib.request.Request(
            API + f"/core/v1/accounts/{int(account_id)}/items/{ITEM_ID}/",
            method="DELETE", headers=auth)
        try:
            delete_status, _ = send(delete_req)
        except Exception:
            return result("delete", "unknown_outcome_no_retry", request_sent=True)
        if delete_status not in (200, 202, 204):
            return result("delete", "api_rejected_or_unsupported", http_status=delete_status,
                          request_sent=True)
        # Read back exactly once; NEVER automatically retry a mutation.
        try:
            found_after, _ = active_listing(token, send)
        except Exception:
            return result("verify", "postcheck_inconclusive", http_status=delete_status,
                          request_sent=True)
        if found_after == "missing":
            return result("verify", "not_in_active_list_after_archive_request",
                http_status=delete_status, request_sent=True, no_longer_active=True)
        return result("verify", "postcheck_inconclusive_or_still_active",
            http_status=delete_status, request_sent=True,
            no_longer_active=False if found_after == "found" else None)
    except Exception:
        # Do not log exception text, which could include secrets or HTTP data.
        return result("pre_delete", "precheck_error_no_mutation")


def main():
    if os.environ.get("AVITO_REMOVE_EXACT_8347570435") != "YES":
        print(json.dumps(result("guard", "not_authorized_for_this_run")))
        return 2
    reply = remove_once(os.environ.get("AVITO_CLIENT_ID", ""),
                        os.environ.get("AVITO_CLIENT_SECRET", ""))
    print(json.dumps(reply, sort_keys=True))
    return 0 if reply["outcome"] == "not_in_active_list_after_archive_request" else 1


if __name__ == "__main__":
    sys.exit(main())
