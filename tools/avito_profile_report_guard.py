#!/usr/bin/env python3
"""Validate and export a strictly redacted Avito profile inventory summary.

Only allowlisted booleans, integer HTTP codes and known public XML field names
may enter the public GitHub repository. No account ID, token, contact or chat data.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ALLOWED_HTTP = {"account", "autoload_profile", "active_items", "category_tree"}
ALLOWED_FIELDS = {
    "PriceList", "ServiceName", "ServicePrice", "ServicePriceType",
    "ServiceTitle", "ServiceStartingPrice", "Title", "Description",
    "Images", "Price", "Address", "ListingFee", "AdStatus",
}
ITEM_BOOL = {"moscow_active", "petersburg_active_first_page"}
ITEM_COUNT = {"active_items_first_page_count"}
BOOL_KEYS = {"oauth_ok", "autoload_enabled", "category_leaf_discovered",
             "pricelist_observed_in_fields"}
COUNT_KEYS = {"writes", "messages_read", "messages_sent", "charges_rub"}
MAX_BYTES = 200000


def http_code(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 100 or value > 599:
        raise ValueError("invalid HTTP status")
    return value


def safe_bool(payload: dict[str, Any], key: str) -> bool | None:
    if key not in payload:
        return None
    if type(payload[key]) is not bool:
        raise ValueError("non-boolean field")
    return payload[key]


def validate(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("expected dict")
    for key in COUNT_KEYS:
        if payload.get(key) != 0 or type(payload.get(key)) is not int:
            raise ValueError("non-read-only report")
    result: dict[str, Any] = {
        "schema": "avito.profile.inventory.redacted.v1",
        "source": "Avito official read-only API",
        "read_only": True,
        "oauth_http": http_code(payload.get("oauth_http")),
        "oauth_ok": safe_bool(payload, "oauth_ok"),
        "writes": 0,
        "messages_read": 0,
        "messages_sent": 0,
        "charges_rub": 0,
    }
    http = payload.get("http", {})
    if not isinstance(http, dict):
        raise ValueError("unexpected HTTP responses")
    result["http"] = {key: http_code(http.get(key))
                      for key in sorted(ALLOWED_HTTP) if key in http}
    result["category_fields_http"] = http_code(payload.get("category_fields_http"))
    for key in sorted(BOOL_KEYS - {"oauth_ok"}):
        if key in payload:
            result[key] = safe_bool(payload, key)
    items = payload.get("items")
    if items is not None:
        if not isinstance(items, dict):
            raise ValueError("unexpected items")
        safe_items: dict[str, Any] = {}
        for key in ITEM_BOOL:
            if key in items:
                if type(items[key]) is not bool:
                    raise ValueError("unexpected item state")
                safe_items[key] = items[key]
        for key in ITEM_COUNT:
            if key in items:
                value = items[key]
                if type(value) is not int or not (0 <= value <= 99):
                    raise ValueError("unexpected item count")
                safe_items[key] = value
        result["items"] = safe_items
    fields = payload.get("category_fields_observed")
    if fields is not None:
        if not isinstance(fields, list) or len(fields) > len(ALLOWED_FIELDS):
            raise ValueError("unexpected fields")
        if any(not isinstance(x, str) or x not in ALLOWED_FIELDS for x in fields):
            raise ValueError("private or unknown field not allowed")
        result["category_fields_observed"] = sorted(set(fields))
    return result


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) != 2:
        print("Usage: avito_profile_report_guard.py INPUT_JSON OUTPUT_JSON", file=sys.stderr)
        return 2
    src, dst = map(Path, argv)
    if src.stat().st_size > MAX_BYTES:
        print("INPUT_TOO_LARGE", file=sys.stderr)
        return 3
    try:
        sanitized = validate(json.loads(src.read_text(encoding="utf-8")))
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    except (ValueError, TypeError, OSError, json.JSONDecodeError):
        print("REPORT_REJECTED", file=sys.stderr)
        return 4
    print("SANITIZED_REPORT_CREATED", dst.as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
