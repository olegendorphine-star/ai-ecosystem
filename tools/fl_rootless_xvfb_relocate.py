#!/usr/bin/env python3
"""Rootless Xvfb path relocation test on a throwaway private binary copy.

Only tests local virtual screen + headed Chrome about:blank. Never modifies
the system or installed Xvfb, never accesses FL.ru, credentials, or CAPTCHA.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from pathlib import Path

BASE = Path.home() / ".fl-agent/xvfb-runtime"
XVFB = BASE / "usr/bin/Xvfb"
COMP = BASE / "usr/bin/xkbcomp"
FONT = Path.home() / ".fl-agent/fontconfig/fonts.conf"
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def run() -> dict:
    d = {
        "schema": "fl.rootless.xvfb.relocate.v1",
        "private_xvfb": XVFB.is_file(),
        "private_compiler": COMP.is_file(),
        "xvfb_bin_path_mentions": 0,
        "xvfb_bin_exact_cstring_count": 0,
        "patched_copy_created": False,
        "xvfb_started": False,
        "headed_chrome_started": False,
        "about_blank_screenshot": False,
        "failure_categories": [],
        "network_requests": 0,
        "owner_session_used": False,
        "captcha_interacted": False,
        "write_account_actions": False,
    }
    if not (XVFB.is_file() and COMP.is_file()):
        return d
    data = XVFB.read_bytes()
    d["xvfb_bin_path_mentions"] = data.count(b"/usr/bin")
    d["xvfb_bin_exact_cstring_count"] = data.count(bytes((47,117,115,114,47,98,105,110,0)))
    old = bytes((47,117,115,114,47,98,105,110,0))
    if data.count(old) == 0 and data.count(b"/usr/bin/") == 1:
        old = b"/usr/bin/"
    if data.count(old) != 1:
        d["failure_categories"].append("xkb_binary_dir_constant_unavailable")
        return d

    libs = [
        BASE / "usr/lib/x86_64-linux-gnu",
        Path.home() / ".local/usr/lib/x86_64-linux-gnu",
        Path.home() / ".local/lib",
    ]
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = ":".join(map(str, libs)) + (
        ":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    env["PATH"] = str(BASE / "usr/bin") + ":" + env.get("PATH", "")
    env["XKB_CONFIG_ROOT"] = str(BASE / "usr/share/X11/xkb")
    if FONT.is_file():
        env["FONTCONFIG_FILE"] = str(FONT)
        env["FONTCONFIG_PATH"] = str(FONT.parent)

    # Exactly 8-character ephemeral /tmp/<three> path is needed for a same-size
    # replacement of the X server's compiled-in "/usr/bin" constant.
    xkb_wrapper_dir = None
    for _ in range(35):
        candidate = Path("/tmp") / "".join(secrets.choice(ALPHABET) for _ in range(3))
        try:
            candidate.mkdir(mode=0o700)
            xkb_wrapper_dir = candidate
            break
        except FileExistsError:
            pass
    if xkb_wrapper_dir is None:
        d["failure_categories"].append("no_private_short_dir")
        return d

    try:
        (xkb_wrapper_dir / "xkbcomp").symlink_to(COMP)
        new = str(xkb_wrapper_dir).encode("ascii") + old[-1:]
        if len(new) != len(old):
            d["failure_categories"].append("binary_patch_size_mismatch")
            return d
        with tempfile.TemporaryDirectory(prefix="fl-xvfb-copy-", dir=Path.home()/".fl-agent") as tmp:
            td = Path(tmp)
            binary = td / "Xvfb-test"
            binary.write_bytes(data.replace(old, new))
            binary.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            d["patched_copy_created"] = True
            display = None
            for i in range(1700, 1900):
                if not Path(f"/tmp/.X11-unix/X{i}").exists() and not Path(f"/tmp/.X{i}-lock").exists():
                    display = i
                    break
            if display is None:
                d["failure_categories"].append("no_free_x_display")
                return d
            errfile = td / "stderr"
            proc = None
            browser = None
            pw = None
            try:
                cmd = [str(binary), f":{display}", "-screen", "0",
                       "960x680x24", "-nolisten", "tcp"]
                with errfile.open("wb") as fp:
                    proc = subprocess.Popen(cmd, env=env,
                        stdout=subprocess.DEVNULL, stderr=fp, start_new_session=True)
                for _ in range(40):
                    if proc.poll() is not None:
                        break
                    if Path(f"/tmp/.X11-unix/X{display}").exists():
                        d["xvfb_started"] = True
                        break
                    time.sleep(.1)
                if d["xvfb_started"] and FONT.is_file():
                    root = Path.home() / ".cache/ms-playwright"
                    chrome_candidates = sorted(
                        p for p in root.rglob("chrome")
                        if p.is_file() and os.access(p, os.X_OK)) if root.is_dir() else []
                    if chrome_candidates:
                        from playwright.sync_api import sync_playwright
                        env["DISPLAY"] = f":{display}"
                        pw = sync_playwright().start()
                        browser = pw.chromium.launch(
                            executable_path=str(chrome_candidates[-1]),
                            headless=False, env=env,
                            args=["--no-sandbox", "--disable-dev-shm-usage"],
                            timeout=12000,
                        )
                        d["headed_chrome_started"] = True
                        pg = browser.new_page(viewport={"width": 960, "height": 680})
                        screenshot = pg.screenshot(type="png", timeout=7000)
                        d["about_blank_screenshot"] = screenshot[:4] == bytes((137,80,78,71))
            except Exception as exc:
                low = str(exc).lower()
                cat = "timeout" if "timeout" in low else (
                    "missing_shared_lib" if "shared object" in low else "chrome_or_xvfb_error")
                d["failure_categories"].append(cat)
            finally:
                if browser:
                    try: browser.close()
                    except Exception: pass
                if pw:
                    try: pw.stop()
                    except Exception: pass
                if proc:
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                        proc.wait(timeout=3)
                    except (OSError, subprocess.TimeoutExpired):
                        try: os.killpg(proc.pid, signal.SIGKILL)
                        except OSError: pass
                if not d["xvfb_started"]:
                    try:
                        err = errfile.read_text("utf-8",errors="replace").lower()[-12000:]
                        labels = {
                            "xkb_error": ("xkb", "keymap", "keyboard"),
                            "xvfb_fatal": ("fatal server error",),
                            "xkbcomp_exec_missing": ("xkbcomp: not found", "xkbcomp: no such file", "cannot execute xkbcomp"),
                            "shared_library": ("shared libraries", "symbol lookup"),
                            "socket_issue": ("x11-unix", "socket"),
                        }
                        d["failure_categories"].extend(sorted(
                            key for key, needles in labels.items()
                            if any(needle in err for needle in needles)))
                    except OSError:
                        pass
    finally:
        try:
            (xkb_wrapper_dir / "xkbcomp").unlink(missing_ok=True)
            xkb_wrapper_dir.rmdir()
        except OSError:
            pass
    return d


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
