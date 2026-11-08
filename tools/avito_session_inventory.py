#!/usr/bin/env python3
"""Read-only inspection of private Avito browser-session persistence.

Runs on the existing VPS over SSH. Never prints file paths, cookie names/values,
tokens, account information, screenshot contents, or raw browser responses.
It is NOT an authentication test and never changes the session or navigates.
"""
from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from urllib.request import Request, ProxyHandler, build_opener
from urllib.error import URLError

MAX_BYTES = 2 * 1024 * 1024
LOOPBACK_STATUS = "http://127.0.0.1:8787/api/status"


def status_flags(payload: object) -> dict:
    if not isinstance(payload, dict):
        return {"browser_ready": False, "on_avito_public_origin": False}
    url = payload.get("url")
    is_on_avito = isinstance(url, str) and (
        url == "https://www.avito.ru/" or url.startswith("https://www.avito.ru/")
    )
    return {
        "browser_ready": payload.get("ok") is True and not payload.get("startup_error"),
        "on_avito_public_origin": is_on_avito,
    }


def inspect_profile(root: Path, *, current_time: float | None = None) -> dict:
    now = time.time() if current_time is None else current_time
    result = {
        "profile_present": False,
        "saved_state_present": False,
        "saved_state_valid": False,
        "saved_state_owner_only": False,
        "avito_cookie_present": False,
        "saved_state_age": "unknown",
        "authenticated": "unverified",
    }
    try:
        if root.is_symlink() or not root.is_dir():
            return result
        result["profile_present"] = True
        state = root / "storage_state.json"
        if state.is_symlink() or not state.is_file():
            return result
        info = state.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES or info.st_size < 2:
            return result
        result["saved_state_present"] = True
        result["saved_state_owner_only"] = (info.st_mode & 0o077) == 0
        # Read only from a private owner-local file; never copy it or publish values.
        data = json.loads(state.read_bytes().decode("utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("cookies"), list):
            return result
        result["saved_state_valid"] = True
        result["avito_cookie_present"] = any(
            isinstance(cookie, dict)
            and isinstance(cookie.get("domain"), str)
            and cookie["domain"].lstrip(".").lower() in {"avito.ru", "www.avito.ru"}
            for cookie in data["cookies"]
        )
        elapsed = max(0, now - info.st_mtime)
        if elapsed < 3600:
            result["saved_state_age"] = "under_1h"
        elif elapsed < 86400:
            result["saved_state_age"] = "under_1d"
        else:
            result["saved_state_age"] = "over_1d"
    except (OSError, UnicodeError, ValueError, TypeError):
        pass
    return result


def browser_probe() -> dict:
    result = {"browser_ready": False, "on_avito_public_origin": False}
    try:
        opener = build_opener(ProxyHandler({}))
        req = Request(LOOPBACK_STATUS, method="GET", headers={"Accept": "application/json"})
        with opener.open(req, timeout=3) as response:
            if response.status != 200:
                return result
            body = response.read(4097)
        if len(body) > 4096:
            return result
        return status_flags(json.loads(body))
    except (OSError, ValueError, UnicodeError, TypeError, URLError):
        return result


def main() -> None:
    root = Path(os.environ.get("AVITO_BROWSER_PROFILE_DIR") or Path.home() / ".avito-agent" / "profile").expanduser()
    report = {
        "schema": "avito.session.inventory.v1",
        "action": "session_inventory",
        **inspect_profile(root),
        **browser_probe(),
        "write_actions": False,
    }
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
