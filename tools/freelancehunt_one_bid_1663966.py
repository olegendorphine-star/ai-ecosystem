#!/usr/bin/env python3
"""Exactly-once owner-authorized bid on Freelancehunt project 1663966.

Only this project, only 5000 UAH, only a non-premium free proposal.
No bids to other projects, no emails, no paid upgrades. No retry on errors.
"""
import datetime,json,os,pathlib,sys,urllib.error,urllib.request
TOKEN=pathlib.Path.home()/".freelancehunt-agent/token"
ROOT=pathlib.Path.home()/".freelancehunt-agent"
MARKER=ROOT/"bid_1663966_attempt.json"
PROJECT="1663966"
BASE="https://api.freelancehunt.com/v2"
COMMENT=(
"Вітаю! Пропоную виконати обидві частини завдання. "
"1) Перевірю сценарії Make: тригери, вебхуки, права доступу, обробку помилок; "
"відновлю погоджену інтеграцію Instagram → SendPulse → Telegram та проведу тест. "
"2) Налаштую контент-таблицю для соцмереж (канал, текст/медіа, дата, статус, ID публікації) "
"і сценарій автопостингу із захистом від дублювання та журналом виконання. "
"Використовую Python, API, Telegram, Google Sheets та VPS у власних інженерних проєктах автоматизації. "
"Виконання — через офіційні доступні інтеграції; можливості Instagram залежать від типу акаунта та прав. "
"Для початку знадобляться доступ до потрібних сценаріїв Make через роль, інформація про облікові записи "
"SendPulse/Instagram/Telegram і приклад контент-плану. "
"Ціна — 5 000 грн за погоджений обсяг, термін — до 5 робочих днів від отримання доступів. "
"Деталі можемо узгодити текстом у чаті Freelancehunt без дзвінків."
)
def api(path,token,method="GET",data=None):
    headers={"Authorization":"Bearer "+token,"Accept":"application/json",
             "Accept-Language":"uk","User-Agent":"ai-ecosystem/1.0"}
    body=None
    if data is not None:
        headers["Content-Type"]="application/json"
        body=json.dumps(data,ensure_ascii=False).encode("utf-8")
    request=urllib.request.Request(BASE+path,headers=headers,data=body,method=method)
    try:
        with urllib.request.urlopen(request,timeout=16) as resp:
            raw=resp.read(250000)
            return resp.status,(json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code,{}
    except Exception:
        return None,{}
def marker_write(obj):
    with open(MARKER,"w",encoding="utf-8") as f:
        json.dump(obj,f,ensure_ascii=False,sort_keys=True)
        f.flush();os.fsync(f.fileno())
def stop(status,**kw):
    print("FH_BID_RESULT "+json.dumps({"project":PROJECT,"status":status,**kw},ensure_ascii=False,sort_keys=True))
def main():
    if TOKEN.is_symlink() or not TOKEN.is_file() or TOKEN.stat().st_mode&0o077:
        stop("token_unavailable");return
    if not ROOT.is_dir() or ROOT.is_symlink() or ROOT.stat().st_mode&0o077:
        stop("unsafe_root");return
    if MARKER.exists() or MARKER.is_symlink():
        stop("prior_attempt_detected_no_retry");return
    token=TOKEN.read_text(encoding="utf-8").strip()
    ps,obj=api("/projects/"+PROJECT,token)
    if ps!=200 or not isinstance(obj.get("data"),dict):
        stop("project_preflight_failed",http=ps);return
    x=obj["data"];a=x.get("attributes") or {}
    status=a.get("status") or {}
    b=a.get("budget") or {}
    if (str(x.get("id"))!=PROJECT or status.get("id")!=11 or a.get("is_premium") is not False
        or a.get("safe_type")!="employer" or b.get("amount")!=5000 or b.get("currency")!="UAH"
        or "контент-таблицю" not in str(a.get("name","")).lower()):
        stop("project_changed_no_bid");return
    try:
        deadline=datetime.datetime.fromisoformat(a["expired_at"])
        if deadline<=datetime.datetime.now(datetime.timezone.utc):
            stop("expired_no_bid");return
    except (KeyError,ValueError,TypeError):
        stop("invalid_deadline_no_bid");return
    bs,bids=api("/my/bids?filter[project_id]="+PROJECT,token)
    if bs!=200 or not isinstance(bids.get("data"),list):
        stop("bid_list_unavailable_no_bid",http=bs);return
    if bids["data"]:
        stop("already_bid_no_duplicate");return
    profile_code,profile=api("/my/profile",token)
    if profile_code!=200 or (profile.get("data") or {}).get("type")!="freelancer":
        stop("owner_not_verified_no_bid");return
    # One-shot marker created BEFORE network POST. Never retry even if HTTP timeout.
    data={
        "days":5,"safe_type":"employer",
        "budget":{"amount":5000,"currency":"UAH"},
        "comment":COMMENT,"is_hidden":False
    }
    try:
        fd=os.open(MARKER,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump({"project":PROJECT,"status":"attempt_started","never_retry":True},f)
            f.flush();os.fsync(f.fileno())
    except OSError:
        stop("marker_creation_failed_no_bid");return
    http,response=api("/projects/"+PROJECT+"/bids",token,method="POST",data=data)
    bidid=(response.get("data") or {}).get("id") if isinstance(response,dict) else None
    result={"project":PROJECT,"status":"api_accepted" if http==201 else "submission_unconfirmed",
            "http":http,"bid_id":str(bidid) if bidid else None,"never_retry":True}
    # Confirmation is read-only. On uncertain status do NOT send again.
    if http==201:
        chk,check=api("/my/bids?filter[project_id]="+PROJECT,token)
        result["readback_http"]=chk
        result["readback_found"]=bool(chk==200 and any(str((i.get("attributes") or {}).get("project",{}).get("id"))==PROJECT for i in check.get("data",[]) if isinstance(i,dict)))
        if result["readback_found"]:result["status"]="confirmed_sent"
    try:marker_write(result)
    except OSError:pass
    stop(result["status"],http=http,bid_id=result["bid_id"],readback_found=result.get("readback_found"))
if __name__=="__main__":main()
