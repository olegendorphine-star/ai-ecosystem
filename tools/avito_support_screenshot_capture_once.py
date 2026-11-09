#!/usr/bin/env python3
"""One-shot, read-only, private Avito firewall evidence collection ON EXISTING VPS.

Prints a tar.gz binary to stdout over SSH; never prints IP, cookies, DOM,
screenshots or credentials to logs. Makes no HTTP request to avito.ru.
Only captures existing Chromium screenshot if its last page was 403/429
on the actual owner /profile route, and tries independent IP screenshot
from a different one-shot, clean browser at api4.ipify.org.
"""
from __future__ import annotations

import datetime
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

MAX_PNG = 8_000_000
PNG_HEADER = b"\x89PNG\r\n\x1a\n"
IP_URL = "https://api4.ipify.org/"
LOCAL = "http://127.0.0.1:8787/"
def read_local(path, limit):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(LOCAL + path, timeout=5) as r:
        data = r.read(limit + 1)
        if r.status != 200 or len(data) > limit:
            raise ValueError("local_response_invalid")
        return data

def clean_png(data):
    return data if data.startswith(PNG_HEADER) and 1000 < len(data) <= MAX_PNG else None

def existing_error_screenshot():
    try:
        status = json.loads(read_local("api/status", 8192))
        url = urlparse(status.get("url", ""))
        code = status.get("last_navigation_http_status")
        is_profile = url.scheme == "https" and url.hostname == "www.avito.ru" and (
            url.path == "/profile" or url.path.startswith("/profile/"))
        if not is_profile or type(code) is not int or code not in (403, 429):
            return None, None
        image = clean_png(read_local("screenshot", MAX_PNG))
        return image, code
    except (OSError, ValueError, TypeError, KeyError, TimeoutError):
        return None, None

def ip_screenshot():
    home = Path.home()
    root = home / ".cache" / "ms-playwright"
    chrome = sorted(p for p in root.rglob("chrome") if p.is_file() and os.access(p, os.X_OK)) if root.exists() else []
    if not chrome:
        return None
    library = [
        str(home / ".local" / "usr" / "lib" / "x86_64-linux-gnu"),
        str(home / ".local" / "lib"),
    ]
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = ":".join(library) + (
        ":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    with tempfile.TemporaryDirectory(prefix="avito-firewall-", dir="/tmp") as folder:
        path = Path(folder)
        os.chmod(path, 0o700)
        png_file = path / "ip-browser.png"
        profile_dir = path / "chrome-data"
        cmd = [
            str(chrome[-1]), "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-gpu", "--no-zygote", "--disable-extensions",
            "--no-first-run", "--disable-background-networking", "--hide-scrollbars",
            "--window-size=1280,900",
            "--user-data-dir=" + str(profile_dir),
            "--screenshot=" + str(png_file),
            IP_URL,
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=38, env=env, check=False)
            return clean_png(png_file.read_bytes()) if png_file.is_file() else None
        except (OSError, subprocess.TimeoutExpired):
            return None

def main():
    error_image, http_code = existing_error_screenshot()
    ip_image = ip_screenshot()
    info = {
        "schema": "avito.firewall.capture.v1",
        "captured_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "existing_profile_error_screenshot": bool(error_image),
        "existing_profile_last_http": http_code,
        "ip_browser_screenshot": bool(ip_image),
        "avito_navigation_requests": 0,
        "local_browser_context_changed": False,
    }
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        contents = {"report.json": json.dumps(info, sort_keys=True).encode()}
        if error_image:
            contents["avito-profile-error.png"] = error_image
        if ip_image:
            contents["vps-ip-browser.png"] = ip_image
        for name, data in contents.items():
            header = tarfile.TarInfo(name)
            header.mode = 0o600
            header.size = len(data)
            tar.addfile(header, io.BytesIO(data))
    sys.stdout.buffer.write(output.getvalue())

if __name__ == "__main__":
    main()
