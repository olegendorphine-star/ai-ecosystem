#!/usr/bin/env python3
"""One public GET of an existing Avito XML checker result; no new submission.

No Avito account endpoints, secrets, messages, purchases or publication.
All network bodies stay on the runner and only a safe summary is persisted.
"""
from __future__ import annotations
import gzip
from html.parser import HTMLParser
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

RESULT_URL = "https://autoload.avito.ru/api/v2/public/xml_checker/result/6aec57e6213afa1bce7d3974/"
MAX_BODY = 2000000


class _VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "template"):
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "template") and self.hidden:
            self.hidden -= 1

    def handle_data(self, text: str) -> None:
        if not self.hidden and text.strip() and len(self.nodes) < 500:
            self.nodes.append(text.strip()[:400])


def visible_report_markers(raw: bytes) -> dict[str, Any]:
    """Inspect visible text of public HTML; never export raw ad or customer text."""
    parser = _VisibleTextParser()
    parser.feed(raw.decode("utf-8-sig", "replace"))
    text = re.sub(r"\s+", " ", " ".join(parser.nodes)).lower()
    invalid = "xml не соответствует формату" in text
    valid = "xml соответствует формату" in text and not invalid
    count = re.search(r"проверено объявлений\s*:?\s*(\d{1,5})", text)
    return {
        "report_heading_visible": "общий статус" in text,
        "format_valid_text_visible": valid,
        "format_invalid_text_visible": invalid,
        "explicit_errors_found": (
            "в вашем файле найдены следующие ошибки" in text
            or "найдены ошибки формата" in text
            or "обнаружены ошибки" in text
        ),
        "explicit_no_errors": (
            "ошибок не найдено" in text or "ошибки не найдены" in text
        ),
        "checked_ad_count": int(count.group(1)) if count else None,
        "visible_text_node_count": len(parser.nodes)
    }


def classify(body: bytes, content_type: str = "", encoding: str = "") -> dict[str, Any]:
    summary: dict[str, Any] = {"response_size": len(body),
                                "prefix_hex": body[:8].hex(),
                                "content_type": content_type.split(";", 1)[0].strip().lower()
                                    if content_type.split(";", 1)[0].strip().lower()
                                    in {"application/json", "text/html", "text/plain", "application/xml", "text/xml", "application/octet-stream"}
                                    else "other"}
    if body[:2] == b"\x1f\x8b" or encoding.lower() == "gzip":
        try:
            decoded = gzip.decompress(body)
            if len(decoded) > MAX_BODY:
                summary["parse_type"] = "gzip_oversized"
                return summary
            body = decoded
            summary["compression"] = "gzip"
        except (OSError, EOFError, ValueError):
            summary["parse_type"] = "gzip_invalid"
            return summary
    else:
        summary["compression"] = "none"
    try:
        doc = json.loads(body.decode("utf-8-sig"))
        if isinstance(doc, dict):
            keys = {"data", "result", "status", "error", "errors", "report", "success"}
            summary["parse_type"] = "json_object"
            summary["top_level_known_keys"] = sorted(keys.intersection(doc))
            inner = doc.get("data") if isinstance(doc.get("data"), dict) else doc
            if isinstance(inner, dict):
                summary["nested_known_keys"] = sorted(keys.intersection(inner))
            return summary
        summary["parse_type"] = "json_array_or_value"
        return summary
    except (UnicodeError, ValueError):
        pass
    text = body.decode("utf-8-sig", "replace").strip().lower()
    if text.startswith(")]}'") or text.startswith("for (;;);"):
        summary["parse_type"] = "anti_json_prefix"
        return summary
    if text.startswith("<"):
        try:
            root = ET.fromstring(body)
            summary["parse_type"] = "xml"
            summary["root_tag_is_html"] = root.tag.lower().endswith("html")
        except (ET.ParseError, ValueError):
            summary["parse_type"] = "html_fragment_or_invalid_xml"
    else:
        summary["parse_type"] = "plain_text"
    # These are classifications, not copies of user data.
    flags = {
      "pending_phrase": ("отчёт в работе" in text or "отчет в работе" in text),
      "xml_formally_valid_phrase": "xml соответствует формату" in text,
      "xml_formally_invalid_phrase": "xml не соответствует формату" in text,
      "error_phrase": ("ошибк" in text or "error" in text),
      "price_list_reference": "pricelist" in text,
    }
    summary["body_markers"] = flags
    if summary["content_type"] == "text/html":
        summary["visible_html_report"] = visible_report_markers(body)
    return summary


def read_public_result() -> dict[str, Any]:
    request = urllib.request.Request(
        RESULT_URL,
        method="GET",
        headers={"Accept": "application/json, text/plain, */*",
                 "User-Agent": "AvitoXMLResultReadOnly/1.0",
                 "Accept-Encoding": "identity"}
    )
    result: dict[str, Any] = {
        "schema": "avito.xml_checker.response_probe.v1",
        "check_id": "6aec57e6213afa1bce7d3974",
        "endpoint": "public_xml_checker_result",
        "account_mutations": 0, "validator_submissions": 0,
        "ad_upload_requests": 0, "messages_read": 0, "messages_sent": 0, "charges_rub": 0,
    }
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read(MAX_BODY + 1)
            result["http_status"] = response.status
            content_type = response.headers.get("Content-Type", "")
            encoding = response.headers.get("Content-Encoding", "")
        if len(body) > MAX_BODY:
            result["parse_type"] = "oversized"
        else:
            result.update(classify(body, content_type, encoding))
    except urllib.error.HTTPError as e:
        result["http_status"] = e.code
        result["parse_type"] = "http_error"
    except (urllib.error.URLError, OSError, TimeoutError):
        result["http_status"] = None
        result["parse_type"] = "network_error"
    return result


def main(path: str) -> None:
    result = read_public_result()
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print("PUBLIC_GET_HTTP", result.get("http_status"))
    print("PARSE_KIND", result.get("parse_type"))
    print("ACCOUNT_MUTATIONS", result["account_mutations"])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: avito_checker_result_probe.py OUTPUT_JSON")
    main(sys.argv[1])
