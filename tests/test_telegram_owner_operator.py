import asyncio
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import telegram_owner_operator as op
import telegram_secure_bridge as bridge


def command(action="status", params=None):
    now = dt.datetime.now(dt.timezone.utc)
    return {
        "schema": "tg.owner.command.v1", "command_id": str(uuid.uuid4()),
        "action": action, "issued_at": now.isoformat(),
        "expires_at": (now + dt.timedelta(minutes=5)).isoformat(),
        "params": params or {},
    }


class FakeBackend:
    def __init__(self, authorized=True, inbound=True):
        self.auth = authorized
        self.inbound = inbound
        self.calls = []

    async def authorized(self):
        return self.auth

    async def dialogs(self, limit):
        return [{"chat_id": 12, "title": "Private demo",
                 "unread_count": 1}][:limit]

    async def read(self, chat, limit):
        return [{"message_id": 99, "incoming": True, "text": "hello"}]

    async def inbound_exists(self, chat, msg):
        return self.inbound and chat == 12 and msg == 99

    async def send_reply(self, chat, msg, text, random_id):
        self.calls.append((chat, msg, text, random_id))


class TestCommands(unittest.TestCase):
    def test_status(self):
        self.assertEqual(op.validate(command())["action"], "status")

    def test_wrong_param_rejected(self):
        with self.assertRaises(op.Rejected):
            op.validate(command("status", {"shell": "whoami"}))

    def test_reply_owner_confirmation_required(self):
        with self.assertRaises(op.Rejected):
            op.validate(command("reply", {
                "chat_id": 12, "reply_to_id": 99, "text": "x"
            }))

    def test_reply_no_unrequested_chat(self):
        with self.assertRaises(op.Rejected):
            op.validate(command("reply", {
                "chat_id": 12, "reply_to_id": 99, "text": "x",
                "approved_by_owner": True, "username": "target"
            }))

    def test_expiration(self):
        c = command()
        c["expires_at"] = (
            dt.datetime.now(dt.timezone.utc) -
            dt.timedelta(seconds=1)
        ).isoformat()
        with self.assertRaises(op.Rejected):
            op.validate(c)

    def test_no_unknown_actions(self):
        c = command()
        c["action"] = "delete_chat"
        with self.assertRaises(op.Rejected):
            op.validate(c)

    def test_auth_required(self):
        r = asyncio.run(op.execute(command(), FakeBackend(authorized=False)))
        self.assertEqual(r["status"], "auth_required")

    def test_read_only(self):
        c = command("read", {"chat_id": 12})
        r = asyncio.run(op.execute(c, FakeBackend()))
        self.assertEqual(r["messages"][0]["text"], "hello")

    def test_not_inbound_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            os.chmod(td, 0o700)
            ledger = op.Ledger(Path(td) / "state.sqlite3")
            try:
                c = command("reply", {
                    "chat_id": 12, "reply_to_id": 99,
                    "text": "ok", "approved_by_owner": True
                })
                with self.assertRaises(op.Rejected):
                    asyncio.run(op.execute(
                        c, FakeBackend(inbound=False), ledger
                    ))
            finally:
                ledger.close()

    def test_idempotent_reply(self):
        with tempfile.TemporaryDirectory() as td:
            os.chmod(td, 0o700)
            ledger = op.Ledger(Path(td) / "state.sqlite3")
            try:
                c = command("reply", {
                    "chat_id": 12, "reply_to_id": 99,
                    "text": "ok", "approved_by_owner": True
                })
                backend = FakeBackend()
                self.assertEqual(
                    asyncio.run(op.execute(c, backend, ledger))["status"],
                    "sent"
                )
                self.assertEqual(
                    asyncio.run(op.execute(c, backend, ledger))["status"],
                    "already_sent"
                )
                self.assertEqual(len(backend.calls), 1)
                self.assertTrue(0 < backend.calls[0][-1] < 2**63)
            finally:
                ledger.close()

    def test_conflicting_replay_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            os.chmod(td, 0o700)
            ledger = op.Ledger(Path(td) / "l.sqlite3")
            try:
                c = command("reply", {
                    "chat_id": 12, "reply_to_id": 99,
                    "text": "ok", "approved_by_owner": True
                })
                ledger.prepare(c)
                c["params"]["text"] = "different"
                with self.assertRaises(op.Rejected):
                    ledger.prepare(c)
            finally:
                ledger.close()


class TestEncryptedTransport(unittest.TestCase):
    def test_round_trip_private_content(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            os.chmod(path, 0o700)
            server_private = path / "server.pem"
            server_public = bridge.generate_private_key(server_private)
            state = path / "response.pem"
            original = command("read", {"chat_id": -777, "limit": 3})
            envelope = bridge.encrypt_request(original, server_public, state)
            self.assertNotIn("-777", json.dumps(envelope))
            payload, shared = bridge.decrypt_request(
                envelope, bridge.load_key(server_private)
            )
            self.assertEqual(payload, original)
            encrypted = bridge.encrypt_result(
                {"status": "ok", "private_text": "hello client"},
                shared, envelope["sender_pub"]
            )
            self.assertNotIn("hello client", json.dumps(encrypted))
            decoded = bridge.decrypt_result(
                encrypted, bridge.load_key(state), server_public
            )
            self.assertEqual(decoded["private_text"], "hello client")

    def test_ciphertext_tampering_fails(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            os.chmod(path, 0o700)
            server_private = path / "server.pem"
            public = bridge.generate_private_key(server_private)
            env = bridge.encrypt_request(
                command(), public, path / "ephemeral.pem"
            )
            env["ciphertext"] = "AAAA" + env["ciphertext"][4:]
            with self.assertRaises(Exception):
                bridge.decrypt_request(
                    env, bridge.load_key(server_private)
                )

    def test_private_key_rejects_world_readable(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            os.chmod(path, 0o700)
            key = path / "server.pem"
            bridge.generate_private_key(key)
            os.chmod(key, 0o644)
            with self.assertRaises(op.Rejected):
                bridge.load_key(key)

    def test_wrong_reply_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            os.chmod(path, 0o700)
            private = path / "server.pem"
            public = bridge.generate_private_key(private)
            a = bridge.encrypt_request(
                command(), public, path / "a.pem"
            )
            bridge.encrypt_request(command(), public, path / "b.pem")
            _, shared = bridge.decrypt_request(
                a, bridge.load_key(private)
            )
            result = bridge.encrypt_result(
                {"status": "ok"}, shared, a["sender_pub"]
            )
            with self.assertRaises(op.Rejected):
                bridge.decrypt_result(
                    result, bridge.load_key(path / "b.pem"), public
                )

    def test_execute_encrypted_without_live_telegram(self):
        async def fake(cmd):
            return {"status": "authorized"}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            os.chmod(path, 0o700)
            private = path / "server.pem"
            public = bridge.generate_private_key(private)
            c = command()
            envelope = bridge.encrypt_request(
                c, public, path / "e.pem"
            )
            result = asyncio.run(bridge.handle_envelope(
                envelope, bridge.load_key(private), fake
            ))
            decoded = bridge.decrypt_result(
                result, bridge.load_key(path / "e.pem"), public
            )
            self.assertEqual(decoded["command_id"], c["command_id"])
            self.assertEqual(decoded["status"], "authorized")


if __name__ == "__main__":
    unittest.main()
