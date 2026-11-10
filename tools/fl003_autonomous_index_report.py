#!/usr/bin/env python3
"""FL-003 autonomous non-interactive marketplace research from Yandex Search API.

Pipeline: search-index evidence -> strict product-card filter -> source-labeled
comparison -> synthetic MIME + CSV/DOCX analysis -> unsent response draft ->
optional own Telegram Saved Messages status. Does not attempt CAPTCHA, auth,
purchase, third-party messaging, or label indexed prices as live verified.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from fl003_yandex_marketplace_search import is_product_card
from fl003_client_demo import create_synthetic_mail, parse_mail, draft_reply

ALLOWED = ("Ozon", "Avito")
SCHEMA = "fl003.autonomous.marketplace.report.v1"
PRICE_RE = re.compile(r"(?<!\d)(\d{2,5})(?:[ \u00a0\u202f]?)(?:₽|руб(?:лей|ля|\.|))(?=\W|$)",re.I)
STATED_LIMIT = 2000

def extract_indexed_price(snippet):
    """Only single, unqualified ruble price from text, never called live price."""
    if not isinstance(snippet,str):
        return None
    hits=[]
    for m in PRICE_RE.finditer(snippet[:1200]):
        left=snippet[max(0,m.start()-8):m.start()].lower().strip()
        if re.search(r"(?:от|до|скидк[аи])\s*$",left):
            continue
        value=int(m.group(1))
        if 100 <= value <= 20000:
            hits.append(value)
    return hits[0] if len(hits)==1 else None

def build_report(data, apish=None):
    if not isinstance(data,dict) or data.get("schema")!="fl003.yandex.search.index.v1":
        raise ValueError("not_a_yandex_fl003_search_report")
    if len(data.get("marketplaces",[])) != 2:
        raise ValueError("expected_two_marketplaces")
    try:
        checked=dt.datetime.fromisoformat(data["checked_utc"].replace("Z","+00:00"))
        if checked.tzinfo is None:
            raise ValueError
    except (ValueError,KeyError,AttributeError):
        raise ValueError("invalid_search_timestamp")
    mail=parse_mail(create_synthetic_mail())
    if len(mail["structured_requirements"])<1 or not all(
        x.get("status") in ("parsed","parsed_docx")
        for x in mail["attachments"]
    ):
        raise RuntimeError("email_fixture_parse_failed")
    products=[]
    all_counts={}
    for marketplace in ALLOWED:
        entry=next((m for m in data["marketplaces"]
                    if m.get("marketplace")==marketplace),None)
        if entry is None:
            raise ValueError("marketplace_missing")
        if entry.get("status")!="found":
            products.append({"marketplace":marketplace,"status":"search_unavailable",
                             "source":"Yandex Search API",
                             "source_checked_utc":data["checked_utc"],
                             "candidates":[]})
            all_counts[marketplace]=0
            continue
        candidates=[]
        seen=set()
        for c in entry.get("candidates",[])[:30]:
            if not isinstance(c,dict):
                continue
            url=c.get("url","")
            title=c.get("title","")
            snippet=c.get("snippet","")
            if not all(isinstance(v,str) for v in (url,title,snippet)):
                continue
            if not is_product_card(url,marketplace,title):
                continue
            if c.get("source_type")!="yandex_search_index" or c.get("live_price_verified") is not False:
                continue
            if url in seen:
                continue
            seen.add(url)
            price=extract_indexed_price(snippet)
            candidates.append({
                "marketplace":marketplace,
                "title":title[:180],"url":url[:750],
                "source":"Yandex Search API index",
                "checked_utc":data["checked_utc"],
                "indexed_price_rub":price,
                "price_status":"indexed_unverified" if price is not None else "not_found",
                "current_price_verified":False,
                "seller_verified":False,"availability_verified":False,
                "rating_verified":False,"reviews_verified":False,
                "snippet":snippet[:450],
            })
        all_counts[marketplace]=len(candidates)
        products.append({
            "marketplace":marketplace,
            "status":"index_candidates_found" if candidates else "no_product_cards",
            "source":"Yandex Search API",
            "source_checked_utc":data["checked_utc"],
            "candidates":candidates[:8],
        })
    # Optional independent Avito provider is useful only when its source
    # explicitly reports a fresh, uncached fetch; never present it as
    # directly browser-verified.
    avito_provider_offers=[]
    if isinstance(apish,dict) and apish.get("schema")=="fl003.avito.provider.search.v1" and apish.get("status")=="completed":
        fresh=apish.get("provider_recent_uncached") is True
        for c in (apish.get("listings") or [])[:20]:
            if (isinstance(c,dict) and
                is_product_card(c.get("url",""),"Avito",c.get("title","")) and
                type(c.get("price_rub")) in (int,float) and
                100<=c["price_rub"]<=20000):
                avito_provider_offers.append({
                    "url":c["url"],"title":c.get("title"),
                    "price_rub":c["price_rub"],
                    "price_status":"provider_recent_not_site_verified" if fresh else "provider_stale_or_cached",
                    "source":"API.SH Avito public listing API",
                    "source_fetched_at":apish.get("fetched_at_utc"),
                    "seller_name":c.get("seller_name"),
                    "seller_rating":c.get("seller_rating"),
                    "seller_reviews":c.get("seller_reviews"),
                    "seller_data_directly_verified":False,
                    "live_site_verified":False})
    indexed = [
        {"marketplace":group["marketplace"],"url":c["url"],
         "price_rub":c["indexed_price_rub"],"verified":False}
        for group in products for c in group["candidates"]
        if c["indexed_price_rub"] is not None
    ]
    shop={"products":[{"marketplace":g["marketplace"],
                      "status":"indexed_not_live_verified",
                      "source_url":g["candidates"][0]["url"] if g["candidates"] else "",
                      "price_rub":None}
                      for g in products]}
    reply=draft_reply(mail,shop)
    # In this autonomous mode the user is never asked to solve site challenges.
    # The shared legacy draft template references a manual browser; replace only
    # that advice with a truthful autonomous fallback statement.
    legacy="Для завершения нужна разрешённая проверка карточек в браузере; при запросе сайта — ручное участие владельца."
    replacement="Система зафиксировала ограничение доступа площадок. Ручная капча не требуется: продолжим искать доступные разрешённые источники, а непроверенные сведения не будем выдавать за актуальные."
    if legacy in reply.get("text",""):
        reply["text"]=reply["text"].replace(legacy,replacement)
    report={
        "schema":SCHEMA,
        "generated_utc":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "searched_utc":data["checked_utc"],
        "execution":"autonomous_no_user_step",
        "workstation_required":False,
        "marketplaces":products,
        "candidate_counts":all_counts,
        "indexed_price_examples":indexed[:8],
        "verified_current_prices":0,
        "provider_recent_avito_prices":sum(
            a["price_status"]=="provider_recent_not_site_verified"
            for a in avito_provider_offers),
        "avito_provider_offers":avito_provider_offers,
        "marketplace_comparison_ready":False,
        "next_action":"search_other_approved_sources_or_report_limit",
        "requires_owner_captcha":False,
        "mail":{
            "source":"synthetic_MIME_fixture_not_real_mailbox",
            "subject":mail["subject"],
            "attachments":[{"filename":a["file"],"status":a["status"]}
                           for a in mail["attachments"]],
            "requirements":mail["structured_requirements"],
            "draft_status":"created_not_sent"
        },
        "draft_reply":reply,
        "telegram": {"destination":"owner_saved_messages_only",
                     "delivery_status":"not_requested"},
        "kimi_api_called":False,
        "mailbox_connected":False,
        "client_demo_accepted":False,
        "external_messages_sent":0,"purchases":0,
    }
    return report

def owner_note(report):
    counts=report["candidate_counts"]
    first={g["marketplace"]:(g["candidates"][0]["url"] if g["candidates"] else "")
           for g in report["marketplaces"]}
    # Keep two real links if their lengths fit the explicit Telegram adapter cap.
    msg=("FL003 VPS без капчи: Яндекс нашёл Ozon "+
         str(counts["Ozon"])+", Авито "+str(counts["Avito"])+
         ". Живые цены не подтверждены (0/2). Письмо CSV/DOCX разобрано, черновик готов.")
    links="\nOzon: "+first["Ozon"]+"\nАвито: "+first["Avito"]
    if first["Ozon"] and first["Avito"] and len(msg+links)<=300:
        msg+=links
    return msg[:300]

def safe_write(path, obj):
    target=Path(path).expanduser()
    if target.is_symlink():
        raise ValueError("unsafe_output_symlink")
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    target.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf8")
    os.chmod(target,0o600)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--search-json")
    p.add_argument("--apish-json",default="")
    p.add_argument("--out")
    p.add_argument("--notify-own-telegram",action="store_true")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:
        assert extract_indexed_price("Цена 799 ₽") == 799
        assert extract_indexed_price("Цена от 799 ₽") is None
        assert extract_indexed_price("799 ₽ или 899 ₽") is None
        assert extract_indexed_price("До 2000 рублей") is None
        assert extract_indexed_price("модель M185 1000 dpi")==None
        print(json.dumps({"schema":SCHEMA,"selftest":True}))
        return
    if not args.search_json:
        raise SystemExit("missing_search_json")
    data=json.loads(Path(args.search_json).read_text(encoding="utf8"))
    provider=json.loads(Path(args.apish_json).read_text(encoding="utf8")) if args.apish_json else None
    result=build_report(data,provider)
    if args.notify_own_telegram:
        try:
            from fl003_task_engine import _telegram_socket_call
            outcome=_telegram_socket_call({
                "action":"web_self_note",
                "params":{"text":owner_note(result),"approved_by_owner":True}
            })
            status=outcome.get("status","no_status")
            result["telegram"]["delivery_status"]=str(status) if status in (
                "sent_confirmed","already_attempted_no_resend") else "not_confirmed"
        except Exception:
            result["telegram"]["delivery_status"]="not_confirmed"
    if args.out:
        safe_write(args.out,result)
        # Keep the most recent autonomous discovery as a bounded local data source
        # for the pre-existing Telegram task engine. Never write outside the
        # caller-selected private report directory.
        latest=Path(args.out).expanduser().parent/"latest.json"
        if latest != Path(args.out).expanduser():
            safe_write(latest,result)
    print(json.dumps({
        "schema":SCHEMA,
        "status":"finished_with_source_limitations",
        "counts":result["candidate_counts"],
        "indexed_prices_found":len(result["indexed_price_examples"]),
        "verified_prices":0,
        "provider_recent_avito_prices":result["provider_recent_avito_prices"],
        "mail_fixture_attachments":result["mail"]["attachments"],
        "telegram_delivery":result["telegram"]["delivery_status"],
        "client_demo_accepted":False,
        "no_human_step_requested":True,
    },ensure_ascii=False))

if __name__=="__main__":
    main()
