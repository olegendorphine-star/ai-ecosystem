#!/usr/bin/env python3
"""Identify why private Xvfb cannot compile its keyboard map.

SSH-only, no browser/account/captcha. No raw local logs, paths or keymaps
leave VPS; stdout contains only allowlisted status flags and categories.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

BASE = Path.home() / ".fl-agent/xvfb-runtime"
BIN = BASE / "usr/bin/xkbcomp"
XKB = BASE / "usr/share/X11/xkb"
XVFB = BASE / "usr/bin/Xvfb"

SOURCE = """xkb_keymap {
    xkb_keycodes { include "evdev+aliases(qwerty)"; };
    xkb_types { include "complete"; };
    xkb_compatibility { include "complete"; };
    xkb_symbols { include "pc+us+inet(evdev)"; };
    xkb_geometry { include "pc(pc105)"; };
};
"""

def classify(stderr: str) -> list[str]:
    s = stderr.lower()
    checks = {
        "xkbcomp_not_found": ("xkbcomp: not found", "xkbcomp: command not found", "could not invoke xkbcomp"),
        "xkb_library_missing": ("libxkbfile.so", "error while loading shared libraries", "symbol lookup error"),
        "xkb_include_missing": ("can't find file", "can't open include file", "couldn't find file"),
        "xkb_compilation_failed": ("failed to compile keymap", "couldn't compile keymap", "syntax error"),
        "xkb_rules_missing": ("could not resolve keymap", "no symbols defined", "unknown keysym"),
        "permission_error": ("permission denied", "cannot create", "read-only file system"),
    }
    return sorted(k for k, needles in checks.items() if any(n in s for n in needles))


def command(args: list[str], env: dict, timeout: int = 9) -> dict:
    try:
        r = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=env, timeout=timeout, check=False)
        return {"ok": r.returncode == 0,
                "code": r.returncode if -255 <= r.returncode <= 255 else None,
                "category": classify((r.stdout + r.stderr)[-16384:].decode("utf-8", "replace"))}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": None, "category": ["timeout"]}
    except OSError:
        return {"ok": False, "code": None, "category": ["launch_failed"]}


def inspect() -> dict:
    env = os.environ.copy()
    local_libs = [BASE / "usr/lib/x86_64-linux-gnu",
                  Path.home() / ".local/usr/lib/x86_64-linux-gnu",
                  Path.home() / ".local/lib"]
    env["LD_LIBRARY_PATH"] = ":".join(map(str, local_libs)) + (
        ":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    env["PATH"] = str(BASE / "usr/bin") + ":" + env.get("PATH", "")
    env["XKB_CONFIG_ROOT"] = str(XKB)
    data = {
        "schema": "fl.xkb.compiler.preflight.v1",
        "xkbcomp_present": BIN.is_file(),
        "xkb_data": {
            "evdev_rules": (XKB/"rules/evdev").is_file(),
            "keycodes": (XKB/"keycodes/evdev").is_file(),
            "symbols": (XKB/"symbols/us").is_file(),
            "types": (XKB/"types/complete").is_file(),
        },
        "xvfb_present": XVFB.is_file(),
        "xvfb_supports_xkbdir": False,
        "xvfb_supports_kb": False,
        "xkbcomp_version": {"ok": False, "code": None, "category": []},
        "xkbcomp_dependencies_missing": [],
        "xkb_compile": {"ok": False, "code": None, "category": []},
        "owner_session_used": False, "write_actions": False
    }
    if XVFB.is_file():
        help_cmd = command([str(XVFB), "-help"], env)
        try:
            r = subprocess.run([str(XVFB), "-help"], env=env,
                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=False)
            h = r.stdout + r.stderr
            data["xvfb_supports_xkbdir"] = b"-xkbdir" in h
            data["xvfb_supports_kb"] = b"-kb " in h
        except (OSError, subprocess.TimeoutExpired):
            pass
    if not BIN.is_file():
        return data
    data["xkbcomp_version"] = command([str(BIN), "-version"], env)
    try:
        r = subprocess.run(["ldd",str(BIN)], env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=5, check=False, text=True)
        missing = re.findall(r"^\s*([-\w+.]+\.so(?:\.\d+)*)\s+=>\s+not found",
                             r.stdout, flags=re.M)
        data["xkbcomp_dependencies_missing"] = sorted(set(missing))[:15]
    except (OSError, subprocess.TimeoutExpired):
        pass
    with tempfile.TemporaryDirectory(prefix="fl-xkb-preflight-") as td:
        source = Path(td) / "example.xkb"
        dest = Path(td) / "example.xkm"
        source.write_text(SOURCE, encoding="utf-8")
        data["xkb_compile"] = command(
            [str(BIN), "-I", f"-I{XKB}", "-w", "0", "-xkm", str(source), str(dest)], env)
        data["xkb_compile"]["output_present"] = dest.is_file() and dest.stat().st_size > 20
    return data

if __name__ == "__main__":
    print(json.dumps(inspect(), sort_keys=True))
