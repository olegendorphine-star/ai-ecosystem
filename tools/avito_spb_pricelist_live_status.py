#!/usr/bin/env python3
"""One-shot read-only verification of the live SPb PriceList rollout."""
from __future__ import annotations
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

API = "https://api.avito.ru"
FEED = "https://olegendorphine-star.github.io/ai-ecosystem/avito-feed.xml"
ALLOWED_GETS = {
    "/core/v1/items", "/autoload/v4/uploads/current",
    "/autoload/v4/uploads/current/items"
}
MAX_BODY = 1000000


def http(url: str, *, auth: str | None = None, body: bytes | None = None) -> tuple[int | None, Any]:
    path = urllib.parse.urlsplit(url).path
    if body is not None and url != API + "/token/":
        raise ValueError("only OAuth POST is permitted")
    if body is None and url != FEED and (not url.startswith(API) or path not in ALLOWED_GETS):
        raise ValueError("only allowlisted GET is permitted")
    headers = {"Accept": "application/json", "User-Agent": "AvitoSPbPriceListReadOnly/1.0"}
    if auth:
        headers["Authorization"] = "Bearer " + auth
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, headers=headers, data=body, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            raw = response.read(MAX_BODY + 1)
            status = response.status
        if len(raw) > MAX_BODY:
            return status, None
        if url == FEED:
            return status, raw
        try:
            return status, json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError):
            return status, None
    except urllib.error.HTTPError as err:
        return err.code, None
    except (urllib.error.URLError, OSError, TimeoutError):
        return None, None


def feed_check(xml: bytes) -> dict[str, Any]:
    root = ET.fromstring(xml)
    ads = root.findall("Ad")
    if len(ads) != 2:
        return {"two_ads": False, "spb_three_prices": False, "moscow_has_no_price_list": False,
                "all_original_images": False, "free_package": False}
    mos, spb = ads
    price_vals = [x.text for x in spb.findall("./PriceList/Service/ServicePrice")]
    return {
        "two_ads": len(ads) == 2,
        "spb_three_prices": price_vals == ["5000", "30000", "150000"],
        "moscow_has_no_price_list": mos.find("PriceList") is None,
        "all_original_images": (
            len(mos.findall("./Images/Image")) == 6
            and len(spb.findall("./Images/Image")) == 6
        ),
        "free_package": all(ad.findtext("ListingFee") == "Package"
                            and ad.findtext("AdStatus") == "Free"
                            and ad.findtext("Price") == "5000" for ad in ads),
        "ids_stable": mos.findtext("AvitoId") == "8347570435"
            and mos.findtext("Id") == "ai-assistant-memory-moscow-001"
            and spb.findtext("Id") == "ai-assistant-memory-spb-001",
    }


def active_check(payload: Any) -> dict[str, Any]:
    res = payload.get("resources") if isinstance(payload, dict) else None
    res = res if isinstance(res, list) else []
    mos = next((x for x in res if isinstance(x, dict)
                and str(x.get("id")) == "8347570435"), None)
    spb = next((x for x in res if isinstance(x, dict)
                and "sankt-peterburg" in str(x.get("url", "")).lower()), None)
    return {"moscow_active": bool(mos and mos.get("status") == "active" and mos.get("price") == 5000),
            "spb_active": bool(spb and spb.get("status") == "active" and spb.get("price") == 5000),
            "active_page_count": len(res)}


def upload_check(current: Any, items: Any) -> dict[str, Any]:
    upload_id = current.get("upload_id") if isinstance(current, dict) else None
    if type(upload_id) is not int:
        upload_id = None
    status = current.get("status") if isinstance(current, dict) else None
    allowed_statuses = {"processing", "completed", "error", "failed", "success", "finished"}
    entries = items.get("items") if isinstance(items, dict) else None
    entries = entries if isinstance(entries, list) else []
    spb = next((x for x in entries if isinstance(x, dict)
                and x.get("id") == "ai-assistant-memory-spb-001"), None)
    section = spb.get("section") if isinstance(spb, dict) else None
    slug = section.get("slug") if isinstance(section, dict) else section
    allowed_sections = {"success_published", "processing", "error_params",
                        "error_payment", "error_content", "removed_complete", "pending"}
    return {"upload_id": upload_id,
            "upload_status": status if status in allowed_statuses else "unknown",
            "spb_in_current_items": spb is not None,
            "spb_section": slug if isinstance(slug, str) and slug in allowed_sections else "unknown"}


def inspect() -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema": "avito.spb.pricelist.live-read.v1",
        "account_mutations": 0, "messages_read": 0, "messages_sent": 0,
        "charges_rub": 0, "autoload_posts": 0,
    }
    feed_http, raw = http(FEED)
    summary["public_feed_http"] = feed_http
    if feed_http != 200 or not isinstance(raw, bytes):
        return summary
    try:
        summary["public_feed"] = feed_check(raw)
    except ET.ParseError:
        summary["public_feed"] = {"xml_parse_ok": False}
        return summary
    if not all(summary["public_feed"].values()):
        return summary
    cid, secret = os.environ.get("AVITO_CLIENT_ID"), os.environ.get("AVITO_CLIENT_SECRET")
    if not cid or not secret:
        summary["oauth_ok"] = False
        return summary
    form = urllib.parse.urlencode({"grant_type": "client_credentials",
                                   "client_id": cid, "client_secret": secret}).encode()
    auth_code, payload = http(API + "/token/", body=form)
    token = payload.get("access_token") if isinstance(payload, dict) else None
    summary["oauth_ok"] = auth_code == 200 and isinstance(token, str) and bool(token)
    if not summary["oauth_ok"]:
        summary["oauth_http"] = auth_code
        return summary
    checks = [
        ("active_items", "/core/v1/items?status=active&per_page=99&page=1"),
        ("current_upload", "/autoload/v4/uploads/current"),
        ("current_items", "/autoload/v4/uploads/current/items"),
    ]
    results = {name: http(API + path, auth=token) for name, path in checks}
    summary["http"] = {name: code for name, (code, _) in results.items()}
    if results["active_items"][0] == 200:
        summary["active_items"] = active_check(results["active_items"][1])
    if results["current_upload"][0] == 200:
        summary["current_upload"] = upload_check(
            results["current_upload"][1],
            results["current_items"][1] if results["current_items"][0] == 200 else None)
    return summary


def main(out: str) -> None:
    data = inspect()
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("FEED_HTTP", data.get("public_feed_http"))
    print("ACTIVE_HTTP", data.get("http", {}).get("active_items"))
    print("AUTOLOAD_POSTS", data["autoload_posts"])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: avito_spb_pricelist_live_status.py OUTPUT")
    main(sys.argv[1])
