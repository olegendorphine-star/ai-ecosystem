#!/usr/bin/env python3
"""Safe v1 daily views report: only public listing IDs and aggregated view counts."""
import json
import os
from datetime import date, timedelta
from tools.avito_stats_access_probe import IDS, request, stats_path

CITIES={8347570435:"Москва",8477159401:"Санкт-Петербург",8531755111:"Сургут",8414224003:"Чита"}

def summarize(payload):
    result=payload.get("result") if isinstance(payload,dict) else None
    items=result.get("items") if isinstance(result,dict) else None
    if not isinstance(items,list):
        raise ValueError("Missing result.items")
    report={str(k):{"city":v,"days":0,"views":0,"daily":{}} for k,v in CITIES.items()}
    for item in items:
        if not isinstance(item,dict):
            raise ValueError("Malformed item")
        ident=item.get("itemId")
        if str(ident) not in report:
            continue
        stats=item.get("stats")
        if not isinstance(stats,list):
            raise ValueError("Missing stats")
        seen=set()
        for point in stats:
            if not isinstance(point,dict):
                raise ValueError("Malformed point")
            day=point.get("date")
            views=point.get("views")
            if not isinstance(day,str) or not isinstance(views,int) or isinstance(views,bool) or views<0:
                raise ValueError("Missing or invalid daily views")
            try:
                normalized=date.fromisoformat(day).isoformat()
            except ValueError:
                raise ValueError("Invalid date")
            if normalized!=day or day in seen:
                raise ValueError("Duplicate or invalid date")
            seen.add(day)
            report[str(ident)]["days"]+=1
            report[str(ident)]["views"]+=views
            report[str(ident)]["daily"][day]=views
    return report


def main():
    if os.getenv("AVITO_ALLOW_STATS_READONLY")!="YES" or os.getenv("GITHUB_REF")!="refs/heads/main":
        print("LIVE_BLOCKED");return 2
    import urllib.request,urllib.parse
    cid,secret=os.getenv("AVITO_CLIENT_ID"),os.getenv("AVITO_CLIENT_SECRET")
    if not cid or not secret:
        print("MISSING_SECRETS");return 3
    form=urllib.parse.urlencode({"grant_type":"client_credentials","client_id":cid,"client_secret":secret}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.avito.ru/token/",data=form,method="POST",
            headers={"Content-Type":"application/x-www-form-urlencoded"}),timeout=20) as resp:
            token=json.loads(resp.read(100000))["access_token"]
    except Exception:
        print("AUTH_FAILED");return 1
    status,account=request("/core/v1/accounts/self",token=token)
    account_id=account.get("id",account.get("user_id")) if isinstance(account,dict) else None
    if status!=200 or not str(account_id).isdigit():
        print("ACCOUNT_READ_FAILED");return 1
    end=date.today()-timedelta(days=1)
    start=end-timedelta(days=6)
    payload={"dateFrom":start.isoformat(),"dateTo":end.isoformat(),
             "fields":["views","contacts","favorites"],"itemIds":IDS,"periodGrouping":"day"}
    status,data=request(stats_path("v1",account_id),token=token,payload=payload)
    if status!=200:
        print(json.dumps({"stats_http":status,"report":None}))
        return 1
    try:
        summary=summarize(data)
    except ValueError:
        print("UNSUPPORTED_RESPONSE_SCHEMA");return 1
    output={"period":{"from":start.isoformat(),"to":end.isoformat()},
          "source":"avito_stats_v1","stats_http":status,"views_by_listing":summary,
          "contacts":None,"impressions":None,"writes":0,"charges_rub":0}
    if os.getenv("AVITO_STATS_REPORT_FILE"):
        from pathlib import Path
        dest=Path(os.environ["AVITO_STATS_REPORT_FILE"])
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(output,ensure_ascii=False,sort_keys=True)+"\\n",encoding="utf-8")
    print(json.dumps(output,ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
