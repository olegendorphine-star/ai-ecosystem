#!/usr/bin/env python3
"""FL-003: compare public product access from independent GitHub runner egress.

A bounded diagnostic, not a scraper or customer demonstration. Never logs in,
submits forms, solves challenges, pays, sends messages or modifies accounts.
Even HTTP 200 is not accepted without identifying a real product page.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

TARGETS=(
    ("Ozon","https://www.ozon.ru/product/logitech-m185-m186-besprovodnaya-mysh-seraya-7231898/"),
    ("Avito","https://www.avito.ru/ufa/tovary_dlya_kompyutera/besprovodnaya_mysh_logitech_m185_7203258990"),
    ("MVideo","https://www.mvideo.ru/products/400885231"),
)
SCHEMA="fl003.marketplace.egress.v1"
ALLOW_HOSTS={"www.ozon.ru","www.avito.ru","www.mvideo.ru"}
BLOCK_MARKERS=(
    "checking your browser", "access denied", "доступ ограничен",
    "проверяем соединение", "временно усилена защита", "captcha",
    "подозрительная активность", "вы не робот", "слишком много запросов",
    "request was blocked", "your request has been blocked",
)

def valid_destination(url):
    try:
        p=urlsplit(url)
        return (p.scheme=="https" and p.hostname in ALLOW_HOSTS and
                p.username is None and p.password is None and p.port is None and
                p.query=="" and p.fragment=="" and len(p.path)<350)
    except ValueError:
        return False

def classify(title,body,http_status):
    if type(http_status) is not int or http_status>=400:
        return "http_error"
    if not isinstance(body,str) or not isinstance(title,str):
        return "invalid_document"
    low=(title+"\n"+body[:2500]).lower()
    if any(marker in low for marker in BLOCK_MARKERS):
        return "challenge_or_blocked"
    # Genuine M185 h1 is essential: "product title" elsewhere may be
    # unrelated recommendations, or the site homepage.
    if "m185" not in title.lower():
        return "not_target_product"
    if len(body)<120:
        return "empty_product_document"
    return "target_product_page_rendered"

def probe(output):
    from playwright.sync_api import sync_playwright
    out=Path(output)
    if out.is_symlink():
        raise ValueError("unsafe_output_symlink")
    out.mkdir(parents=True,exist_ok=True)
    results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
        try:
            for name,url in TARGETS:
                if not valid_destination(url):
                    raise ValueError("disallowed_destination")
                page=browser.new_page(viewport={"width":1280,"height":720},
                                      locale="ru-RU",timezone_id="Europe/Moscow")
                entry={"marketplace":name,"url":url,
                       "checked_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
                       "browser_location":"GitHub-hosted Ubuntu runner",
                       "account_login":False}
                try:
                    response=page.goto(url,wait_until="domcontentloaded",timeout=18000)
                    page.wait_for_timeout(1300)
                    code=response.status if response else None
                    title=(page.locator("h1").first.inner_text(timeout=2200)
                           if page.locator("h1").count() else "")
                    body=page.locator("body").inner_text(timeout=2200)
                    state=classify(title,body,code)
                    entry.update({"http_status":code,"page_status":state,
                                  "h1":title[:130] if state=="target_product_page_rendered" else None})
                    if state=="target_product_page_rendered":
                        shot=out/(name.lower()+".png")
                        page.screenshot(path=str(shot),full_page=False)
                        entry["screenshot_file"]=shot.name
                except Exception:
                    entry.update({"page_status":"timeout_or_navigation_error",
                                  "http_status":None})
                finally:
                    results.append(entry)
                    page.close()
        finally:
            browser.close()
    data={"schema":SCHEMA,
          "requests_limit":len(TARGETS),
          "all_targets_static_allowlisted":True,
          "outbound_messages_sent":0,"purchases":0,
          "actual_marketplace_prices_verified":0,
          "sites":results}
    (out/"report.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf8")
    return data

def selftest():
    assert all(valid_destination(url) for _,url in TARGETS)
    assert not valid_destination("https://www.avito.ru.evil.example/item")
    assert not valid_destination("http://www.ozon.ru/product/test")
    assert classify("Мышь Logitech M185", "Актуальная карточка мыши"+" ."*200,200)=="target_product_page_rendered"
    assert classify("Мышь Logitech M185","Проверяем соединение",200)=="challenge_or_blocked"
    assert classify("Мышь Logitech M185","",403)=="http_error"
    assert classify("404 страница", "M185 рекомендуем купить"+" ."*400,200)=="not_target_product"
    return {"schema":SCHEMA,"selftest":True}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out-dir")
    a=p.parse_args()
    if a.selftest:
        print(json.dumps(selftest(),ensure_ascii=False))
        return
    if not a.out_dir:
        p.error("--out-dir required")
    data=probe(a.out_dir)
    print(json.dumps({"schema":SCHEMA,"sites":[
        {"marketplace":x["marketplace"],"status":x["page_status"],
         "http_status":x["http_status"]} for x in data["sites"]],
        "outbound_messages_sent":0},ensure_ascii=False))

if __name__=="__main__":
    main()
