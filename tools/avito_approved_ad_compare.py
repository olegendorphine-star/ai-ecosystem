#!/usr/bin/env python3
"""One-time read-only inspection of approved Avito listing 8347570435.
No edits, purchases, messages or uploads. Only safe comparison diagnostics.
"""
import json, os, urllib.parse, urllib.request, urllib.error, sys
BASE="https://api.avito.ru"
ID=8347570435
TITLE="Персональная ИИ-экосистема — для бизнеса и жизни"
def get(path,token):
    req=urllib.request.Request(BASE+path,headers={"Authorization":"Bearer "+token,"Accept":"application/json"},method="GET")
    try:
        with urllib.request.urlopen(req,timeout=15) as f: return f.status,json.loads(f.read(65536))
    except urllib.error.HTTPError as e:
        return e.code,None
def emit(stage,http,**fields):
    print(json.dumps(dict(stage=stage,http_status=http,changed=False,**fields),ensure_ascii=False,sort_keys=True))
def main():
    if os.getenv("AVITO_APPROVED_AD_READONLY")!="YES":
        emit("guard",None,outcome="offline")
        return 0
    creds={x:os.getenv(x,"") for x in ("AVITO_CLIENT_ID","AVITO_CLIENT_SECRET")}
    if not all(creds.values()):
        emit("guard",None,outcome="missing_secrets")
        return 2
    body=urllib.parse.urlencode(dict(grant_type="client_credentials",client_id=creds["AVITO_CLIENT_ID"],client_secret=creds["AVITO_CLIENT_SECRET"])).encode()
    req=urllib.request.Request(BASE+"/token/",data=body,headers={"Content-Type":"application/x-www-form-urlencoded"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=15) as f:
            token=json.loads(f.read(65536)).get("access_token")
            auth_status=f.status
    except urllib.error.HTTPError as e:
        emit("token",e.code)
        return 1
    if not token: emit("token",auth_status,outcome="no_token");return 1
    emit("token",auth_status,outcome="ok")
    status,profile=get("/core/v1/accounts/self",token)
    uid=profile.get("id") if isinstance(profile,dict) else None
    emit("profile",status,outcome="ok" if uid else "missing_id")
    if not isinstance(uid,int):return 1
    status,data=get("/core/v1/items?status=active&page=1&per_page=99",token)
    arr=data.get("resources",[]) if isinstance(data,dict) else []
    if isinstance(arr,dict):arr=arr.get("items",[])
    item=next((x for x in arr if isinstance(x,dict) and str(x.get("id"))==str(ID)),None) if isinstance(arr,list) else None
    emit("list",status,target_found=bool(item),title_matches=(item.get("title")==TITLE if item else None),price_present=(item.get("price") is not None if item else None))
    status,detail=get("/core/v1/accounts/%d/items/%d/"%(uid,ID),token)
    if isinstance(detail,dict):
        if isinstance(detail.get("result"),dict):detail=detail["result"]
    fields=list(detail.keys()) if isinstance(detail,dict) else []
    emit("detail",status,has_description=("description" in fields or "body" in fields),has_images=("images" in fields or "photos" in fields),has_price=("price" in fields),has_title=("title" in fields),has_status=("status" in fields))
    status,autoload=get("/autoload/v2/profile",token)
    emit("autoload_profile",status,autoload_enabled=autoload.get("autoload_enabled") if isinstance(autoload,dict) and isinstance(autoload.get("autoload_enabled"),bool) else None)
    return 0
if __name__=="__main__":
    try:sys.exit(main())
    except Exception:emit("transport",None,outcome="error");sys.exit(1)
