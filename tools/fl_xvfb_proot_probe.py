#!/usr/bin/env python3
"""FL VPS: private, account-free graphical X server diagnosis.

Tests whether a user-space Debian proot bind can make the already-installed
xkbcomp available at /usr/bin/xkbcomp to private Xvfb. No FL traffic, cookies,
passwords, screenshots, profile reads or account writes. Status only.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path.home() / ".fl-agent"
PROOT_ROOT = ROOT / "proot-runtime"
XVFB_ROOT = ROOT / "xvfb-runtime"
PROOT = PROOT_ROOT / "usr/bin/proot"
XVFB = XVFB_ROOT / "usr/bin/Xvfb"
XKBCOMP = XVFB_ROOT / "usr/bin/xkbcomp"
XKBDATA = XVFB_ROOT / "usr/share/X11/xkb"
PKGS = ("proot", "libtalloc2")


def private_dir(path: Path) -> bool:
    if path.is_symlink():
        return False
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_uid != os.getuid():
        return False
    path.chmod(0o700)
    return True


def run(args: list[str], env: dict[str, str], *, cwd: Path | None = None, timeout: int = 15):
    try:
        return subprocess.run(args, env=env, cwd=cwd, timeout=timeout, check=False,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    except (OSError, subprocess.TimeoutExpired):
        return None


def check() -> dict:
    out = {
        "schema": "fl.xvfb.proot.diagnostic.v1",
        "system_xkbcomp_missing": not Path("/usr/bin/xkbcomp").is_file(),
        "private_xkbcomp_present": XKBCOMP.is_file(),
        "private_xkb_data_present": (XKBDATA / "rules/evdev").is_file(),
        "private_xvfb_present": XVFB.is_file(),
        "proot_package_downloaded": False,
        "proot_binary_ready": False,
        "proot_version_works": False,
        "proot_xvfb_ready": False,
        "xvfb_failed": False,
        "packages_unavailable": [],
        "owner_session_used": False,
        "fl_network_requests": 0,
        "captcha_interacted": False,
        "write_actions": False,
    }
    if not (out["private_xkbcomp_present"] and out["private_xkb_data_present"]
            and out["private_xvfb_present"]):
        return out
    if not private_dir(ROOT) or not private_dir(PROOT_ROOT):
        return out
    libs = [
        PROOT_ROOT / "usr/lib/x86_64-linux-gnu",
        XVFB_ROOT / "usr/lib/x86_64-linux-gnu",
        Path.home() / ".local/usr/lib/x86_64-linux-gnu",
        Path.home() / ".local/lib",
    ]
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = ":".join(str(p) for p in libs) + (":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    env["PATH"] = str(XVFB_ROOT / "usr/bin") + ":" + env.get("PATH", "")
    if not PROOT.is_file():
        with tempfile.TemporaryDirectory(prefix="fl-proot-pkgs-", dir=ROOT) as d:
            folder = Path(d)
            for package in PKGS:
                rc = run(["apt-get", "download", package], env, cwd=folder, timeout=60)
                candidates = list(folder.glob(package + "_*.deb"))
                if rc != 0 or len(candidates) != 1:
                    out["packages_unavailable"].append(package)
                    continue
                if run(["dpkg-deb", "-x", str(candidates[0]), str(PROOT_ROOT)], env, timeout=20) != 0:
                    out["packages_unavailable"].append(package)
    out["proot_binary_ready"] = PROOT.is_file() and os.access(PROOT, os.X_OK)
    out["proot_package_downloaded"] = out["proot_binary_ready"]
    if not out["proot_binary_ready"]:
        return out
    out["proot_version_works"] = run([str(PROOT), "--version"], env, timeout=8) == 0
    if not out["proot_version_works"]:
        return out
    with tempfile.TemporaryDirectory(prefix="fl-xvfb-proot-", dir=ROOT) as d:
        temp = Path(d)
        compiled = temp / "compiled"
        compiled.mkdir(mode=0o700)
        env["XKB_CONFIG_ROOT"] = str(XKBDATA)
        env["XKB_OUTPUT_DIR"] = str(compiled)
        env["XKB_BIN_DIRECTORY"] = str(XVFB_ROOT / "usr/bin")
        display = None
        for candidate in range(650, 750):
            if not Path(f"/tmp/.X11-unix/X{candidate}").exists():
                display = candidate
                break
        if display is None:
            return out
        command = [
            str(PROOT),
            "-b", f"{XKBCOMP}:/usr/bin/xkbcomp",
            "-b", f"{XKBDATA}:/usr/share/X11/xkb",
            "-b", f"{compiled}:/var/lib/xkb/compiled",
            str(XVFB), f":{display}", "-screen", "0", "800x600x24", "-nolisten", "tcp",
        ]
        proc = None
        try:
            proc = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, start_new_session=True)
            for _ in range(45):
                if Path(f"/tmp/.X11-unix/X{display}").exists() and proc.poll() is None:
                    out["proot_xvfb_ready"] = True
                    break
                if proc.poll() is not None:
                    out["xvfb_failed"] = True
                    break
                time.sleep(0.1)
        except OSError:
            out["xvfb_failed"] = True
        finally:
            if proc is not None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    try: os.killpg(proc.pid, signal.SIGKILL)
                    except OSError: pass
    return out


if __name__ == "__main__":
    print(json.dumps(check(), sort_keys=True))
