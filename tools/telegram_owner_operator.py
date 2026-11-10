#!/usr/bin/env python3
"""Private Telegram user-account adapter. Never store sessions or messages in Git.

The public GitHub repository contains code only. All Telegram API authorization,
conversation content and SQLite replay state stay on the owner's VPS.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path.home() / ".telegram-agent"
SESSION = ROOT / "auth" / "owner"
LEDGER = ROOT / "state" / "outbound.sqlite3"
ALLOWED = frozenset({"status", "dialogs", "read", "reply",
                     "web_status", "web_dialogs", "web_read", "web_self_read", "web_reply",
                     "web_self_note", "web_phone_message", "web_username_message",
                     "web_chat_message", "web_owner_contact_link", "web_username_read"})
MAX_TEXT = 3500


class Rejected(ValueError):
    """Unsafe or unsupported owner command."""


def private_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (path.stat().st_mode & 0o077):
        raise Rejected("private directory has unsafe permissions")


def validate(command: dict) -> dict:
    if not isinstance(command, dict) or set(command) != {
        "schema", "command_id", "action", "issued_at", "expires_at", "params"
    }:
        raise Rejected("invalid command fields")
    if command["schema"] != "tg.owner.command.v1" or command["action"] not in ALLOWED:
        raise Rejected("unsupported action")
    try:
        if str(uuid.UUID(command["command_id"])) != command["command_id"]:
            raise ValueError
        issued = dt.datetime.fromisoformat(command["issued_at"].replace("Z", "+00:00"))
        expiry = dt.datetime.fromisoformat(command["expires_at"].replace("Z", "+00:00"))
        if issued.utcoffset() is None or expiry.utcoffset() is None:
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise Rejected("invalid UUID or timestamps") from exc
    now = dt.datetime.now(dt.timezone.utc)
    if not (issued <= now + dt.timedelta(seconds=30) and
            now <= expiry and
            0 < (expiry-issued).total_seconds() <= 600):
        raise Rejected("command expired or lifetime too long")
    params = command["params"]
    action = command["action"]
    if not isinstance(params, dict):
        raise Rejected("params must be an object")
    allowed_fields = {
        "status": set(), "dialogs": {"limit"},
        "read": {"chat_id", "limit"},
        "reply": {"chat_id", "reply_to_id", "text", "approved_by_owner"},
        "web_status": set(), "web_dialogs": {"limit"},
        "web_read": {"peer_id", "limit"},
        "web_self_read": {"limit"},
        "web_username_read": {"username", "limit"},
        "web_reply": {"peer_id", "reply_to_id", "text", "approved_by_owner"},
        "web_self_note": {"text", "approved_by_owner"},
        "web_phone_message": {"phone", "text", "approved_by_owner"},
        "web_username_message": {"username", "text", "approved_by_owner"},
        "web_chat_message": {"peer_id", "text", "approved_by_owner"},
        "web_owner_contact_link": set(),
    }[action]
    if not set(params).issubset(allowed_fields):
        raise Rejected("unexpected params")
    if action in {"dialogs", "web_dialogs"}:
        cap = 30 if action == "dialogs" else 20
        if type(params.get("limit", 10)) is not int or not 1 <= params.get("limit", 10) <= cap:
            raise Rejected("invalid dialog limit")
    if action in {"read", "reply"}:
        if (type(params.get("chat_id")) is not int or
            not -(2**63) < params["chat_id"] < 2**63 or
            params["chat_id"] == 0):
            raise Rejected("invalid chat id")
    if action in {"read", "web_read", "web_username_read", "web_self_read"}:
        cap = 20 if action == "read" else 12
        if type(params.get("limit", 10)) is not int or not 1 <= params.get("limit", 10) <= cap:
            raise Rejected("invalid message limit")
    if action in {"web_read", "web_reply", "web_chat_message"}:
        peer_id = params.get("peer_id")
        if type(peer_id) is not int or not -(2**53) < peer_id < 2**53 or peer_id == 0:
            raise Rejected("invalid web peer id")
    if action == "web_username_read":
        username = params.get("username")
        if (type(username) is not str or
                not __import__("re").fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{4,31}", username)):
            raise Rejected("read requires one exact public username")
    if action == "web_phone_message":
        phone, msg = params.get("phone"), params.get("text")
        if (type(phone) is not str or
            not __import__("re").fullmatch(r"\+[1-9][0-9]{7,14}", phone) or
            type(msg) is not str or not 1 <= len(msg.strip()) <= 300 or
            params.get("approved_by_owner") is not True):
            raise Rejected("direct phone message requires approved text and E.164 number")
    if action == "web_chat_message":
        msg = params.get("text")
        if (type(params.get("peer_id")) is not int or params["peer_id"] <= 0 or
            type(msg) is not str or not 1 <= len(msg.strip()) <= 1200 or
            params.get("approved_by_owner") is not True):
            raise Rejected("existing private chat send requires exact user peer and approved text")
    if action == "web_username_message":
        username, msg = params.get("username"), params.get("text")
        if (type(username) is not str or
            not __import__("re").fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{4,31}", username)
            or type(msg) is not str or not 1 <= len(msg.strip()) <= 1200
            or params.get("approved_by_owner") is not True):
            raise Rejected("username send requires exact public username and approved text")
    if action == "web_self_note":
        msg = params.get("text")
        if type(msg) is not str or not 1 <= len(msg.strip()) <= 300 or params.get("approved_by_owner") is not True:
            raise Rejected("owner approval and 1-300 character text required for Saved Messages")
    if action == "web_reply":
        mid = params.get("reply_to_id")
        text = params.get("text")
        if (type(mid) is not int or not 0 < mid < 2**53
            or type(text) is not str or not 1 <= len(text.strip()) <= 2000
            or params.get("approved_by_owner") is not True):
            raise Rejected("web reply requires exact inbound message and explicit owner approval")
    if action == "reply":
        if (type(params.get("reply_to_id")) is not int or params["reply_to_id"] <= 0 or
            not isinstance(params.get("text"), str) or
            not 1 <= len(params["text"].strip()) <= MAX_TEXT or
            params.get("approved_by_owner") is not True):
            raise Rejected("reply requires owner approval, existing inbound message and valid text")
    return command


class Ledger:
    def __init__(self, path: Path = LEDGER):
        private_dir(path.parent)
        self.path = path
        self.connection = sqlite3.connect(path, timeout=10)
        self.connection.execute("PRAGMA busy_timeout=10000")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS outgoing ("
            "command_id TEXT PRIMARY KEY, digest TEXT NOT NULL, "
            "random_id INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0)"
        )
        self.connection.commit()
        os.chmod(path, 0o600)

    def prepare(self, command: dict) -> tuple[int, bool]:
        digest = hashlib.sha256(
            json.dumps(command, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute(
                "SELECT digest,random_id,done FROM outgoing WHERE command_id=?",
                (command["command_id"],)
            ).fetchone()
            if row:
                if row[0] != digest:
                    raise Rejected("command id reused for different payload")
                value = (row[1], bool(row[2]))
            else:
                random_id = secrets.randbits(63) or 1
                self.connection.execute(
                    "INSERT INTO outgoing(command_id,digest,random_id,done) VALUES (?,?,?,0)",
                    (command["command_id"], digest, random_id)
                )
                value = (random_id, False)
            self.connection.commit()
            return value
        except Exception:
            self.connection.rollback()
            raise

    def completed(self, command_id: str):
        self.connection.execute(
            "UPDATE outgoing SET done=1 WHERE command_id=?", (command_id,)
        )
        self.connection.commit()

    def close(self):
        self.connection.close()


async def execute(command: dict, backend, ledger: Ledger | None = None) -> dict:
    validate(command)
    action, p = command["action"], command["params"]
    if not await backend.authorized():
        return {"status": "auth_required", "action": action}
    if action == "status":
        return {"status": "authorized", "action": action}
    if action == "dialogs":
        return {"status": "ok", "action": action,
                "dialogs": await backend.dialogs(p.get("limit", 10))}
    if action == "read":
        return {"status": "ok", "action": action,
                "messages": await backend.read(p["chat_id"], p.get("limit", 10))}
    if ledger is None:
        raise Rejected("reply requires durable replay ledger")
    if not await backend.inbound_exists(p["chat_id"], p["reply_to_id"]):
        raise Rejected("reply target must be an existing inbound message")
    random_id, done = ledger.prepare(command)
    if done:
        return {"status": "already_sent", "action": action,
                "command_id": command["command_id"]}
    try:
        await backend.send_reply(p["chat_id"], p["reply_to_id"], p["text"], random_id)
    except Exception as exc:
        # Telegram deduplicates the low-level SendMessageRequest random_id on retry.
        if exc.__class__.__name__ != "RandomIdDuplicateError":
            raise
    ledger.completed(command["command_id"])
    return {"status": "sent", "action": action,
            "command_id": command["command_id"]}


class TelethonBackend:
    def __init__(self, client):
        self.client = client

    async def authorized(self):
        return await self.client.is_user_authorized()

    async def dialogs(self, limit: int):
        items = await self.client.get_dialogs(limit=limit)
        return [{"chat_id": int(d.id), "title": (d.name or "")[:120],
                 "unread_count": d.unread_count} for d in items]

    async def read(self, chat_id: int, limit: int):
        # Never mark as read. Content is visible only in encrypted GitHub result.
        peer = await self.client.get_input_entity(chat_id)
        messages = await self.client.get_messages(peer, limit=limit)
        return [{"message_id": m.id, "incoming": not m.out,
                 "text": (m.message or "")[:1200]} for m in messages]

    async def inbound_exists(self, chat_id: int, message_id: int):
        peer = await self.client.get_input_entity(chat_id)
        message = await self.client.get_messages(peer, ids=message_id)
        return bool(message and not message.out and message.id == message_id)

    async def send_reply(self, chat_id: int, reply_to_id: int, text: str, random_id: int):
        from telethon import functions, types
        peer = await self.client.get_input_entity(chat_id)
        await self.client(functions.messages.SendMessageRequest(
            peer=peer, message=text, random_id=random_id,
            reply_to=types.InputReplyToMessage(reply_to_msg_id=reply_to_id),
            no_webpage=True,
        ))


def _run_private_web_adapter(command: dict) -> dict:
    """Never route browser plaintext through CI; subprocess stays entirely VPS."""
    script = ROOT / "browser" / "telegram_web_encrypted_operator.py"
    if not script.is_file() or script.is_symlink():
        return {"status": "web_browser_adapter_not_deployed"}
    try:
        process = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps(command, ensure_ascii=False),
            text=True, capture_output=True, timeout=100,
            check=False,
        )
        if process.returncode or len(process.stdout) > 64000:
            return {"status": "private_web_execution_failed"}
        response = json.loads(process.stdout)
        if not isinstance(response, dict) or not isinstance(response.get("status"), str):
            return {"status": "private_web_result_invalid"}
        return response
    except Exception:
        # Never return browser exception text, private URLs or chat data to logs.
        return {"status": "private_web_execution_failed"}


async def run_command(command: dict) -> dict:
    """Call only on owner's VPS; results returned only via encrypted bridge."""
    validate(command)
    if command["action"].startswith("web_"):
        return await asyncio.to_thread(_run_private_web_adapter, command)
    from telethon import TelegramClient
    app_id = os.environ.get("TELEGRAM_API_ID", "")
    app_hash = os.environ.get("TELEGRAM_API_HASH", "")
    if not app_id.isdecimal() or not app_hash:
        return {"status": "configuration_required"}
    private_dir(ROOT)
    private_dir(SESSION.parent)
    os.umask(0o077)
    client = TelegramClient(str(SESSION), int(app_id), app_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            return {"status": "auth_required"}
        ledger = Ledger() if command["action"] == "reply" else None
        try:
            return await execute(command, TelethonBackend(client), ledger)
        finally:
            if ledger is not None:
                ledger.close()
    finally:
        await client.disconnect()
        session_file = Path(str(SESSION) + ".session")
        if session_file.exists():
            os.chmod(session_file, 0o600)


async def interactive_login():
    """Owner-only local terminal setup, never over a public web form or CI log."""
    from telethon import TelegramClient
    app_id = os.environ.get("TELEGRAM_API_ID", "")
    app_hash = os.environ.get("TELEGRAM_API_HASH", "")
    if not app_id.isdecimal() or not app_hash:
        raise Rejected("set TELEGRAM_API_ID and TELEGRAM_API_HASH privately on the VPS")
    private_dir(ROOT)
    private_dir(SESSION.parent)
    os.umask(0o077)
    client = TelegramClient(str(SESSION), int(app_id), app_hash)
    await client.start()
    try:
        print("TELEGRAM_OWNER_AUTHORIZED" if await client.is_user_authorized()
              else "TELEGRAM_AUTH_REQUIRED")
    finally:
        await client.disconnect()
    os.chmod(str(SESSION) + ".session", 0o600)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", action="store_true",
                        help="Interactive first-time sign-in locally on VPS only")
    args = parser.parse_args()
    if args.login:
        asyncio.run(interactive_login())
    else:
        print("Use telegram_secure_bridge.py execute; plaintext commands are not accepted by CLI.")
