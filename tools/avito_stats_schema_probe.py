#!/usr/bin/env python3
"""Read-only Avito stats response shape inspection, without logging business data."""
import json
import os
from tools.avito_stats_access_probe import request, stats_path, IDS
from datetime import date, timedelta

SAFE_KEYS = frozenset(("result","results","items","data","stats","statistics",
 "metrics","date","dateFrom","dateTo","itemId","itemID","itemIds","id",
 "views","contacts","favorites","impressions","value","values","count",
 "total","grouping","period","periods","type","name","date","metric","group","errors","error","message","status"))
MAX_DEPTH=9

def shape(value, depth=0):
    if depth>=MAX_DEPTH:
        return "depth_limit"
    if isinstance(value,dict):
        return {"type":"object","keys":sorted(k for k in value if k in SAFE_KEYS),
                "unknown_key_count":sum(k not in SAFE_KEYS for k in value),
                "children":{k:shape(v,depth+1) for k,v in value.items()
                            if k in SAFE_KEYS and isinstance(v,(dict,list))}}
    if isinstance(value,list):
        return {"type":"array","length_band":("0" if not value else "1" if len(value)==1 else "2+"),
                "sample_shape":shape(value[0],depth+1) if value else None}
    return type(value).__name__

def main():
    if os.getenv("AVITO_ALLOW_STATS_READONLY")!="YES" or os.getenv("GITHUB_REF")!="refs/heads/main":
        print("LIVE_BLOCKED");return 2
    cid,secret=os.getenv("AVITO_CLIENT_ID"),os.getenv("AVITO_CLIENT_SECRET")
    if not cid or not secret:
        print("MISSING_SECRETS");return 3
    import urllib.parse,urllib.request
    form=urllib.parse.urlencode({"grant_type":"client_credentials","client_id":cid,"client_secret":secret}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(
            "https://api.avito.ru/token/",data=form,method="POST",
            headers={"Content-Type":"application/x-www-form-urlencoded"}),timeout=20) as resp:
            token=json.loads(resp.read(100000)).get("access_token")
    except Exception:
        print("AUTH_FAILED");return 1
    status,profile=request("/core/v1/accounts/self",token=token)
    account_id=profile.get("id",profile.get("user_id")) if isinstance(profile,dict) else None
    if status!=200 or not str(account_id).isdigit():
        print("ACCOUNT_READ_FAILED");return 1
    end=date.today()-timedelta(days=1)
    start=end-timedelta(days=6)
    requests={
        "v1":{"dateFrom":start.isoformat(),"dateTo":end.isoformat(),
              "fields":["views","contacts","favorites"],"itemIds":IDS,"periodGrouping":"day"},
        "v2":{"dateFrom":start.isoformat(),"dateTo":end.isoformat(),
              "metrics":["views","contacts","favorites","impressions"],
              "grouping":"day","filter":{"itemIDs":IDS},"limit":100}}
    result={}
    for version,payload in requests.items():
        http,data=request(stats_path(version,account_id),token=token,payload=payload)
        result[version]={"http":http,"shape":shape(data)}
    result.update(writes=0,messages_sent=0,charges_rub=0)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
