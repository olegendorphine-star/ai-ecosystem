#!/usr/bin/env python3
"""Telegram Web K browser adapter behind the EXISTING encrypted owner-only bridge.

Uses only the already-authorized Chromium profile on the owner's VPS.
No Telegram MTProto API keys or second login. Caller receives results via X25519
and AES-GCM encrypted GitHub issue response (never GH logs, artifacts or files).

Allowlisted actions:
  web_status  -- boolean logged-in status only
  web_dialogs -- bounded titles/peer identifiers from visible chat list
  web_read    -- bounded visible messages in one selected chat
Opening a chat may cause Telegram to mark its messages as read.
No sending, deletion, arbitrary browser automation or scripts from caller.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path.home() / ".telegram-agent" / "browser"
LOCK = ROOT / "rootless_owner.lock"
ALLOWED = frozenset({"web_status", "web_dialogs", "web_read"})

# This checks UI state only. Chat titles and messages are collected separately,
# and passed to the response encryptor on the VPS, NEVER to workflow logs.
UI_STATE_JS = r"""() => {
  const visible = s => [...document.querySelectorAll(s)].some(
    el => el.getClientRects().length > 0);
  return {
    sidebar: visible('#column-left'),
    chatlist: visible('#column-left .chatlist-chat'),
    login_form: visible('input[type="tel"], input[autocomplete="tel"], ' +
      '#auth-pages .qr-container, #auth-pages input'),
  };
}"""

DIALOGS_JS = r"""limit => {
  const rows = [...document.querySelectorAll('#column-left .chatlist-chat[data-peer-id]')];
  const matches = rows.filter(el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  });
  return matches.slice(0, limit).map(row => {
    const peerId = Number(row.getAttribute('data-peer-id'));
    const titleNode = row.querySelector('.dialog-title .user-title, .user-title, .peer-title, .dialog-title, .row-title');
    const title = (titleNode?.textContent || '').trim().slice(0, 120);
    const badge = row.querySelector('.dialog-unread-count, .badge-count, .unread-count');
    const unreadRaw = badge?.textContent?.trim() || '';
    return {
      peer_id: Number.isSafeInteger(peerId) && peerId !== 0 ? peerId : null,
      title,
      unread_label: /^[0-9]{1,5}$/.test(unreadRaw) ? unreadRaw : '',
    };
  }).filter(d => d.peer_id !== null && !!d.title);
}"""

MESSAGES_JS = r"""limit => {
  const bubbles = [...document.querySelectorAll('#column-center .bubble[data-mid]')];
  return bubbles.slice(-limit).map(bubble => {
    const mid = Number(bubble.getAttribute('data-mid'));
    const text = (bubble.querySelector('.message [data-message-text-source]')?.textContent
      || bubble.querySelector('.message')?.textContent || '').trim().slice(0, 1200);
    const incoming = bubble.classList.contains('is-in') ? true
      : bubble.classList.contains('is-out') ? false : null;
    return {
      message_id: Number.isSafeInteger(mid) && mid > 0 ? mid : null,
      incoming, text,
      has_media: !!bubble.querySelector('.media-container, .document, .audio, video, .photo'),
    };
  }).filter(m => m.message_id !== null);
}"""


def classify_ui(url: str, flags: dict) -> str:
    if not isinstance(url, str) or not url.startswith("https://web.telegram.org/"):
        return "unknown"
    if not isinstance(flags, dict):
        return "unknown"
    if flags.get("login_form"):
        return "auth_required"
    if flags.get("sidebar") and flags.get("chatlist"):
        return "authorized"
    return "unknown"


def normalize_dialogs(rows, limit: int):
    if not isinstance(rows, list):
        raise ValueError("unexpected_dialogs")
    unique = set()
    result = []
    for item in rows[:limit]:
        if not isinstance(item, dict):
            continue
        peer = item.get("peer_id")
        name = item.get("title")
        if type(peer) is not int or not -(2 ** 53) < peer < 2 ** 53 or peer == 0:
            continue
        if type(name) is not str or not name.strip() or peer in unique:
            continue
        unique.add(peer)
        label = item.get("unread_label")
        result.append({"peer_id": peer, "title": name.strip()[:120],
                       "unread_label": label if isinstance(label, str) and
                       re.fullmatch(r"[0-9]{1,5}", label) else ""})
    return result


def normalize_messages(rows, limit: int):
    if not isinstance(rows, list):
        raise ValueError("unexpected_messages")
    result = []
    for item in rows[-limit:]:
        if not isinstance(item, dict) or type(item.get("message_id")) is not int:
            continue
        text = item.get("text")
        if not isinstance(text, str):
            text = ""
        incoming = item.get("incoming")
        result.append({
            "message_id": item["message_id"],
            "incoming": incoming if type(incoming) is bool else None,
            "text": text[:1200],
            "has_media": item.get("has_media") is True,
        })
    return result


def run_command(command: dict) -> dict:
    """Start one private headed Chromium process and close it deterministically."""
    action = command["action"]
    p = command["params"]
    if action not in ALLOWED:
        return {"status": "unsupported_action"}
    if ROOT.is_symlink() or not ROOT.is_dir() or LOCK.is_symlink():
        return {"status": "profile_unavailable"}
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "owner_browser_busy"}
        sys.path.insert(0, str(ROOT))
        import telegram_web_owner_portal as portal
        import telegram_web_session_check as checker
        if not checker.profile_safe(portal.PROFILE):
            return {"status": "profile_unavailable"}
        if not portal.load_private_browser_proxy():
            return {"status": "proxy_unavailable"}
        browser = portal.Browser()
        try:
            with tempfile.TemporaryDirectory(prefix="tg-encrypted-command-", dir=ROOT) as tmp:
                browser.open(Path(tmp))
                page = browser.page
                state = "unknown"
                for _ in range(18):
                    state = classify_ui(page.url, page.evaluate(UI_STATE_JS))
                    if state != "unknown":
                        break
                    page.wait_for_timeout(750)
                if state != "authorized":
                    return {"status": "auth_required" if state == "auth_required"
                            else "login_state_unverified"}
                if action == "web_status":
                    return {"status": "authorized", "action": action,
                            "persistent_profile": True}
                if action == "web_dialogs":
                    items = page.evaluate(DIALOGS_JS, p.get("limit", 10))
                    return {"status": "ok", "action": action,
                            "dialogs": normalize_dialogs(items, p.get("limit", 10))}
                # web_read can mark messages as read: caller explicitly
                # requested this operation and receives result encrypted.
                peer_id = p["peer_id"]
                selector = f'#column-left a.chatlist-chat[data-peer-id="{peer_id}"]'
                row = page.locator(selector).first
                if row.count() != 1 or not row.is_visible():
                    return {"status": "chat_not_in_visible_list", "action": action}
                row.focus()
                page.keyboard.press("Enter")
                # A forum row or hidden overlay can swallow Enter. The
                # signed-in client's supported internal chat opening method is
                # used only for the exact already-verified visible peer.
                selected = False
                for attempt in range(20):
                    selected = bool(page.evaluate(
                        "(peer) => String(window.appImManager?.chat?.peerId) === String(peer)",
                        peer_id))
                    if selected:
                        break
                    if attempt == 8:
                        try:
                            page.evaluate(
                                "(peer) => { const m = window.appImManager;"
                                "if (!m || typeof m.setInnerPeer !== 'function') return false;"
                                "m.setInnerPeer({peerId: peer}); return true; }",
                                peer_id)
                        except Exception:
                            pass
                    page.wait_for_timeout(550)
                if not selected:
                    checks = page.evaluate(
                        "(peer) => { const r = document.querySelector("
                        "'#column-left .chatlist-chat[data-peer-id=\\\"' + peer + '\\"]');"
                        "return {chat_present:!!window.appImManager?.chat,"
                        "row_active:!!r?.classList.contains('active'),"
                        "center_visible:!!document.querySelector('#column-center .bubble')}; }",
                        peer_id)
                    # Diagnostic booleans only, encrypted result: never reveal
                    # internal peer ID or chat content if selection is uncertain.
                    return {"status": "requested_chat_not_opened", "action": action,
                            "selection_checks": checks}
                page.wait_for_timeout(900)
                messages = normalize_messages(
                    page.evaluate(MESSAGES_JS, p.get("limit", 10)),
                    p.get("limit", 10))
                return {"status": "ok", "action": action, "peer_id": peer_id,
                        "messages": messages, "may_mark_read": True}
        finally:
            browser.close()


def main():
    # Only parsed allowlisted commands from bridge are used. The whole input
    # remains inside the VPS. Nothing from stderr is forwarded to CI.
    try:
        data = json.load(sys.stdin)
        if (not isinstance(data, dict) or data.get("action") not in ALLOWED or
                not isinstance(data.get("params"), dict)):
            raise ValueError("unsupported")
        response = run_command(data)
    except Exception:
        response = {"status": "private_browser_error"}
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
