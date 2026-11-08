#!/usr/bin/env python3
"""SSH-only read-only diagnosis of the already running FL owner handoff.

No changes, clicks, password entry, or screenshot disclosure.
The handoff token is read on VPS, never sent off VPS and never printed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path.home() / ".fl-agent"
PORT = 8990
ALLOWED_STATUSES = {200, 400, 401, 403, 404, 405, 429, 500, 502, 503, 504}
TIMEOUT = 12


def local_get(path: str, token: str) -> tuple[int | None, bytes]:
    req = Request(
        f"http://127.0.0.1:{PORT}{path}",
        method="GET",
        headers={"Cookie": f"fl_handoff={token}", "Accept": "application/json"},
    )
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(req, timeout=TIMEOUT) as response:
            return response.status, response.read(4097)
    except HTTPError as exc:
        return exc.code, b""
    except (OSError, URLError):
        return None, b""


def private_diagnostics() -> dict:
    report = {
        "schema": "fl.handoff.diagnostic.v1",
        "handoff_token_present": False,
        "service_http_status": None,
        "browser_ready": False,
        "fl_origin_seen": False,
        "session_saved": False,
        "screenshot_http_status": None,
        "screenshot_available": False,
        "chrome_debug_available": False,
        "write_actions": False,
    }
    try:
        token_file = ROOT / "handoff_token"
        if token_file.is_symlink():
            return report
        meta = token_file.stat()
        if meta.st_uid != os.getuid() or (meta.st_mode & 0o077):
            return report
        token = token_file.read_text().strip()
        if not 32 <= len(token) <= 128:
            return report
        report["handoff_token_present"] = True
        code, raw = local_get("/api/status", token)
        report["service_http_status"] = code if code in ALLOWED_STATUSES else None
        if code == 200:
            body = json.loads(raw)
            if isinstance(body, dict):
                report["browser_ready"] = body.get("ready") is True
                report["fl_origin_seen"] = body.get("on_fl_domain") is True
                report["session_saved"] = body.get("saved") is True
        code, body = local_get("/shot", token)
        report["screenshot_http_status"] = code if code in ALLOWED_STATUSES else None
        report["screenshot_available"] = code == 200 and body.startswith(b"\x89PNG\r\n\x1a\n")
        # Probe Chrome CDP liveness, not page contents.
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                args = Path("/proc", pid, "cmdline").read_bytes().split(b"\0")
            except OSError:
                continue
            if not args or b"chrome" not in args[0].lower():
                continue
            if not any(b"/.fl-agent/" in a and b"--user-data-dir=" in a for a in args):
                continue
            ports = [a.decode().split("=", 1)[1] for a in args
                     if a.startswith(b"--remote-debugging-port=")]
            if not ports or not ports[0].isdigit():
                continue
            port = int(ports[0])
            if not 1024 <= port <= 65535:
                continue
            opener = build_opener(ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{port}/json/version", timeout=2) as response:
                report["chrome_debug_available"] = response.status == 200
            break
    except (OSError, ValueError, TypeError, UnicodeError, URLError):
        pass
    return report


if __name__ == "__main__":
    print(json.dumps(private_diagnostics(), sort_keys=True))
