#!/usr/bin/env python3
"""One-off, read-only Freelancehunt project scout for owner account.

Uses already-present VPS token; never sends bids. Only public project text
and URLs are printed. The site owner has deprecated the API: any HTTP error
must be treated as a stop condition, never retried aggressively.
"""
import html,json,pathlib,re,sys,time,urllib.error,urllib.parse,urllib.request
ROOT=pathlib.Path.home()/".freelancehunt-agent"
TOK=ROOT/"token"
BASE="https://api.freelancehunt.com/v2"
TERMS={
 "розробка бота":12,"бота":7,"штучн":6,"інтеграц":7,"автоматизац":9,
 "ии":8,"ai":6,"нейросет":6,"искусственн":6,"автоматизац":9,
 "automation":7,"integration":6,"интеграц":7,"telegram":7,"телеграм":7,
 "bot":4,"бот":4,"api":6,"python":6,"таблиц":5,"sheets":6,
 "google":4,"n8n":7,"llm":8,"rag":7,"ассистент":7,
 "парсинг":3,"аналитик":4,"dashboard":4,"crm":4,"webhook":5,
 "чатбот":4,"чат-бот":4,"агент":5,"синхронизац":5,
}
NEGATIVE={"маркетинг":-8,"таргет":-12,"реклам":-8,"логотип":-10,"сайту":-3,"магазин":-4,"дизайн":-7,"figma":-7,"верстк":-5,"звон":-7,"созвон":-10,
          "вордпресс":-5,"wordpress":-5,"seo":-3,"youtube":-3,"видео":-4}
def clean(v):
    t=re.sub(r"<[^>]*>"," ",str(v or ""))
    t=html.unescape(t)
    return " ".join(t.split())
def request(path,token):
    req=urllib.request.Request(BASE+path,headers={
        "Authorization":"Bearer "+token,"Accept":"application/json",
        "Accept-Language":"ru","User-Agent":"ai-ecosystem-scout/1.0"},method="GET")
    try:
        with urllib.request.urlopen(req,timeout=15) as res:
            if res.status!=200:raise RuntimeError("non_200")
            return json.load(res)
    except urllib.error.HTTPError as ex:
        raise RuntimeError("http_"+str(ex.code)) from None
    except Exception:
        raise RuntimeError("network_or_schema_error") from None
def main():
    out={"schema":"fh.public.scout.v1","status":"stopped","read_only":True,
         "bids_sent":False,"pages_checked":0,"projects_checked":0,"results":[]}
    try:
        if TOK.is_symlink() or not TOK.is_file() or TOK.stat().st_mode&0o077:
            raise RuntimeError("private_token_unavailable")
        token=TOK.read_text().strip()
        existing=set()
        try:
            bids=request("/my/bids?page[number]=1",token)
            for item in bids.get("data",[]) if isinstance(bids,dict) else []:
                obj=(item.get("attributes") or {}).get("project") or {}
                if str(obj.get("id","")).isdigit():existing.add(str(obj["id"]))
        except RuntimeError:
            out["bids_check"]="unavailable"
        else:out["bids_check"]="ok"
        found=[]
        for page in range(1,16):
            data=request("/projects?page[number]="+str(page),token)
            items=data.get("data",[])
            if not isinstance(items,list):raise RuntimeError("invalid_project_list")
            out["pages_checked"]+=1
            out["projects_checked"]+=len(items)
            for item in items:
                if not isinstance(item,dict):continue
                pid=str(item.get("id",""))
                a=item.get("attributes") or {}
                title=clean(a.get("name",""))
                desc=clean(a.get("description","") or a.get("description_html",""))
                stat=a.get("status") or {}
                status=stat.get("id") if isinstance(stat,dict) else stat
                if status not in (11,"11",None):continue
                if pid in existing:continue
                titlelow=title.lower(); full=(title+" "+desc).lower()
                score=sum(value*(2 if word in titlelow else 1) for word,value in TERMS.items() if (re.search(r"(?<!\\w)"+word+r"(?!\\w)",full) if word in ("ии","ai","api","bot","rag","crm","llm") else word in full))
                score+=sum(value*(2 if word in titlelow else 1) for word,value in NEGATIVE.items() if word in full)
                if score<10:continue
                budget=a.get("budget") if isinstance(a.get("budget"),dict) else {}
                found.append({
                    "id":pid,"title":title[:170],"description":desc[:1450],
                    "budget":budget.get("amount"),"currency":budget.get("currency"),
                    "score":score,"status":status,
                    "only_plus":bool(a.get("is_only_for_plus",False)),
                    "is_premium":bool(a.get("is_premium",False)),
                    "bid_count":a.get("bid_count"),
                    "tags":a.get("tags") if isinstance(a.get("tags"),list) else [],
                    "published_at":a.get("published_at"),"expired_at":a.get("expired_at"),
                    "available_attribute_keys":sorted(a.keys()),
                    "raw_links_keys":sorted((item.get("links") or {}).keys()) if isinstance(item.get("links"),dict) else [],
                })
            if len(items)==0:break
            time.sleep(.35)
        found.sort(key=lambda x:(x["score"],str(x.get("published_at") or "")),reverse=True)
        out["status"]="ok";out["results"]=found[:50]
    except Exception as ex:
        out["error_type"]=str(ex) if str(ex).startswith(("http_","network_","invalid_","private_")) else "error"
    print("FH_SCOUT_RESULT "+json.dumps(out,ensure_ascii=False,sort_keys=True))
if __name__=="__main__":main()
