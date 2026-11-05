#!/usr/bin/env python3
"""Read-only Avito API capability and multi-city status audit.

No calls modifying Avito are implemented. Output is strictly redacted and safe for
GitHub logs. Requires an explicit authorization gate for each live execution.
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
from typing import Any

API = "https://api.avito.ru"
EXPECTED_MOSCOW_ID = "8347570435"
EXPECTED_PRICE = 5000
MAX_RESPONSE = 2_000_000


@dataclass(frozen=True)
class Probe:
    label: str
    status: int | None
    payload: Any | None = None


def request_json(path: str, *, token: str | None = None, form: bytes | None = None) -> Probe:
    """Only allow approved URLs. The form request is restricted to OAuth token."""
    path_only = urllib.parse.urlsplit(path).path
    if form is not None:
        if path_only != "/token/":
            raise ValueError("OAuth POST is the only accepted POST")
        method = "POST"
    else:
        if not (path_only == "/core/v1/accounts/self"
                or path_only == "/core/v1/items"
                or path_only in ("/autoload/v2/profile", "/autoload/v4/uploads/current",
                                 "/autoload/v4/uploads/current/items")
                or path_only.startswith("/messenger/v2/accounts/") and path_only.endswith("/chats")):
            raise ValueError("Non-whitelisted read-only route")
        method = "GET"
    headers = {"Accept": "application/json", "User-Agent": "AvitoCapabilityAudit/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(API + path, method=method, headers=headers, data=form)
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            code = res.status
            raw = res.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            return Probe(path_only, code, None)
        try:
            result = json.loads(raw) if raw else {}
        except (ValueError, UnicodeError):
            result = None
        return Probe(path_only, code, result)
    except urllib.error.HTTPError as exc:
        # Never print or store HTTP response bodies: they may contain user data.
        return Probe(path_only, exc.code, None)
    except (urllib.error.URLError, TimeoutError, OSError):
        return Probe(path_only, None, None)


def derive_summary(active: Any, items: Any) -> dict[str, Any]:
    """Return only public ad-state booleans. No account, chat or item payloads."""
    resources = active.get("resources") if isinstance(active, dict) else None
    entries = items.get("items") if isinstance(items, dict) else None
    resources = resources if isinstance(resources, list) else []
    entries = entries if isinstance(entries, list) else []
    moscow = next((x for x in resources if isinstance(x, dict)
                   and str(x.get("id")) == EXPECTED_MOSCOW_ID), None)
    spb = next((x for x in resources if isinstance(x, dict)
                and "sankt-peterburg" in str(x.get("url", "")).lower()), None)
    spb_record = next((x for x in entries if isinstance(x, dict)
                       and x.get("id") == "ai-assistant-memory-spb-001"), None)
    section = spb_record.get("section") if isinstance(spb_record, dict) else None
    slug = section.get("slug") if isinstance(section, dict) else section
    allowed_sections = {"success_published", "error_params", "error_payment", "error_content",
                        "removed_complete", "processing", "pending"}
    return {
        "moscow_active_in_first_page": bool(moscow and moscow.get("status") == "active"
                                            and moscow.get("price") == EXPECTED_PRICE),
        "spb_active_in_first_page": bool(spb and spb.get("status") == "active"
                                         and spb.get("price") == EXPECTED_PRICE),
        "spb_in_latest_import": bool(spb_record),
        "spb_import_section": slug if isinstance(slug, str) and slug in allowed_sections else "unknown",
        "active_page_size": len(resources),
    }


def audit(*, messenger: bool = False) -> dict[str, Any]:
    """Metadata-only audit; messenger probe reads HTTP status but never parses chat content."""
    client_id = os.environ.get("AVITO_CLIENT_ID", "")
    client_secret = os.environ.get("AVITO_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError("Missing repository Actions secret(s): AVITO_CLIENT_ID / AVITO_CLIENT_SECRET")
    form = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()
    token_response = request_json("/token/", form=form)
    if token_response.status != 200 or not isinstance(token_response.payload, dict):
        return {"oauth_http": token_response.status, "oauth_ok": False}
    token = token_response.payload.get("access_token")
    if not isinstance(token, str) or not token:
        return {"oauth_http": token_response.status, "oauth_ok": False}
    endpoints = {
        "self": "/core/v1/accounts/self",
        "active_items": "/core/v1/items?status=active&per_page=99&page=1",
        "autoload_profile": "/autoload/v2/profile",
        "current_upload": "/autoload/v4/uploads/current",
        "current_items": "/autoload/v4/uploads/current/items",
    }
    responses = {name: request_json(path, token=token) for name, path in endpoints.items()}
    result: dict[str, Any] = {"oauth_http": 200, "oauth_ok": True,
                               "endpoints_http": {n: r.status for n, r in responses.items()}}
    if responses["active_items"].status == 200 and responses["current_items"].status == 200:
        result["listings"] = derive_summary(responses["active_items"].payload,
                                             responses["current_items"].payload)
    if messenger:
        self_data = responses["self"].payload
        account_id = self_data.get("id") if isinstance(self_data, dict) else None
        if account_id is not None and str(account_id).isdigit():
            # This response can contain private messages. Discard it before output.
            route = f"/messenger/v2/accounts/{int(account_id)}/chats?limit=1&offset=0"
            probe = request_json(route, token=token)
            result["messenger_metadata_http"] = probe.status
            result["messenger_read_supported"] = probe.status == 200
        else:
            result["messenger_metadata_http"] = None
            result["messenger_read_supported"] = False
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Perform read-only requests; opt-in required")
    parser.add_argument("--approve-readonly", action="store_true", help="Explicit live authorization")
    parser.add_argument("--include-messenger-metadata", action="store_true",
                        help="Test chats endpoint HTTP status, without writing message data")
    args = parser.parse_args(argv)
    if not args.live:
        print(json.dumps({"mode": "offline", "network_calls": 0, "mutations": 0, "charges_rub": 0}))
        return 0
    if not args.approve_readonly or os.environ.get("AVITO_ALLOW_CAPABILITY_AUDIT") != "YES":
        print("LIVE_RUN_BLOCKED_APPROVAL_REQUIRED")
        return 2
    try:
        result = audit(messenger=args.include_messenger_metadata)
    except RuntimeError as e:
        print(str(e))
        return 3
    result.update({"mutations": 0, "charges_rub": 0, "messages_sent": 0})
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("oauth_ok") else 4


if __name__ == "__main__":
    sys.exit(main())
