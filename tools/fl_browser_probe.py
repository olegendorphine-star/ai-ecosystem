#!/usr/bin/env python3
"""FL.ru owner operator: isolated, read-only browser preflight.

Explicitly scoped to freelancer olegend... (not the second customer login).
No payment, click, forms, login, messages, edits or external CDP binding.
The result is a narrow technical JSON report; no page text or cookies.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import socket
import stat
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

FL_LOGIN = "olegendorphine"
FL_HOME = "https://www.fl.ru"
PUBLIC_ROUTES = {
    "profile": "/users/olegendorphine/",
    "projects": "/projects/",
}
PRIVATE_ROUTES = {"owner_settings": "/profile/setup/main/"}
AUTH_ROUTE_PREFIXES = ("/account/login", "/account/registration")
AGENT_DIR = Path.home() / ".fl-agent"
PROFILE_DIR = AGENT_DIR / "profile"
STATE_FILE = PROFILE_DIR / "storage_state.json"
MAX_STATE_BYTES = 2 * 1024 * 1024


def safe_hostname(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https" and parsed.hostname in {"fl.ru", "www.fl.ru"}
    except (TypeError, ValueError):
        return False


def classify_response(status: int | None, destination: str, expected_path: str) -> dict:
    path = urlparse(destination).path if safe_hostname(destination) else ""
    if status in (403, 451):
        state = "access_restricted"
    elif status == 429:
        state = "rate_limited"
    elif path.startswith(AUTH_ROUTE_PREFIXES):
        state = "auth_required"
    elif status is not None and 200 <= status < 400 and path == expected_path:
        state = "reachable"
    else:
        state = "unverified"
    return {
        "http_status": status if type(status) is int and 100 <= status <= 599 else None,
        "fl_domain": safe_hostname(destination),
        "expected_route": path == expected_path,
        "state": state,
    }


def safe_state_inventory() -> dict:
    result = {"saved_session_present": False, "saved_state_owner_only": False,
              "authentication": "unverified"}
    try:
        if PROFILE_DIR.is_symlink() or STATE_FILE.is_symlink() or not STATE_FILE.is_file():
            return result
        meta = STATE_FILE.stat()
        if not stat.S_ISREG(meta.st_mode) or meta.st_size < 2 or meta.st_size > MAX_STATE_BYTES:
            return result
        if meta.st_uid != os.getuid():
            return result
        result["saved_session_present"] = True
        result["saved_state_owner_only"] = (meta.st_mode & 0o077) == 0
    except OSError:
        pass
    return result


def make_private_folder(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeError("unsafe_profile_symlink")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_uid != os.getuid():
        raise RuntimeError("unsafe_profile_owner")
    path.chmod(0o700)


def chrome_executable() -> Path | None:
    cache = Path.home() / ".cache" / "ms-playwright"
    if not cache.is_dir():
        return None
    choices = sorted(
        p for p in cache.rglob("chrome")
        if p.is_file() and os.access(p, os.X_OK)
    )
    return choices[-1] if choices else None


def failure_type(exc: Exception) -> str:
    error = str(exc).lower()
    if "timeout" in error:
        return "timeout"
    if "net::err_name_not_resolved" in error:
        return "dns"
    if "err_cert_" in error or "err_ssl_" in error:
        return "tls"
    if "err_connection_" in error:
        return "network"
    if "shared object" in error:
        return "missing_library"
    if "cdp" in error or "debugging" in error:
        return "browser_startup"
    return "browser_or_site_error"


def assess_private_session(route: dict) -> str:
    if route["state"] in ("access_restricted", "rate_limited", "auth_required"):
        return route["state"]
    if route["state"] == "reachable":
        return "likely_active_unverified"
    return "unverified"


def probe_routes(action: str) -> dict:
    result = {
        "schema": "fl.owner.operator.preflight.v1",
        "login": FL_LOGIN,
        "action": action,
        "ok": False,
        "browser_ready": False,
        "profile_separate_from_avito": True,
        "write_actions": False,
        "payments": False,
        "failure_category": "none",
        **safe_state_inventory(),
    }
    targets = dict(PUBLIC_ROUTES)
    if action == "session_probe":
        targets = PRIVATE_ROUTES
        if not result["saved_session_present"]:
            result["auth_state"] = "auth_required"
            result["reason"] = "no_server_session"
            return result
        if not result["saved_state_owner_only"]:
            result["auth_state"] = "unverified"
            result["reason"] = "unsafe_session_permissions"
            return result

    # A short-lived, exclusively locked Chrome instance with its own profile.
    make_private_folder(AGENT_DIR)
    make_private_folder(PROFILE_DIR)
    lock_path = AGENT_DIR / "probe.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    proc = None
    p = None
    browser = None
    with os.fdopen(fd, "r+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            result["failure_category"] = "already_running"
            return result
        try:
            chrome = chrome_executable()
            if chrome is None:
                result["failure_category"] = "browser_missing"
                return result
            from playwright.sync_api import sync_playwright
            # Allocate a fresh random debug port, bound to 127.0.0.1 only.
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                debug_port = sock.getsockname()[1]
            # Ephemeral runtime never shares Avito user data or CDP.
            with tempfile.TemporaryDirectory(prefix="chrome-", dir=AGENT_DIR) as runtime:
                cmd = [
                    str(chrome), "--headless=new", "--no-sandbox",
                    "--disable-dev-shm-usage", "--disable-gpu", "--no-zygote",
                    "--no-first-run", "--no-default-browser-check",
                    "--remote-debugging-address=127.0.0.1",
                    f"--remote-debugging-port={debug_port}",
                    f"--user-data-dir={runtime}", "about:blank"
                ]
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, start_new_session=True)
                endpoint = f"http://127.0.0.1:{debug_port}/json/version"
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for _ in range(35):
                    if proc.poll() is not None:
                        raise RuntimeError("browser_process_exited")
                    try:
                        with opener.open(endpoint, timeout=1) as r:
                            if r.status == 200:
                                break
                    except OSError:
                        time.sleep(0.2)
                else:
                    raise RuntimeError("browser_debugging_unavailable")
                p = sync_playwright().start()
                browser = p.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{debug_port}", timeout=7000
                )
                state_opts = {}
                if action == "session_probe":
                    state_opts["storage_state"] = str(STATE_FILE)
                context = browser.new_context(**state_opts)
                page = context.new_page()
                result["browser_ready"] = True
                outcome = {}
                for key, path in targets.items():
                    try:
                        response = page.goto(FL_HOME + path, wait_until="commit", timeout=18000)
                        code = response.status if response else None
                        outcome[key] = classify_response(code, page.url, path)
                    except Exception as exc:
                        outcome[key] = {"http_status": None, "fl_domain": False,
                                        "expected_route": False, "state": "unverified",
                                        "failure_category": failure_type(exc)}
                result["routes"] = outcome
                if action == "session_probe":
                    result["auth_state"] = assess_private_session(outcome["owner_settings"])
                result["ok"] = all(v["state"] == "reachable" for v in outcome.values()) \
                    if action == "public_probe" else result["auth_state"] == "likely_active_unverified"
                context.close()
        except Exception as exc:
            result["failure_category"] = failure_type(exc)
        finally:
            if browser is not None:
                try: browser.close()
                except Exception: pass
            if p is not None:
                try: p.stop()
                except Exception: pass
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=4)
                except subprocess.TimeoutExpired: proc.kill()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=("public_probe", "session_probe"),
                        default="public_probe")
    args = parser.parse_args()
    print(json.dumps(probe_routes(args.action), sort_keys=True))


if __name__ == "__main__":
    main()
