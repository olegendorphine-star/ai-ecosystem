#!/usr/bin/env python3
"""FL-003 Yandex web-search discovery: real source URLs, never verified live prices.

A minimal bounded API fallback when direct Ozon/Avito Chromium gets 403/439.
At most two paid synchronous Yandex Search API requests per invocation.
Never makes marketplace purchases, messages, login attempts or bypasses gates.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ENDPOINT = "https://searchapi.api.cloud.yandex.net/v2/web/search"
SOURCES = (
    ("Ozon", "site:ozon.ru/product/ Logitech M185 мышь"),
    ("Avito", "site:avito.ru Logitech M185 беспроводная мышь"),
)
DOMAIN_ALLOW = {"Ozon": ("ozon.ru",), "Avito": ("avito.ru",)}
MAX_RAW_BYTES = 3_000_000

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def domain_matches(host, names):
    return any(host == name or host.endswith("." + name) for name in names)

def is_product_card(url, marketplace, title=""):
    """Reject Avito search/category pages and Ozon non-product pages."""
    try:
        u = urllib.parse.urlsplit(url)
        host = (u.hostname or "").lower()
        if (u.scheme != "https" or not domain_matches(host, DOMAIN_ALLOW[marketplace])
                or u.username or u.password or u.port or u.query or u.fragment):
            return False
        parts = [urllib.parse.unquote(x) for x in u.path.split("/") if x]
        name = (title + " " + (parts[-1] if parts else "")).lower()
        if "m185" not in name:
            return False
        if marketplace == "Ozon":
            return (len(parts) == 2 and parts[0] == "product"
                    and re.search(r"-[0-9]{6,13}$", parts[-1]) is not None)
        if marketplace == "Avito":
            return (len(parts) == 3 and parts[1] == "tovary_dlya_kompyutera"
                    and re.search(r"_[0-9]{7,13}$", parts[-1]) is not None)
        return False
    except (ValueError, TypeError, KeyError):
        return False


def parse_xml_docs(xml_bytes, marketplace, limit=8):
    root=ET.fromstring(xml_bytes)
    results=[]
    seen=set()
    for doc in root.iter("doc"):
        url=(doc.findtext("url") or "").strip()
        try:
            parsed=urllib.parse.urlsplit(url)
        except ValueError:
            continue
        title=doc.find("title")
        # Search result markup may contain <hlword> nested emphasis.
        title_text="".join(title.itertext()) if title is not None else ""
        if not is_product_card(url, marketplace, title_text):
            continue
        if url in seen:
            continue
        seen.add(url)
        fragments=[]
        pnode=doc.find("passages")
        if pnode is not None:
            for pass_node in list(pnode)[:3]:
                fragments.append("".join(pass_node.itertext()))
        results.append({"marketplace": marketplace,
                        "url": url[:750], "title": title_text[:180],
                        "snippet": re.sub(r"\s+", " ", " ".join(fragments))[:450],
                        "source_type": "yandex_search_index",
                        "url_verified_as_product_path": True,
                        "live_price_verified": False, "availability_verified": False,
                        "seller_verified": False})
        if len(results)>=limit:
            break
    return results

def query_yandex(api_key, phrase, region="225", folder_id=""):
    payload={"query":{"searchType":"SEARCH_TYPE_RU","queryText":phrase},
             "region":region,"responseFormat":"FORMAT_XML",
             "groupSpec":{"groupMode":"GROUP_MODE_FLAT","groupsOnPage":"12","docsInGroup":"1"}}
    if folder_id:
        payload["folderId"]=folder_id
    request=urllib.request.Request(ENDPOINT,
        data=json.dumps(payload,ensure_ascii=False).encode("utf8"),
        headers={"Authorization":"Api-Key "+api_key, "Content-Type":"application/json",
                 "Accept":"application/json","User-Agent":"fl003-marketplace-discovery/1"},
        method="POST")
    with urllib.request.urlopen(request,timeout=30) as response:
        raw=response.read(MAX_RAW_BYTES+1)
    if len(raw)>MAX_RAW_BYTES:
        raise ValueError("search_response_too_large")
    data=json.loads(raw)
    if not isinstance(data,dict) or not isinstance(data.get("rawData"),str):
        raise ValueError("search_response_shape_invalid")
    xml=base64.b64decode(data["rawData"],validate=True)
    if len(xml)>MAX_RAW_BYTES:
        raise ValueError("search_xml_too_large")
    return xml

def execute(api_key,folder_id=""):
    report={"schema":"fl003.yandex.search.index.v1","checked_utc":now(),
            "marketplaces":[],"source":"Yandex Search API v2",
            "customer_demo_live_comparison_ready":False,
            "price_verification":"NOT_PERFORMED_search_index_only",
            "requests_sent":0,"max_requests":2,
            "external_messages_sent":0,"purchases":0}
    if not api_key:
        report["status"]="not_configured_api_key"
        return report
    for marketplace,phrase in SOURCES:
        item={"marketplace":marketplace,"query":phrase,"status":"unknown","candidates":[]}
        report["requests_sent"]+=1
        try:
            xml=query_yandex(api_key,phrase,folder_id=folder_id)
            candidates=parse_xml_docs(xml,marketplace)
            item["status"]="found" if candidates else "no_index_results"
            item["candidates"]=candidates
        except urllib.error.HTTPError as err:
            item["status"]="http_error"
            item["http_status"]=err.code
        except (urllib.error.URLError, TimeoutError):
            item["status"]="network_unavailable"
        except (ValueError,ET.ParseError,OverflowError,TypeError,KeyError):
            item["status"]="unexpected_response"
        report["marketplaces"].append(item)
    report["status"]="completed"
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="")
    p.add_argument("--dry-run",action="store_true")
    args=p.parse_args()
    if args.dry_run:
        assert domain_matches("www.ozon.ru",("ozon.ru",))
        assert not domain_matches("ozon.ru.evil.example",("ozon.ru",))
        assert not domain_matches("avito.ru.evil.example",("avito.ru",))
        assert is_product_card("https://www.avito.ru/ufa/tovary_dlya_kompyutera/besprovodnaya_mysh_logitech_m185_7203258990", "Avito")
        assert is_product_card("https://www.ozon.ru/product/logitech-m185-7231898/", "Ozon")
        assert not is_product_card("https://www.avito.ru/moskva/tovary_dlya_kompyutera?q=logitech+m185", "Avito")
        assert not is_product_card("https://www.avito.ru/moskva/tovary_dlya_kompyutera/klaviatury_i_myshi-ASgBAgICAUTGB7xO", "Avito")
        assert not is_product_card("https://www.ozon.ru/category/m185-logitech/", "Ozon")
        print(json.dumps({"selftest":True,"max_requests":2}))
        return
    report=execute(os.getenv("YANDEX_FL003_API_KEY",""),os.getenv("YANDEX_FL003_FOLDER_ID",""))
    if args.out:
        path=Path(args.out).expanduser()
        if path.is_symlink():
            raise ValueError("unsafe_report_symlink")
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    summary={k:report[k] for k in ("schema","status","checked_utc","source","requests_sent")}
    summary["marketplaces"]=[{"name":x["marketplace"],"status":x["status"],
                               "candidates":len(x["candidates"]),
                               "http_status":x.get("http_status")} for x in report["marketplaces"]]
    print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":
    main()
