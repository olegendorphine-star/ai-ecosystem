#!/usr/bin/env python3
"""FL003 read-only autonomous retail fallback with actual browser evidence.

Tries two public non-marketplace retailers when Ozon/Avito return HTTP 403/429.
Never pretends the retailer is Ozon/Avito and never buys, contacts anyone,
submits forms, bypasses challenges or uses authentication. No paid API calls.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA="fl003.retail.fallback.v1"
SOURCES=(
    {"shop":"MVideo","url":"https://www.mvideo.ru/products/400885231"},
    {"shop":"KNS","url":"https://www.knskrsk.ru/product/mish-logitech-910-002239/"},
)
GATES=("captcha","капча","доступ ограничен","проверяем соединение",
       "access denied","forbidden","подозрительная активность")
PRICE=re.compile(r"(?<!\d)(\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d{3,5})\s*₽")

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def amount(value):
    try:
        num=int(re.sub(r"\s","",value))
        return num if 100<=num<=20000 else None
    except (ValueError,TypeError):
        return None

def classify(shop,title,body,http_status=None):
    """Deterministic extraction from visible text of this exact product page."""
    result={"shop":shop,"status":"not_verified","price_rub":None,
            "currency":"RUB","seller":None,"availability":"not_verified",
            "source":"retailer_public_page","marketplace_name":None,
            "source_timestamp_utc":now(),"read_only":True,
            "region_specific_terms_verified":False}
    if http_status is None or http_status>=400:
        result["status"]="http_access_blocked_or_error"
        result["http_status"]=http_status
        return result
    if not isinstance(body,str) or not isinstance(title,str):
        result["status"]="invalid_page"
        return result
    lower=(title+"\n"+body[:2500]).lower()
    if any(s in lower for s in GATES):
        result["status"]="access_challenge_detected"
        return result
    if "m185" not in title.lower():
        result["status"]="different_product_or_page"
        return result
    result["product_name"]=title[:170]
    if shop=="MVideo":
        # Restrict to main pricing box BEFORE checkout. Site also shows unrelated
        # prices for accessories and recommended products farther down the page.
        m=re.search(r"войдите\s*[—\-–]?\s*цена\s+станет\s+ниже(.{0,650}?)в корзину",
                    body,flags=re.I|re.S)
        if not m:
            result["status"]="price_block_not_found"
            return result
        prices=[amount(x) for x in PRICE.findall(m.group(1))]
        prices=[v for v in prices if v is not None]
        if not prices:
            result["status"]="price_not_verified"
            return result
        result["price_rub"]=prices[0]
        result["price_method"]="public_visible_retailer_price_block"
        # Stock/delivery is tied to the product's own CTA, not recommended tiles.
        next_segment=body[m.end():m.end()+800].lower()
        if "нет в наличии" in next_segment or "товар закончился" in next_segment:
            result["availability"]="out_of_stock"
            result["status"]="not_available"
            return result
        if not ("завтра" in next_segment or "сегодня" in next_segment or
                "склад продавца" in next_segment):
            result["availability"]="delivery_unconfirmed"
            result["status"]="availability_not_verified"
            return result
        result["availability"]="order_button_with_delivery_hint"
        seller=re.search(r"(ООО\s*[«\"].{3,75}?[»\"])",next_segment,flags=re.I)
        if seller:
            result["seller"]=seller.group(1)
        # Delivery date and price may vary by ZIP / region or account.
        result["status"]="price_and_orderability_seen_on_public_page"
        return result
    if shop=="KNS":
        header=body[:2500].lower()
        if "последняя цена" in header or "нет в наличии" in header:
            result["status"]="not_available"
            result["availability"]="out_of_stock"
            return result
        m=re.search(r"цена:\s*(.{0,150}?)в корзину",body[:2500],re.I|re.S)
        if not m:
            result["status"]="price_block_not_found"
            return result
        p=[amount(x) for x in PRICE.findall(m.group(1))]
        p=[x for x in p if x is not None]
        if not p:
            result["status"]="price_not_verified"
            return result
        if "есть на складе" not in header:
            result["status"]="availability_not_verified"
            return result
        result["price_rub"]=p[-1]  # discounted final visible price, if present
        result["price_method"]="public_retailer_price_block"
        result["availability"]="stock_stated_on_public_page"
        result["status"]="price_and_orderability_seen_on_public_page"
        return result
    return result

def selftest():
    body=('Описание Logitech M185\nВойдите — цена станет ниже\n'
          '1 014 ₽   2 990 ₽ -66 %\nВ корзину\n'
          'Завтра,склад продавца\nООО "МАГ ДЕВАЙС"\nОтзывы')
    x=classify("MVideo","Мышь беспроводная Logitech M185 Black",body,200)
    assert x["price_rub"]==1014 and x["status"]=="price_and_orderability_seen_on_public_page"
    assert x["seller"]=='ООО "МАГ ДЕВАЙС"'
    y=classify("KNS","Мышь Logitech M185 Dark Blue",
               "Последняя цена: 1193 руб. Наличие: Нет в наличии",200)
    assert y["status"]=="not_available" and y["price_rub"] is None
    z=classify("MVideo","Мышь Logitech M185","Captcha — проверяем соединение",200)
    assert z["status"]=="access_challenge_detected"
    assert classify("MVideo","Другая мышь","1 014 ₽",200)["price_rub"] is None
    assert classify("MVideo","Мышь Logitech M185","",403)["status"]=="http_access_blocked_or_error"
    return {"schema":SCHEMA,"selftest":True,"outbound_messages":0}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",default="")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:
        print(json.dumps(selftest(),ensure_ascii=False))
        return
    if not args.output_dir:
        p.error("required --output-dir")
    root=Path(args.output_dir).expanduser()
    if root.is_symlink():raise ValueError("unsafe_output_symlink")
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(root,0o700)
    from playwright.sync_api import sync_playwright
    entries=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=["--no-sandbox"])
        ctx=browser.new_context(viewport={"width":1280,"height":720},
                                locale="ru-RU",timezone_id="Europe/Moscow",
                                record_video_dir=str(root))
        page=ctx.new_page()
        video=page.video
        for src in SOURCES:
            entry={"shop":src["shop"],"url":src["url"],"checked_utc":now()}
            host=urlsplit(src["url"]).hostname
            if host not in ("www.mvideo.ru","www.knskrsk.ru"):
                raise ValueError("unapproved_retailer_host")
            try:
                response=page.goto(src["url"],wait_until="domcontentloaded",timeout=18000)
                page.wait_for_timeout(2500)
                http=response.status if response else None
                title=page.locator("h1").first.inner_text(timeout=3500)[:200] \
                    if page.locator("h1").count() else ""
                body=page.locator("body").inner_text(timeout=4000)[:35000]
                details=classify(src["shop"],title,body,http)
                entry.update(details)
                if details["status"]=="price_and_orderability_seen_on_public_page":
                    page.screenshot(path=str(root/(src["shop"]+".png")),full_page=False)
                page.wait_for_timeout(1800)
            except Exception:
                entry["status"]="network_or_renderer_error"
                entry["price_rub"]=None
                entry["availability"]="unverified"
            entries.append(entry)
        page.close()
        video.save_as(str(root/"retail-fallback-browser.webm"))
        ctx.close(); browser.close()
    report={"schema":SCHEMA,"checked_utc":now(),
            "execution":"VPS Chromium read-only direct retailer pages",
            "blocked_primary_marketplaces":["Ozon","Avito"],
            "retailer_sources":entries,
            "retailer_price_verifications":sum(
                x.get("status")=="price_and_orderability_seen_on_public_page" for x in entries),
            "primary_marketplace_current_prices_verified":0,
            "fulfills_original_customer_marketplace_scope":False,
            "region_checkout_terms_verified":False,
            "external_messages_sent":0,"purchases":0,
            "user_action_requested":False,
            "recording_is_actual_browser":True}
    path=root/"report.json"
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    os.chmod(path,0o600)
    print(json.dumps({"schema":SCHEMA,
                      "retailer_statuses":[{"shop":x["shop"],"status":x.get("status"),
                                           "price_rub":x.get("price_rub")} for x in entries],
                      "primary_marketplace_current_prices_verified":0,
                      "external_messages_sent":0},ensure_ascii=False))

if __name__=="__main__":main()
