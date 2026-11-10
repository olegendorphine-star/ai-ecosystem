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


def find_existing_result(gh_token: str, command_id: str) -> bool:
    # Fail closed on any GitHub read error, especially before a billed request.
    comments = request_json(GITHUB_COMMENTS + "?per_page=100", "Bearer " + gh_token)
    if not isinstance(comments, list):
        raise ValueError("unexpected_github_response")
    for comment in comments:
        body = comment.get("body", "") if isinstance(comment, dict) else ""
        if body.startswith(RESULT_PREFIX):
            try:
                obj = json.loads(body[len(RESULT_PREFIX):])
                if obj.get("command_id") == command_id:
                    return True
            except (ValueError, TypeError, AttributeError):
                continue
    return False


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
    if not folder_id:
        return {"status": "not_configured", "missing": "folder_id"}
    payload = {"phrase": command["phrase"], "numPhrases": 20,
               "regions": [command["region"]], "devices": [command["device"]],
               "folderId": folder_id}
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
    try:
        if find_existing_result(gh_token, command["command_id"]):
            print("Command already handled")
            return 0
        response = call_wordstat(
            command,
            os.environ.get("YANDEX_WORDSTAT_API_KEY", ""),
            os.environ.get("YANDEX_WORDSTAT_FOLDER_ID", ""),
            os.environ.get("WORDSTAT_ALLOW_BILLABLE", "false").lower() == "true",
        )
    except HTTPError as exc:
        response = {"status": "upstream_http_error", "code": exc.code}
    except (URLError, TimeoutError, ValueError, TypeError, KeyError):
        response = {"status": "upstream_unavailable"}
    response["command_id"] = command["command_id"]
    response["checked_at"] = now.isoformat()
    response["source"] = "Yandex Wordstat API"
    body = RESULT_PREFIX + json.dumps(response, ensure_ascii=False, separators=(",", ":"))
    try:
        request_json(GITHUB_COMMENTS, "Bearer " + gh_token, {"body": body}, "POST")
    except (HTTPError, URLError, TimeoutError, ValueError):
        print("Result could not be posted; do not re-run a billed request blindly")
        return 1
    print("Posted status:", response["status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
