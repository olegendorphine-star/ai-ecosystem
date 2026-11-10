#!/usr/bin/env python3
"""Owner-authorized FL003 demo: send exactly two harmless test markers to own Saved Messages.

No arbitrary contacts/phones, no external recipients, no private message export.
Uses the existing owner-resident Telegram bridge and its durable at-most-once
ledger. Test markers trigger only FL003 task engine routines.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from fl003_task_engine import _telegram_socket_call, ROOT, safe_dir

TESTS=("FL003: ПИСЬМО ТЕСТ", "FL003: ТОВАР M185")
ONCE=ROOT/"state"/"telegram_selftest_once.json"

def run():
    safe_dir(ONCE.parent)
    if ONCE.is_symlink():raise ValueError("unsafe_once_symlink")
    if ONCE.exists():
        return {"schema":"fl003.telegram.selftest.v1","status":"already_attempted_no_resend"}
    outcomes=[]
    for body in TESTS:
        try:
            response=_telegram_socket_call({"action":"web_self_note","params":{
                "text":body,"approved_by_owner":True}})
            status=response.get("status","invalid_result")
        except Exception:
            status="resident_unavailable"
        outcomes.append({"kind":"mail" if "ПИСЬМО" in body else "shop","status":status})
    # Always mark after attempting: ambiguous sends must never be repeated blindly.
    fd=__import__("os").open(ONCE,__import__("os").O_CREAT|__import__("os").O_EXCL|__import__("os").O_WRONLY,0o600)
    with __import__("os").fdopen(fd,"w",encoding="utf-8") as f:
        json.dump(outcomes,f,ensure_ascii=False)
    return {"schema":"fl003.telegram.selftest.v1","status":"attempts_recorded","results":outcomes}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--run-once",action="store_true")
    a=p.parse_args()
    if not a.run_once:
        assert len(TESTS)==2 and all(len(x)<=300 for x in TESTS)
        print(json.dumps({"schema":"fl003.telegram.selftest.v1","offline_verified":True}))
        sys.exit(0)
    print(json.dumps(run(),ensure_ascii=False))
