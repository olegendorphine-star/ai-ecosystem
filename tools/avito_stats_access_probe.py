#!/usr/bin/env python3
"""One-shot Avito statistics access probe. Prints HTTP statuses only, never response data."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE = "https://api.avito.ru"
IDS = [8347570435,8477159401,8531755111,8414224003]
READ_ONLY_POST_PATHS = {"/stats/v1/accounts/{id}/items", "/stats/v2/accounts/{id}/items"}


def request(path, *, token=None, payload=None):
    headers = {"Accept":"application/json","User-Agent":"AvitoStatsReadOnlyProbe/1.0"}
    data = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, headers=headers, data=data,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req,timeout=20) as resp:
            body = resp.read(100000)
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except (urllib.error.URLError,TimeoutError,OSError,ValueError):
        return None, {}


def stats_path(version, account_id):
    if version not in ("v1","v2") or not str(account_id).isdigit():
        raise ValueError("Invalid endpoint")
    path = f"/stats/{version}/accounts/{account_id}/items"
    if path.replace(str(account_id),"{id}") not in READ_ONLY_POST_PATHS:
        raise ValueError("Non-read-only path")
    return path


def main():
    if (os.getenv("AVITO_ALLOW_STATS_READONLY") != "YES" or
            os.getenv("GITHUB_REF") != "refs/heads/main"):
        print("LIVE_BLOCKED")
        return 2
    cid,secret = os.getenv("AVITO_CLIENT_ID"),os.getenv("AVITO_CLIENT_SECRET")
    if not cid or not secret:
        print("MISSING_SECRETS")
        return 3
    form = urllib.parse.urlencode({"grant_type":"client_credentials",
                                   "client_id":cid,"client_secret":secret}).encode()
    req = urllib.request.Request(BASE+"/token/",data=form,method="POST",
          headers={"Content-Type":"application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req,timeout=20) as resp:
            token = json.loads(resp.read(100000)).get("access_token")
            auth_status = resp.status
    except urllib.error.HTTPError as exc:
        token,auth_status = None,exc.code
    except (urllib.error.URLError,OSError,TimeoutError,ValueError):
        token,auth_status = None,None
    report = {"oauth_http":auth_status,"stats_v1_http":None,"stats_v2_http":None,
              "writes":0,"messages_sent":0,"charges_rub":0}
    if not token:
        print(json.dumps(report))
        return 1
    account_status,profile = request("/core/v1/accounts/self",token=token)
    report["account_http"] = account_status
    account_id = profile.get("id") if isinstance(profile,dict) else None
    if account_id is None and isinstance(profile,dict):
        account_id = profile.get("user_id")
    if not str(account_id).isdigit():
        report["account_id_available"] = False
        print(json.dumps(report))
        return 1
    report["account_id_available"] = True
    end = date.today()-timedelta(days=1)
    start = end-timedelta(days=6)
    v1 = {"dateFrom":start.isoformat(),"dateTo":end.isoformat(),
          "fields":["views","contacts","favorites"],"itemIds":IDS,
          "periodGrouping":"day"}
    v2 = {"dateFrom":start.isoformat(),"dateTo":end.isoformat(),
          "metrics":["views","contacts","favorites","impressions"],
          "grouping":"day","filter":{"itemIDs":IDS},"limit":100}
    report["stats_v1_http"],_ = request(stats_path("v1",account_id),token=token,payload=v1)
    report["stats_v2_http"],_ = request(stats_path("v2",account_id),token=token,payload=v2)
    print(json.dumps(report,sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
