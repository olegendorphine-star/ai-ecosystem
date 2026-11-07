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
import urllib.request
from pathlib import Path

ACTIONS = {"health", "browser_health", "connect_status"}


def http_status(url: str) -> int | None:
    try:
        request = urllib.request.Request(url, method="GET", headers={"User-Agent": "AvitoBridgeHealth/1.0"})
        with urllib.request.urlopen(request, timeout=8) as response:
            return int(response.status)
    except Exception:
        return None


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
        list(browser_cache.glob("chromium-*/chrome-linux/chrome"))
        + list(browser_cache.glob("chromium_headless_shell-*/chrome-linux/headless_shell"))
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=sorted(ACTIONS), required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = {"health": health, "browser_health": browser_health, "connect_status": connect_status}[args.action]()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
