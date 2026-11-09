#!/usr/bin/env python3
"""Rootless FL graphics capability test: precompiled XKB keymap + Xvfb.

Only local about:blank. No FL requests, account data, CAPTCHA, tunnels or writes.
Results are allowlisted flags/categories; no private paths, stderr or screenshots
leave the VPS. All test processes are short-lived.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

BASE = Path.home() / ".fl-agent/xvfb-runtime"
XVFB = BASE / "usr/bin/Xvfb"
COMP = BASE / "usr/bin/xkbcomp"
XKB = BASE / "usr/share/X11/xkb"
FONT = Path.home() / ".fl-agent/fontconfig/fonts.conf"

SOURCE = """xkb_keymap {
    xkb_keycodes { include "evdev+aliases(qwerty)" };
    xkb_types { include "complete" };
    xkb_compat { include "complete" };
    xkb_symbols { include "pc+us+inet(evdev)" };
    xkb_geometry { include "pc(pc105)" };
};
"""


def result() -> dict:
    out = {
        "schema": "fl.rootless.xkbmap.gui.v1",
        "private_xvfb": XVFB.is_file(),
        "private_xkbcomp": COMP.is_file(),
        "private_xkbdata": (XKB / "rules/evdev").is_file(),
        "xkbmap_option_advertised": False,
        "compiled_keymap": False,
        "xvfb_started": False,
        "headed_chromium_started": False,
        "about_blank_screenshot": False,
        "browser_still_connected": False,
        "failure_categories": [],
        "fl_requests": 0,
        "session_used": False,
        "captcha_interacted": False,
        "write_actions": False,
    }
    if not (out["private_xvfb"] and out["private_xkbcomp"] and out["private_xkbdata"]):
        return out
    chrome = None
    root = Path.home() / ".cache/ms-playwright"
    if root.is_dir():
        candidates = sorted(p for p in root.rglob("chrome") if p.is_file() and os.access(p, os.X_OK))
        if candidates:
            chrome = candidates[-1]
    libs = [
        BASE / "usr/lib/x86_64-linux-gnu",
        Path.home() / ".local/usr/lib/x86_64-linux-gnu",
        Path.home() / ".local/lib",
    ]
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = ":".join(str(p) for p in libs) + (
        ":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    env["PATH"] = str(BASE / "usr/bin") + ":" + env.get("PATH", "")
    env["XKB_CONFIG_ROOT"] = str(XKB)
    if FONT.is_file():
        env["FONTCONFIG_FILE"] = str(FONT)
        env["FONTCONFIG_PATH"] = str(FONT.parent)
    try:
        help_run = subprocess.run([str(XVFB), "-help"], env=env, timeout=5,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        out["xkbmap_option_advertised"] = b"-xkbmap" in (help_run.stdout + help_run.stderr)
    except (OSError, subprocess.TimeoutExpired):
        out["failure_categories"].append("xvfb_help_unavailable")
    with tempfile.TemporaryDirectory(prefix="fl-rootless-keymap-") as tmp:
        td = Path(tmp)
        source = td / "keymap.xkb"
        target = td / "keymap.xkm"
        source.write_text(SOURCE, encoding="utf-8")
        try:
            compile_run = subprocess.run([
                str(COMP), f"-I{XKB}", "-w", "0", "-xkm", str(source), str(target)],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=12, check=False)
            out["compiled_keymap"] = (compile_run.returncode == 0
                and target.is_file() and target.stat().st_size > 20)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if not out["compiled_keymap"]:
            out["failure_categories"].append("cannot_precompile_xkb")
            return out
        display = None
        for candidate in range(1300, 1500):
            if not Path(f"/tmp/.X11-unix/X{candidate}").exists() and not Path(f"/tmp/.X{candidate}-lock").exists():
                display = candidate
                break
        if display is None:
            out["failure_categories"].append("no_free_display")
            return out
        errfile = td / "xvfb-stderr"
        proc = None
        p = None
        browser = None
        try:
            cmd = [str(XVFB), f":{display}", "-screen", "0", "1024x768x24",
                   "-nolisten", "tcp", "-xkbmap", str(target)]
            with errfile.open("wb") as f:
                proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL,
                                        stderr=f, start_new_session=True)
            for _ in range(40):
                if proc.poll() is not None:
                    break
                if Path(f"/tmp/.X11-unix/X{display}").exists():
                    out["xvfb_started"] = True
                    break
                time.sleep(.1)
            if out["xvfb_started"] and chrome is not None and FONT.is_file():
                from playwright.sync_api import sync_playwright
                env["DISPLAY"] = f":{display}"
                p = sync_playwright().start()
                browser = p.chromium.launch(executable_path=str(chrome), headless=False,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                    env=env, timeout=15000)
                out["headed_chromium_started"] = True
                page = browser.new_page(viewport={"width": 1024, "height": 768})
                png = page.screenshot(type="png", timeout=6000)
                out["about_blank_screenshot"] = png[:4] == bytes((137, 80, 78, 71))
                out["browser_still_connected"] = browser.is_connected()
        except Exception as exc:
            msg = str(exc).lower()
            if "timeout" in msg:
                out["failure_categories"].append("browser_timeout")
            elif "shared object" in msg:
                out["failure_categories"].append("missing_chrome_library")
            else:
                out["failure_categories"].append("browser_launch_failure")
        finally:
            if browser:
                try: browser.close()
                except Exception: pass
            if p:
                try: p.stop()
                except Exception: pass
            if proc:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    try: os.killpg(proc.pid, signal.SIGKILL)
                    except OSError: pass
            if not out["xvfb_started"]:
                try:
                    diagnostic = errfile.read_text("utf-8", errors="replace").lower()[-12000:]
                    patterns = {
                        "xkb_compilation": ("xkb", "keymap", "keyboard"),
                        "unsupported_argument": ("unrecognized option", "unknown option", "unrecognized argument"),
                        "xserver_fatal": ("fatal server error",),
                        "missing_xkbcomp": ("xkbcomp: no such file", "xkbcomp: not found"),
                        "permission_denied": ("permission denied",),
                        "socket_problem": ("x11-unix", "cannot establish", "socket"),
                    }
                    out["failure_categories"].extend(sorted(
                        k for k, v in patterns.items() if any(x in diagnostic for x in v)))
                except OSError:
                    pass
    return out


if __name__ == "__main__":
    print(json.dumps(result(), sort_keys=True))
