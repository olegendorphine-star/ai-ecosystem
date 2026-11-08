#!/usr/bin/env python3
"""Isolated read-only Chrome rendering check. Never uses owner's cookies or login.

No screenshots, URLs, exceptions, paths or page text are emitted, only
bounded verdicts that distinguish browser crash from site font/render issue.
"""
from __future__ import annotations
import base64
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


def category(exc) -> str:
    err = str(exc).lower()
    if "target closed" in err or "browser has been closed" in err or "target page" in err:
        return "target_closed"
    if "timeout" in err:
        return "timeout"
    if "err_name_not_resolved" in err:
        return "dns_failed"
    if "err_cert_" in err or "err_ssl_" in err:
        return "tls_failed"
    if "err_connection_" in err:
        return "network_failed"
    if "cannot open shared object file" in err:
        return "library_missing"
    return "other_error"


def probe(*, single_process: bool = False) -> dict:
    result = {
        "schema": "fl.render.isolation.v1",
        "mode": "single_process" if single_process else "normal",
        "chrome_exit_code": None,
        "chrome_launched": False, "cdp_connected": False,
        "blank_screenshot": "not_checked", "fl_navigation": "not_checked",
        "fl_http_status": None, "fl_origin_seen": False,
        "fl_playwright_screenshot": "not_checked",
        "fl_cdp_screenshot": "not_checked",
        "chrome_alive_after": False,
        "write_actions": False,
        "owner_session_used": False,
    }
    root = Path.home() / ".cache" / "ms-playwright"
    browsers = sorted(
        x for x in root.rglob("chrome") if x.is_file() and os.access(x, os.X_OK)
    ) if root.is_dir() else []
    if not browsers:
        result["blank_screenshot"] = "browser_missing"
        return result
    proc = None
    p = None
    browser = None
    with tempfile.TemporaryDirectory(prefix="fl-render-smoke-") as tmp:
        try:
            from playwright.sync_api import sync_playwright
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
            args = [
                str(browsers[-1]), "--headless=new", "--no-sandbox",
                "--disable-gpu", "--disable-dev-shm-usage", "--no-zygote",
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={tmp}/chrome-data", "about:blank"
            ]
            if single_process:
                # Controlled compatibility experiment on a fresh, cookie-free profile.
                args.insert(1, "--single-process")
            proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(30):
                if proc.poll() is not None:
                    raise RuntimeError("target closed")
                try:
                    with opener.open(f"http://127.0.0.1:{port}/json/version", timeout=1) as res:
                        if res.status == 200:
                            break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError("cdp unavailable")
            result["chrome_launched"] = True
            p = sync_playwright().start()
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=7000)
            result["cdp_connected"] = True
            context = browser.new_context(viewport={"width": 1280, "height": 850})
            page = context.new_page()
            try:
                page.goto("about:blank", wait_until="commit", timeout=4000)
                png = page.screenshot(type="png", timeout=5000)
                result["blank_screenshot"] = "ok" if png.startswith(b"\x89PNG\r\n\x1a\n") else "invalid"
            except Exception as exc:
                result["blank_screenshot"] = category(exc)

            try:
                response = page.goto("https://www.fl.ru/account/login/", wait_until="commit", timeout=15000)
                code = response.status if response else None
                result["fl_http_status"] = code if type(code) is int and 100 <= code <= 599 else None
                result["fl_origin_seen"] = page.url.startswith("https://www.fl.ru/") or page.url.startswith("https://fl.ru/")
                result["fl_navigation"] = "ok"
            except Exception as exc:
                result["fl_navigation"] = category(exc)

            try:
                png = page.screenshot(type="png", timeout=5000, animations="disabled")
                result["fl_playwright_screenshot"] = "ok" if png.startswith(b"\x89PNG\r\n\x1a\n") else "invalid"
            except Exception as exc:
                result["fl_playwright_screenshot"] = category(exc)

            try:
                cdp = context.new_cdp_session(page)
                try:
                    data = cdp.send("Page.captureScreenshot", {"format":"png","captureBeyondViewport":False})
                    png = base64.b64decode(data.get("data", ""), validate=True)
                    result["fl_cdp_screenshot"] = "ok" if png.startswith(b"\x89PNG\r\n\x1a\n") else "invalid"
                finally:
                    cdp.detach()
            except Exception as exc:
                result["fl_cdp_screenshot"] = category(exc)
            result["chrome_alive_after"] = proc.poll() is None
            result["chrome_exit_code"] = proc.poll()
            context.close()
        except Exception as exc:
            if result["blank_screenshot"] == "not_checked":
                result["blank_screenshot"] = category(exc)
        finally:
            if browser:
                try: browser.close()
                except Exception: pass
            if p:
                try: p.stop()
                except Exception: pass
            if proc and proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=3)
                except subprocess.TimeoutExpired: proc.kill()
    return result


if __name__ == "__main__":
    print(json.dumps({
        "schema": "fl.render.isolation.compare.v1",
        "normal": probe(single_process=False),
        "single_process": probe(single_process=True),
        "owner_session_used": False,
        "write_actions": False,
    }, sort_keys=True))
