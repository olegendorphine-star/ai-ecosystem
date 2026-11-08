#!/usr/bin/env python3
"""Safe Session Guardian decision core for own Avito browser.

Pure decision function. Never logs session cookies, retries blocked routes,
sends messages or touches the remote browser. It is not a running daemon.
"""
from __future__ import annotations

import json


def classify_owner_probe(probe: object) -> dict:
    result = {
        "schema": "avito.session.guardian.state.v1",
        "state": "unverified",
        "next_action": "verify_owner_ui",
        "automatic_login_allowed": False,
        "browser_write_actions_allowed": False,
        "retry_blocked_page": False,
    }
    if not isinstance(probe, dict):
        return result
    if probe.get("browser_ready") is not True:
        result["state"] = "browser_unavailable"
        result["next_action"] = "diagnose_browser_over_ssh"
        return result
    status = probe.get("site_http_status")
    if type(status) is int and status in {403, 451}:
        result["state"] = "access_restricted"
        result["next_action"] = "stop_and_request_support_review"
        return result
    if type(status) is int and status == 429:
        result["state"] = "rate_limited"
        result["next_action"] = "stop_and_respect_rate_limit"
        return result
    if probe.get("auth_challenge_visible") is True or probe.get("auth_state") == "auth_required" or status == 401:
        result["state"] = "auth_required"
        result["next_action"] = "request_owner_login"
        return result
    if (probe.get("profile_route_reached") is True
            and probe.get("auth_state") == "likely_active"
            and type(status) is int and 200 <= status < 300):
        result["state"] = "likely_active_unverified"
        result["next_action"] = "verify_owner_ui_before_browser_actions"
    return result


def main() -> None:
    # Only sanitized probe data, never raw browser responses or session files.
    import sys
    raw = sys.stdin.read(4097)
    if len(raw) > 4096:
        print(json.dumps(classify_owner_probe(None), sort_keys=True))
        return
    try:
        report = classify_owner_probe(json.loads(raw))
    except (ValueError, TypeError):
        report = classify_owner_probe(None)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
