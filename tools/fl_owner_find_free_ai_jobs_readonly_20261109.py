#!/usr/bin/env python3
"""Discover current FL public AI jobs; verify FREE eligibility in authenticated OWNER session.
Strictly read-only: no bids, customer messages, payments, or CAPTCHA actions.
"""
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime,timezone
import json,sys,tempfile,re
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
SOURCES=[
 ("latest","https://www.fl.ru/projects/"),
 ("latest_page2","https://www.fl.ru/projects/page-1/"),
 ("ai","https://www.fl.ru/projects/category/ai-iskusstvenniy-intellekt/"),
 ("ai_agents","https://www.fl.ru/projects/category/ai-iskusstvenniy-intellekt/ai-agenty/"),
 ("business","https://www.fl.ru/projects/category/avtomatizaciya-biznesa/"),
 ("leadgen","https://www.fl.ru/projects/category/reklama-marketing/prodaji-i-generatsiya-lidov/"),
 ("n8n","https://www.fl.ru/projects/category/ai-iskusstvenniy-intellekt/n8n/"),
 ("bots","https://www.fl.ru/projects/category/messendzhery/"),
]
SKIP={"5528311","5528212","5528431","5528498","5528403","5527732","5527458","5528049","5528568","5528574","5527838","5528616"}
TERMS=["ии","ai","агент","бот","n8n","автоматиз","интеграц","crm","api","telegram","таблиц","документ","данн","google","скрипт","впс","vps","чат","ассистент","нейросет","ботов","rag","python","ocr","бизнес-аналит","голосов","тз","партнер","процесс","система","автопарк","привлечение клиентов","авито","лиды","лидоген"]
out={"schema":"fl.owner.free.ai.job.discovery.v1","asof_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),"owner_verified":False,"read_only":True,"bids_sent":False,"payments":False,"messages_read":False,"captcha":False,"categories":[],"candidates":[],"details":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-free-ai-jobs-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  r=p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  sign=p.evaluate("""()=>({owner:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),main:(document.body.innerText||'').includes('Основные настройки')})""")
  out["owner_verified"]=bool(r and r.status==200 and is_fl_url(p.url) and sign["owner"] and sign["main"])
  if out["owner_verified"]:
   seen=set()
   for label,url in SOURCES:
    row={"source":label,"count":0,"http":None}
    out["categories"].append(row)
    try:
     r=p.goto(url,wait_until="domcontentloaded",timeout=17000)
     row["http"]=r.status if r else None
     if not r or r.status!=200 or not is_fl_url(p.url):continue
     items=p.evaluate("""()=>{
      const links=Array.from(document.querySelectorAll('a[href*="/projects/"]'));
      const out=[],seen=new Set();
      for(const a of links){
       const u=new URL(a.href,location.href);
       const m=u.pathname.match(/^\\/projects\\/(\\d+)\\/([^/]+)\\.html$/);
       if(!m||!['fl.ru','www.fl.ru'].includes(u.hostname)||seen.has(m[1]))continue;
       const wrap=a.closest('article,li,[class*="project"],[class*="card"],[class*="item"]')||a.parentElement?.parentElement;
       const text=(wrap?.innerText||a.parentElement?.innerText||a.innerText||'').trim().replace(/\\s+/g,' ').slice(0,650);
       const title=(a.innerText||a.title||'').trim().replace(/\\s+/g,' ');
       if(!title||/откликнуться/i.test(title))continue;
       seen.add(m[1]);out.push({id:m[1],title:title.slice(0,190),url:u.origin+u.pathname,snippet:text,free_listed:/Для всех/i.test(text)});
       if(out.length>=45)break;
      }return out
     }""")
     row["count"]=len(items)
     for x in items:
      if x["id"] in SKIP or x["id"] in seen:continue
      text=(x["title"]+" "+x["snippet"]).lower()
      score=sum(1 for word in TERMS if word in text)
      if score<1:continue
      seen.add(x["id"])
      x["source"]=label;x["score"]=score
      out["candidates"].append(x)
    except Exception as e:row["status"]="nav_or_parse_error"
   out["candidates"].sort(key=lambda x:(-x["score"],-int(x["id"])))
   # Read up to 22 high-fit jobs in current owner session. No forms are touched.
   for x in out["candidates"][:65]:
    d={"id":x["id"],"title":x["title"],"url":x["url"],"status":"not_checked","free_verified":False,"already_sent":False}
    out["details"].append(d)
    try:
     r=p.goto(x["url"],wait_until="domcontentloaded",timeout=13500)
     if not r or r.status!=200 or not is_fl_url(p.url) or urlsplit(p.url).path!=urlsplit(x["url"]).path:
      d["status"]="not_200_or_redirect";continue
     p.wait_for_timeout(230)
     signs=p.evaluate("""()=>{
      const h=(document.querySelector('h1')?.innerText||'').trim();
      const text=document.body?.innerText||'';
      const ix=Math.max(0,text.indexOf(h));
      const segment=text.slice(ix,ix+4800);
      const btn=document.querySelector('#el-submit');
      const form=document.querySelector('form textarea#el-descr');
      return {
       headline:h.slice(0,180),
       description:segment.slice(0,1500).replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}/gi,'[email]'),
       free:/Для всех/i.test(segment),
       already:/редактировать отклик|ваш отклик отправлен|вы уже откликнулись/i.test(segment),
       closed:/исполнитель определ[её]н|проект закрыт|проект заверш[её]н|снят с публикации/i.test(segment),
       has_form:!!form,has_send:btn?.innerText?.trim()==='Отправить отклик',
       pay_request:/оплатите отклик|купить отклики|недостаточно откликов/i.test(segment),
       timestamp:(segment.match(/Заказ\\s+(?:сегодня|вчера|\\d+[^\\n]{0,35})/i)||[])[0]||null,
       price:(segment.match(/(?:от|до)?\\s*[\\d\\s]{4,10}\\s*₽/i)||[])[0]||null
      }
     }""")
     d.update({"status":"checked","free_verified":bool(signs["free"] and signs["has_form"] and signs["has_send"] and not signs["already"] and not signs["closed"] and not signs["pay_request"]),
       "free_badge":signs["free"],"already_sent":signs["already"],"closed":signs["closed"],
       "form_present":signs["has_form"],"send_button_present":signs["has_send"],"payment_prompt":signs["pay_request"],
       "headline":signs["headline"],"excerpt":signs["description"],"price":signs["price"],"timestamp":signs["timestamp"]})
    except Exception as e:d["status"]="timeout_or_parse_error"
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
