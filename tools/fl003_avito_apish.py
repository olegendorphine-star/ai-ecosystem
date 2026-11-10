#!/usr/bin/env python3
"""Optional API.SH Avito research adapter for FL-003.

Does not call the provider unless a key and explicit ENABLED=1 are supplied.
Uses read-only search API, enforces public Avito listing URLs and realistic
Logitech M185 prices; includes provenance and does not claim Ozon coverage.
No purchases/messages/logins, safe for no-key CI.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENDPOINT="https://api.api.sh/avito/v1/search"
SCHEMA="fl003.avito.provider.search.v1"
LISTING_RE=re.compile(r"^/[a-z0-9_-]+/tovary_dlya_kompyutera/[a-z0-9_-]*m185[a-z0-9_-]*_[0-9]{7,13}$",re.I)

def allowed(url):
    if not isinstance(url,str) or len(url)>1000:
        return False
    try:
        p=urllib.parse.urlsplit(url)
        return (p.scheme=="https" and p.hostname in ("www.avito.ru","avito.ru") and
                not p.username and not p.password and p.port is None and
                bool(LISTING_RE.fullmatch(p.path)))
    except ValueError:
        return False

def parse_reviews_count(seller):
    """Provider's documented field is reviews_text, e.g. '3 930 отзывов'."""
    if not isinstance(seller,dict):
        return None
    direct=seller.get("reviews")
    if type(direct) is int and 0<=direct<=10_000_000:
        return direct
    value=seller.get("reviews_text")
    if not isinstance(value,str) or len(value)>100:
        return None
    found=re.search(r"(\\d[\\d\\s\\u00a0\\u202f]{0,16})\\s+отзыв",value,re.I)
    if not found:
        return None
    try:
        n=int(re.sub(r"\\s","",found.group(1)))
        return n if 0<=n<=10_000_000 else None
    except ValueError:
        return None

def parse_response(data, now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(data,dict) or data.get("success") is False:
        raise ValueError("invalid_provider_response")
    when=data.get("fetched_at")
    try:
        parsed=dt.datetime.fromisoformat(str(when).replace("Z","+00:00"))
        if parsed.tzinfo is None: raise ValueError
        age=(now-parsed.astimezone(dt.timezone.utc)).total_seconds()
    except (ValueError,TypeError):
        age=None
    is_fresh=(age is not None and -120<=age<=3600 and data.get("cached") is False)
    result={"schema":SCHEMA,"source":"API.SH Avito public listings",
            "fetched_at_utc":when, "cached":data.get("cached"),
            "provider_recent_uncached":is_fresh,
            "live_avito_page_verified":False,"cost_credits":data.get("credits_used"),
            "listings":[]}
    for item in (data.get("listings") or [])[:50]:
        if not isinstance(item,dict) or not allowed(item.get("url")):continue
        if "m185" not in str(item.get("title","")).lower():continue
        price=item.get("price")
        if type(price) not in (int,float) or not 100<=price<=20000:continue
        if item.get("currency")!="RUB":continue
        seller=item.get("seller") or {}
        if not isinstance(seller,dict):seller={}
        result["listings"].append({
            "marketplace":"Avito","url":item["url"],"title":str(item["title"])[:180],
            "price_rub":price,"price_status":"provider_fresh" if is_fresh else "provider_unconfirmed_freshness",
            "source":"API.SH","fetched_at_utc":when,
            "actual_avito_page_verified":False,
            "condition":str(item.get("params") or "")[:200],
            "condition_new_confirmed":bool(re.search(r"\\b(новый|новая|новое|new)\\b",str(item.get("params") or ""),re.I)),
            "seller_name":str(seller.get("name") or "")[:80] or None,
            "seller_rating":seller.get("rating") if type(seller.get("rating")) in (float,int) else None,
            "seller_reviews":parse_reviews_count(seller),
            "delivery":item.get("delivery") if type(item.get("delivery")) is bool else None,
        })
    return result

def query(key):
    params={"q":"Logitech M185","location":"rossiya","category":"tovary_dlya_kompyutera",
            "price_max":"2000","page":"1"}
    req=urllib.request.Request(ENDPOINT+"?"+urllib.parse.urlencode(params),
        headers={"x-api-key":key,"Accept":"application/json",
                 "User-Agent":"FL003-data-research/1.0"})
    with urllib.request.urlopen(req,timeout=60) as res:
        payload=res.read(2_000_001)
    if len(payload)>2_000_000:raise ValueError("provider_response_too_large")
    return json.loads(payload)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:
        assert allowed("https://www.avito.ru/ufa/tovary_dlya_kompyutera/mysh_logitech_m185_7203258990")
        assert not allowed("https://www.avito.ru.evil.example/ufa/tovary_dlya_kompyutera/mysh_m185_7203258990")
        assert not allowed("https://www.avito.ru/ufa/tovary_dlya_kompyutera?q=m185")
        sample={"cached":False,"fetched_at":"2026-11-11T00:00:00Z","credits_used":5,
                "listings":[{"title":"Logitech M185","url":"https://www.avito.ru/ufa/tovary_dlya_kompyutera/mysh_m185_7203258990",
                             "price":690,"currency":"RUB","seller":{"name":"магазин","rating":4.9,"reviews":12}}]}
        report=parse_response(sample,now=dt.datetime(2026,11,11,tzinfo=dt.timezone.utc))
        assert report["listings"][0]["price_rub"]==690
        assert report["listings"][0]["price_status"]=="provider_fresh"
        assert report["live_avito_page_verified"] is False
        assert parse_reviews_count({"reviews_text":"3 930 отзывов"}) == 3930
        assert parse_reviews_count({"reviews_text":"отзывы неизвестны"}) is None
        assert parse_reviews_count({"reviews_text":"15 отзывов"}) == 15
        print(json.dumps({"selftest":True,"schema":SCHEMA}))
        return
    key=os.environ.get("FL003_APISH_KEY","")
    if os.environ.get("FL003_APISH_ENABLED")!="1" or not key:
        result={"schema":SCHEMA,"status":"disabled_no_approved_access",
                "listings":[],"outbound_requests":0}
    else:
        try:
            result=parse_response(query(key))
            result["status"]="completed"
            result["outbound_requests"]=1
        except urllib.error.HTTPError as ex:
            result={"schema":SCHEMA,"status":"provider_http_error",
                    "http_status":ex.code,"listings":[],"outbound_requests":1}
        except (urllib.error.URLError,TimeoutError,ValueError,TypeError,KeyError):
            result={"schema":SCHEMA,"status":"provider_unavailable",
                    "listings":[],"outbound_requests":1}
    if args.out:
        path=Path(args.out).expanduser()
        if path.is_symlink():raise ValueError("unsafe_report_symlink")
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({k:result.get(k) for k in
        ("schema","status","outbound_requests","http_status")},
        ensure_ascii=False))
if __name__=="__main__":main()
