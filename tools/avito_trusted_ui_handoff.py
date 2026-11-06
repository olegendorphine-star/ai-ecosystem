#!/usr/bin/env python3
"""Offline-only, public-safe request contract for a FUTURE trusted Avito UI executor.

No browser, Avito HTTP, GitHub writes, cookies, tokens, or private profile data.
This module does not execute an account operation. A separate trusted service
must implement session verification and browser handling after an authorized
live test. Public Issue #32 must never carry edit instructions or credentials.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import uuid
from typing import Any

OWNER_LOGIN = "olegendorphine-star"
OWNER_USER_ID = 351021616
REQUEST_PREFIX = "AVITO_TRUSTED_UI_COMMAND_V1 "
RESULT_PREFIX = "AVITO_TRUSTED_UI_RESULT_V1 "
REQUEST_SCHEMA = "avito.trusted-ui.command.v1"
RESULT_SCHEMA = "avito.trusted-ui.result.v1"
INVENTORY_SCHEMA = "avito.owner-ui.inventory.v1"
PURPOSES = frozenset(("portfolio", "public-profile"))
CATEGORIES = frozenset(("portfolio", "profile", "media", "edit"))
CONTROL_TYPES = frozenset(("button", "link", "tab", "textbox", "file"))
MAX_TTL_SECONDS = 600
MAX_COMMENT_LENGTH = 1500


class InvalidTrustedRequest(ValueError):
    """Strictly reject unknown or expired public commands."""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_utc(value: Any) -> dt.datetime:
    if not isinstance(value, str):
        raise InvalidTrustedRequest("timestamp must be a string")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidTrustedRequest("invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise InvalidTrustedRequest("timestamp must include UTC offset")
    return parsed.astimezone(dt.timezone.utc)


def validate_request(request: Any, now: dt.datetime | None = None) -> dict[str, str]:
    """Allow only read-only UI control counts; no URL, payload, selectors or edits."""
    if not isinstance(request, dict) or set(request) != {
        "schema", "request_id", "action", "purpose", "issued_at", "expires_at"
    }:
        raise InvalidTrustedRequest("unexpected request fields")
    if request["schema"] != REQUEST_SCHEMA or request["action"] != "inventory":
        raise InvalidTrustedRequest("only read-only inventory allowed")
    if request["purpose"] not in PURPOSES:
        raise InvalidTrustedRequest("unsupported screen")
    raw_id = request["request_id"]
    if not isinstance(raw_id, str):
        raise InvalidTrustedRequest("invalid request ID")
    try:
        parsed_id = uuid.UUID(raw_id)
    except (TypeError, ValueError, AttributeError) as exc:
        raise InvalidTrustedRequest("invalid UUID") from exc
    if parsed_id.version != 4 or str(parsed_id) != raw_id:
        raise InvalidTrustedRequest("canonical UUIDv4 required")
    issued = parse_utc(request["issued_at"])
    expires = parse_utc(request["expires_at"])
    now = now or utc_now()
    if now.tzinfo is None:
        raise InvalidTrustedRequest("naive current time")
    now = now.astimezone(dt.timezone.utc)
    lifetime = (expires - issued).total_seconds()
    if not 0 < lifetime <= MAX_TTL_SECONDS:
        raise InvalidTrustedRequest("TTL out of range")
    if not issued - dt.timedelta(seconds=30) <= now <= expires:
        raise InvalidTrustedRequest("request expired or from future")
    return dict(request)


def prepare_inventory_request(
    purpose: str, now: dt.datetime | None = None, request_id: str | None = None
) -> str:
    """Generate public command text only; do NOT post or run it automatically."""
    if purpose not in PURPOSES:
        raise InvalidTrustedRequest("unsupported screen")
    issued = now or utc_now()
    if issued.tzinfo is None:
        raise InvalidTrustedRequest("naive current time")
    issued = issued.astimezone(dt.timezone.utc)
    payload = {
        "schema": REQUEST_SCHEMA,
        "request_id": request_id or str(uuid.uuid4()),
        "action": "inventory",
        "purpose": purpose,
        "issued_at": issued.isoformat(),
        "expires_at": (issued + dt.timedelta(minutes=10)).isoformat(),
    }
    validate_request(payload, issued)
    return REQUEST_PREFIX + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def parse_owner_comment(comment: Any, now: dt.datetime | None = None) -> dict[str, str] | None:
    """Treat GitHub's authenticated actor metadata as authoritative, not body claims."""
    if not isinstance(comment, dict):
        return None
    author = comment.get("user")
    if not isinstance(author, dict):
        return None
    if author.get("login") != OWNER_LOGIN or type(author.get("id")) is not int:
        return None
    if author["id"] != OWNER_USER_ID:
        return None
    body = comment.get("body")
    if not isinstance(body, str) or len(body) > MAX_COMMENT_LENGTH:
        return None
    if not body.startswith(REQUEST_PREFIX):
        return None
    try:
        request = json.loads(body[len(REQUEST_PREFIX):])
        return validate_request(request, now)
    except (ValueError, TypeError):
        return None


def fresh_requests(
    comments: list[Any], already_done: set[str], now: dt.datetime | None = None
) -> list[dict[str, str]]:
    """Filter duplicates in input order. Caller must persist successful IDs privately."""
    pending = []
    seen = set(already_done)
    for comment in comments:
        request = parse_owner_comment(comment, now)
        if request is not None and request["request_id"] not in seen:
            pending.append(request)
            seen.add(request["request_id"])
    return pending


def sanitized_inventory(raw: Any) -> dict[str, dict[str, int]]:
    """Accept only the categories returned by avito_browser_operator.inventory_controls.

    Never copy raw labels, field values, links, screenshots, cookies, IPs, or exceptions.
    """
    if not isinstance(raw, dict) or set(raw) != {
        "schema", "screen", "privacy", "categories", "control_types"
    }:
        raise ValueError("invalid inventory envelope")
    if (raw["schema"] != INVENTORY_SCHEMA or raw["screen"] != "owner-selected"
            or raw["privacy"] != "category-counts-only"):
        raise ValueError("invalid inventory provenance")
    result = {}
    for key, allowed in (("categories", CATEGORIES), ("control_types", CONTROL_TYPES)):
        source = raw[key]
        if not isinstance(source, dict) or not set(source).issubset(allowed):
            raise ValueError("unexpected inventory keys")
        values = {}
        for name in sorted(allowed):
            value = source.get(name, 0)
            if type(value) is not int or not 0 <= value <= 500:
                raise ValueError("invalid inventory count")
            values[name] = value
        result[key] = values
    return result


def make_public_result(
    request: dict[str, str], raw_inventory: Any = None,
    *, session_verified: bool = False,
) -> str:
    """A successful report only proves count extraction, not identity or public visibility."""
    payload: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "request_id": request["request_id"],
        "action": "inventory",
        "purpose": request["purpose"],
        "status": "blocked",
        "reason": "no_verified_session",
        "public_profile_updated": False,
        "price_list_visible": "unverified",
    }
    if session_verified:
        try:
            if raw_inventory is None:
                raise ValueError("no inventory")
            payload["inventory"] = sanitized_inventory(raw_inventory)
            payload["status"] = "observed_controls"
            payload["reason"] = "none"
        except (ValueError, TypeError):
            payload["reason"] = "invalid_inventory"
    # Fixed allowlisted envelope and counts only; nothing else gets published.
    return RESULT_PREFIX + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="Print an unexecuted, read-only Issue command")
    prep.add_argument("--purpose", choices=sorted(PURPOSES), required=True)
    commands.add_parser("self-check", help="Show the strictly offline capabilities")
    args = parser.parse_args()
    if args.command == "prepare":
        print(prepare_inventory_request(args.purpose))
    else:
        print(json.dumps({
            "contract": REQUEST_SCHEMA,
            "mode": "offline_only",
            "allowed_action": "inventory",
            "write_operations": False,
            "github_posting": False,
            "browser_execution": False,
        }, sort_keys=True))


if __name__ == "__main__":
    main()
