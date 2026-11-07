#!/usr/bin/env python3
"""Policy engine for the Avito/Connect work-search operator.

This first version plans and gates actions. It never sends a message, spends
money, accepts a contract, or bypasses authentication. A browser worker can be
attached after the policy decision is recorded.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ALLOWED_SOURCES = frozenset({"fl", "telegram", "connect", "avito"})
READ_ONLY_STATES = frozenset({"ready", "unknown", "auth_required", "blocked"})


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_task(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("task must be an object")
    required = {"task_id", "source", "order_url", "title", "response_text"}
    missing = sorted(required - set(data))
    if missing:
        raise ValueError("missing fields: " + ",".join(missing))
    if data["source"] not in ALLOWED_SOURCES:
        raise ValueError("unsupported source")
    for key in ("task_id", "source", "order_url", "title", "response_text"):
        if not isinstance(data[key], str) or not data[key].strip():
            raise ValueError(f"invalid {key}")
    return data


def evaluate(task: dict, checked_at: dt.datetime) -> dict:
    paid = bool(task.get("paid", False) or task.get("fee_rub", 0) not in (0, None))
    session = task.get("session_status", "unknown")
    approval = task.get("approval") if isinstance(task.get("approval"), dict) else {}
    text_hash = sha256_text(task["response_text"])
    base = {
        "task_id": task["task_id"],
        "source": task["source"],
        "order_url": task["order_url"],
        "text_sha256": text_hash,
        "checked_at": checked_at.isoformat(timespec="seconds"),
        "paid": paid,
    }
    if paid and approval.get("allow_paid") is not True:
        return {**base, "decision": "blocked_paid", "next_action": "request_owner_approval"}
    if session != "ready":
        return {**base, "decision": "auth_required", "next_action": "restore_session_or_handoff"}
    if approval.get("allow_send") is not True:
        return {**base, "decision": "approval_required", "next_action": "request_send_approval"}
    expiry = approval.get("expires_at")
    if not isinstance(expiry, str):
        return {**base, "decision": "approval_required", "next_action": "add_expiring_approval"}
    try:
        if parse_time(expiry) <= checked_at:
            return {**base, "decision": "approval_expired", "next_action": "request_fresh_approval"}
    except ValueError:
        return {**base, "decision": "approval_required", "next_action": "fix_approval_timestamp"}
    return {**base, "decision": "ready_to_submit", "next_action": "browser_worker_submit"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-file", type=Path, required=True)
    parser.add_argument("--now", help="UTC ISO time for deterministic tests")
    args = parser.parse_args()
    try:
        task = load_task(args.task_file)
        checked_at = parse_time(args.now) if args.now else now_utc()
        result = evaluate(task, checked_at)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"decision": "invalid_task", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
