#!/usr/bin/env python3
"""Fail-closed FL.ru freelancer action policy, independent of browser/UI.

Produces decisions, never sends messages or modifies the account.
No payment or premium offers, no duplicate bids and no unapproved edits.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
from urllib.parse import urlparse

OWNER_LOGIN = "olegendorphine"
FREE_BADGE = "для всех"
ACTIONS = frozenset({"scan_public", "inspect_profile", "draft_bid", "submit_bid", "update_profile"})
SENSITIVE_FIELDS = frozenset({"password", "email", "phone", "2fa", "billing", "payment", "plan"})


def valid_fl_project(url: object) -> bool:
    if not isinstance(url, str):
        return False
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"www.fl.ru", "fl.ru"}
        and not parsed.username and not parsed.password
        and parsed.port is None
        and parsed.path.startswith("/projects/")
        and parsed.path.endswith(".html")
    )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def timestamp(value: object) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except (ValueError, OverflowError):
        return None


def evaluate(request: object, *, now: dt.datetime, already_sent: set[str] | None = None) -> dict:
    """A narrow permit-to-execute decision, never actual execution."""
    result = {
        "schema": "fl.owner.operator.policy.v1",
        "decision": "blocked", "next_action": "check_request",
        "owner_login": OWNER_LOGIN, "send_performed": False,
        "profile_changed": False, "payment_performed": False,
    }
    if not isinstance(request, dict):
        return result
    action = request.get("action")
    if request.get("login") != OWNER_LOGIN or action not in ACTIONS:
        return result
    if action == "scan_public":
        return {**result, "decision": "read_only_allowed", "next_action": "browser_scan"}
    if action == "draft_bid":
        if not valid_fl_project(request.get("project_url")):
            return result
        return {**result, "decision": "draft_allowed", "next_action": "prepare_unique_draft"}
    if request.get("session_state") != "verified_owner":
        return {**result, "decision": "auth_required", "next_action": "private_owner_login"}
    if action == "inspect_profile":
        return {**result, "decision": "read_only_allowed", "next_action": "browser_profile_inventory"}

    if request.get("fee_rub") not in (None, 0) or request.get("paid") is not False:
        return {**result, "decision": "blocked_paid", "next_action": "request_separate_payment_approval"}
    approval = request.get("approval")
    if not isinstance(approval, dict):
        return {**result, "decision": "approval_required", "next_action": "ask_owner"}
    expiry = timestamp(approval.get("expires_at"))
    if expiry is None or expiry <= now:
        return {**result, "decision": "approval_expired", "next_action": "ask_owner"}

    if action == "submit_bid":
        url = request.get("project_url")
        if not valid_fl_project(url):
            return result
        job_id = urlparse(url).path.split("/")[2]
        if job_id in (already_sent or set()):
            return {**result, "decision": "duplicate_bid", "next_action": "read_existing_reply"}
        # Unknown fee status is not free. Must be verified at submission time.
        if request.get("free_badge_verified") is not True:
            return {**result, "decision": "free_status_unverified", "next_action": "check_free_for_all_badge"}
        proposal = request.get("proposal")
        if not isinstance(proposal, str) or not (50 <= len(proposal) <= 3000):
            return result
        if approval.get("allow_send") is not True or approval.get("sha256") != digest(proposal):
            return {**result, "decision": "approval_required", "next_action": "approve_exact_bid"}
        return {**result, "decision": "approved_not_executed", "next_action": "authorized_browser_submit_then_verify"}

    if action == "update_profile":
        changes = request.get("changes")
        if not isinstance(changes, dict) or not changes or any(
            str(k).lower() in SENSITIVE_FIELDS for k in changes
        ):
            return result
        prepared = json.dumps(changes, ensure_ascii=False, sort_keys=True)
        if approval.get("allow_profile_edit") is not True or approval.get("sha256") != digest(prepared):
            return {**result, "decision": "approval_required", "next_action": "approve_exact_profile_diff"}
        return {**result, "decision": "approved_not_executed", "next_action": "authorized_browser_apply_then_verify"}
    return result
