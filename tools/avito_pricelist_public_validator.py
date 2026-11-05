#!/usr/bin/env python3
"""Validate an isolated, public Avito XML candidate with Avito's PUBLIC XML checker.

This script DOES NOT use Avito credentials, autoload, account, ads or messages APIs.
Exactly one POST to the public XML checker (not the customer's Avito account).
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

CANDIDATE = "https://olegendorphine-star.github.io/ai-ecosystem/avito-pricelist-validation-preview-2026-11-05.xml"
CHECKER = "https://autoload.avito.ru"
SUBMIT = CHECKER + "/api/v2/public/xml_checker/from_url/"
RESULT = CHECKER + "/api/v2/public/xml_checker/result/"
MAX_BYTES = 1_000_000

class CheckError(Exception):
    def __init__(self, code: str, status: int | None = None):
        self.code = code
        self.status = status
        super().__init__(code)

def decode_response(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        sample = raw[:2500].decode("utf-8", "replace").strip().lower()
        if not raw:
            kind = "empty"
        elif sample.startswith("<!doctype html") or "<html" in sample[:300]:
            kind = "html"
        elif "отчёт в работе" in sample or "отчет в работе" in sample:
            kind = "text_pending"
        else:
            kind = "plain_text"
        # Never expose raw response bodies, which may include arbitrary HTML.
        return {"_result_format": kind, "_result_size": len(raw)}


def fetch(url: str, data: bytes | None = None, content_type: str | None = None) -> Any:
    if url != CANDIDATE and url != SUBMIT and not url.startswith(RESULT):
        raise ValueError("URL not allowlisted")
    headers = {"User-Agent": "AvitoXMLReadOnlyValidation/1.0", "Accept": "application/json"}
    if content_type is not None:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, headers=headers,
                      method="POST" if data is not None else "GET", data=data)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read(MAX_BYTES + 1)
            code = response.status
        if len(raw) > MAX_BYTES:
            raise CheckError("response_too_large", code)
        if url == CANDIDATE:
            return (code, raw)
        return (code, decode_response(raw))
    except urllib.error.HTTPError as exc:
        # Untrusted error bodies may contain private content.
        raise CheckError("http_error", exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise CheckError("network_error")
    except (UnicodeError, ValueError):
        raise CheckError("invalid_json")

def extract_id(obj: Any) -> str | None:
    # The public API has returned data.id in previous real attempts.
    if not isinstance(obj, dict):
        return None
    data = obj.get("data")
    ident = data.get("id") if isinstance(data, dict) else None
    if ident is None:
        ident = obj.get("id")
    if isinstance(ident, (str, int)) and re.fullmatch(r"[A-Za-z0-9_-]{8,80}", str(ident)):
        return str(ident)
    return None

def describe_result(obj: Any) -> dict[str, Any]:
    """Conservative sanitized summary. Never infer pass from HTTP 200 alone."""
    if not isinstance(obj, dict):
        return {"state": "unknown", "schema_keys": []}
    if obj.get("_result_format") in ("empty", "html", "text_pending", "plain_text"):
        kind = obj["_result_format"]
        return {"state": "pending" if kind == "text_pending" else "non_json_response",
                "body_format": kind, "body_size": obj.get("_result_size")}
    keys = sorted(k for k in obj.keys() if k in ("data", "result", "status", "error", "success", "message"))
    statuses: list[str] = []
    codes: list[str] = []
    errors = 0
    def walk(v: Any, depth: int = 0):
        nonlocal errors
        if depth > 8:
            return
        if isinstance(v, dict):
            for k, value in v.items():
                if k in ("status", "state", "result_status") and isinstance(value, str):
                    if len(value) <= 60 and re.fullmatch(r"[\w -]{1,60}", value, re.UNICODE):
                        statuses.append(value.lower())
                if k in ("code", "errorCode") and isinstance(value, (str, int)):
                    if re.fullmatch(r"[A-Za-z0-9_-]{1,30}", str(value)):
                        codes.append(str(value))
                if k in ("errors", "errors_list", "validationErrors") and isinstance(value, list):
                    errors += len(value)
                if isinstance(value, (dict, list)):
                    walk(value, depth + 1)
        elif isinstance(v, list):
            for child in v[:40]:
                walk(child, depth + 1)
    walk(obj)
    raw = json.dumps(obj, ensure_ascii=False)[:30000].lower()
    pending = any(s in ("pending", "processing", "running", "in_progress", "queued") for s in statuses) or "отчёт в работе" in raw or "отчет в работе" in raw
    if pending:
        state = "pending"
    elif errors:
        state = "errors_reported"
    elif any(s in ("failed", "error", "rejected", "invalid") for s in statuses):
        state = "failed_reported"
    elif any(s in ("completed", "complete", "done", "success", "valid", "ready") for s in statuses):
        # Only a terminal marker, not success of the actual advert.
        state = "final_report_returned"
    else:
        state = "unclassified_response"
    return {"state": state, "schema_keys": keys, "reported_statuses": sorted(set(statuses))[:12],
            "reported_error_codes": sorted(set(codes))[:20], "error_count_at_least": errors}

def main(output: str) -> int:
    result: dict[str, Any] = {
        "schema": "avito.price_list.public_validator.v1",
        "candidate_url": CANDIDATE, "checker": "public_xml_checker",
        "account_mutations": 0, "ad_upload_requests": 0,
        "messages_read": 0, "messages_sent": 0, "charges_rub": 0,
        "validation_passed": False, "status": "not_run",
    }
    try:
        # Allow Pages deployment to catch up before posting to checker.
        for _ in range(18):
            try:
                code, body = fetch(CANDIDATE)
                if code == 200 and b"<PriceList>" in body and body.count(b"<Ad>") == 2:
                    result["candidate_available"] = True
                    break
            except CheckError:
                pass
            time.sleep(10)
        else:
            result["status"] = "candidate_unavailable"
            return save(output, result)

        code, payload = fetch(SUBMIT, data=CANDIDATE.encode("utf-8"), content_type="text/plain")
        result["submit_http"] = code
        ident = extract_id(payload)
        result["checker_id_issued"] = ident is not None
        if ident:
            result["public_checker_id"] = ident
        if not ident:
            result["status"] = "checker_id_missing"
            result["submit_response_keys"] = sorted(k for k in payload if k in ("data", "error", "message", "status")) if isinstance(payload, dict) else []
            return save(output, result)

        result["status"] = "pending"
        non_json_count = 0
        for i in range(18):
            time.sleep(15)
            c, obj = fetch(RESULT + ident + "/")
            result["result_http"] = c
            assessment = describe_result(obj)
            result["assessment"] = assessment
            if assessment["state"] == "non_json_response":
                non_json_count += 1
                if non_json_count >= 2:
                    result["status"] = "non_json_response"
                    break
                continue
            if assessment["state"] in ("final_report_returned", "errors_reported", "failed_reported"):
                result["status"] = assessment["state"]
                # No inference of validation_passed unless full official error data is available.
                break
        else:
            result["status"] = "pending_or_unclassified"
    except CheckError as e:
        result["status"] = e.code
        result["error_http"] = e.status
    return save(output, result)

def save(output: str, result: dict[str, Any]) -> int:
    p = Path(output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print("PUBLIC_VALIDATOR_STATUS", result["status"])
    print("ACCOUNT_MUTATIONS", result["account_mutations"])
    return 0

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: avito_pricelist_public_validator.py OUTPUT_JSON")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
