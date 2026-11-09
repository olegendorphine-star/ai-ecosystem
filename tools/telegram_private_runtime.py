#!/usr/bin/env python3
"""Load owner-only Telegram API credentials from a VPS file before encrypted bridge."""
import os
import re
import sys
from pathlib import Path

ROOT = Path.home() / ".telegram-agent"
CREDS = ROOT / "private" / "telegram.env"
FIELDS = {"TELEGRAM_API_ID", "TELEGRAM_API_HASH"}


def load_credentials(path=CREDS):
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise RuntimeError("TG_CREDENTIALS_NOT_READY")
    found = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeError("TG_INVALID_CONFIG")
        key, val = line.split("=", 1)
        if key not in FIELDS or not re.fullmatch(r"[0-9A-Za-z_\-]+", val):
            raise RuntimeError("TG_INVALID_CONFIG")
        found[key] = val
    if set(found) != FIELDS or not found["TELEGRAM_API_ID"].isdigit():
        raise RuntimeError("TG_CREDENTIALS_NOT_READY")
    os.environ.update(found)


if __name__ == "__main__":
    # A missing credential file must not prevent an encrypted status response.
    # The owner will see configuration_required inside the encrypted result.
    if CREDS.is_file():
        try:
            load_credentials()
        except Exception:
            print("TG_CONFIG_INVALID")
            sys.exit(1)
    from telegram_secure_bridge import cli
    cli()
