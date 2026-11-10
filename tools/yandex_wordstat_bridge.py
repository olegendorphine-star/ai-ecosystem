#!/usr/bin/env python3
"""Narrow GitHub-issue -> Yandex Wordstat API bridge.

No browser session, no user data, no ability to change Yandex or FL.ru objects.
The GitHub issue is PUBLIC: use only non-confidential marketing phrases.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ISSUE_NUMBER = 162
OWNER = "olegendorphine-star"
REPO = "olegendorphine-star/ai-ecosystem"
COMMAND_PREFIX = "WORDSTAT_BRIDGE_COMMAND_V1 "
RESULT_PREFIX = "WORDSTAT_BRIDGE_RESULT_V1 "
YANDEX_BASE = "https://searchapi.api.cloud.yandex.net/v2/wordstat/"
GITHUB_COMMENTS = "https://api.github.com/repos/" + REPO + "/issues/162/comments"
DEVICES = {"DEVICE_ALL", "DEVICE_DESKTOP", "DEVICE_PHONE", "DEVICE_TABLET"}


def parse_command(event: dict, now: dt.datetime) -> dict | None:
    if event.get("action") != "created":
        return None
    if event.get("issue", {}).get("number") != ISSUE_NUMBER:
        return None
    comment = event.get("comment", {})
    if comment.get("user", {}).get("login") != OWNER:
        return None
    body = comment.get("body", "")
    if not isinstance(body, str) or not body.startswith(COMMAND_PREFIX):
        return None
    data = json.loads(body[len(COMMAND_PREFIX):])
    if not isinstance(data, dict):
        raise ValueError("invalid_command")
    command_id = str(uuid.UUID(str(data["command_id"])))
    action = data.get("action")
    if action not in ("regions", "top"):
        raise ValueError("action_not_allowed")
    if data.get("schema") != "wordstat.bridge.command.v1":
        raise ValueError("invalid_schema")
    issued = dt.datetime.fromisoformat(data["issued_at"].replace("Z", "+00:00"))
    expires = dt.datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    if issued.tzinfo is None or expires.tzinfo is None:
        raise ValueError("timestamps_require_offset")
    if not (issued <= now <= expires) or (expires - issued).total_seconds() > 600:
        raise ValueError("expired_or_future_command")
    normalized = {"command_id": command_id, "action": action}
    if action == "top":
        phrase = data.get("phrase")
        if not isinstance(phrase, str) or not 2 <= len(phrase.strip()) <= 80:
            raise ValueError("invalid_phrase")
        if any(ord(c) < 32 for c in phrase) or len(phrase.split()) > 10:
            raise ValueError("unsafe_phrase")
        region = str(data.get("region", "225"))
        device = data.get("device", "DEVICE_ALL")
        if not re.fullmatch(r"[0-9]{1,8}", region) or device not in DEVICES:
            raise ValueError("invalid_region_or_device")
        normalized.update(phrase=phrase.strip(), region=region, device=device)
    return normalized


def request_json(url: str, token: str, payload: dict | None = None,
                 method: str = "GET") -> object:
    headers = {"Accept": "application/json", "User-Agent": "wordstat-chat-bridge/1"}
    if token:
        headers["Authorization"] = token
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, headers=headers, data=data, method=method)
    with urlopen(req, timeout=15) as response:
        raw = response.read(300001)
    if len(raw) > 300000:
        raise ValueError("response_too_large")
    return json.loads(raw.decode("utf-8"))


def read_bot_results(gh_token: str) -> list[dict]:
    """Read all visible response pages; fail closed if the history exceeds cap."""
    results = []
    for page in range(1, 21):
        url = GITHUB_COMMENTS + "?per_page=100&page=" + str(page)
        comments = request_json(url, "Bearer " + gh_token)
        if not isinstance(comments, list):
            raise ValueError("unexpected_github_response")
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            if comment.get("user", {}).get("login") != "github-actions[bot]":
                continue
            body = comment.get("body", "")
            if not isinstance(body, str) or not body.startswith(RESULT_PREFIX):
                continue
            try:
                record = json.loads(body[len(RESULT_PREFIX):])
                if isinstance(record, dict):
                    results.append(record)
            except ValueError:
                continue
        if len(comments) < 100:
            return results
    raise ValueError("history_too_large_fail_closed")


def find_existing_result(gh_token: str, command_id: str) -> bool:
    return any(record.get("command_id") == command_id
               for record in read_bot_results(gh_token))


def count_daily_paid_reservations(records: list[dict], now: dt.datetime) -> int:
    """All paid requests must have a durable reservation before dispatch."""
    day = now.date().isoformat()
    return sum(1 for item in records
               if item.get("status") == "started"
               and item.get("method") == "GetTop"
               and str(item.get("checked_at", "")).startswith(day))


def post_result(gh_token: str, result: dict) -> None:
    body = RESULT_PREFIX + json.dumps(result, ensure_ascii=False,
                                      separators=(",", ":"))
    request_json(GITHUB_COMMENTS, "Bearer " + gh_token,
                 {"body": body}, "POST")


def call_wordstat(command: dict, api_key: str, folder_id: str,
                  allow_paid: bool) -> dict:
    if not api_key:
        return {"status": "not_configured", "missing": "api_key"}
    auth = "Api-Key " + api_key
    if command["action"] == "regions":
        # The official REST example also supports a POST without a folder ID.
        # Include it when available, but avoid requiring a second secret
        # just for the free connection check.
        payload = {"folderId": folder_id} if folder_id else {}
        result = request_json(YANDEX_BASE + "getRegionsTree", auth,
                              payload, method="POST")
        if not isinstance(result, dict) or not isinstance(result.get("regions"), list):
            return {"status": "unexpected_yandex_response"}
        roots = result["regions"]
        return {"status": "ok", "method": "GetRegionsTree", "root_regions":
                [{"id": str(x.get("id", "")), "name": str(x.get("name", x.get("label", "")))[:60]}
                 for x in roots[:8] if isinstance(x, dict)],
                "root_count": len(roots), "billable": False}
    if not allow_paid:
        return {"status": "paid_requests_disabled", "method": "GetTop"}
    # For an API key issued to a service account, Yandex Search API uses
    # that account's folder. An explicit mismatched folderId can return 403.
    # Do not attach the optional folderId even if a secret is configured.
    payload = {"phrase": command["phrase"], "numPhrases": 20,
               "regions": [command["region"]], "devices": [command["device"]]}
    result = request_json(YANDEX_BASE + "topRequests", auth, payload, method="POST")
    if not isinstance(result, dict) or not isinstance(result.get("results"), list):
        return {"status": "unexpected_yandex_response"}
    def select(items, maximum):
        return [{"phrase": str(x.get("phrase", ""))[:110],
                 "count": str(x.get("count", ""))[:24]}
                for x in items[:maximum] if isinstance(x, dict)]
    return {"status": "ok", "method": "GetTop", "billable": True,
            "phrase": command["phrase"], "region": command["region"],
            "device": command["device"],
            "totalCount": str(result.get("totalCount", ""))[:24],
            "results": select(result["results"], 10),
            "associations": select(result.get("associations", []), 5)}


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc)
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as fh:
        event = json.load(fh)
    try:
        command = parse_command(event, now)
    except (KeyError, ValueError, TypeError, AttributeError):
        print("Ignored invalid or expired command")
        return 0
    if command is None:
        print("No matching owner command")
        return 0
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    if not gh_token:
        print("GitHub token unavailable")
        return 1

    key = os.environ.get("YANDEX_WORDSTAT_API_KEY", "")
    folder_id = os.environ.get("YANDEX_WORDSTAT_FOLDER_ID", "")
    allow_paid = os.environ.get("WORDSTAT_ALLOW_BILLABLE", "false").lower() == "true"
    try:
        history = read_bot_results(gh_token)
        if any(item.get("command_id") == command["command_id"] for item in history):
            print("Command already handled")
            return 0
        if command["action"] == "top" and allow_paid and key:
            # Fixed spending limit: 10 GetTop requests per UTC day (10 x 0.02 RUB).
            # Fail closed if a reservation cannot be posted to the trusted issue.
            # Reservations prevent a crashed run from silently retrying a paid call.
            if count_daily_paid_reservations(history, now) >= 10:
                response = {"status": "daily_paid_limit_reached",
                            "daily_limit": 10, "method": "GetTop"}
            else:
                post_result(gh_token, {
                    "status": "started", "method": "GetTop", "billable": True,
                    "command_id": command["command_id"],
                    "checked_at": now.isoformat(), "source": "Yandex Wordstat API"
                })
                response = call_wordstat(command, key, folder_id, True)
        else:
            response = call_wordstat(command, key, folder_id, allow_paid)
    except HTTPError as exc:
        response = {"status": "upstream_http_error", "code": exc.code}
    except (URLError, TimeoutError, ValueError, TypeError, KeyError):
        response = {"status": "upstream_unavailable"}
    response["command_id"] = command["command_id"]
    response["checked_at"] = now.isoformat()
    response["source"] = "Yandex Wordstat API"
    try:
        post_result(gh_token, response)
    except (HTTPError, URLError, TimeoutError, ValueError):
        print("Result could not be posted; do not re-run a billed request blindly")
        return 1
    print("Posted status:", response["status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
