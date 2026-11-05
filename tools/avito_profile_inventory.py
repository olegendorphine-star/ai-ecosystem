#!/usr/bin/env python3
"""Non-mutating Avito profile and category field discovery.

Never reads messages, changes ads, pays, or logs personal account data.
An explicit opt-in gate is required for each live run.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

API = "https://api.avito.ru"
MAX_BYTES = 1500000
READ_PATHS = {
    "/core/v1/accounts/self",
    "/autoload/v2/profile",
    "/autoload/v1/user-docs/tree",
    "/core/v1/items",
}
NODE = re.compile(r"^/autoload/v1/user-docs/node/([A-Za-z0-9_-]{1,120})/fields$")
PUBLIC_FIELD_NAMES = {
    "PriceList", "ServiceName", "ServicePrice", "ServicePriceType",
    "ServiceTitle", "ServiceStartingPrice", "Title", "Description",
    "Images", "Price", "Address", "ListingFee", "AdStatus",
}
CATEGORY_TERMS = ("программирование", "настройка crm", "it, дизайн, тексты", "деловые услуги")


@dataclass(frozen=True)
class Result:
    status: int | None
    data: Any = None


def call(path: str, *, token: str | None = None, oauth_form: bytes | None = None) -> Result:
    pathname = urllib.parse.urlsplit(path).path
    if oauth_form is not None:
        if pathname != "/token/":
            raise ValueError("Only OAuth POST is permitted")
        method = "POST"
    else:
        if pathname not in READ_PATHS and not NODE.fullmatch(pathname):
            raise ValueError("Unapproved GET endpoint")
        method = "GET"
    headers = {"Accept": "application/json", "User-Agent": "AvitoProfileInventory/1.0"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if oauth_form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(
        API + path, headers=headers, method=method, data=oauth_form
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            data = response.read(MAX_BYTES + 1)
            status = response.status
        if len(data) > MAX_BYTES:
            return Result(status)
        try:
            return Result(status, json.loads(data) if data else {})
        except (ValueError, UnicodeError):
            return Result(status)
    except urllib.error.HTTPError as err:
        # Never echo response bodies, URLs or account identifiers.
        return Result(err.code)
    except (urllib.error.URLError, OSError, TimeoutError):
        return Result(None)


def find_category_slug(tree: Any) -> str | None:
    """Prefer the service leaf. Do not output private data from the tree."""
    matches: list[tuple[int, str]] = []
    def walk(value: Any, depth: int = 0) -> None:
        if depth > 20:
            return
        if isinstance(value, dict):
            name = str(value.get("name") or value.get("title") or "").lower()
            slug = value.get("slug")
            if isinstance(slug, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,120}", slug):
                if any(term in name for term in CATEGORY_TERMS):
                    score = (4 if "программирование" in name else
                             3 if "crm" in name else
                             2 if "it, дизайн" in name else 1)
                    matches.append((score, slug))
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                walk(child, depth + 1)
    walk(tree)
    return max(matches, default=(0, None))[1]


def allowed_field_names(payload: Any) -> list[str]:
    """Never emit arbitrary response values, names of clients or contact details."""
    found: set[str] = set()
    def walk(value: Any, depth: int = 0) -> None:
        if depth > 25:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if key in PUBLIC_FIELD_NAMES:
                    found.add(key)
                if key in ("name", "field", "tag", "xmlName") and isinstance(item, str):
                    if item in PUBLIC_FIELD_NAMES:
                        found.add(item)
                if isinstance(item, (list, dict)):
                    walk(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                walk(item, depth + 1)
    walk(payload)
    return sorted(found)


def summarize_items(payload: Any) -> dict[str, Any]:
    rows = payload.get("resources") if isinstance(payload, dict) else []
    rows = rows if isinstance(rows, list) else []
    moscow = next((x for x in rows if isinstance(x, dict)
                   and str(x.get("id")) == "8347570435"), None)
    petersburg = next((x for x in rows if isinstance(x, dict)
                       and "sankt-peterburg" in str(x.get("url", "")).lower()), None)
    return {
        "active_items_first_page_count": len(rows),
        "moscow_active": bool(moscow and moscow.get("status") == "active"),
        "petersburg_active_first_page": bool(petersburg and petersburg.get("status") == "active"),
    }


def inventory() -> dict[str, Any]:
    client_id = os.environ.get("AVITO_CLIENT_ID")
    client_secret = os.environ.get("AVITO_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Avito GitHub Actions secrets missing")
    form = urllib.parse.urlencode({
        "grant_type": "client_credentials", "client_id": client_id,
        "client_secret": client_secret,
    }).encode()
    oauth = call("/token/", oauth_form=form)
    token = oauth.data.get("access_token") if isinstance(oauth.data, dict) else None
    summary: dict[str, Any] = {
        "oauth_http": oauth.status, "oauth_ok": bool(oauth.status == 200 and token),
        "writes": 0, "messages_read": 0, "messages_sent": 0, "charges_rub": 0,
    }
    if not summary["oauth_ok"]:
        return summary
    # Endpoint HTTP codes only. Never log account profile fields/values or a feed URL.
    endpoints = {
        "account": "/core/v1/accounts/self",
        "autoload_profile": "/autoload/v2/profile",
        "active_items": "/core/v1/items?status=active&per_page=99&page=1",
        "category_tree": "/autoload/v1/user-docs/tree",
    }
    results = {key: call(path, token=token) for key, path in endpoints.items()}
    summary["http"] = {key: result.status for key, result in results.items()}
    if results["active_items"].status == 200:
        summary["items"] = summarize_items(results["active_items"].data)
    profile = results["autoload_profile"].data
    if results["autoload_profile"].status == 200 and isinstance(profile, dict):
        summary["autoload_enabled"] = profile.get("autoload_enabled") is True
    tree = results["category_tree"].data
    if results["category_tree"].status == 200:
        slug = find_category_slug(tree)
        summary["category_leaf_discovered"] = bool(slug)
        if slug:
            fields = call(f"/autoload/v1/user-docs/node/{slug}/fields", token=token)
            summary["category_fields_http"] = fields.status
            if fields.status == 200:
                supported = allowed_field_names(fields.data)
                summary["category_fields_observed"] = supported
                summary["pricelist_observed_in_fields"] = "PriceList" in supported
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--approve-readonly", action="store_true")
    args = parser.parse_args(argv)
    if not args.live:
        print(json.dumps({"mode": "offline", "network_calls": 0, "writes": 0}))
        return 0
    if not args.approve_readonly or os.environ.get("AVITO_ALLOW_PROFILE_INVENTORY") != "YES":
        print("LIVE_BLOCKED_APPROVAL_REQUIRED")
        return 2
    try:
        data = inventory()
    except RuntimeError:
        print("MISSING_SECRETS")
        return 3
    print(json.dumps(data, ensure_ascii=False, sort_keys=True))
    return 0 if data.get("oauth_ok") else 4


if __name__ == "__main__":
    sys.exit(main())
