#!/usr/bin/env python3
"""One-shot read-only verification of the live SPb PriceList rollout."""
from __future__ import annotations
import json
from datetime import datetime, timezone
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
    """Check full four-city SEO feed before accessing the Avito API."""
    root = ET.fromstring(xml)
    ads = root.findall("Ad")
    expected = (
        ("ai-assistant-memory-moscow-001", "Москва",
         "Автоматизация бизнеса с ИИ — аудит и внедрение"),
        ("ai-assistant-memory-spb-001", "Санкт-Петербург",
         "ИИ-ассистент для бизнеса и базы знаний"),
        ("ai-assistant-memory-surgut-001", "Сургут",
         "ИИ-ассистент для бизнеса — настройка"),
        ("ai-assistant-memory-chita-001", "Чита",
         "ИИ-ассистент для бизнеса и документов"),
    )
    def prices(ad: Any) -> list[str | None]:
        return [s.findtext("ServicePrice")
                for s in ad.findall("./PriceList/Service")]
    matched = len(ads) == len(expected)
    expected_ids_cities = matched and all(
        (ad.findtext("Id"), ad.findtext("Address")) == (ident, city)
        for ad, (ident, city, _) in zip(ads, expected))
    titles = [ad.findtext("Title", "") for ad in ads]
    image_lists = [
        [im.attrib.get("url") for im in ad.findall("./Images/Image")]
        for ad in ads]
    return {
        "four_ads": matched,
        "expected_ids_cities": expected_ids_cities,
        "seo_titles_ready": matched and all(
            ad.findtext("Title") == title
            for ad, (_, _, title) in zip(ads, expected)),
        "unique_titles": len(set(titles)) == 4 and all(titles),
        "four_price_lists": matched and all(
            prices(ad) == ["5000", "30000", "150000"] for ad in ads),
        "all_original_images": matched and all(
            len(urls) == 6 and urls == image_lists[0] for urls in image_lists),
        "free_package": matched and all(
            ad.findtext("ListingFee") == "Package"
            and ad.findtext("AdStatus") == "Free"
            and ad.findtext("Price") == "5000" for ad in ads),
        "ids_stable": expected_ids_cities
            and ads[0].findtext("AvitoId") == "8347570435",
    }


def active_check(payload: Any) -> dict[str, Any]:
    res = payload.get("resources") if isinstance(payload, dict) else None
    res = res if isinstance(res, list) else []
    mos = next((x for x in res if isinstance(x, dict)
                and str(x.get("id")) == "8347570435"), None)
    spb = next((x for x in res if isinstance(x, dict)
                and "sankt-peterburg" in str(x.get("url", "")).lower()), None)
    surgut = next((x for x in res if isinstance(x, dict)
                   and str(x.get("id")) == "8531755111"), None)
    # A city/price match alone is not proof this is our newly created Chita ad.
    # Only one strictly canonical Chita URL is carried forward as a candidate.
    def canonical_chita_url(item: dict[str, Any]) -> str | None:
        raw = item.get("url")
        if not isinstance(raw, str):
            return None
        parsed = urllib.parse.urlsplit(raw)
        if (parsed.scheme != "https" or parsed.netloc not in ("avito.ru", "www.avito.ru")
                or not parsed.path.startswith("/chita/")
                or ".." in parsed.path or len(parsed.path) > 250):
            return None
        item_id = item.get("id")
        if type(item_id) is not int or not (0 < item_id < 1000000000000000):
            return None
        if not parsed.path.endswith("_" + str(item_id)):
            return None
        return "https://www.avito.ru" + parsed.path
    candidates = [(x, canonical_chita_url(x)) for x in res
                  if isinstance(x, dict) and x.get("status") == "active"
                  and x.get("price") == 5000]
    candidates = [(x, url) for x, url in candidates if url is not None]
    chita = candidates[0] if len(candidates) == 1 else None
    result = {"moscow_active": bool(mos and mos.get("status") == "active" and mos.get("price") == 5000),
              "spb_active": bool(spb and spb.get("status") == "active" and spb.get("price") == 5000),
              "surgut_active": bool(surgut and surgut.get("status") == "active"
                                    and surgut.get("price") == 5000),
              "chita_candidate_active": chita is not None,
              "active_page_count": len(res)}
    if chita:
        result["chita_public_ad_id"] = chita[0]["id"]
        result["chita_public_url"] = chita[1]
    # Listing IDs and canonical public URLs are public advertising metadata.
    # Do not expose raw URLs, query parameters, contact details or API payloads.
    if isinstance(spb, dict):
        item_id = spb.get("id")
        if type(item_id) is int and 0 < item_id < 1000000000000000:
            result["spb_public_ad_id"] = item_id
        raw_url = spb.get("url")
        if isinstance(raw_url, str):
            parsed = urllib.parse.urlsplit(raw_url)
            if (parsed.scheme == "https" and parsed.hostname in ("avito.ru", "www.avito.ru")
                    and parsed.port is None and parsed.path.startswith("/sankt-peterburg/")
                    and ".." not in parsed.path and len(parsed.path) <= 250):
                result["spb_public_url"] = "https://www.avito.ru" + parsed.path
    return result


def upload_check(current: Any, items: Any) -> dict[str, Any]:
    upload_id = current.get("upload_id") if isinstance(current, dict) else None
    if type(upload_id) is not int:
        upload_id = None
    status = current.get("status") if isinstance(current, dict) else None
    allowed_statuses = {"processing", "completed", "error", "failed", "success", "finished"}
    entries = items.get("items") if isinstance(items, dict) else None
    entries = entries if isinstance(entries, list) else []
    def by_stable_id(stable_id: str) -> dict[str, Any] | None:
        return next((x for x in entries if isinstance(x, dict)
                     and (x.get("id") == stable_id or x.get("ad_id") == stable_id)), None)
    spb = by_stable_id("ai-assistant-memory-spb-001")
    chita = by_stable_id("ai-assistant-memory-chita-001")
    section = spb.get("section") if isinstance(spb, dict) else None
    slug = section.get("slug") if isinstance(section, dict) else section
    chita_section = chita.get("section") if isinstance(chita, dict) else None
    chita_slug = (chita_section.get("slug") if isinstance(chita_section, dict)
                  else chita_section)
    chita_id = chita.get("avito_id", chita.get("avitoId")) if chita else None
    if isinstance(chita_id, str) and chita_id.isdecimal():
        chita_id = int(chita_id)
    if type(chita_id) is not int or not (0 < chita_id < 1000000000000000):
        chita_id = None
    allowed_sections = {"success_published", "processing", "error_params",
                        "error_payment", "error_content", "removed_complete", "pending"}
    # An import started before the SEO feed deployment cannot verify SEO.
    seo_live_since = datetime(2026, 11, 10, 10, 19, 9, tzinfo=timezone.utc)
    started_raw = current.get("started_at") if isinstance(current, dict) else None
    started = None
    if isinstance(started_raw, str):
        try:
            parsed = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                started = parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    import_after_seo = started is not None and started > seo_live_since
    expected_ids = ("ai-assistant-memory-moscow-001",
                    "ai-assistant-memory-spb-001",
                    "ai-assistant-memory-surgut-001",
                    "ai-assistant-memory-chita-001")
    all_four_success = all(
        (row := by_stable_id(stable)) is not None
        and isinstance(row.get("section"), dict)
        and row["section"].get("slug") == "success_published"
        for stable in expected_ids)
    # Reports processing/queued as NOT confirmed even if sections look green.
    seo_import_verified = bool(import_after_seo and
        status in ("success", "completed", "finished") and all_four_success)
    return {"upload_id": upload_id,
            "upload_status": status if status in allowed_statuses else "unknown",
            "upload_started_at_utc": started.isoformat() if started else None,
            "import_started_after_seo": import_after_seo,
            "four_items_success_published": all_four_success,
            "seo_import_four_items_verified": seo_import_verified,
            "spb_in_current_items": spb is not None,
            "spb_section": slug if isinstance(slug, str) and slug in allowed_sections else "unknown",
            "chita_in_current_items": chita is not None,
            "chita_section": (chita_slug if isinstance(chita_slug, str)
                              and chita_slug in allowed_sections else "unknown"),
            "chita_avito_id": chita_id}


def inspect() -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema": "avito.spb.pricelist.live-read.v2",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
    ]
    results = {name: http(API + path, auth=token) for name, path in checks}
    summary["http"] = {name: code for name, (code, _) in results.items()}
    if results["active_items"][0] == 200:
        summary["active_items"] = active_check(results["active_items"][1])
    if results["current_upload"][0] == 200:
        current = results["current_upload"][1]
        current_status = current.get("status") if isinstance(current, dict) else None
        # Avoid a third API call while Avito is still processing an upload.
        # The items endpoint previously returned 429; never retry it in a loop.
        if current_status == "processing":
            summary["current_items_check"] = "skipped_while_processing"
            item_data = None
        elif current_status in {"completed", "success", "finished", "error", "failed"}:
            item_code, item_data = http(
                API + "/autoload/v4/uploads/current/items", auth=token)
            summary["http"]["current_items"] = item_code
            summary["current_items_check"] = (
                "read" if item_code == 200 else
                "rate_limited" if item_code == 429 else "unavailable"
            )
            if item_code != 200:
                item_data = None
        else:
            summary["current_items_check"] = "skipped_unknown_upload_status"
            item_data = None
        summary["current_upload"] = upload_check(current, item_data)
    # A confirmed Chita card requires BOTH current upload correlation and an
    # active public listing at the same assigned Avito ID, at Price=5000.
    a = summary.get("active_items", {})
    u = summary.get("current_upload", {})
    summary["chita_confirmed_active"] = bool(
        a.get("chita_candidate_active") is True
        and u.get("chita_in_current_items") is True
        and u.get("chita_section") == "success_published"
        and a.get("chita_public_ad_id") == u.get("chita_avito_id")
        and type(a.get("chita_public_ad_id")) is int)
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
