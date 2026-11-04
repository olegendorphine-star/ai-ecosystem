#!/usr/bin/env python3
"""Read-only, one-time per-item promotion inventory. No edits or purchases.
Only prints approved item ID, quoted ruble prices, active promotion labels/dates
and auction/CPX numbers. Never logs tokens, identifiers of account holder,
raw responses, customer data, or errors containing request credentials.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error

BASE = "https://api.avito.ru"
ITEM_ID = 8347570435
MAX_BYTES = 131072
TIMEOUT = 15

NAMES = {
    "highlight": "Выделить", "xl": "XL-объявление",
    "stickerpack_x1": "1 значок XL", "stickerpack_x2": "2 значка XL",
    "stickerpack_x3": "3 значка XL",
    "x2_1": "До 2x просмотров, 1 день", "x2_7": "До 2x просмотров, 7 дней",
    "x5_1": "До 5x просмотров, 1 день", "x5_7": "До 5x просмотров, 7 дней",
    "x10_1": "До 10x просмотров, 1 день", "x10_7": "До 10x просмотров, 7 дней",
    "x15_1": "До 15x просмотров, 1 день", "x15_7": "До 15x просмотров, 7 дней",
    "x20_1": "До 20x просмотров, 1 день", "x20_7": "До 20x просмотров, 7 дней",
}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None

OPENER = urllib.request.build_opener(NoRedirect)

def request(path, method, token=None, data=None, form=False):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    raw = None
    if data is not None:
        if form:
            raw = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            raw = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, method=method, headers=headers, data=raw)
    try:
        with OPENER.open(req, timeout=TIMEOUT) as resp:
            status, payload = resp.status, resp.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        status, payload = exc.code, exc.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        return status, None
    try:
        return status, json.loads(payload)
    except (UnicodeError, ValueError):
        return status, None

def emit(check, http, **fields):
    print(json.dumps({"check":check,"http_status":http,"changed":False,**fields},
                     sort_keys=True,ensure_ascii=False))

def safe_text(value,limit=140):
    return value[:limit] if isinstance(value,str) else None

def record_prices(status, obj):
    lines=[]
    if isinstance(obj,list):
        arr=obj
    elif isinstance(obj,dict):
        arr=obj.get("items",obj.get("resources",[]))
    else:
        arr=[]
    for item in arr if isinstance(arr,list) else []:
        if not isinstance(item,dict) or str(item.get("itemId"))!=str(ITEM_ID):
            continue
        for x in item.get("vas",[]) if isinstance(item.get("vas"),list) else []:
            if not isinstance(x,dict): continue
            slug=x.get("slug")
            if not isinstance(slug,str):continue
            lines.append({"slug":slug[:60],"name":NAMES.get(slug,"Неизвестный slug"),
                          "price_rub":x.get("price") if isinstance(x.get("price"),(int,float)) else None,
                          "old_price_rub":x.get("priceOld") if isinstance(x.get("priceOld"),(int,float)) else None})
    emit("prices",status,services=lines,listing_in_response=bool(arr),currency="RUB")

def record_active(status,obj):
    active=[]
    arr=obj.get("items",[]) if isinstance(obj,dict) else []
    for item in arr if isinstance(arr,list) else []:
        if not isinstance(item,dict) or str(item.get("itemId"))!=str(ITEM_ID):continue
        for x in item.get("services",[]) if isinstance(item.get("services"),list) else []:
            if not isinstance(x,dict): continue
            active.append({k:safe_text(x.get(k)) for k in ("slug","name","startDate","endDate")})
    emit("active",status,services=active,degraded=obj.get("degraded") if isinstance(obj,dict) else None,
         errors_count=len(obj.get("errors",[])) if isinstance(obj,dict) and isinstance(obj.get("errors"),list) else None)

def record_auction(status,obj):
    found=[]
    for x in obj.get("items",[]) if isinstance(obj,dict) and isinstance(obj.get("items"),list) else []:
        if not isinstance(x,dict) or str(x.get("itemID"))!=str(ITEM_ID):continue
        available=x.get("availablePrices")
        found.append({"current_kopeks":x.get("pricePenny"),
                      "expiration":safe_text(x.get("expirationTime")),
                      "available_kopeks":[v.get("pricePenny") for v in available if isinstance(v,dict)][:25] if isinstance(available,list) else None})
    emit("auction",status,listing=found)

def main():
    if os.environ.get("AVITO_PROMO_CATALOG_READONLY")!="YES":
        emit("guard",None,outcome="offline_only")
        return 0
    client=os.environ.get("AVITO_CLIENT_ID")
    secret=os.environ.get("AVITO_CLIENT_SECRET")
    if not client or not secret:
        emit("guard",None,outcome="missing_credentials")
        return 2
    try:
        status,body=request("/token/","POST",data={"grant_type":"client_credentials",
                   "client_id":client,"client_secret":secret},form=True)
        token=body.get("access_token") if isinstance(body,dict) else None
        emit("token",status,outcome="ok" if token else "failed")
        if status!=200 or not isinstance(token,str) or not token: return 1
        status,profile=request("/core/v1/accounts/self","GET",token)
        uid=profile.get("id") if isinstance(profile,dict) else None
        if not isinstance(uid,int):
            emit("profile",status,outcome="missing_id")
            return 1
        emit("profile",status,outcome="ok")
        checks=[
            ("prices",f"/core/v1/accounts/{uid}/vas/prices","POST",{"itemIds":[ITEM_ID]}),
            ("active","/promotion/v2/items/services/get","POST",{"itemIds":[ITEM_ID]}),
            ("auction","/auction/1/bids?fromItemID=0&batchSize=200","GET",None),
            ("cpx",f"/cpxpromo/1/getBids/{ITEM_ID}","GET",None),
            ("bbip","/promotion/v1/items/services/bbip/suggests/get","POST",{"itemIds":[ITEM_ID]}),
        ]
        for name,path,method,data in checks:
            try:
                status,obj=request(path,method,token,data)
                if name=="prices":record_prices(status,obj)
                elif name=="active":record_active(status,obj)
                elif name=="auction":record_auction(status,obj)
                elif name=="cpx":
                    emit("cpx",status,selected_type=safe_text(obj.get("selectedType")) if isinstance(obj,dict) else None,
                         action_type=obj.get("actionTypeID") if isinstance(obj,dict) else None,
                         auto_available=isinstance(obj.get("auto"),dict) if isinstance(obj,dict) else None,
                         manual_available=isinstance(obj.get("manual"),dict) if isinstance(obj,dict) else None)
                elif name=="bbip":
                    items=obj.get("items",[]) if isinstance(obj,dict) else []
                    emit("bbip",status,offers_count=len(items) if isinstance(items,list) else None)
            except Exception:
                emit(name,None,outcome="transport_or_parse_error")
        return 0
    except Exception:
        emit("bootstrap",None,outcome="safe_error")
        return 1

if __name__=="__main__":
    sys.exit(main())
