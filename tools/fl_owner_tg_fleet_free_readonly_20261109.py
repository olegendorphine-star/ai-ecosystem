#!/usr/bin/env python3
"""Read-only look-up of new Telegram-fleet and sales-automation FL projects.
Uses saved owner session, no login and no writes/payments.
"""
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime,timezone
import sys,json,re,tempfile
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
PAGES=[
"https://www.fl.ru/projects/",
"https://www.fl.ru/projects/page-1/",
"https://www.fl.ru/projects/category/programmirovanie/python/",
"https://www.fl.ru/projects/category/avtomatizaciya-biznesa/"
]
TARGET_TERMS=["автопарком","таксопарк","telegram-бота","система продаж","телеграм-бота","комплексной разработки"]
out={"schema":"fl.owner.fleet.newjobs.v1","at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
"owner_verified":False,"read_only":True,"writes":False,"paid_actions":False,"pages":[],"matches":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-fleet-readonly-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  r=p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  signs=p.evaluate("""()=>({owner:Array.from(document.querySelectorAll('input')).some(i=>(i.value||'').toLowerCase().trim()==='olegendorphine@gmail.com'),settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner_verified"]=bool(r and r.status==200 and is_fl_url(p.url) and signs["owner"] and signs["settings"])
  if out["owner_verified"]:
   seen={}
   for url in PAGES:
    item={"url":url,"http":None,"count":0};out["pages"].append(item)
    try:
     r=p.goto(url,wait_until="domcontentloaded",timeout=18000)
     item["http"]=r.status if r else None
     if not r or r.status!=200 or not is_fl_url(p.url):continue
     links=p.evaluate("""()=>Array.from(document.querySelectorAll('a[href*="/projects/"]'))
       .map(a=>({title:(a.innerText||a.getAttribute('title')||'').replace(/\\s+/g,' ').trim(),url:a.href}))
       .filter(x=>x.title&&/^https:\\/\\/(www\\.)?fl\\.ru\\/projects\\/\\d+\\/[^/]+\\.html$/.test(x.url))
       .slice(0,200)""")
     item["count"]=len(links)
     for x in links:
      if any(word in x["title"].lower() for word in TARGET_TERMS):
       seen[x["url"]]=x["title"][:180]
    except Exception:item["error"]="navigate_or_parse_failed"
   for url,title in list(seen.items())[:12]:
    d={"url":url,"title":title,"status":"error"}
    out["matches"].append(d)
    try:
     r=p.goto(url,wait_until="domcontentloaded",timeout=18000)
     if not r or r.status!=200 or urlsplit(p.url).path!=urlsplit(url).path or not is_fl_url(p.url):
      d["status"]="wrong_url_or_http";continue
     signs=p.evaluate("""()=>{
      const h=(document.querySelector('h1')?.innerText||'').trim(),t=document.body?.innerText||'',
       ix=Math.max(0,t.indexOf(h)),v=t.slice(ix,ix+6600),bt=document.querySelector('#el-submit');
      return{title:h,free:/Для всех/i.test(v),send:bt?.innerText?.trim()==='Отправить отклик',
       form:!!document.querySelector('textarea#el-descr'),already:/Редактировать отклик|Изменить отклик|Вы уже откликнулись/i.test(v),
       closed:/исполнитель определ[её]н|проект закрыт|проект заверш[её]н|снят с публикации/i.test(v),
       payment:/Купить 1 отклик|Купить отклики|оплатите отклик/i.test(v),excerpt:v.slice(0,2600)}
     }""")
     d.update({"status":"checked","title":signs["title"][:180],
       "free":signs["free"],"form":signs["form"],"send":signs["send"],"already":signs["already"],
       "closed":signs["closed"],"payment":signs["payment"],"excerpt":signs["excerpt"],
       "free_verified":bool(signs["free"] and signs["send"] and signs["form"] and not signs["already"] and not signs["closed"] and not signs["payment"])})
    except Exception:d["status"]="navigation_or_parse_failed"
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
