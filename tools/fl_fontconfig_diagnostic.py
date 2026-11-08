#!/usr/bin/env python3
"""Read-only FL Chromium font runtime diagnostic; no cookies or site access.

This inspects only the already configured VPS font infrastructure.
Never prints raw paths, font names, user files, stderr or credentials.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
from pathlib import Path


def safe_run(args: list[str]) -> dict:
    result = {"available": False, "exit_ok": False, "category": "unavailable"}
    if shutil.which(args[0]) is None:
        return result
    result["available"] = True
    try:
        proc = subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=6, check=False,
        )
        result["exit_ok"] = proc.returncode == 0
        diagnostic = proc.stderr[-2048:].decode("utf-8", "replace").lower()
        if "cannot load default config" in diagnostic:
            result["category"] = "no_default_fontconfig"
        elif "not a valid" in diagnostic or "syntax error" in diagnostic:
            result["category"] = "fontconfig_parse_error"
        elif "no fonts" in diagnostic:
            result["category"] = "no_fonts"
        elif "permission denied" in diagnostic:
            result["category"] = "font_permission_error"
        elif "symbol lookup error" in diagnostic or "cannot open shared object" in diagnostic:
            result["category"] = "font_library_missing"
        elif proc.returncode != 0:
            result["category"] = "other_failure"
        else:
            result["category"] = "ok"
        if proc.returncode == 0:
            result["output_nonempty"] = bool(proc.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        result["category"] = "process_error"
    return result


def probe() -> dict:
    font_dirs = [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".local" / "share" / "fonts",
    ]
    return {
        "schema": "fl.fontconfig.runtime.v1",
        "system_fontconfig_exists": Path("/etc/fonts/fonts.conf").is_file(),
        "system_fonts_dir_exists": font_dirs[0].is_dir(),
        "font_dirs_with_font_files": sum(
            bool(any(p.rglob("*.ttf")) or any(p.rglob("*.otf")))
            for p in font_dirs if p.is_dir()
        ),
        "fc_match": safe_run(["fc-match", "-f", "%{family}", "sans-serif"]),
        "fc_list": safe_run(["fc-list", "-f", "%{family}\n"]),
        "fontconfig_env_defined": any(
            os.environ.get(n) for n in ("FONTCONFIG_FILE", "FONTCONFIG_PATH")
        ),
        "owner_session_used": False,
        "write_actions": False,
    }


if __name__ == "__main__":
    print(json.dumps(probe(), sort_keys=True))
