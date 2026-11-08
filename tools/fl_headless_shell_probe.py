#!/usr/bin/env python3
"""Isolated FL.ru Playwright headless-shell smoke; never loads owner state.

One unauthenticated navigation to FL.ru login. Screenshots are discarded.
Only fixed technical flags and error categories go to public GitHub logs.
"""
from __future__ import annotations
import json
from pathlib import Path


def category(error: Exception) -> str:
    message = str(error).lower()
    if "executable doesn't exist" in message or "browser executable" in message:
        return "headless_shell_not_installed"
    if "target closed" in message or "browser has been closed" in message:
        return "browser_closed"
    if "timeout" in message:
        return "timeout"
    if "cannot open shared object" in message:
        return "missing_runtime_library"
    if "err_name_not_resolved" in message:
        return "dns_failed"
    if "err_cert_" in message or "err_ssl_" in message:
        return "tls_failed"
    if "err_connection_" in message:
        return "network_error"
    return "other_error"


def screenshot_status(page) -> str:
    try:
        png = page.screenshot(type="png", timeout=7000, animations="disabled")
        return "ok" if isinstance(png, bytes) and png.startswith(b"\x89PNG\r\n\x1a\n") else "invalid_png"
    except Exception as error:
        return category(error)


def probe() -> dict:
    result = {
        "schema": "fl.headless.shell.smoke.v1",
        "browser_binary_exists": False,
        "browser_started": False,
        "blank_screenshot": "not_attempted",
        "fl_navigation": "not_attempted",
        "fl_http_status": None,
        "fl_screenshot": "not_attempted",
        "browser_alive_after": False,
        "owner_session_used": False,
        "write_actions": False,
    }
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            # Playwright launch(headless=True) uses chromium_headless_shell if
            # it exists, instead of the old chrome-linux CDP executable.
            binary = Path(pw.chromium.executable_path)
            result["browser_binary_exists"] = binary.is_file()
            if not result["browser_binary_exists"]:
                result["blank_screenshot"] = "headless_shell_not_installed"
                return result
            browser = None
            try:
                browser = pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                    timeout=15000,
                )
                result["browser_started"] = True
                page = browser.new_page(viewport={"width": 1280, "height": 850})
                result["blank_screenshot"] = screenshot_status(page)
                try:
                    response = page.goto(
                        "https://www.fl.ru/account/login/",
                        wait_until="commit", timeout=15000,
                    )
                    code = response.status if response is not None else None
                    result["fl_http_status"] = (
                        code if type(code) is int and 100 <= code <= 599 else None
                    )
                    result["fl_navigation"] = "ok"
                except Exception as error:
                    result["fl_navigation"] = category(error)
                result["fl_screenshot"] = screenshot_status(page)
                result["browser_alive_after"] = browser.is_connected()
            except Exception as error:
                if not result["browser_started"]:
                    result["blank_screenshot"] = category(error)
                else:
                    result["fl_screenshot"] = category(error)
            finally:
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass
    except Exception:
        result["blank_screenshot"] = "playwright_unavailable"
    return result


if __name__ == "__main__":
    print(json.dumps(probe(), sort_keys=True))
