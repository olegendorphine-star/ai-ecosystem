#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, re, shlex, subprocess, sys
ALLOWED_ACTIONS=frozenset({"health","browser_health","connect_status"})
DEFAULT_REMOTE_WORKER="avito-agent/avito_server_worker.py"
HOST_RE=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
USER_RE=re.compile(r"^[A-Za-z_][A-Za-z0-9._-]{0,63}$")
PATH_RE=re.compile(r"^avito-agent/[A-Za-z0-9._/-]+$")
def required(name):
 v=os.environ.get(name,"")
 if not v: raise SystemExit(f"missing environment variable: {name}")
 return v
def build_command(action):
 host,user=required("AVITO_SERVER_HOST"),required("AVITO_SERVER_USER")
 key_file,known_hosts=required("AVITO_SERVER_SSH_KEY_FILE"),required("AVITO_SERVER_KNOWN_HOSTS_FILE")
 remote_worker=os.environ.get("AVITO_SERVER_WORKER",DEFAULT_REMOTE_WORKER)
 if not HOST_RE.fullmatch(host) or not USER_RE.fullmatch(user): raise SystemExit("invalid server target")
 if action not in ALLOWED_ACTIONS: raise SystemExit("unsupported action")
 if not PATH_RE.fullmatch(remote_worker): raise SystemExit("invalid AVITO_SERVER_WORKER")
 remote_cmd="python3 \"$HOME/"+remote_worker+"\" --action "+shlex.quote(action)+" --json"
 return ["ssh","-T","-BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={known_hosts}","-o","IdentitiesOnly=yes","-i",key_file,f"{user}@{host}","sh","-lc",remote_cmd]
def error_kind(stderr):
 s=(stderr or "").lower()
 if "permission denied" in s or "error in libcrypto" in s: return "ssh_auth_failed"
 if "host key verification failed" in s: return "host_key_failed"
 if "no such file" in s or "can't open file" in s: return "remote_worker_missing"
 if "could not resolve" in s or "name or service not known" in s: return "dns_failed"
 if "connection closed" in s or "connection reset" in s: return "connection_closed"
 if "connection timed out" in s or "unreachable" in s: return "network_failed"
 return "ssh_failed"
def main():
 p=argparse.ArgumentParser(); p.add_argument("--action",required=True,choices=sorted(ALLOWED_ACTIONS)); p.add_argument("--dry-run",action="store_true"); a=p.parse_args(); cmd=build_command(a.action)
 if a.dry_run: print(json.dumps({"ok":True,"action":a.action,"mode":"dry_run"})); return 0
 done=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
 if done.returncode: print(json.dumps({"ok":False,"action":a.action,"result":error_kind(done.stderr)})); return 1
 try: result=json.loads(done.stdout)
 except json.JSONDecodeError: print(json.dumps({"ok":False,"action":a.action,"result":"invalid_worker_response"})); return 1
 if not isinstance(result,dict) or result.get("action")!=a.action: print(json.dumps({"ok":False,"action":a.action,"result":"unexpected_worker_response"})); return 1
 print(json.dumps(result,ensure_ascii=False,sort_keys=True)); return 0
if __name__=="__main__": sys.exit(main())
