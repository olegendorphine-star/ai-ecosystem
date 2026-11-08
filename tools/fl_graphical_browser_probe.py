#!/usr/bin/env python3
"""Read-only graphical Chrome environment check on existing VPS.

No account, cookies, captcha interaction, button clicks or automation of FL actions.
Only safe capability flags, fixed status and failure categories are emitted.
"""
from __future__ import annotations
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path


def classify(err: Exception) -> str:
    msg = str(err).lower()
    if "timeout" in msg:
        return "timeout"
    if "executable doesn't exist" in msg:
        return "browser_missing"
    if "target closed" in msg or "browser has been closed" in msg:
        return "browser_closed"
    if "cannot open shared object" in msg:
        return "missing_library"
    if "cannot open display" in msg or "x server" in msg:
        return "display_error"
    if "err_connection" in msg:
        return "network_error"
    return "other_failure"



def classify_xvfb_log(raw: bytes) -> list[str]:
    """Categorize local X-server stderr without revealing paths or contents."""
    text = raw[-16384:].decode("utf-8", "replace").lower()
    labels = {
        "x11_fonts_missing": ("could not open default font", "font 'fixed'", "couldn't open default font"),
        "xkb_configuration_missing": ("xkb", "xkeyboard", "keymap"),
        "unix_socket_permission": ("socket", "x11-unix", "permission denied"),
        "server_already_active": ("server is already active", "display already"),
        "xorg_module_missing": ("failed to load module", "unable to load module"),
        "shared_library_error": ("error while loading shared libraries", "symbol lookup error"),
        "fatal_server_error": ("fatal server error",),
        "glx_error": ("glx", "glamor", "gl_init"),
    }
    return sorted(key for key, values in labels.items() if any(v in text for v in values))

def locate_chrome() -> Path | None:
    root = Path.home() / ".cache" / "ms-playwright"
    if not root.is_dir():
        return None
    choices = sorted(p for p in root.rglob("chrome")
                     if p.is_file() and os.access(p, os.X_OK))
    return choices[-1] if choices else None


def probe() -> dict:
    out = {
        "schema": "fl.graphical.browser.probe.v1",
        "xvfb_present": shutil.which("Xvfb") is not None,
        "xorg_present": shutil.which("Xorg") is not None,
        "display_env_present": bool(os.getenv("DISPLAY")),
        "desktop_chrome_present": False,
        "fontconfig_isolated_ready": False,
        "graphical_browser_started": False,
        "blank_screenshot": "not_checked",
        "fl_public_navigation": "not_checked",
        "fl_http_status": None,
        "fl_public_screenshot": "not_checked",
        "browser_alive_after": False,
        "result": "not_ready",
        "xvfb_log_categories": [],
        "xvfb_exit_code": None,
        "credentials_used": False,
        "captcha_interacted": False,
        "write_actions": False,
    }
    chrome = locate_chrome()
    out["desktop_chrome_present"] = chrome is not None
    fontconf = Path.home() / ".fl-agent/fontconfig/fonts.conf"
    out["fontconfig_isolated_ready"] = fontconf.is_file()
    if not chrome:
        out["result"] = "full_chrome_missing"
        return out
    if not shutil.which("Xvfb"):
        out["result"] = "xvfb_missing"
        return out
    if not fontconf.is_file():
        out["result"] = "fontconfig_missing"
        return out
    xvfb = None
    pw = None
    browser = None
    with tempfile.TemporaryDirectory(prefix="fl-graphical-check-") as tmp:
        stderr_file = Path(tmp) / "xvfb.stderr"
        try:
            from playwright.sync_api import sync_playwright
            # Test a private X display. Do not attach to other users' desktops.
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                candidate = sock.getsockname()[1] % 10000 + 200
            display = f":{candidate}"
            if Path(f"/tmp/.X11-unix/X{candidate}").exists():
                out["result"] = "display_conflict"
                return out
            with stderr_file.open("wb") as stream:
                xvfb = subprocess.Popen(
                    ["Xvfb", display, "-screen", "0", "1280x850x24", "-nolisten", "tcp"],
                    stdout=subprocess.DEVNULL, stderr=stream
                )
            for _ in range(35):
                if xvfb.poll() is not None:
                    out["result"] = "xvfb_exited"
                    return out
                if Path(f"/tmp/.X11-unix/X{candidate}").exists():
                    break
                time.sleep(.1)
            else:
                out["result"] = "xvfb_not_ready"
                return out
            env = os.environ.copy()
            env["DISPLAY"] = display
            env["FONTCONFIG_FILE"] = str(fontconf)
            env["FONTCONFIG_PATH"] = str(fontconf.parent)
            pw = sync_playwright().start()
            browser = pw.chromium.launch(
                executable_path=str(chrome), headless=False,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
                env=env, timeout=18000,
            )
            out["graphical_browser_started"] = True
            page = browser.new_page(viewport={"width": 1280, "height": 850})
            try:
                png = page.screenshot(type="png", timeout=7000)
                out["blank_screenshot"] = "ok" if png.startswith(b"\x89PNG\r\n\x1a\n") else "invalid"
            except Exception as exc:
                out["blank_screenshot"] = classify(exc)
            try:
                resp = page.goto("https://www.fl.ru/account/login/",
                                 wait_until="commit", timeout=18000)
                code = resp.status if resp else None
                out["fl_http_status"] = code if type(code) is int and 100 <= code <= 599 else None
                out["fl_public_navigation"] = "ok"
            except Exception as exc:
                out["fl_public_navigation"] = classify(exc)
            try:
                png = page.screenshot(type="png", timeout=7000)
                out["fl_public_screenshot"] = "ok" if png.startswith(b"\x89PNG\r\n\x1a\n") else "invalid"
            except Exception as exc:
                out["fl_public_screenshot"] = classify(exc)
            out["browser_alive_after"] = browser.is_connected()
            if (out["fl_http_status"] == 200 and out["fl_public_screenshot"] == "ok"
                    and out["browser_alive_after"]):
                out["result"] = "graphical_public_smoke_pass"
            else:
                out["result"] = "graphical_public_smoke_failed"
        except Exception as exc:
            out["result"] = classify(exc)
        finally:
            if browser:
                try: browser.close()
                except Exception: pass
            if pw:
                try: pw.stop()
                except Exception: pass
            if xvfb:
                out["xvfb_exit_code"] = xvfb.poll()
                if xvfb.poll() is None:
                    xvfb.terminate()
                    try: xvfb.wait(timeout=3)
                    except subprocess.TimeoutExpired: xvfb.kill()
            try:
                out["xvfb_log_categories"] = classify_xvfb_log(stderr_file.read_bytes())
            except OSError:
                pass
    return out


if __name__ == "__main__":
    print(json.dumps(probe(), sort_keys=True))
