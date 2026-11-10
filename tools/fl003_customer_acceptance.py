#!/usr/bin/env python3
"""FL-003 customer-facing demo acceptance. Fail closed; never invent evidence.

This reads only the real VPS run JSON. It does not contact people, websites,
Telegram, or paid services. GitHub technical success != client acceptance.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from pathlib import Path

SCHEMA="fl003.customer.acceptance.v1"

def assess(report):
    if not isinstance(report,dict) or report.get("schema")!="fl003.real.vps.screencast.v1":
        raise ValueError("unexpected_server_report")
    reasons=[]
    products=report.get("products")
    if not isinstance(products,list):
        products=[]
    by_market={}
    for obj in products:
        if isinstance(obj,dict) and obj.get("marketplace") in ("Ozon","Avito"):
            by_market[obj["marketplace"]]=obj
    for market in ("Ozon","Avito"):
        obj=by_market.get(market)
        if not obj:
            reasons.append(market+":missing_browser_card")
            continue
        status=obj.get("http_status")
        if status in (401,403,429,439):
            reasons.append(market+":site_access_denied_http_"+str(status))
        elif obj.get("status")!="verified_price_and_card":
            reasons.append(market+":live_card_not_verified")
        price=obj.get("price_rub")
        if (type(price) not in (int,float) or not math.isfinite(price)
                or not 1<=price<=200000):
            reasons.append(market+":current_price_not_verified")
        title=(obj.get("title") or "").lower()
        if "m185" not in title:
            reasons.append(market+":product_model_not_verified")
        # This is the actual advertised comparison, not merely two prices.
        if not (isinstance(obj.get("seller"),str) and obj["seller"].strip()):
            reasons.append(market+":seller_not_verified")
        if (type(obj.get("rating")) not in (float,int) or
                not 0<=obj["rating"]<=5):
            reasons.append(market+":rating_not_verified")
        if (type(obj.get("review_count")) is not int or
                obj["review_count"]<0):
            reasons.append(market+":reviews_not_verified")
    mail=report.get("mail") or {}
    statuses=mail.get("attachment_statuses") or []
    if not ("parsed" in statuses and "parsed_docx" in statuses):
        reasons.append("mail:attachments_not_processed")
    if not (report.get("mailbox_connected") is True):
        reasons.append("mail:live_server_mailbox_not_connected")
    if not (report.get("telegram_connected") is True):
        reasons.append("telegram:owner_command_transport_not_proven_in_video")
    if not (report.get("kimi_api_called") is True):
        reasons.append("ai:live_agent_model_execution_not_proven")
    if not (report.get("browser_on_vps") is True and
            report.get("recording_is_real_browser_session") is True):
        reasons.append("video:real_vps_browser_not_proven")
    if not (mail.get("draft_created") is True and mail.get("draft_sent") is False):
        reasons.append("mail:unsent_reply_draft_not_proven")
    reasons=sorted(set(reasons))
    return {
        "schema":SCHEMA,
        "customer_deliverable_ready":len(reasons)==0,
        "customer_delivery_permitted":len(reasons)==0,
        "technical_recording_only":len(reasons)>0,
        "verified_marketplaces":sum(
            m in by_market and by_market[m].get("status")=="verified_price_and_card"
            for m in ("Ozon","Avito")),
        "blocking_reasons":reasons,
        "messages_sent_by_validator":0,
    }

def selftest():
    base={"schema":"fl003.real.vps.screencast.v1",
          "browser_on_vps":True,"recording_is_real_browser_session":True,
          "products":[{"marketplace":"Ozon","http_status":403,
                       "status":"site_access_or_human_login_required"},
                      {"marketplace":"Avito","http_status":429,
                       "status":"site_access_or_human_login_required"}],
          "mail":{"attachment_statuses":["parsed","parsed_docx"],
                  "draft_created":True,"draft_sent":False},
          "mailbox_connected":False,"telegram_connected":False,
          "kimi_api_called":False}
    result=assess(base)
    assert result["customer_deliverable_ready"] is False
    assert "Ozon:site_access_denied_http_403" in result["blocking_reasons"]
    assert "Avito:site_access_denied_http_429" in result["blocking_reasons"]
    assert "mail:live_server_mailbox_not_connected" in result["blocking_reasons"]
    assert result["messages_sent_by_validator"]==0
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--out")
    parser.add_argument("--selftest",action="store_true")
    args=parser.parse_args()
    if args.selftest:
        print(json.dumps({"selftest_passed":True,
                          "blocked_reasons":selftest()["blocking_reasons"]},
                          ensure_ascii=False))
        return
    if not args.input or not args.out:
        parser.error("required: --input and --out")
    data=json.loads(Path(args.input).read_text(encoding="utf8"))
    result=assess(data)
    output=Path(args.out)
    if output.is_symlink():raise ValueError("unsafe_output_symlink")
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({
        "customer_deliverable_ready":result["customer_deliverable_ready"],
        "blocking_reasons":result["blocking_reasons"],
        "disposition":"NOT_FOR_CLIENT" if result["technical_recording_only"] else "READY_FOR_FINAL_VISUAL_REVIEW"
    },ensure_ascii=False))
if __name__=="__main__":
    main()
