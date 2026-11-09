#!/usr/bin/env python3
"""Owner-private, rootless, resident Telegram Web operator.

One authenticated Chromium stays open on the owner's VPS. The encrypted
GitHub->SSH bridge communicates with it over a 0600 same-user Unix socket.
No public listener, no Telegram credentials or message text in logs/state.
A bounded, read-only unread-badge monitor runs when the socket is idle.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import signal
import socket
import stat
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path.home() / ".telegram-agent" / "browser"
RUNTIME = ROOT / "resident"
SOCKET = RUNTIME / "operator.sock"
STATE = RUNTIME / "monitor.json"
LOCK = ROOT / "rootless_owner.lock"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path.home() / ".telegram-agent" / "app" / "tools"))

MAX_REQUEST = 16000
MAX_REPLY = 65536
POLL_SECONDS = 12.0

def safe_runtime():
    if ROOT.is_symlink() or not ROOT.is_dir():
        raise RuntimeError("profile_missing")
    if RUNTIME.is_symlink():
        raise RuntimeError("runtime_symlink")
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    info = RUNTIME.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or
            info.st_mode & 0o077):
        raise RuntimeError("runtime_permissions")

def monitor_snapshot(dialogs):
    """Only aggregate unread counts. Never persist a title, ID, or message."""
    total = 0
    active = 0
    for item in dialogs[:20]:
        badge = item.get("unread_label", "")
        if type(badge) is str and badge.isascii() and badge.isdecimal():
            value = min(9999, int(badge))
            if value > 0:
                total += value
                active += 1
    return {"unread_total_visible": min(total, 99999),
            "unread_chats_visible": min(active, 20)}

def write_private_state(payload):
    tmp = RUNTIME / (".state-" + str(os.getpid()))
    fd = os.open(tmp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(payload, out, separators=(",", ":"), ensure_ascii=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, STATE)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass

def request_socket(payload, timeout=4):
    if SOCKET.is_symlink() or not SOCKET.exists():
        return {"status": "resident_not_running"}
    info = SOCKET.stat()
    if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077):
        return {"status": "resident_socket_unsafe"}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(SOCKET))
            client.sendall(json.dumps(payload, separators=(",", ":")).encode())
            client.shutdown(socket.SHUT_WR)
            raw = bytearray()
            while True:
                data = client.recv(4096)
                if not data:
                    break
                raw.extend(data)
                if len(raw) > MAX_REPLY:
                    return {"status": "resident_reply_oversize"}
        value = json.loads(raw)
        if isinstance(value, dict) and isinstance(value.get("status"), str):
            return value
    except Exception:
        pass
    return {"status": "resident_not_responding"}

class Agent:
    def __init__(self):
        self.stop = False
        self.browser = None
        self.page = None
        self.authorized = False
        self.last_total = None
        self.last_increase_at = None
        self.last_check_at = None
        self.snapshot = {"unread_total_visible": 0, "unread_chats_visible": 0}
        self.started_at = dt.datetime.now(dt.timezone.utc).isoformat()

    def handle_signal(self, *_args):
        self.stop = True

    def state(self):
        return {"status": "running", "resident": True,
                "authorized": self.authorized,
                "browser_alive": bool(self.browser and
                                      self.browser.live_status().get("chrome_alive")),
                "unread_total_visible": self.snapshot["unread_total_visible"],
                "unread_chats_visible": self.snapshot["unread_chats_visible"],
                "last_check_at": self.last_check_at,
                "last_unread_increase_at": self.last_increase_at}

    def tick(self, web):
        self.last_check_at = dt.datetime.now(dt.timezone.utc).isoformat()
        state = web.classify_ui(self.page.url, self.page.evaluate(web.UI_STATE_JS))
        self.authorized = state == "authorized"
        if self.authorized:
            items = web.normalize_dialogs(
                self.page.evaluate(web.DIALOGS_JS, 20), 20)
            snapshot = monitor_snapshot(items)
            new_total = snapshot["unread_total_visible"]
            if self.last_total is not None and new_total > self.last_total:
                self.last_increase_at = self.last_check_at
            self.last_total = new_total
            self.snapshot = snapshot
        write_private_state(self.state())

    def serve_socket(self, web, owner):
        if SOCKET.is_symlink():
            raise RuntimeError("unsafe_socket")
        if SOCKET.exists():
            info = SOCKET.stat()
            if (not stat.S_ISSOCK(info.st_mode) or
                    info.st_uid != os.getuid()):
                raise RuntimeError("unsafe_socket")
            SOCKET.unlink()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(SOCKET))
            os.chmod(SOCKET, 0o600)
            server.listen(4)
            server.settimeout(1.0)
            last_tick = 0.0
            try:
                while not self.stop:
                    now = time.monotonic()
                    if now - last_tick >= POLL_SECONDS:
                        try:
                            if not self.browser.live_status().get("chrome_alive"):
                                raise RuntimeError("browser_stopped")
                            self.tick(web)
                        except Exception:
                            raise RuntimeError("resident_browser_recovery")
                        last_tick = time.monotonic()
                    try:
                        client, _ = server.accept()
                    except socket.timeout:
                        continue
                    with client:
                        client.settimeout(130)
                        try:
                            # Linux SO_PEERCRED: reject any other user even if
                            # filesystem ACLs were accidentally loosened.
                            if hasattr(socket, "SO_PEERCRED"):
                                import struct
                                creds = client.getsockopt(
                                    socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                                _, uid, _ = struct.unpack("3i", creds)
                                if uid != os.getuid():
                                    raise ValueError("unauthorized_user")
                            raw = bytearray()
                            while True:
                                part = client.recv(4096)
                                if not part:
                                    break
                                raw.extend(part)
                                if len(raw) > MAX_REQUEST:
                                    raise ValueError("oversize")
                            request = json.loads(raw)
                            if request == {"internal_control": "status"}:
                                result = self.state()
                            elif request == {"internal_control": "stop"}:
                                self.stop = True
                                result = {"status": "stopping"}
                            else:
                                command = owner.validate(request)
                                if command["action"] not in web.ALLOWED:
                                    raise ValueError("unsupported")
                                # Ensure a lost login cannot be mistaken for
                                # a valid preexisting authenticated session.
                                state = web.classify_ui(
                                    self.page.url,
                                    self.page.evaluate(web.UI_STATE_JS))
                                if state != "authorized":
                                    result = {"status": "auth_required"
                                              if state == "auth_required"
                                              else "login_state_unverified"}
                                else:
                                    result = web.execute_on_page(
                                        self.page, command)
                                    if command["action"] == "web_status":
                                        result["resident"] = True
                                        result["monitor"] = self.snapshot
                        except Exception:
                            result = {"status": "resident_command_rejected_or_failed"}
                        try:
                            data = json.dumps(
                                result, ensure_ascii=False,
                                separators=(",", ":")).encode()
                            client.sendall(data[:MAX_REPLY])
                        except Exception:
                            pass
            finally:
                try: SOCKET.unlink(missing_ok=True)
                except OSError: pass

    def run(self):
        safe_runtime()
        if LOCK.is_symlink():
            raise RuntimeError("unsafe_lock")
        fd = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        import telegram_web_encrypted_operator as web
        import telegram_web_owner_portal as portal
        import telegram_web_session_check as checker
        import telegram_owner_operator as owner
        with os.fdopen(fd, "r+") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 2
            if not checker.profile_safe(portal.PROFILE):
                return 3
            try:
                if not portal.load_private_browser_proxy():
                    return 4
            except Exception:
                return 4
            signal.signal(signal.SIGTERM, self.handle_signal)
            signal.signal(signal.SIGINT, self.handle_signal)
            backoff = 3
            while not self.stop:
                self.browser = portal.Browser()
                try:
                    with tempfile.TemporaryDirectory(
                            prefix="tg-resident-", dir=ROOT) as tmp:
                        self.browser.open(Path(tmp))
                        self.page = self.browser.page
                        self.tick(web)
                        self.serve_socket(web, owner)
                    backoff = 3
                except Exception:
                    # No exception, stack trace, contact IDs, or browser
                    # messages are written to public logs.
                    self.authorized = False
                    self.last_check_at = dt.datetime.now(
                        dt.timezone.utc).isoformat()
                    try: write_private_state(self.state())
                    except Exception: pass
                finally:
                    try: self.browser.close()
                    except Exception: pass
                    self.browser = None
                    self.page = None
                    try: SOCKET.unlink(missing_ok=True)
                    except OSError: pass
                if not self.stop:
                    time.sleep(backoff)
                    backoff = min(60, backoff * 2)
        return 0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["serve", "status", "stop"])
    args = parser.parse_args()
    if args.action in {"status", "stop"}:
        name = "status" if args.action == "status" else "stop"
        print(json.dumps(request_socket({"internal_control": name}),
                         separators=(",", ":")))
        return
    try:
        rc = Agent().run()
        sys.exit(rc)
    except Exception:
        # Caller gets only a stable exit status; never private data.
        sys.exit(1)

if __name__ == "__main__":
    main()
