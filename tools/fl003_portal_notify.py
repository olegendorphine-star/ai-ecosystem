#!/usr/bin/env python3
"""Privately deliver a one-time FL003 browser URL to owner's own Telegram Saved Messages.

Run on the VPS only, not inside public CI. Never emit plaintext URL, token,
cookie, phone number, or message text. No sending to third-party peers.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit
from fl003_task_engine import _telegram_socket_call

ROOT = Path.home() / ".fl003-handoff"
DOMAIN = re.compile(r"^https://[a-z0-9-]{6,80}\.trycloudflare\.com$")


def load_link(root=ROOT):
    token_file = root / "handoff_token"
    log_file = root / "cloudflared.log"
    if token_file.is_symlink() or log_file.is_symlink():
        raise ValueError("unsafe_portal_path")
    token = token_file.read_text(encoding="utf8").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,120}", token):
        raise ValueError("invalid_token")
    text = log_file.read_text(encoding="utf8", errors="replace")
    found = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", text)
    if not found:
        raise ValueError("no_tunnel_link")
    domain = found[-1]
    if not DOMAIN.fullmatch(domain):
        raise ValueError("untrusted_host")
    return domain + "/#" + token


def main():
    if "--selftest" in sys.argv:
        assert DOMAIN.fullmatch("https://random-host-abc123.trycloudflare.com")
        assert not DOMAIN.fullmatch("https://trycloudflare.com.evil.example")
        assert not DOMAIN.fullmatch("http://bad.trycloudflare.com")
        print(json.dumps({"schema":"fl003.portal.private.delivery.v1",
                          "selftest":True,"secrets_emitted":False}))
        return
    link = load_link()
    note = ("FL-003: защищённая проверка двух карточек в браузере VPS.\n"
            "Открой ссылку сейчас (действует до 20 минут). "
            "Если сайт попросит проверку, пройди её самостоятельно, затем нажми "
            "«Проверить карточку».\n"+link)
    if not 1 <= len(note) <= 300:
        raise ValueError("note_too_long")
    try:
        result = _telegram_socket_call(
            {"action":"web_self_note",
             "params":{"text":note, "approved_by_owner":True}})
        status = result.get("status","unavailable")
    except Exception:
        status = "resident_unavailable_or_uncertain"
    # Print only a fixed allowlisted status; never print exception text or URL.
    if status == "sent_confirmed":
        print("FL003_PRIVATE_TELEGRAM_SAVED_MESSAGES_SENT_CONFIRMED")
        return
    if status == "already_attempted_no_resend":
        print("FL003_PRIVATE_TELEGRAM_ALREADY_ATTEMPTED")
        return
    print("FL003_PRIVATE_TELEGRAM_DELIVERY_NOT_CONFIRMED")
    raise SystemExit(1)


if __name__=="__main__":
    main()
