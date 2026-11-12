#!/usr/bin/env python3
"""Avito read-only bridge: GitHub issue command -> server pull -> sanitized issue result.

This worker deliberately has NO browser login, Avito API credentials, write methods,
shell execution, or promotion/payment capabilities. First-stage transport only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

REPOSITORY = "olegendorphine-star/ai-ecosystem"
OWNER = "olegendorphine-star"
ISSUE = 32
API = "https://api.github.com"
FEED_URL = "https://olegendorphine-star.github.io/ai-ecosystem/avito-feed.xml"
AVITO_URL = "https://www.avito.ru/"
COMMAND_PREFIX = "AVITO_BRIDGE_COMMAND_V1 "
RESULT_PREFIX = "AVITO_BRIDGE_RESULT_V1 "
SCHEMA = "avito.bridge.command.v1"
RESULT_SCHEMA = "avito.bridge.result.v1"
ALLOWED_ACTIONS = frozenset(("ping", "check_public_feed", "check_avito_public_access", "check_live_avito_api"))
API_READ_COOLDOWN_SEC = 3600
STATE_FILE = Path.home() / ".local" / "state" / "ai-ecosystem" / "avito-bridge-state.json"
MAX_PAGES = 15
MAX_BODY = 1500000
COMMAND_LIFETIME_SEC = 900


class InvalidCommand(ValueError):
    pass


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parsed_time(value: Any) -> dt.datetime:
    if not isinstance(value, str):
        raise InvalidCommand("timestamp must be an ISO8601 string")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidCommand("invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise InvalidCommand("timezone required")
    return parsed.astimezone(dt.timezone.utc)


def validate_command(data: Any, now: dt.datetime | None = None) -> dict[str, str]:
    now = now or utcnow()
    if not isinstance(data, dict) or set(data) != {
        "schema", "command_id", "action", "issued_at", "expires_at"
    }:
        raise InvalidCommand("unexpected fields")
    if data["schema"] != SCHEMA or data["action"] not in ALLOWED_ACTIONS:
        raise InvalidCommand("unsupported schema or action")
    raw_id = data["command_id"]
    if not isinstance(raw_id, str) or len(raw_id) != 36:
        raise InvalidCommand("invalid command_id")
    try:
        parsed_id = uuid.UUID(raw_id)
    except ValueError as exc:
        raise InvalidCommand("invalid command_id") from exc
    if str(parsed_id) != raw_id.lower():
        raise InvalidCommand("command_id must be canonical UUID")
    issued = parsed_time(data["issued_at"])
    expiry = parsed_time(data["expires_at"])
    lifetime = (expiry - issued).total_seconds()
    if not 0 < lifetime <= COMMAND_LIFETIME_SEC:
        raise InvalidCommand("command TTL exceeded")
    if not issued - dt.timedelta(seconds=30) <= now <= expiry:
        raise InvalidCommand("command stale or from future")
    return dict(data)


def parse_owner_command(comment: Any, now: dt.datetime | None = None) -> dict[str, str] | None:
    if not isinstance(comment, dict) or comment.get("user", {}).get("login") != OWNER:
        return None
    body = comment.get("body")
    if not isinstance(body, str) or not body.startswith(COMMAND_PREFIX):
        return None
    try:
        return validate_command(json.loads(body[len(COMMAND_PREFIX):]), now)
    except (ValueError, TypeError):
        return None


def seen_completed_results(comments: list[Any]) -> set[str]:
    out: set[str] = set()
    for comment in comments:
        if not isinstance(comment, dict) or comment.get("user", {}).get("login") not in (OWNER, "github-actions[bot]"):
            continue
        body = comment.get("body")
        if not isinstance(body, str) or not body.startswith(RESULT_PREFIX):
            continue
        try:
            payload = json.loads(body[len(RESULT_PREFIX):])
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict) or payload.get("schema") != RESULT_SCHEMA:
            continue
        if isinstance(payload.get("command_id"), str):
            out.add(payload["command_id"])
    return out


def request(url: str, token: str | None = None, post: dict | None = None) -> tuple[int, bytes]:
    # Only allow HTTPS to an explicit allowlist, no arbitrary URLs from commands.
    if not url.startswith((API + "/repos/" + REPOSITORY + "/issues/" + str(ISSUE) + "/comments",
                           FEED_URL, AVITO_URL)):
        raise ValueError("request URL is not allowlisted")
    data = json.dumps(post).encode("utf-8") if post is not None else None
    headers = {
        "Accept": "application/vnd.github+json" if url.startswith(API) else "*/*",
        "User-Agent": "AiEcosystemAvitoReadOnlyBridge/1.0"
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    if post is not None:
        if url != API + "/repos/" + REPOSITORY + "/issues/" + str(ISSUE) + "/comments":
            raise ValueError("POST only allowed to GitHub issue comments")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if post is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            raw = res.read(MAX_BODY + 1)
            if len(raw) > MAX_BODY:
                raise ValueError("HTTP body too large")
            return res.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, b""


def get_issue_comments() -> list[Any]:
    results: list[Any] = []
    for page in range(1, MAX_PAGES + 1):
        status, raw = request(API + "/repos/" + REPOSITORY + "/issues/" + str(ISSUE)
                              + "/comments?per_page=100&page=" + str(page))
        if status != 200:
            raise RuntimeError("GitHub status " + str(status))
        items = json.loads(raw.decode("utf-8"))
        if not isinstance(items, list):
            raise RuntimeError("Invalid GitHub response")
        results.extend(items)
        if len(items) < 100:
            return results
    raise RuntimeError("Issue comment pagination limit reached")


def check_feed_xml(raw: bytes) -> dict[str, Any]:
    # Public-only and authenticated checks share the same reviewed feed schema.
    try:
        from avito_spb_pricelist_live_status import feed_check
    except ModuleNotFoundError:
        from tools.avito_spb_pricelist_live_status import feed_check
    return feed_check(raw)


def sanitize_live_api_report(raw: dict[str, Any]) -> dict[str, Any]:
    """Produce a strict public-only boolean/status summary; never publish Avito payloads."""
    if not isinstance(raw, dict):
        return {"result": "invalid"}
    safe: dict[str, Any] = {
        "result": "checked",
        "price_list_visible_on_public_ad": "unverified",
        "oauth_ok": raw.get("oauth_ok") if type(raw.get("oauth_ok")) is bool else None,
    }
    if raw.get("api_check_status") in {
        "skipped_feed_unavailable", "skipped_invalid_xml", "skipped_feed_mismatch",
        "skipped_credentials_missing", "oauth_attempted", "checked"
    }:
        safe["api_check_status"] = raw["api_check_status"]
        if raw["api_check_status"].startswith("skipped_"):
            safe["result"] = "skipped"
    if type(raw.get("feed_ad_count")) is int:
        safe["feed_ad_count"] = raw["feed_ad_count"]
    if type(raw.get("public_feed_http")) is int:
        safe["public_feed_http"] = raw["public_feed_http"]
    if isinstance(raw.get("public_feed"), dict):
        flags = raw["public_feed"]
        safe["feed_integrity_ok"] = (bool(flags) and all(v is True for v in flags.values()))
    if isinstance(raw.get("active_items"), dict):
        items = raw["active_items"]
        safe["moscow_active"] = items.get("moscow_active") is True
        safe["spb_active"] = items.get("spb_active") is True
        safe["surgut_active"] = items.get("surgut_active") is True
        safe["chita_candidate_active"] = items.get("chita_candidate_active") is True
    if isinstance(raw.get("current_upload"), dict):
        upload = raw["current_upload"]
        safe["upload_status"] = upload.get("upload_status") if upload.get("upload_status") in {
            "processing", "completed", "error", "failed", "success", "finished"
        } else "unknown"
        safe["spb_in_current_items"] = upload.get("spb_in_current_items") is True
        safe["spb_section"] = upload.get("spb_section") if upload.get("spb_section") in {
            "success_published", "processing", "error_params", "error_payment",
            "error_content", "removed_complete", "pending"
        } else "unknown"
        safe["chita_in_current_items"] = upload.get("chita_in_current_items") is True
        safe["chita_section"] = upload.get("chita_section") if upload.get("chita_section") in {
            "success_published", "processing", "error_params", "error_payment",
            "error_content", "removed_complete", "pending"
        } else "unknown"
    # Never equate upload success, a city-only candidate, or HTTP 200
    # with an independently correlated, active Chita advertisement.
    safe["chita_confirmed_active"] = False
    if raw.get("chita_confirmed_active") is True and isinstance(raw.get("active_items"), dict):
        item = raw["active_items"]
        item_id, item_url = item.get("chita_public_ad_id"), item.get("chita_public_url")
        if type(item_id) is int and 0 < item_id < 1000000000000000 and isinstance(item_url, str):
            parsed = urllib.parse.urlsplit(item_url)
            if (parsed.scheme == "https" and parsed.netloc == "www.avito.ru"
                    and parsed.path.startswith("/chita/")
                    and parsed.path.endswith("_" + str(item_id))
                    and ".." not in parsed.path and len(parsed.path) <= 250):
                safe["chita_confirmed_active"] = True
                safe["chita_public_ad_id"] = item_id
                safe["chita_public_url"] = "https://www.avito.ru" + parsed.path
    if raw.get("current_items_check") in {
        "read", "rate_limited", "unavailable", "skipped_while_processing",
        "skipped_unknown_upload_status"
    }:
        safe["current_items_check"] = raw["current_items_check"]
    if isinstance(raw.get("http"), dict):
        safe["http"] = {
            key: (raw["http"].get(key) if type(raw["http"].get(key)) is int else None)
            for key in ("active_items", "current_upload", "current_items")
        }
    return safe


def has_recent_api_check(comments: list[Any], now: dt.datetime) -> bool:
    """Limit account API checks to one successful invocation per 60 min."""
    for comment in comments:
        if not isinstance(comment, dict) or comment.get("user", {}).get("login") not in (OWNER, "github-actions[bot]"):
            continue
        body = comment.get("body")
        if not isinstance(body, str) or not body.startswith(RESULT_PREFIX):
            continue
        try:
            payload = json.loads(body[len(RESULT_PREFIX):])
            if (payload.get("schema") != RESULT_SCHEMA or
                payload.get("action") != "check_live_avito_api"):
                continue
            if payload.get("detail", {}).get("result") == "cooldown":
                continue
            checked = parsed_time(payload.get("checked_at"))
            if dt.timedelta(0) <= now - checked < dt.timedelta(seconds=API_READ_COOLDOWN_SEC):
                return True
        except (ValueError, TypeError, AttributeError):
            continue
    return False


def execute(action: str) -> dict[str, Any]:
    """Run only allowlisted, read-only, parameter-free actions."""
    if action == "ping":
        return {"bridge": "alive", "mode": "public_read_only"}
    if action == "check_public_feed":
        try:
            status, body = request(FEED_URL)
            if status != 200:
                return {"http_status": status, "feed_validation": "unavailable"}
            flags = check_feed_xml(body)
            return {"http_status": status, "feed_validation": "match" if all(flags.values())
                    else "mismatch", "flags": flags}
        except (ValueError, OSError, ET.ParseError):
            return {"feed_validation": "unavailable"}
    if action == "check_avito_public_access":
        try:
            status, _ = request(AVITO_URL)
            return {"http_status": status, "reachable": status == 200,
                    "note": "public GET only; login and PriceList visibility not verified"}
        except (OSError, ValueError):
            return {"reachable": False, "note": "network or TLS error"}
    if action == "check_live_avito_api":
        # Imports the previously tested public-feed and authenticated GET-only helper.
        # OAuth POST is the sole non-GET request; its token is never returned.
        try:
            from avito_spb_pricelist_live_status import inspect
            return sanitize_live_api_report(inspect())
        except Exception:
            # No raw exception, API responses, credentials, or remote host values.
            return {"result": "unavailable", "price_list_visible_on_public_ad": "unverified"}
    raise InvalidCommand("action not allowlisted")


def make_result(command: dict[str, str], detail: dict[str, Any], now: dt.datetime | None = None) -> dict:
    return {
        "schema": RESULT_SCHEMA,
        "command_id": command["command_id"],
        "action": command["action"],
        "checked_at": (now or utcnow()).isoformat(timespec="seconds"),
        "status": "completed",
        "detail": detail,
    }


def load_state(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or any(not isinstance(v, str) for v in data):
        raise ValueError("Corrupted private replay state")
    return set(data)


def save_state(path: Path, seen: set[str]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        path.parent.chmod(0o700)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        os.chmod(tmp, 0o600) if os.name != "nt" else None
        json.dump(sorted(seen)[-1000:], fh)
    os.replace(tmp, path)


def single_pass(*, dry_run: bool = False, state_file: Path = STATE_FILE) -> dict[str, Any]:
    comments = get_issue_comments()
    now = utcnow()
    complete = seen_completed_results(comments) | load_state(state_file)
    commands = [c for comment in comments if (c := parse_owner_command(comment, now))]
    pending = []
    queued = set(complete)
    for command in commands:
        if command["command_id"] in queued:
            continue
        pending.append(command)
        queued.add(command["command_id"])
    if not pending:
        return {"pending": 0, "posted": 0}
    token = os.environ.get("AVITO_BRIDGE_GITHUB_TOKEN", "")
    if not dry_run and not token:
        raise RuntimeError("AVITO_BRIDGE_GITHUB_TOKEN missing; no results posted")
    posted = 0
    recent_api = has_recent_api_check(comments, now)
    for command in pending:
        if command["action"] == "check_live_avito_api" and recent_api:
            detail = {"result": "cooldown", "retry_after_minutes": 60,
                      "price_list_visible_on_public_ad": "unverified"}
        else:
            detail = execute(command["action"])
            if command["action"] == "check_live_avito_api" and detail.get("result") != "cooldown":
                recent_api = True
        payload = make_result(command, detail)
        if dry_run:
            print(RESULT_PREFIX + json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            status, _ = request(API + "/repos/" + REPOSITORY + "/issues/" + str(ISSUE)
                                + "/comments", token=token,
                                post={"body": RESULT_PREFIX +
                                      json.dumps(payload, ensure_ascii=False, sort_keys=True)})
            if status != 201:
                raise RuntimeError("GitHub result POST returned " + str(status))
            complete.add(command["command_id"])
            save_state(state_file, complete)
            posted += 1
    return {"pending": len(pending), "posted": posted if not dry_run else 0,
            "simulated": len(pending) if dry_run else 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Poll GitHub commands one time")
    parser.add_argument("--watch", action="store_true", help="Poll repeatedly until stopped")
    parser.add_argument("--dry-run", action="store_true", help="Do not POST results or change state")
    parser.add_argument("--interval", type=int, default=120)
    parser.add_argument("--state-file", type=Path, default=STATE_FILE)
    args = parser.parse_args()
    if args.once == args.watch:
        parser.error("Choose exactly one: --once or --watch")
    if args.interval < 60:
        parser.error("Minimum polling interval 60 seconds")
    while True:
        try:
            status = single_pass(dry_run=args.dry_run, state_file=args.state_file)
            print(json.dumps(status, ensure_ascii=False))
        except Exception as exc:
            # Never print credential-bearing URLs or arbitrary response bodies.
            print("bridge_pass_failed:", type(exc).__name__)
            if args.once:
                raise SystemExit(1) from None
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
