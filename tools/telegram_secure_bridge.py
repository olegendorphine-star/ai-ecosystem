#!/usr/bin/env python3
"""End-to-end encrypted Telegram command bridge for a PUBLIC GitHub issue.

Issue comments contain ONLY ciphertext. The VPS decrypts; the assistant uses
per-command ephemeral keys to decrypt private results.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

try:
    from telegram_owner_operator import Rejected, ROOT, private_dir, run_command, validate
except ModuleNotFoundError:
    from tools.telegram_owner_operator import Rejected, ROOT, private_dir, run_command, validate

KEY_PATH = ROOT / "private" / "bridge_x25519.pem"
SCHEMA = "tg.bridge.encrypted.v1"
PREFIX = "TG_BRIDGE_COMMAND_V1 "
RESULT_PREFIX = "TG_BRIDGE_RESULT_V1 "


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64(value: str) -> bytes:
    if not isinstance(value, str) or len(value) > 100000:
        raise Rejected("invalid envelope")
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def derive(shared: bytes, purpose: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32,
                salt=None, info=purpose).derive(shared)


def generate_private_key(path: Path = KEY_PATH) -> str:
    private_dir(path.parent)
    private = x25519.X25519PrivateKey.generate()
    data = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()
    )
    # Fail closed if a server private key already exists.
    with path.open("xb") as f:
        f.write(data)
    os.chmod(path, 0o600)
    return b64(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ))


def load_key(path: Path):
    if path.stat().st_mode & 0o077:
        raise Rejected("private key permissions unsafe")
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def encrypt_request(command: dict, server_public: str,
                    ephemeral_path: Path) -> dict:
    validate(command)
    server = x25519.X25519PublicKey.from_public_bytes(unb64(server_public))
    key = x25519.X25519PrivateKey.generate()
    private_dir(ephemeral_path.parent)
    with ephemeral_path.open("xb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()
        ))
    os.chmod(ephemeral_path, 0o600)
    shared = key.exchange(server)
    nonce = os.urandom(12)
    ciphertext = AESGCM(derive(shared, b"tg-bridge-request-v1")).encrypt(
        nonce, json.dumps(command, ensure_ascii=False,
                          separators=(",", ":")).encode(), SCHEMA.encode()
    )
    return {"schema": SCHEMA,
            "sender_pub": b64(key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw)),
            "nonce": b64(nonce), "ciphertext": b64(ciphertext)}


def decrypt_request(envelope: dict, private_key) -> tuple[dict, bytes]:
    if (not isinstance(envelope, dict) or
        set(envelope) != {"schema", "sender_pub", "nonce", "ciphertext"} or
        envelope["schema"] != SCHEMA):
        raise Rejected("invalid request envelope")
    public = x25519.X25519PublicKey.from_public_bytes(unb64(envelope["sender_pub"]))
    nonce, ciphertext = unb64(envelope["nonce"]), unb64(envelope["ciphertext"])
    if len(nonce) != 12 or len(ciphertext) > 65536:
        raise Rejected("unsafe envelope length")
    shared = private_key.exchange(public)
    raw = AESGCM(derive(shared, b"tg-bridge-request-v1")).decrypt(
        nonce, ciphertext, SCHEMA.encode()
    )
    return validate(json.loads(raw)), shared


def encrypt_result(result: dict, shared: bytes, sender_pub: str) -> dict:
    nonce = os.urandom(12)
    ciphertext = AESGCM(derive(shared, b"tg-bridge-result-v1")).encrypt(
        nonce, json.dumps(result, ensure_ascii=False,
                          separators=(",", ":")).encode(), SCHEMA.encode()
    )
    return {"schema": SCHEMA, "sender_pub": sender_pub,
            "nonce": b64(nonce), "ciphertext": b64(ciphertext)}


def decrypt_result(envelope: dict, private_key, server_public: str) -> dict:
    if (not isinstance(envelope, dict) or
        set(envelope) != {"schema", "sender_pub", "nonce", "ciphertext"} or
        envelope["schema"] != SCHEMA):
        raise Rejected("invalid result envelope")
    expected = b64(private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ))
    if envelope["sender_pub"] != expected:
        raise Rejected("response is not for this command key")
    server = x25519.X25519PublicKey.from_public_bytes(unb64(server_public))
    shared = private_key.exchange(server)
    raw = AESGCM(derive(shared, b"tg-bridge-result-v1")).decrypt(
        unb64(envelope["nonce"]), unb64(envelope["ciphertext"]), SCHEMA.encode()
    )
    return json.loads(raw)


async def handle_envelope(envelope: dict, private_key,
                          dispatcher=run_command) -> dict:
    command, shared = decrypt_request(envelope, private_key)
    try:
        result = await dispatcher(command)
    except Rejected:
        result = {"status": "command_rejected"}
    except Exception:
        # Never expose exception text containing names, IDs or private messages.
        result = {"status": "runtime_error"}
    result["command_id"] = command["command_id"]
    return encrypt_result(result, shared, envelope["sender_pub"])


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("action",
                        choices=["init-key", "public-key", "encode", "execute", "decode"])
    parser.add_argument("--key", type=Path, default=KEY_PATH)
    parser.add_argument("--server-public", help="Base64 public X25519 key from VPS")
    parser.add_argument("--state", type=Path, help="Private ephemeral response key path")
    args = parser.parse_args()
    if args.action == "init-key":
        print(generate_private_key(args.key))
        return
    if args.action == "public-key":
        key = load_key(args.key)
        print(b64(key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )))
        return
    if args.action == "encode":
        if not args.server_public or not args.state:
            parser.error("encode requires --server-public and --state")
        request = encrypt_request(json.load(sys.stdin),
                                  args.server_public, args.state)
        print(PREFIX + json.dumps(request, separators=(",", ":")))
        return
    if args.action == "execute":
        raw = sys.stdin.read(100000)
        if not raw.startswith(PREFIX):
            raise Rejected("wrong command prefix")
        result = asyncio.run(handle_envelope(
            json.loads(raw[len(PREFIX):]), load_key(args.key)
        ))
        print(RESULT_PREFIX + json.dumps(result, separators=(",", ":")))
        return
    if args.action == "decode":
        if not args.server_public or not args.state:
            parser.error("decode requires --server-public and --state")
        key = load_key(args.state)
        raw = sys.stdin.read(100000)
        if not raw.startswith(RESULT_PREFIX):
            raise Rejected("wrong result prefix")
        result = decrypt_result(
            json.loads(raw[len(RESULT_PREFIX):]), key, args.server_public
        )
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        cli()
    except Exception:
        # Never expose commands, private keys or private messages to CI logs.
        print("TG_BRIDGE_ERROR")
        sys.exit(1)
