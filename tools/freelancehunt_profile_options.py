#!/usr/bin/env python3
"""One-shot capabilities probe for authorized Freelancehunt account. No writes."""
import json, pathlib, urllib.request, urllib.error
path=pathlib.Path.home()/".freelancehunt-agent/token"
if not path.is_file(): raise SystemExit("FH_TOKEN_MISSING")
token=path.read_text().strip()
base="https://api.freelancehunt.com/v2"
out={"schema":"fh.profile.methods.readonly.v1","writes":0,"responses":[]}
for endpoint in ("/my/profile","/skills"):
 for method in ("OPTIONS",):
  r={"endpoint":endpoint,"method":method}
  try:
   request=urllib.request.Request(base+endpoint,headers={"Authorization":"Bearer "+token,"Accept":"application/json","User-Agent":"FreelancehuntOwnerCapabilityCheck/1"},method=method)
   with urllib.request.urlopen(request,timeout=15) as resp:
    r["http"]=resp.status
    allow=resp.headers.get("Allow","")
    cors=resp.headers.get("Access-Control-Allow-Methods","")
    r["allow"]=allow[:120] if allow else None
    r["cors_methods"]=cors[:120] if cors else None
  except urllib.error.HTTPError as e:
   r["http"]=e.code
   r["allow"]=e.headers.get("Allow",None)
  except Exception:r["error"]="network_error"
  out["responses"].append(r)
print(json.dumps(out,sort_keys=True))
