#!/usr/bin/env python3
"""Safe read-only preflight for a self-hosted Steel Browser pilot on the owner's VPS.

No installation, Docker image pull, account access, session, or credential reads.
Outputs only non-sensitive capacity and capability flags.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
from pathlib import Path


def _command_works(argv: list[str], timeout: int = 6) -> bool:
    try:
        result = subprocess.run(argv, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=timeout,
                                check=False)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _meminfo_mb(field: str) -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith(field + ":"):
                return int(line.split()[1]) // 1024
    except (OSError, IndexError, ValueError):
        pass
    return None


def _port_in_use(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        return sock.connect_ex(("127.0.0.1", port)) == 0
    finally:
        sock.close()


def inspect() -> dict:
    usage = shutil.disk_usage(Path.home())
    docker_cli = shutil.which("docker") is not None
    docker_access = docker_cli and _command_works(["docker", "info", "--format", "{{.ServerVersion}}"])
    arch = platform.machine().lower()
    mem = _meminfo_mb("MemTotal")
    available = _meminfo_mb("MemAvailable")
    disk = usage.free // (1024 * 1024)
    ports = {str(port): _port_in_use(port) for port in (3000, 9223, 13000, 19223)}
    return {
        "schema": "ai.steel.vps.preflight.v1",
        "read_only": True,
        "architecture": "amd64" if arch in ("x86_64", "amd64") else
                        "arm64" if arch in ("aarch64", "arm64") else "other",
        "memory_total_mb": mem,
        "memory_available_mb": available,
        "disk_free_mb_home": disk,
        "docker_cli_present": docker_cli,
        "docker_daemon_accessible": docker_access,
        "node_cli_present": shutil.which("node") is not None,
        "npm_cli_present": shutil.which("npm") is not None,
        "existing_steel_container": bool(
            docker_access and _command_works(
                ["docker", "container", "inspect", "ai-ecosystem-steel-pilot"]
            )
        ),
        "ports_in_use_loopback": ports,
        "meets_documented_docker_prerequisites": bool(
            docker_access and mem is not None and mem >= 4096
            and disk >= 10240 and not ports["13000"] and not ports["19223"]
        ),
    }


if __name__ == "__main__":
    print(json.dumps(inspect(), ensure_ascii=False, sort_keys=True))
