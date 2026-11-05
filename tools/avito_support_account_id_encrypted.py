#!/usr/bin/env python3
"""Encrypted one-time read of own Avito account ID for support ticket 79397429.

Only OAuth POST and GET /core/v1/accounts/self. Plaintext profile ID is
never logged or written to repo; OpenSSL OAEP ciphertext is safe to publish.
"""
from __future__ import annotations
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API = "https://api.avito.ru"
PUBLIC_KEY = Path(__file__).with_name("avito_support_account_public_key.pem")
MAX_BODY = 100_000
OPT_IN = "AVITO_ALLOW_SUPPORT_ID_READONLY"


def identify(obj: Any) -> str | None:
    """Own account ID, not an item ID, from verified accounts/self."""
    if not isinstance(obj, dict):
        return None
    value = obj.get("id")
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{3,17}", value):
        return None
    return value


def call(path: str, token: str | None = None, data: bytes | None = None) -> tuple[int | None, Any]:
    if path not in ("/token/", "/core/v1/accounts/self"):
        raise ValueError("unsupported endpoint")
    if (data is None) == (path == "/token/"):
        raise ValueError("unsupported method")
    headers = {"Accept": "application/json", "User-Agent": "AvitoSupportOwnAccountId/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(API + path, method="POST" if data is not None else "GET",
                                 headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read(MAX_BODY + 1)
            status = r.status
        if len(raw) > MAX_BODY:
            return status, None
        try:
            return status, json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError):
            return status, None
    except urllib.error.HTTPError as e:
        return e.code, None
    except (OSError, urllib.error.URLError, TimeoutError):
        return None, None


def encrypt_numeric_id(identifier: str, public_key: Path = PUBLIC_KEY) -> str:
    if not re.fullmatch(r"[1-9][0-9]{3,17}", identifier):
        raise ValueError("invalid identifier")
    command = ["openssl", "pkeyutl", "-encrypt", "-pubin", "-inkey", str(public_key),
               "-pkeyopt", "rsa_padding_mode:oaep",
               "-pkeyopt", "rsa_oaep_md:sha256"]
    result = subprocess.run(command, input=identifier.encode("ascii"),
                            capture_output=True, check=False, timeout=15)
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError("encryption unavailable")
    return base64.b64encode(result.stdout).decode("ascii")


def inspect() -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema": "avito.support.own-profile-id.encrypted.v1",
        "ticket": "79397429",
        "source": "GET /core/v1/accounts/self",
        "read_only": True, "messages_read": 0,
        "ads_changed": 0, "charges_rub": 0,
        "plaintext_logged": False, "plaintext_stored": False,
    }
    cid, secret = os.environ.get("AVITO_CLIENT_ID"), os.environ.get("AVITO_CLIENT_SECRET")
    if not cid or not secret:
        out["status"] = "missing_credentials"
        return out
    form = urllib.parse.urlencode({"grant_type": "client_credentials",
                                   "client_id": cid, "client_secret": secret}).encode()
    auth_status, auth_data = call("/token/", data=form)
    out["oauth_http"] = auth_status
    token = auth_data.get("access_token") if isinstance(auth_data, dict) else None
    if auth_status != 200 or not isinstance(token, str) or not token:
        out["status"] = "auth_unavailable"
        return out
    status, data = call("/core/v1/accounts/self", token=token)
    out["profile_http"] = status
    if status != 200:
        out["status"] = "account_api_unavailable"
        return out
    identifier = identify(data)
    if identifier is None:
        out["status"] = "id_missing_or_unexpected"
        return out
    try:
        out["encrypted_id"] = encrypt_numeric_id(identifier)
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        out["status"] = "encryption_failed"
        return out
    out["algorithm"] = "RSA-OAEP-SHA256"
    out["status"] = "encrypted_id_ready"
    return out


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) != 2 or argv[0] != "--live" or os.environ.get(OPT_IN) != "YES":
        print("LIVE_BLOCKED_OR_BAD_ARGS", file=sys.stderr)
        return 2
    out = inspect()
    path = Path(argv[1])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ACCOUNT_ID_RESULT", out.get("status"))
    print("PLAINTEXT_LOGGED", out["plaintext_logged"])
    return 0 if out.get("status") == "encrypted_id_ready" else 4


if __name__ == "__main__":
    sys.exit(main())
