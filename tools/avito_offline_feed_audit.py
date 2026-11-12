#!/usr/bin/env python3
"""Offline-only audit of the four-city Avito XML feed. No network or writes."""
from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "ai-assistant-memory-moscow-001": "Москва",
    "ai-assistant-memory-spb-001": "Санкт-Петербург",
    "ai-assistant-memory-surgut-001": "Сургут",
    "ai-assistant-memory-chita-001": "Чита",
}
EXPECTED_PRICES = [5000, 30000, 150000]


def audit(xml_data: bytes) -> dict:
    root = ET.fromstring(xml_data)
    if root.tag != "Ads":
        raise ValueError("Root element must be Ads")
    records = []
    issues = []
    seen = set()
    for ad in root.findall("Ad"):
        ident = ad.findtext("Id", "").strip()
        if not ident or ident in seen:
            issues.append("missing_or_duplicate_id")
        seen.add(ident)
        city = ad.findtext("Address", "").strip()
        if EXPECTED.get(ident) != city:
            issues.append("unexpected_id_or_city")
        prices = []
        for el in ad.findall("./PriceList/Service/ServicePrice"):
            try:
                prices.append(int((el.text or "").strip()))
            except ValueError:
                issues.append("invalid_service_price")
        if prices != EXPECTED_PRICES:
            issues.append("unexpected_price_tiers")
        image_count = len(ad.findall("./Images/Image"))
        if image_count != 6:
            issues.append("unexpected_image_count")
        category = {key: ad.findtext(key, "") for key in (
            "Category", "ServiceType", "ServiceSubtype",
            "ServiceSubspecies", "Specialty", "WorkingWithAI")}
        records.append({
            "id": ident, "city": city, "title": ad.findtext("Title", ""),
            "category": category, "image_count": image_count,
            "price_tiers_rub": prices,
        })
    if set(seen) != set(EXPECTED) or len(records) != len(EXPECTED):
        issues.append("expected_exactly_four_known_ads")
    return {
        "schema": "avito.offline-feed-audit.v1",
        "ad_count": len(records),
        "ads": records,
        "issues": sorted(set(issues)),
        "safe_to_propose_migration": False,
        "reason": "Full AI category enumerations and published-card categories are not verified",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=Path("docs/avito-feed.xml"))
    args = parser.parse_args()
    result = audit(args.feed.read_bytes())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
