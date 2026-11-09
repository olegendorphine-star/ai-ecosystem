#!/usr/bin/env python3
"""Offline fail-closed Avito owner profile action gate. No site or network calls."""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import json
import re

SCHEMA = "avito.owner.profile.intent.v1"
READ = frozenset(("profile_inspect", "portfolio_inspect"))
WRITE = frozenset(("profile_edit", "portfolio_add_image", "portfolio_delete_image",
                   "portfolio_add_document", "portfolio_delete_document"))
DELETE = frozenset(("portfolio_delete_image", "portfolio_delete_document"))
SHA = re.compile(r"^[0-9a-f]{64}$")

def fingerprint(intent):
    return sha256(json.dumps(intent, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode()).hexdigest()

def result(action, decision, next_action):
    return {"schema": "avito.owner.profile.preflight.v1", "action": action,
            "decision": decision, "next_action": next_action, "live_change_performed": False}

def assess(intent, environment, approval=None, now=None):
    """Every green result is only preflight; the executor must re-check UI."""
    if not isinstance(intent, dict) or not isinstance(environment, dict):
        return result("unknown", "invalid_request", "repair_offline_plan")
    action = intent.get("action")
    if not isinstance(action, str) or action not in READ | WRITE:
        return result("unknown", "unsupported_action", "review_action_scope")
    keys = {"schema", "action"} if action in READ else {
        "schema", "action", "target_fingerprint", "payload_sha256"}
    if intent.get("schema") != SCHEMA or set(intent) != keys:
        return result(action, "invalid_request", "repair_offline_plan")
    if action in WRITE and not all(isinstance(intent.get(k), str) and SHA.fullmatch(intent[k])
                                   for k in ("target_fingerprint", "payload_sha256")):
        return result(action, "invalid_request", "repair_offline_plan")
    status = environment.get("site_http_status")
    if type(status) is int and status == 429:
        return result(action, "rate_limited", "stop_without_retry")
    if type(status) is int and status in (403, 451):
        return result(action, "access_restricted", "contact_avito_support")
    if environment.get("browser_ready") is not True:
        return result(action, "browser_unavailable", "diagnose_private_browser")
    if (environment.get("owner_session_verified") is not True or
            environment.get("owner_identity_verified") is not True):
        return result(action, "auth_unverified", "owner_completes_official_login")
    if status != 200:
        return result(action, "page_unverified", "inspect_permitted_owner_page")
    if action in READ:
        return result(action, "read_only_ready", "inspect_verified_owner_ui")
    if (not isinstance(environment.get("ui_supported_actions"), list) or
            action not in environment["ui_supported_actions"]):
        return result(action, "capability_unverified", "verify_exact_live_ui_capability")
    if (environment.get("unique_target_count") != 1 or
            environment.get("target_fingerprint") != intent["target_fingerprint"]):
        return result(action, "target_unverified", "refresh_private_target_inventory")
    if not isinstance(approval, dict) or approval.get("owner_authorized") is not True:
        return result(action, "approval_required", "request_exact_owner_approval")
    if approval.get("intent_sha256") != fingerprint(intent):
        return result(action, "approval_mismatch", "request_exact_owner_approval")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or not isinstance(approval.get("expires_at"), str):
        return result(action, "approval_invalid", "request_expiring_approval")
    try:
        expiry = datetime.fromisoformat(approval["expires_at"].replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError:
        return result(action, "approval_invalid", "request_expiring_approval")
    if not 0 < (expiry - now).total_seconds() <= 1800:
        return result(action, "approval_expired_or_too_long", "request_fresh_approval")
    if action in DELETE:
        if environment.get("private_backup_verified") is not True:
            return result(action, "backup_required", "create_and_verify_private_backup")
        if approval.get("confirm_delete") is not True:
            return result(action, "deletion_confirmation_required", "confirm_exact_delete")
    return result(action, "preflight_approved", "controlled_owner_ui_executor_only")
