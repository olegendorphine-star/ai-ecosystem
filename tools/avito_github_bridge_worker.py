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
ALLOWED_ACTIONS = frozenset(("ping", "check_public_feed", "check_avito_public_access"))
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
    root = ET.fromstring(raw)
    ads = root.findall("Ad")
    mos = next((x for x in ads if x.findtext("Id") == "ai-assistant-memory-moscow-001"), None)
    spb = next((x for x in ads if x.findtext("Id") == "ai-assistant-memory-spb-001"), None)
    prices = ([x.text for x in spb.findall("./PriceList/Service/ServicePrice")]
              if spb is not None else [])
    return {
        "two_ads": len(ads) == 2,
        "moscow_present": mos is not None,
        "spb_present": spb is not None,
        "spb_three_prices": prices == ["5000", "30000", "150000"],
        "moscow_without_pricelist": mos is not None and mos.find("PriceList") is None,
        "images_six_each": mos is not None and spb is not None and
            len(mos.findall("./Images/Image")) == 6 and
            len(spb.findall("./Images/Image")) == 6,
    }


def execute(action: str) -> dict[str, Any]:
    """One of three read-only, parameter-free preapproved actions."""
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
    for command in pending:
        payload = make_result(command, execute(command["action"]))
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
