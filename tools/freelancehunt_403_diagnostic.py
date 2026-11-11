#!/usr/bin/env python3
"""Diagnose owner VPS outbound access to Freelancehunt, read-only.

No tokens, IPs, cookies, unredacted Ray IDs, or HTML are printed. Do not
change headers to imitate clients or route traffic through other networks.
"""
import json
import pathlib
import socket
import ssl
import urllib.error
import urllib.request
from html import unescape

ROOT = pathlib.Path.home() / ".freelancehunt-agent"
TOKEN_PATH = ROOT / "token"
TESTS = (
    ("site_home", "https://freelancehunt.com/", "GET", False),
    ("site_home_head", "https://freelancehunt.com/", "HEAD", False),
    ("site_login", "https://freelancehunt.com/login", "GET", False),
    ("site_profile", "https://freelancehunt.com/my/profile", "GET", False),
    ("site_www", "https://www.freelancehunt.com/", "GET", False),
    ("site_cf_diagnostic", "https://freelancehunt.com/cdn-cgi/trace", "GET", False),
    ("api_self", "https://api.freelancehunt.com/v2/my/profile", "GET", True),
    ("control_public", "https://www.python.org/", "GET", False),
)

def dns_summary(domain):
    try:
        results = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
        families = {x[0] for x in results}
        return {"resolved": True, "ipv4": socket.AF_INET in families,
                "ipv6": socket.AF_INET6 in families}
    except Exception:
        return {"resolved": False}

def parse_response(label, url, method, use_auth, token):
    req_headers = {"Accept": "text/html,application/json",
                   "User-Agent": "FreelancehuntOwnerNetworkAudit/1.0"}
    if use_auth:
        if not token:
            return {"label":label,"status":"no_token"}
        req_headers["Authorization"] = "Bearer " + token
    request=urllib.request.Request(url,headers=req_headers,method=method)
    data=b""
    response=None
    try:
        response=urllib.request.urlopen(request,timeout=15)
        status=response.status
        data=response.read(60000) if method!="HEAD" and not use_auth else b""
    except urllib.error.HTTPError as exc:
        response=exc
        status=exc.code
        data=exc.read(60000) if method!="HEAD" and not use_auth else b""
    except ssl.SSLError:
        return {"label":label,"error":"tls_error"}
    except Exception:
        return {"label":label,"error":"connection_error"}
    headers=response.headers
    txt=unescape(data.decode("utf-8","replace")).lower()
    # Match only diagnostic phrases. Never log arbitrary page text or headers.
    flag_names={
      "sorry_blocked":"sorry, you have been blocked" in txt,
      "cloudflare_error_1020":("error 1020" in txt),
      "access_denied":("access denied" in txt),
      "attention_required":("attention required" in txt),
      "cf_branding":("cloudflare" in txt),
      "ray_in_body":("ray id" in txt),
      "challenge":("checking your browser" in txt or "just a moment" in txt),
      "country_restriction":("country" in txt and "blocked" in txt),
    }
    server=(headers.get("Server") or "").lower()
    ray=headers.get("Cf-Ray") or ""
    row={"label":label,"http":status,"server_cloudflare":"cloudflare" in server,
         "cf_ray_present":bool(ray),"cf_ray_colo":ray.split("-")[-1] if "-" in ray else None,
         "cf_mitigated":(headers.get("Cf-Mitigated") or "")[:24] or None,
         "flags":{k:v for k,v in flag_names.items() if v}}
    response.close()
    return row

def main():
    token=""
    if TOKEN_PATH.is_file() and not TOKEN_PATH.is_symlink() and (TOKEN_PATH.stat().st_mode&0o077)==0:
        token=TOKEN_PATH.read_text().strip()
    out={"schema":"fh.access.diagnostics.v1","read_only":True,"secret_printed":False,
         "dns":{s:dns_summary(s) for s in ("freelancehunt.com","www.freelancehunt.com","api.freelancehunt.com")},
         "tests":[parse_response(*test,token) for test in TESTS]}
    print(json.dumps(out,ensure_ascii=False,sort_keys=True))
if __name__=="__main__":main()
