#!/usr/bin/env python3
"""Preflight two project bids against the user's existing Freelancerhunt account. GET only."""
import json,pathlib,urllib.request,urllib.error
TOK=pathlib.Path.home()/".freelancehunt-agent/token"
BASE="https://api.freelancehunt.com/v2"
IDS=("1663966","1664046")
def get(path,token):
 r=urllib.request.Request(BASE+path,headers={"Authorization":"Bearer "+token,"Accept":"application/json","Accept-Language":"ru"},method="GET")
 try:
  with urllib.request.urlopen(r,timeout=17) as q:return json.load(q)
 except urllib.error.HTTPError as e:raise RuntimeError("http_"+str(e.code)) from None
def main():
 if not TOK.is_file() or TOK.is_symlink() or TOK.stat().st_mode&0o077:print("FH_PREFLIGHT_TOKEN_UNAVAILABLE");return
 token=TOK.read_text().strip()
 out={"schema":"fh.bid.preflight.v1","write_actions":False,"projects":[],"profile":{}}
 p=get("/my/profile",token).get("data",{}).get("attributes",{})
 if isinstance(p,dict):
  out["profile"]={"skills_count":len(p.get("skills") or []),"plus_active":p.get("is_plus_active"),"verification_type":type(p.get("verification")).__name__}
 for id in IDS:
  x=get("/projects/"+id,token)
  a=x.get("data",{}).get("attributes",{})
  try:
   b=get("/my/bids?filter[project_id]="+id,token)
   already=len(b.get("data",[]))>0
  except RuntimeError:
   already="unknown"
  out["projects"].append({"id":id,"title":a.get("name"),"description":a.get("description"),
   "status":a.get("status"),"budget":a.get("budget"),"safe_type":a.get("safe_type"),
   "is_premium":a.get("is_premium"),"bid_count":a.get("bid_count"),"expired_at":a.get("expired_at"),
   "published_at":a.get("published_at"),"already_bid":already,"skills":a.get("skills")})
 print("FH_BID_PREFLIGHT "+json.dumps(out,ensure_ascii=False,sort_keys=True))
if __name__=="__main__":main()
