#!/usr/bin/env python3
"""Safe client for the dedicated Avito server bridge."""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys
ALLOWED_ACTIONS = frozenset({"health", "browser_health", "connect_status"})
DEFAULT_REMOTE_WORKER = "avito-agent/avito_server_worker.py"
HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9._-]{0,63}$")
PATH_RE = re.compile(r"^avito-agent/[A-Za-z0-9._/-]+$")
def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value: raise SystemExit(f"missing environment variable: {name}")
    return value
def build_command(action: str) -> list[str]:
    host, user = required("AVITO_SERVER_HOST"), required("AVITO_SERVER_USER")
    key_file, known_hosts = required("AVITO_SERVER_SSH_KEY_FILE"), required("AVITO_SERVER_KNOWN_HOSTS_FILE")
    remote_worker = os.environ.get("AVITO_SERVER_WORKER", DEFAULT_REMOTE_WORKER)
    if not HOST_RE.fullmatch(host) or not USER_RE.fullmatch(user): raise SystemExit("invalid server target")
    if action not in ALLOWED_ACTIONS: raise SystemExit("unsupported action")
    if not PATH_RE.fullmatch(remote_worker): raise SystemExit("invalid AVITO_SERVER_WORKER")
    return ["ssh", "-BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known_hosts}", "-o", "IdentitiesOnly=yes", "-i", key_file, f"{user}@{host}", "python3", remote_worker, "--action", action, "--json"]
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--action", required=True, choices=sorted(ALLOWED_ACTIONS)); parser.add_argument("--dry-run", action="store_true"); args=parser.parse_args()
    command=build_command(args.action)
    if args.dry_run: print(json.dumps({"ok":True,"action":args.action,"mode":"dry_run"})); return 0
    completed=subprocess.run(command,capture_output=True,text=True,timeout=45)
    if completed.returncode: print(json.dumps({"ok":False,"action":args.action,"result":"ssh_failed"})); return 1
    try: result=json.loads(completed.stdout)
    except json.JSONDecodeError: print(json.dumps({"ok":False,"action":args.action,"result":"invalid_worker_response"})); return 1
    if not isinstance(result,dict) or result.get("action")!=args.action: print(json.dumps({"ok":False,"action":args.action,"result":"unexpected_worker_response"})); return 1
    print(json.dumps(result,ensure_ascii=False,sort_keys=True)); return 0
if __name__ == "__main__": sys.exit(main())
