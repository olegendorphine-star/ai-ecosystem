#!/usr/bin/env python3
"""Install only open-source Debian fonts in the private FL worker home.

No root privileges, shared system changes, session reads or website actions.
Prints only fixed readiness flags; never paths or raw package output.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path.home() / ".fl-agent"
FONTS = ROOT / "fonts"
CONFIG = ROOT / "fontconfig"
CACHE = ROOT / "fontcache"


def private_folder(path: Path):
    if path.is_symlink():
        raise RuntimeError("unsafe_symlink")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.stat().st_uid != os.getuid():
        raise RuntimeError("unsafe_owner")
    path.chmod(0o700)


def make_config(fonts: Path, cache: Path) -> str:
    return (
        '<?xml version="1.0"?>\n'
        '<fontconfig>\n'
        f'  <dir>{escape(str(fonts))}</dir>\n'
        f'  <cachedir>{escape(str(cache))}</cachedir>\n'
        '</fontconfig>\n'
    )


def prepare() -> dict:
    report = {
        "schema": "fl.private.fonts.v1",
        "ok": False,
        "fonts_installed": False,
        "fonts_count": 0,
        "fontconfig_written": False,
        "write_account_actions": False,
        "touches_avito": False,
        "error_category": "none",
    }
    try:
        for path in (ROOT, FONTS, CONFIG, CACHE):
            private_folder(path)
        existing = list(FONTS.glob("*.ttf"))
        if not existing:
            with tempfile.TemporaryDirectory(prefix="font-package-", dir=ROOT) as tmp:
                dest = Path(tmp)
                if shutil.which("apt-get") is None or shutil.which("dpkg-deb") is None:
                    report["error_category"] = "package_tool_missing"
                    return report
                dl = subprocess.run(
                    ["timeout", "65s", "apt-get", "download", "fonts-dejavu-core"],
                    cwd=dest, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=70, check=False,
                )
                if dl.returncode != 0:
                    report["error_category"] = "font_download_failed"
                    return report
                packages = list(dest.glob("fonts-dejavu-core*.deb"))
                if len(packages) != 1:
                    report["error_category"] = "unexpected_font_package"
                    return report
                unpacked = dest / "unpack"
                unpacked.mkdir(mode=0o700)
                extract = subprocess.run(
                    ["dpkg-deb", "-x", str(packages[0]), str(unpacked)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=30, check=False,
                )
                if extract.returncode != 0:
                    report["error_category"] = "font_extract_failed"
                    return report
                candidates = sorted(unpacked.rglob("*.ttf"))
                if not candidates:
                    report["error_category"] = "font_files_missing"
                    return report
                for source in candidates[:20]:
                    if source.is_symlink() or not source.is_file():
                        continue
                    target = FONTS / source.name
                    if target.is_symlink():
                        report["error_category"] = "unsafe_font_symlink"
                        return report
                    shutil.copyfile(source, target)
                    target.chmod(0o600)
        fontfiles = list(FONTS.glob("*.ttf"))
        report["fonts_count"] = len(fontfiles)
        report["fonts_installed"] = bool(fontfiles)
        if not fontfiles:
            return report
        configuration = CONFIG / "fonts.conf"
        if configuration.is_symlink():
            report["error_category"] = "unsafe_config_symlink"
            return report
        temp = CONFIG / ".fonts.conf.tmp"
        if temp.is_symlink():
            report["error_category"] = "unsafe_config_temp_symlink"
            return report
        temp.write_text(make_config(FONTS, CACHE), encoding="utf-8")
        temp.chmod(0o600)
        temp.replace(configuration)
        report["fontconfig_written"] = configuration.is_file()
        report["ok"] = report["fonts_installed"] and report["fontconfig_written"]
    except (OSError, subprocess.TimeoutExpired):
        report["error_category"] = "runtime_setup_failed"
    return report


if __name__ == "__main__":
    print(json.dumps(prepare(), sort_keys=True))
