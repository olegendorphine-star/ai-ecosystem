#!/usr/bin/env python3
"""Classify FL owner handoff startup failure from VPS-local evidence.

Never print raw logs, private files, cookie/token values, page text, URLs,
process command lines, private paths or account details. No writes.
"""
from __future__ import annotations
import json
import os
import re
import stat
from pathlib import Path

ROOT = Path.home() / ".fl-agent"


def classify_log(log: str) -> str:
    data = log.lower()
    if "fl_handoff_render_not_ready" in data:
        return "screenshot_preflight_failed"
    if "chrome_exited" in data or "chrome_process_not_alive" in data:
        return "chrome_exited"
    if "targetclosederror" in data or "target page, context or browser has been closed" in data:
        return "browser_target_closed"
    if "page.goto" in data and "timeout" in data:
        return "fl_navigation_timeout"
    if "page.goto" in data and ("err_connection" in data or "err_name_not_resolved" in data):
        return "fl_navigation_network_error"
    if "browsertype.connect_over_cdp" in data or "browser_debugging_unavailable" in data:
        return "cdp_attach_failed"
    if "cannot open shared object file" in data:
        return "chrome_shared_library_missing"
    if "greenlet.error" in data or "cannot switch to a different thread" in data:
        return "playwright_thread_error"
    if "address already in use" in data:
        return "port_conflict"
    if "traceback" in data:
        return "other_python_exception"
    if "fl_handoff_private_ready" in data:
        return "server_started"
    return "no_classifiable_log"


def memory_mb() -> dict:
    result = {"memory_total_mb": None, "memory_available_mb": None}
    try:
        content = Path("/proc/meminfo").read_text()
        for name, target in (
            ("MemTotal", "memory_total_mb"),
            ("MemAvailable", "memory_available_mb"),
        ):
            match = re.search(rf"(?m)^{name}:\s+(\d+)\s+kB", content)
            if match:
                result[target] = int(match.group(1)) // 1024
    except OSError:
        pass
    return result


def cgroup_oom_count() -> int | None:
    # Cumulative counts only; not necessarily attributable to the current run.
    for filename in ("/sys/fs/cgroup/memory.events", "/sys/fs/cgroup/memory/memory.oom_control"):
        try:
            data = Path(filename).read_text()
            match = re.search(r"(?m)^oom_kill\s+(\d+)\s*$", data)
            if match:
                return int(match.group(1))
        except OSError:
            pass
    return None


def active_process_counts() -> dict:
    result = {"chrome_process_count": 0, "fl_chrome_process_count": 0,
              "fl_gateway_process_count": 0}
    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            path = Path("/proc") / pid
            try:
                if path.stat().st_uid != os.getuid():
                    continue
                args = (path / "cmdline").read_bytes().split(b"\0")
                exe = args[0].rsplit(b"/", 1)[-1].lower() if args else b""
                if b"chrome" in exe or b"chromium" in exe:
                    result["chrome_process_count"] += 1
                    if any(b"--user-data-dir=" in a and b"/.fl-agent/" in a for a in args):
                        result["fl_chrome_process_count"] += 1
                if any(b"/.fl-agent/fl_secure_handoff.py" in a for a in args):
                    result["fl_gateway_process_count"] += 1
            except OSError:
                continue
    except OSError:
        pass
    return result


def report() -> dict:
    result = {
        "schema": "fl.owner.startup.error.v1",
        "action": "classify_startup",
        "error_category": "no_classifiable_log",
        "log_present": False,
        "handoff_token_present": False,
        "cgroup_oom_kill_cumulative": cgroup_oom_count(),
        "write_actions": False,
        **memory_mb(), **active_process_counts(),
    }
    try:
        log = ROOT / "handoff.log"
        if not log.is_symlink() and log.is_file() and log.stat().st_uid == os.getuid():
            result["log_present"] = True
            with log.open("rb") as file:
                file.seek(max(0, log.stat().st_size - 65536))
                raw = file.read(65536)
            result["error_category"] = classify_log(raw.decode("utf-8", "replace"))
        token = ROOT / "handoff_token"
        if (not token.is_symlink() and token.is_file()
                and token.stat().st_uid == os.getuid()
                and stat.S_IMODE(token.stat().st_mode) == 0o600):
            result["handoff_token_present"] = True
    except (OSError, TypeError, ValueError):
        pass
    return result


if __name__ == "__main__":
    print(json.dumps(report(), sort_keys=True))
