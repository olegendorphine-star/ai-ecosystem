#!/usr/bin/env python3
"""FL.ru owner session watchdog. Read-only; no login, CAPTCHA or account writes.

Runs via a scheduled GitHub Actions job through existing pinned SSH.
Browser and cookies remain entirely on the owner's VPS. A failed graphical
launch is retried in a *new* short-lived browser process; no long-running
CDP/remote desktop port is opened. Only allowlisted status flags leave VPS.
"""
from __future__ import annotations

import fcntl
import json
import os
import stat
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path.home() / ".fl-agent"
PROFILE = ROOT / "profile"
STATE = PROFILE / "storage_state.json"
MARKER = ROOT / "fl_session_watch_status.json"
LOCK = ROOT / "fl_session_watch.lock"

ALLOWED_STATUSES = frozenset({
    "healthy", "auth_required", "captcha_required", "access_restricted",
    "technical_error", "state_missing_or_unsafe", "already_running",
})
CAPTCHA_MARKERS = ("captcha", "smartcaptcha", "я не робот", "робот ли вы")


def validate_state_file() -> bool:
    try:
        if ROOT.is_symlink() or PROFILE.is_symlink() or STATE.is_symlink():
            return False
        if not STATE.is_file():
            return False
        meta = STATE.stat()
        return (stat.S_ISREG(meta.st_mode) and meta.st_uid == os.getuid()
                and 2 <= meta.st_size < 2 * 1024 * 1024
                and meta.st_mode & 0o077 == 0)
    except OSError:
        return False


def classify_owner_page(url: str, http_status: int | None,
                        settings_visible: bool, owner_visible: bool,
                        login_visible: bool, captcha_visible: bool) -> str:
    """Fail-closed: never infer login solely from a 200 or an avatar."""
    try:
        p = urlsplit(url)
    except (TypeError, ValueError):
        return "technical_error"
    if p.scheme != "https" or p.hostname not in {"fl.ru", "www.fl.ru"}:
        return "technical_error"
    if http_status in {403, 429, 451}:
        return "access_restricted"
    if captcha_visible:
        return "captcha_required"
    if p.path.startswith(("/account/login", "/account/registration")) or login_visible:
        return "auth_required"
    if (http_status == 200 and settings_visible and owner_visible
            and p.path.startswith("/profile/")):
        return "healthy"
    return "technical_error"


def make_attempt() -> str:
    """Import storage_state only into a fresh, isolated local Chromium."""
    if not validate_state_file():
        return "state_missing_or_unsafe"
    sys.path.insert(0, str(ROOT))
    import fl_rootless_owner_desktop as portal
    browser = portal.Browser()
    try:
        with tempfile.TemporaryDirectory(prefix="fl-watch-", dir=ROOT) as tmp:
            browser.open(Path(tmp))  # imports state, opens FL login page
            page = browser.page
            response = page.goto(portal.ALLOWED_PAGES["settings"],
                                 wait_until="domcontentloaded", timeout=20000)
            code = response.status if response else None
            # Read only boolean signs, never emit email or body text.
            signs = page.evaluate("""() => {
                const text = (document.body?.innerText || '').toLowerCase();
                return {
                    settings: text.includes('основные настройки'),
                    owner: Array.from(document.querySelectorAll('input')).some(
                        e => (e.value || '').trim().toLowerCase() === 'olegendorphine@gmail.com'),
                    login: !!document.querySelector('form[action*="/account/login"]'),
                    captcha: ['smartcaptcha','captcha'].some(w =>
                        !!document.querySelector('[class*="'+w+'"],[id*="'+w+'"]'))
                        || text.includes('я не робот')
                };
            }""")
            return classify_owner_page(
                page.url, code,
                settings_visible=bool(signs.get("settings")),
                owner_visible=bool(signs.get("owner")),
                login_visible=bool(signs.get("login")),
                captcha_visible=bool(signs.get("captcha")))
    finally:
        browser.close()


def read_previous_status() -> str | None:
    try:
        if MARKER.is_symlink() or not MARKER.is_file():
            return None
        meta = MARKER.stat()
        if meta.st_uid != os.getuid() or meta.st_mode & 0o077 or meta.st_size > 1024:
            return None
        previous = json.loads(MARKER.read_text(encoding="utf-8")).get("status")
        return previous if previous in ALLOWED_STATUSES else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def write_marker(status: str) -> bool:
    assert status in ALLOWED_STATUSES
    if MARKER.is_symlink():
        return False
    fd, tmp = tempfile.mkstemp(prefix=".fl-watch-status-", dir=ROOT)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump({"status": status, "checked_utc": datetime.now(
                timezone.utc).isoformat(timespec="seconds")}, out, sort_keys=True)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, MARKER)
        os.chmod(MARKER, 0o600)
        return True
    except OSError:
        return False
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def transition(previous: str | None, status: str) -> str:
    if previous is None:
        return "failure" if status not in {"healthy", "already_running"} else "none"
    if status == previous or status == "already_running":
        return "none"
    if status == "healthy":
        return "recovered"
    return "failure"


def main() -> None:
    output = {
        "schema": "fl.owner.session.watch.v1",
        "account": "olegendorphine",
        "status": "technical_error",
        "attempts": 0,
        "browser_restart_attempted": False,
        "previous_status": None,
        "alert_kind": "none",
        "marker_saved": False,
        "state_file_read_securely": False,
        "captcha_interacted": False,
        "passwords_read": False,
        "cookie_contents_exported": False,
        "profile_changed": False,
        "bids_sent": False,
        "payment_performed": False,
        "external_remote_desktop_opened": False,
    }
    try:
        if ROOT.is_symlink() or not ROOT.is_dir():
            output["status"] = "state_missing_or_unsafe"
            print(json.dumps(output, sort_keys=True))
            return
        fd = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                output["status"] = "already_running"
                print(json.dumps(output, sort_keys=True))
                return
            output["previous_status"] = read_previous_status()
            output["state_file_read_securely"] = validate_state_file()
            if not output["state_file_read_securely"]:
                output["status"] = "state_missing_or_unsafe"
            else:
                # A genuine owner-auth challenge/expired session will not be
                # circumvented. Restart only for browser/site technical faults.
                for attempt in range(2):
                    output["attempts"] = attempt + 1
                    output["browser_restart_attempted"] = attempt > 0
                    try:
                        output["status"] = make_attempt()
                    except Exception:
                        output["status"] = "technical_error"
                    if output["status"] != "technical_error":
                        break
                    if attempt == 0:
                        time.sleep(1)
            output["alert_kind"] = transition(output["previous_status"],
                                               output["status"])
            output["marker_saved"] = write_marker(output["status"])
    except Exception:
        output["status"] = "technical_error"
        output["alert_kind"] = "failure"
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
