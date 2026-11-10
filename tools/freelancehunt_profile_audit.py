#!/usr/bin/env python3
"""Minimal privacy-preserving Freelancehunt profile audit, no raw data saved."""
import json,os,pathlib,stat,sys,urllib.error,urllib.request
PATH=pathlib.Path.home()/".freelancehunt-agent"/"token"
def run():
    if not PATH.is_file() or PATH.is_symlink() or PATH.stat().st_mode&0o077:
        print("FH_AUDIT_TOKEN_UNAVAILABLE");return 2
    token=PATH.read_text().strip()
    req=urllib.request.Request("https://api.freelancehunt.com/v2/my/profile",headers={"Authorization":"Bearer "+token,"Accept":"application/json","Accept-Language":"ru"},method="GET")
    try:
        with urllib.request.urlopen(req,timeout=15) as response:
            obj=json.load(response)
            print("FH_PROFILE_HTTP",response.status)
    except urllib.error.HTTPError as e:
        print("FH_PROFILE_HTTP",e.code);return 1
    except Exception:
        print("FH_PROFILE_NETWORK_ERROR");return 1
    data=obj.get("data",{})
    if not isinstance(data,dict):print("FH_PROFILE_INVALID_SCHEMA");return 1
    att=data.get("attributes",{})
    print("FH_PROFILE_TYPE",str(data.get("type","unknown"))[:60])
    if not isinstance(att,dict):att={}
    print("FH_PROFILE_ATTRIBUTE_KEYS",json.dumps(sorted(att.keys()),ensure_ascii=False))
    # Do not print attribute values or name/login/email. Summarize only completeness.
    for name in ("first_name","last_name","avatar","location","cv","cv_html","headline","title","about","bio","description","description_html","skills","specializations","categories","portfolio","snippet_count","status","verification","is_verified","verified","profile_completed","is_active"):
        if name not in att:continue
        v=att[name]
        if isinstance(v,str):vstate="filled" if v.strip() else "empty"
        elif isinstance(v,(list,dict)):vstate="filled" if v else "empty"
        elif isinstance(v,bool):vstate="true" if v else "false"
        else:vstate="set" if v is not None else "empty"
        print("FH_FIELD",name,vstate)
    rel=data.get("relationships",{})
    if isinstance(rel,dict):print("FH_PROFILE_RELATIONSHIP_KEYS",json.dumps(sorted(rel.keys()),ensure_ascii=False))
    # Check unauthenticated website access without logging cookies or page contents.
    for url in ("https://freelancehunt.com/my/profile","https://freelancehunt.com/login"):
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req,timeout=12) as r:status=r.status
        except urllib.error.HTTPError as e:status=e.code
        except Exception:status="network_error"
        print("FH_WEB_STATUS", "/my/profile" if "/my/profile" in url else "/login",status)
    return 0
if __name__=="__main__":sys.exit(run())
