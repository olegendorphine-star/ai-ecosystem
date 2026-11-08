#!/usr/bin/env python3
"""Unprivileged installation of a private Xvfb runtime for an FL-only test.

Extract allowlisted Debian packages into ~/.fl-agent, never write system paths,
never access user session/cookies, and return only safe status and .so names.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path.home() / ".fl-agent"
DEST = ROOT / "xvfb-runtime"
PKGS = ("xvfb", "libxfont2", "libepoxy0", "libxkbfile1", "xserver-common")
SAFE_SO = re.compile(r"^[A-Za-z0-9_.+-]+\.so(?:\.\d+)*$")


def ensure_private(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeError("unsafe_symlink")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_uid != os.getuid():
        raise RuntimeError("wrong_owner")
    path.chmod(0o700)


def install() -> dict:
    result = {
        "schema": "fl.private.xvfb.v1", "ok": False,
        "xvfb_binary_present": False, "xvfb_executable": False,
        "packages_unavailable": [], "missing_shared_libraries": [],
        "session_used": False, "write_account_actions": False,
    }
    try:
        ensure_private(ROOT)
        ensure_private(DEST)
        binary = DEST / "usr" / "bin" / "Xvfb"
        if not binary.is_file():
            if shutil.which("apt-get") is None or shutil.which("dpkg-deb") is None:
                result["packages_unavailable"] = ["packaging_tools"]
                return result
            with tempfile.TemporaryDirectory(prefix="xvfb-download-", dir=ROOT) as temp:
                folder = Path(temp)
                for pkg in PKGS:
                    proc = subprocess.run(
                        ["timeout", "50s", "apt-get", "download", pkg],
                        cwd=folder, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, timeout=55, check=False
                    )
                    candidates = list(folder.glob(pkg + "_*.deb"))
                    if proc.returncode != 0 or len(candidates) != 1:
                        result["packages_unavailable"].append(pkg)
                        continue
                    unpack = subprocess.run(
                        ["dpkg-deb", "-x", str(candidates[0]), str(DEST)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=20, check=False,
                    )
                    if unpack.returncode != 0:
                        result["packages_unavailable"].append(pkg)
        result["xvfb_binary_present"] = binary.is_file()
        result["xvfb_executable"] = os.access(binary, os.X_OK)
        if not result["xvfb_executable"]:
            return result
        env = os.environ.copy()
        paths = [
            DEST / "usr/lib/x86_64-linux-gnu",
            Path.home() / ".local/usr/lib/x86_64-linux-gnu",
            Path.home() / ".local/lib",
        ]
        env["LD_LIBRARY_PATH"] = ":".join(str(p) for p in paths) + (
            ":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else ""
        )
        proc = subprocess.run(
            ["ldd", str(binary)], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, env=env,
            timeout=8, check=False
        )
        for line in proc.stdout.splitlines():
            if "=> not found" not in line:
                continue
            name = line.strip().split(" ", 1)[0]
            if SAFE_SO.fullmatch(name):
                result["missing_shared_libraries"].append(name)
        result["missing_shared_libraries"] = sorted(set(result["missing_shared_libraries"]))
        result["ok"] = result["xvfb_executable"] and not result["missing_shared_libraries"]
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        pass
    return result


if __name__ == "__main__":
    print(json.dumps(install(), sort_keys=True))
