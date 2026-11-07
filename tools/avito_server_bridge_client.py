#!/usr/bin/env python3
from __future__ import annotations
import argparse, base64, json, os, re, shlex, subprocess, sys
ALLOWED_ACTIONS=frozenset({"health","browser_health","connect_status"})
DEFAULT_REMOTE_WORKER="avito-agent/avito_server_worker.py"
HOST_RE=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
USER_RE=re.compile(r"^[A-Za-z_][A-Za-z0-9._-]{0,63}$")
PATH_RE=re.compile(r"^avito-agent/[A-Za-z0-9._/-]+$")
def required(name):
 v=os.environ.get(name,"")
 if not v: raise SystemExit(f"missing environment variable: {name}")
 return v
def build_command(action, remote_cmd=None, debug=False):
 host,user=required("AVITO_SERVER_HOST"),required("AVITO_SERVER_USER")
 port=os.environ.get("AVITO_SERVER_SSH_PORT") or "22"
 if not port.isdigit() or not 1 <= int(port) <= 65535: raise SystemExit("invalid server port")
 key_file=os.path.expandvars(os.path.expanduser(required("AVITO_SERVER_SSH_KEY_FILE")))
 known_hosts=os.path.expandvars(os.path.expanduser(required("AVITO_SERVER_KNOWN_HOSTS_FILE")))
 if not os.path.isfile(key_file): raise FileNotFoundError("local_key_missing")
 if not os.path.isfile(known_hosts): raise FileNotFoundError("local_known_hosts_missing")
 if not HOST_RE.fullmatch(host) or not USER_RE.fullmatch(user): raise SystemExit("invalid server target")
 if action not in ALLOWED_ACTIONS: raise SystemExit("unsupported action")
 if remote_cmd is None:
  remote_cmd="python3 - --action "+shlex.quote(action)+" --json"
 command=["ssh","-F","/dev/null","-4","-T","-o","BatchMode=yes","-o","ConnectTimeout=15","-o","ConnectionAttempts=1","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={known_hosts}","-o","IdentitiesOnly=yes","-i",key_file,"-p",port,f"{user}@{host}",remote_cmd]
 if debug: command.insert(1,"-vvv")
 return command
def error_kind(stderr, returncode=None):
 if isinstance(stderr, bytes): stderr=stderr.decode("utf-8", "replace")
 s=(stderr or "").lower()
 if "identity file" in s and ("type -1" in s or "not accessible" in s or "no such file" in s): return "identity_file_missing"
 if "host key verification failed" in s or "offending" in s: return "hostkey_mismatch"
 if "permission denied" in s or "error in libcrypto" in s or "publickey" in s: return "auth_failed"
 if "connection refused" in s: return "connection_refused"
 if "connection timed out" in s: return "connection_timeout"
 if "connection reset" in s: return "connection_reset"
 if "host key verification failed" in s: return "host_key_failed"
 if "could not resolve" in s or "name or service not known" in s: return "dns_failed"
 if "connection closed" in s or "connection reset" in s: return "connection_closed"
 if "connection timed out" in s or "unreachable" in s: return "network_failed"
 if "base64" in s: return "remote_base64_failed"
 if "traceback" in s or "syntaxerror" in s or "stdin" in s: return "remote_worker_failed"
 if "no such file" in s or "can't open file" in s: return "remote_dependency_missing"
 if returncode is not None: return f"ssh_failed_rc_{returncode}"
 return "ssh_failed"
def failure(action, result, returncode=None):
 payload={"ok":False,"action":action,"result":result}
 if returncode is not None: payload["ssh_returncode"]=returncode
 print(json.dumps(payload,ensure_ascii=False,sort_keys=True))
def main():
 p=argparse.ArgumentParser(); p.add_argument("--action",required=True,choices=sorted(ALLOWED_ACTIONS)); p.add_argument("--dry-run",action="store_true"); a=p.parse_args()
 try: cmd=build_command(a.action)
 except FileNotFoundError as exc: failure(a.action,str(exc)); return 1
 if a.dry_run: print(json.dumps({"ok":True,"action":a.action,"mode":"dry_run"})); return 0
 preflight_cmd=build_command(a.action, "printf SSH_OK", debug=True)
 try:
  preflight=subprocess.run(preflight_cmd,capture_output=True,text=False,timeout=20)
 except subprocess.TimeoutExpired:
  failure(a.action,"ssh_preflight_timeout"); return 1
 if preflight.returncode or preflight.stdout.strip()!=b"SSH_OK":
  failure(a.action,"ssh_preflight_"+error_kind(preflight.stderr,preflight.returncode),preflight.returncode); return 1
 try:
  worker_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "avito_server_worker.py")
  with open(worker_path, "rb") as worker_file:
   worker_bytes=worker_file.read()
 except OSError:
  failure(a.action,"local_worker_missing"); return 1
 try:
  done=subprocess.run(cmd,input=worker_bytes,capture_output=True,text=False,timeout=45)
 except subprocess.TimeoutExpired:
  failure(a.action,"ssh_timeout"); return 1
 if done.returncode:
  failure(a.action,error_kind(done.stderr,done.returncode),done.returncode); return 1
 try: result=json.loads(done.stdout.decode("utf-8"))
 except json.JSONDecodeError: print(json.dumps({"ok":False,"action":a.action,"result":"invalid_worker_response"})); return 1
 if not isinstance(result,dict) or result.get("action")!=a.action: print(json.dumps({"ok":False,"action":a.action,"result":"unexpected_worker_response"})); return 1
 print(json.dumps(result,ensure_ascii=False,sort_keys=True)); return 0
if __name__=="__main__": sys.exit(main())
