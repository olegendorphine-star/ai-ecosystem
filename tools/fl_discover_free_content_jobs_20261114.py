#!/usr/bin/env python3
"""Read-only discovery of FREE eligible FL.ru owner-session jobs for documents/data.
No bids, no paid actions, no account modification. Bounded current session.
"""
from __future__ import annotations
import json,sys,tempfile,re
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url,LOGIN

SOURCES=[
 ("latest","https://www.fl.ru/projects/"),
 ("present","https://www.fl.ru/projects/category/dizajn/dizajner-prezentacij/"),
 ("business","https://www.fl.ru/projects/category/avtomatizaciya-biznesa/"),
 ("writing","https://www.fl.ru/projects/category/teksty/"),
 ("translation","https://www.fl.ru/projects/category/perevody/"),
 ("marketing","https://www.fl.ru/projects/category/reklama-marketing/marketolog-analitik/"),
 ("ai","https://www.fl.ru/projects/category/ai-iskusstvenniy-intellekt/"),
 ("bots","https://www.fl.ru/projects/category/messendzhery/")
]
TERMS=("презентац","каталог","excel","xlsx","таблиц","отчёт","отчет","анализ","исследован",
"конкурент","python","api","сравнен","парсинг","перевод","документ","обработк",
"текст","инструкци","аналитик","чат","telegram","авито","ии","нейросет","бот","сбор данных")
SKIP=("украин","украї","україна","созвон","звонки","собеседование","по телефону")
out={"schema":"fl.free.content.discovery.v1","read_only":True,"owner_verified":False,"bids_sent":False,"payment_actions":False,"categories":[],"details":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-owner-content-free-search-",dir=ROOT) as tmp:
  b.open(Path(tmp));p=b.page
  r=p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  sign=p.evaluate("""(expected) => ({
   owner:[...document.querySelectorAll('input')].some(e=>(e.value||'').trim().toLowerCase()===expected),
   settings:(document.body?.innerText||'').includes('Основные настройки')
  })""", LOGIN)
  out["owner_verified"]=bool(r and r.status==200 and is_fl_url(p.url) and sign["settings"] and sign["owner"])
  if out["owner_verified"]:
   entries={}
   for key,url in SOURCES:
    row={"category":key,"status":"unavailable","links":0,"potential_free":0}
    out["categories"].append(row)
    try:
     r=p.goto(url,wait_until="domcontentloaded",timeout=18000)
     if not r or r.status!=200 or not is_fl_url(p.url):row["status"]="not_200";continue
     items=p.evaluate("""() => {
       const out=[],seen=new Set();
       for(const a of document.querySelectorAll('a[href*="/projects/"]')){
         const url=new URL(a.href,location.href);
         const m=url.pathname.match(/^\/projects\/(\d+)\/([^/]+)\.html$/);
         if(!m||!['fl.ru','www.fl.ru'].includes(url.hostname)||seen.has(m[1]))continue;
         const title=(a.innerText||a.title||'').replace(/\s+/g,' ').trim();
         if(!title||/откликнуться/i.test(title))continue;
         const wrap=a.closest('article,li,[class*="project"],[class*="card"],[class*="item"]')||a.parentElement?.parentElement;
         const s=(wrap?.innerText||a.parentElement?.innerText||title).replace(/\s+/g,' ').slice(0,650);
         seen.add(m[1]);out.push({id:m[1],title:title.slice(0,180),url:url.origin+url.pathname,listing:s,free_listed:/Для всех/i.test(s)});
         if(out.length>=45)break;
       }return out;
     }""")
     row["status"]="checked";row["links"]=len(items);row["potential_free"]=sum(1 for x in items if x["free_listed"])
     for e in items:
      if e["id"] in entries:continue
      s=(e["title"]+" "+e["listing"]).lower()
      if any(x in s for x in SKIP):continue
      score=sum(2 if x in e["title"].lower() else 1 for x in TERMS if x in s)
      if score<1:continue
      e["score"]=score;e["source"]=key
      entries[e["id"]]=e
    except Exception as e:
     row["status"]="navigation_or_parse_error"
   selected=sorted(entries.values(),key=lambda x:(not x["free_listed"],-x["score"],-int(x["id"])))[:45]
   for e in selected:
    item={k:e[k] for k in ("id","title","url","source","score","free_listed")}
    item["status"]="unavailable";out["details"].append(item)
    try:
     r=p.goto(e["url"],wait_until="domcontentloaded",timeout=15500)
     if not r or r.status!=200 or not is_fl_url(p.url) or urlsplit(p.url).path!=urlsplit(e["url"]).path:
      item["status"]="wrong_url_or_http";continue
     s=p.evaluate("""() => {
       const h=(document.querySelector('h1')?.innerText||'').trim();
       const txt=document.body?.innerText||'';
       const k=txt.indexOf(h),seg=txt.slice(Math.max(k,0),Math.max(k,0)+6500);
       return {title:h,free:/Для всех/i.test(seg),closed:/исполнитель определ[её]н|исполнитель выбран|проект закрыт|проект заверш[её]н|заказ закрыт/i.test(seg),
       already:/вы уже откликнулись|ваш отклик отправлен|редактировать отклик|изменить отклик/i.test(seg),
       pay:/купить [0-9]* отклик|купить отклики|недостаточно откликов|платн.*отклик/i.test(seg),
       captcha:!!document.querySelector('[class*="smartcaptcha"],[id*="captcha"]'),
       form:!!document.querySelector('form textarea#el-descr'),
       send:document.querySelector('#el-submit')?.innerText?.trim()==='Отправить отклик',
       excerpt:seg.slice(0,550)
       };
     }""")
     item.update({"status":"checked","free_badge":s["free"],"closed":s["closed"],"already_sent":s["already"],
       "paid_gate":s["pay"],"form":s["form"],"send":s["send"],
       "free_verified":bool(s["title"].casefold()==e["title"].casefold() and s["free"] and s["form"] and s["send"] and not s["closed"] and not s["already"] and not s["pay"] and not s["captcha"]),
       "excerpt":s["excerpt"].replace("\n"," ")[:550]})
    except Exception:
     item["status"]="timeout_or_parse_error"
finally:
 b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
