#!/usr/bin/env python3
"""Read-only Docker/Podman/rootless runtime diagnostic. No credentials or socket details."""
import json
import os
import shutil
import subprocess
from pathlib import Path


def command(argv, timeout=7):
    try:
        p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         text=True,timeout=timeout,check=False)
        return p.returncode,(p.stdout+p.stderr).lower()
    except (OSError,subprocess.TimeoutExpired):
        return -1,"unavailable"


def docker_failure_kind(message):
    if "permission denied" in message: return "socket_permission_denied"
    if "cannot connect to the docker daemon" in message or "is the docker daemon running" in message:
        return "daemon_unreachable"
    if "context" in message and "does not exist" in message:return "context_missing"
    if "command not found" in message:return "cli_missing"
    if "not found" in message:return "other_not_found"
    if "unavailable" in message:return "unavailable"
    return "other_failure"




def _sudo_check(argv):
    return command(["sudo", "-n"] + argv, timeout=8)[0] == 0

def inspect():
    result={"schema":"ai.steel.vps.runtime.v1","read_only":True,"docker":{},"podman":{},
            "rootless":{},"privilege":{}}
    rc,txt=command(["docker","info","--format","{{.ServerVersion}}"])
    result["docker"]={
        "client_present":shutil.which("docker") is not None,
        "engine_available":rc==0,
        "failure_reason":None if rc==0 else docker_failure_kind(txt),
        "socket_exists":Path("/var/run/docker.sock").exists(),
        "socket_rw":os.access("/var/run/docker.sock",os.R_OK|os.W_OK),
        "dockerd_executable":shutil.which("dockerd") is not None,
    }
    p=shutil.which("podman")
    prc,_=command(["podman","info","--format","json"]) if p else (-1,"")
    result["podman"]={"cli_present":bool(p),"runtime_available":bool(p and prc==0)}
    result["rootless"]={
        "rootlesskit_present":shutil.which("rootlesskit") is not None,
        "dockerd_rootless_present":shutil.which("dockerd-rootless.sh") is not None,
        "newuidmap_present":shutil.which("newuidmap") is not None,
        "newgidmap_present":shutil.which("newgidmap") is not None,
        "user_namespaces_work":command(["unshare","-Ur","true"])[0]==0 if shutil.which("unshare") else False,
    }
    if shutil.which("systemctl"):
        result["privilege"]["docker_system_service_active"]=command(["systemctl","is-active","docker"])[0]==0
        result["privilege"]["docker_user_service_active"]=command(["systemctl","--user","is-active","docker"])[0]==0
    result["privilege"]["is_root"]=os.geteuid()==0
    result["privilege"]["sudo_noninteractive_works"]=(shutil.which("sudo") is not None and _sudo_check(["true"]))
    result["privilege"]["sudo_docker_info_allowed"]=(shutil.which("sudo") is not None and _sudo_check(["docker","info","--format","{{.ServerVersion}}"]))
    return result


if __name__=="__main__":
    print(json.dumps(inspect(),sort_keys=True))
