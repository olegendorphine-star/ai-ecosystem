#!/usr/bin/env python3
"""One-time read-only, owner-only Avito firewall evidence ON existing VPS.

Binary tar on stdout through SSH. Captures existing browser error if present,
otherwise permits ONE controlled /profile navigation (no retries) as
support-requested evidence, after the previous-day 429 cooldown.
Never logs IP, cookies, account identifiers, screenshot bytes or DOM.
Separate fresh Chrome context for public IP. No login, CAPTCHA or edits.
"""
from __future__ import annotations
import datetime as dt
import io
import json
import os
import re
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

PNG = b"\x89PNG\r\n\x1a\n"
MAX_PNG = 8_000_000
BROWSER_LOCAL = "http://127.0.0.1:8787/"
IP_URL = "https://api4.ipify.org/"
PROFILE_URL = "https://www.avito.ru/profile"
LAST_PROFILE_429 = dt.datetime(2026, 11, 8, 16, 42, tzinfo=dt.timezone.utc)
MIN_COOLDOWN = dt.timedelta(hours=20)

def png_ok(data):
    return data if isinstance(data, bytes) and data.startswith(PNG) and 1000 < len(data) <= MAX_PNG else None

def get_loopback(path, limit):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(BROWSER_LOCAL + path, timeout=3) as response:
        blob = response.read(limit + 1)
        if response.status != 200 or len(blob) > limit:
            raise ValueError("invalid_local_response")
        return blob

def existing_error():
    try:
        status = json.loads(get_loopback("api/status", 4096))
        url = urlparse(status.get("url", ""))
        http = status.get("last_navigation_http_status")
        if url.scheme != "https" or url.hostname != "www.avito.ru" or url.path != "/profile":
            return None, None
        if type(http) is int and http in (403, 429):
            return png_ok(get_loopback("screenshot", MAX_PNG)), http
    except (OSError, ValueError, TypeError):
        pass
    return None, None

def find_chrome():
    root = Path.home() / ".cache" / "ms-playwright"
    matches = sorted(p for p in root.rglob("chrome") if p.is_file() and os.access(p, os.X_OK)) if root.is_dir() else []
    return str(matches[-1]) if matches else None

def private_environment():
    home = Path.home()
    env = os.environ.copy()
    add = [str(home / ".local/usr/lib/x86_64-linux-gnu"), str(home / ".local/lib")]
    env["LD_LIBRARY_PATH"] = ":".join(add + ([env["LD_LIBRARY_PATH"]] if env.get("LD_LIBRARY_PATH") else []))
    return env

def browser_screenshots(allow_one_avito_navigation):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, None, None, 0, "playwright_missing"
    chrome = find_chrome()
    if not chrome:
        return None, None, None, 0, "chrome_missing"
    with tempfile.TemporaryDirectory(prefix="avito-firewall-", dir="/tmp") as directory:
        os.chmod(directory, 0o700)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        command = [chrome, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                   "--disable-gpu", "--no-zygote", "--disable-extensions",
                   "--no-first-run", "--disable-background-networking",
                   "--no-proxy-server", "--remote-debugging-address=127.0.0.1",
                   "--remote-debugging-port=" + str(port),
                   "--user-data-dir=" + str(Path(directory) / "chrome-data"),
                   "about:blank"]
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env=private_environment())
        navs = 0
        try:
            endpoint = f"http://127.0.0.1:{port}/json/version"
            ready = False
            for _ in range(60):
                if proc.poll() is not None:
                    break
                try:
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with opener.open(endpoint, timeout=1) as r:
                        ready = r.status == 200
                    if ready:
                        break
                except OSError:
                    time.sleep(.25)
            if not ready:
                return None, None, None, 0, "chrome_debug_unavailable"
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=10000)
                ip_image = None
                img_reason = "ip_unavailable"
                ip_context = browser.new_context(viewport={"width": 1280, "height": 800})
                try:
                    page = ip_context.new_page()
                    response = page.goto(IP_URL, wait_until="domcontentloaded", timeout=26000)
                    content = page.locator("body").inner_text(timeout=5000).strip()
                    if response is not None and response.status == 200 and re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}",content):
                        ip_image = png_ok(page.screenshot(type="png", timeout=10000))
                        img_reason = "ip_site_verified" if ip_image else "ip_screenshot_failed"
                    else:
                        img_reason = "ip_site_not_verified"
                except Exception:
                    img_reason = "ip_browser_navigation_failed"
                finally:
                    ip_context.close()
                err_image, err_http = None, None
                if allow_one_avito_navigation:
                    state = Path.home() / ".avito-agent/profile/storage_state.json"
                    context_args = {"viewport": {"width": 1280, "height": 900}}
                    if state.is_file() and not state.is_symlink():
                        context_args["storage_state"] = str(state)
                    context = browser.new_context(**context_args)
                    try:
                        page = context.new_page()
                        # Exactly one page.goto to the fixed owner route. NEVER retry 403/429.
                        navs += 1
                        response = page.goto(PROFILE_URL, wait_until="commit", timeout=22000)
                        err_http = response.status if response else None
                        if err_http in (403, 429):
                            try:
                                page.wait_for_load_state("domcontentloaded", timeout=4000)
                            except Exception:
                                pass
                            err_image = png_ok(page.screenshot(type="png", timeout=10000))
                    except Exception:
                        pass
                    finally:
                        context.close()
                browser.close()
                return ip_image, err_image, err_http, navs, img_reason
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()

def main():
    existing_image, existing_status = existing_error()
    # Prior diagnostic HTTP 429 was recorded at 2026-11-08 16:42 UTC;
    # a single support-driven follow-up is allowed only after >=20h.
    allowed = existing_image is None and dt.datetime.now(dt.timezone.utc) - LAST_PROFILE_429 >= MIN_COOLDOWN
    ip_image, fresh_error, http, navs, ip_reason = browser_screenshots(allowed)
    error_image = existing_image or fresh_error
    err_code = existing_status or http
    report = {
        "schema": "avito.firewall.capture.v2",
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ip_site_screenshot": bool(ip_image),
        "ip_capture_class": ip_reason,
        "profile_error_screenshot": bool(error_image),
        "profile_http_status": err_code if type(err_code) is int and 100 <= err_code <= 599 else None,
        "profile_navigation_requests": navs,
        "previous_429_cooldown_elapsed": dt.datetime.now(dt.timezone.utc) - LAST_PROFILE_429 >= MIN_COOLDOWN,
        "browser_login_attempts": 0,
        "account_write_actions": 0,
    }
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        items = {"report.json": json.dumps(report, sort_keys=True).encode()}
        if ip_image:
            items["vps-ip-browser.png"] = ip_image
        if error_image:
            items["avito-profile-error.png"] = error_image
        for name, data in items.items():
            header = tarfile.TarInfo(name)
            header.mode = 0o600
            header.size = len(data)
            tar.addfile(header, io.BytesIO(data))
    sys.stdout.buffer.write(output.getvalue())

if __name__ == "__main__":
    main()
