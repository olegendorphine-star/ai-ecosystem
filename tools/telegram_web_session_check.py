#!/usr/bin/env python3
"""Read-only health check of owner Telegram Web in its own persistent VPS profile.

Never retrieve/print chats, messages, contacts, browser storage, screenshots, or
Telegram credentials. The only output is a whitelisted summary of UI signals.
"""
from __future__ import annotations

import fcntl
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path.home() / ".telegram-agent" / "browser"
PROFILE = ROOT / "profile"
LOCK = ROOT / "rootless_owner.lock"
STATES = frozenset({"authenticated", "auth_required", "inconclusive"})


def classify(signals: dict) -> str:
    """Fail closed: domain alone / sidebar alone / cookies are not proof."""
    if not isinstance(signals, dict) or not signals.get("telegram_origin"):
        return "inconclusive"
    if signals.get("auth_ui_visible"):
        return "auth_required"
    if signals.get("sidebar_visible") and signals.get("chatlist_visible"):
        return "authenticated"
    return "inconclusive"


# All fields returned by JavaScript are booleans. No innerText, input values or
# DOM element attributes, account IDs, conversations or credentials leave Chrome.
UI_SIGNALS_JS = r"""() => {
  const visible = selector => [...document.querySelectorAll(selector)].some(
    el => el.getClientRects().length > 0);
  const sidebar = visible('#column-left');
  const chatlist = visible('#column-left .chatlist, #column-left .chatlist-container, ' +
    '#column-left [class*="chatlist"], .chatlist-container, #chatlist-container');
  const auth = visible('input[type="tel"], input[autocomplete="tel"], ' +
    '#auth-pages .qr-container, .auth-form input, #auth-pages input');
  return {sidebar_visible: sidebar, chatlist_visible: chatlist,
          auth_ui_visible: auth};
}"""


def profile_safe(path: Path) -> bool:
    if path.is_symlink() or not path.is_dir():
        return False
    if path.stat().st_uid != os.getuid():
        return False
    if path.stat().st_mode & 0o077:
        return False
    # Check Chromium wrote its own data: this is NOT proof of Telegram login.
    return (path / "Local State").is_file()


def run_once(portal) -> dict:
    browser = portal.Browser()
    result = {"telegram_origin": False, "sidebar_visible": False,
              "chatlist_visible": False, "auth_ui_visible": False}
    try:
        with tempfile.TemporaryDirectory(prefix="tg-session-verify-", dir=ROOT) as tmp:
            browser.open(Path(tmp))
            for _ in range(14):
                url = browser.page.url
                result["telegram_origin"] = portal.is_telegram_url(url)
                ui = browser.page.evaluate(UI_SIGNALS_JS)
                for field in ("sidebar_visible", "chatlist_visible", "auth_ui_visible"):
                    result[field] = bool(ui.get(field, False))
                if classify(result) != "inconclusive":
                    break
                browser.page.wait_for_timeout(1000)
    finally:
        browser.close()
    return result


def main() -> int:
    summary = {"schema": "tg.web.session.restart.v1",
               "profile_present": False,
               "browser_restart_checked": False,
               "first_open": "not_checked",
               "second_open": "not_checked",
               "persistent_authenticated": False,
               "telegram_content_exported": False,
               "account_actions": False}
    try:
        root = ROOT
        if root.is_symlink() or not root.is_dir():
            summary["state"] = "root_missing"
            print(json.dumps(summary, sort_keys=True))
            return 0
        summary["profile_present"] = profile_safe(PROFILE)
        if not summary["profile_present"]:
            summary["state"] = "profile_missing_or_unsafe"
            print(json.dumps(summary, sort_keys=True))
            return 0
        if LOCK.is_symlink():
            summary["state"] = "lock_unsafe"
            print(json.dumps(summary, sort_keys=True))
            return 0
        # Respect an active owner window; do not close/kill it or corrupt its profile.
        fd = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "r+") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                summary["state"] = "owner_window_busy"
                print(json.dumps(summary, sort_keys=True))
                return 0
            sys.path.insert(0, str(ROOT))
            import telegram_web_owner_portal as portal
            if not portal.load_private_browser_proxy():
                summary["state"] = "proxy_not_configured"
                print(json.dumps(summary, sort_keys=True))
                return 0
            first = classify(run_once(portal))
            summary["first_open"] = first
            if first == "authenticated":
                # Fresh Chromium launch after previous Chrome was closed, same
                # persistent disk profile. Verify restoration a second time.
                second = classify(run_once(portal))
                summary["second_open"] = second
                summary["browser_restart_checked"] = True
                summary["persistent_authenticated"] = second == "authenticated"
                summary["state"] = ("authenticated_after_restart"
                                    if summary["persistent_authenticated"]
                                    else "second_launch_not_authenticated")
            else:
                summary["state"] = ("login_required_after_restart" if first == "auth_required"
                                    else "login_state_inconclusive")
    except Exception:
        # No traceback: could expose browser's private runtime/profile data.
        summary["state"] = "private_browser_check_error"
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
