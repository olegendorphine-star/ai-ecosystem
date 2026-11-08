#!/usr/bin/env python3
"""Read-only health worker for the isolated Avito server contour."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import socket
import ssl
import time
import threading
import urllib.request
from pathlib import Path

ACTIONS = {"health", "browser_health", "connect_status", "handoff_health"}


def http_status(url: str) -> int | None:
    result: dict[str, int | None] = {"status": None}
    def probe() -> None:
        try:
            request = urllib.request.Request(url, method="GET", headers={"User-Agent": "AvitoBridgeHealth/1.0"})
            with urllib.request.urlopen(request, timeout=5) as response:
                result["status"] = int(response.status)
        except Exception:
            result["status"] = None
    thread = threading.Thread(target=probe, daemon=True)
    thread.start()
    thread.join(timeout=6)
    return result["status"] if not thread.is_alive() else None


def health() -> dict:
    usage = shutil.disk_usage("/")
    memory = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            memory[key] = int(value.strip().split()[0]) * 1024
    except (OSError, ValueError):
        memory = {}
    return {
        "action": "health",
        "ok": True,
        "hostname_present": bool(socket.gethostname()),
        "cpu_count": os.cpu_count(),
        "memory_total_bytes": memory.get("MemTotal"),
        "memory_available_bytes": memory.get("MemAvailable"),
        "disk_free_bytes": usage.free,
        "checked_at": int(time.time()),
    }


def browser_health() -> dict:
    binaries = ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable"]
    found = {name: shutil.which(name) is not None for name in binaries}
    local_venv = Path.home() / ".avito-agent" / "venv"
    local_playwright = list((local_venv / "lib").glob("python*/site-packages/playwright"))
    browser_cache = Path.home() / ".cache" / "ms-playwright"
    local_browsers = sorted(
        path for path in browser_cache.rglob("*")
        if path.is_file()
        and path.name in {"chrome", "headless_shell"}
        and os.access(path, os.X_OK)
    )
    playwright_installed = importlib.util.find_spec("playwright") is not None or bool(local_playwright)
    browser_path = str(local_browsers[0]) if local_browsers else ""
    browser_available = any(found.values()) or bool(local_browsers)
    profile = os.environ.get("AVITO_BROWSER_PROFILE_DIR", "")
    return {
        "action": "browser_health",
        "ok": browser_available and playwright_installed,
        "browser_binaries": found,
        "playwright_installed": playwright_installed,
        "playwright_user_venv": str(local_venv) if local_playwright else "",
        "playwright_browser_path": browser_path,
        "profile_configured": bool(profile),
        "profile_directory_exists": bool(profile and Path(profile).is_dir()),
    }


def connect_status() -> dict:
    return {
        "action": "connect_status",
        "ok": True,
        "connect_http": http_status("https://connect.tg/"),
        "telegram_http": http_status("https://t.me/"),
        "profile_configured": bool(os.environ.get("AVITO_BROWSER_PROFILE_DIR", "")),
        "write_actions": False,
    }



def _safe_browser_status(payload: object) -> dict:
    """Convert sensitive local UI status into non-identifying readiness flags."""
    result = {
        "action": "handoff_health", "ok": False,
        "local_http_ok": True, "browser_ready": False,
        "startup_failed": False, "write_actions": False,
    }
    if not isinstance(payload, dict):
        return result
    result["startup_failed"] = bool(payload.get("startup_error"))
    page_url = payload.get("url")
    # about:blank counts as an initialized page, not Avito login.
    result["browser_ready"] = (
        payload.get("ok") is True
        and not result["startup_failed"]
        and isinstance(page_url, str)
        and bool(page_url)
    )
    result["ok"] = result["browser_ready"]
    return result


def handoff_health() -> dict:
    """GET only the loopback handoff status through SSH; never expose URL or session."""
    blocked = {
        "action": "handoff_health", "ok": False,
        "local_http_ok": False, "browser_ready": False,
        "startup_failed": False, "write_actions": False,
    }
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    # Forbid proxy environment variables and external targets in this health check.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
    request = urllib.request.Request(
        "http://127.0.0.1:8787/api/status", method="GET",
        headers={"Accept": "application/json", "User-Agent": "AvitoLocalProbe/1.0"},
    )
    try:
        with opener.open(request, timeout=3) as response:
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if response.status != 200 or content_type != "application/json":
                return blocked
            raw = response.read(4097)
        if len(raw) > 4096:
            return blocked
        payload = json.loads(raw.decode("utf-8"))
        return _safe_browser_status(payload)
    except (OSError, ValueError, UnicodeError, TypeError):
        return blocked


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=sorted(ACTIONS), required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = {"health": health, "browser_health": browser_health, "connect_status": connect_status, "handoff_health": handoff_health}[args.action]()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
