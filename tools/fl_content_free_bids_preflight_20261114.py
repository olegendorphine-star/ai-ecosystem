#!/usr/bin/env python3
"""Owner-only FL.ru bid preflight. Read-only, zero writes or messages."""
from __future__ import annotations
import json,sys,tempfile
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent"
sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url

JOBS=[
 ("5529031","Форматирование (оформление по условиям университета Мастрер Тезиса) и проверка на антиплагиат","https://www.fl.ru/projects/5529031/formatirovanie-oformlenie-po-usloviyam-universiteta-mastrer-tezisa-i-proverka-na-antiplagiat.html")
]
out={"schema":"fl.free.content.preflight.v1","owner_verified":False,"read_only":True,"bids_sent":False,"projects":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-new-content-preflight-",dir=ROOT) as tmp:
  b.open(Path(tmp));p=b.page
  r=p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=24000)
  sign=p.evaluate("""() => ({
   settings:(document.body?.innerText||'').includes('Основные настройки'),
   owner:[...document.querySelectorAll('input')].some(e=>(e.value||'').toLowerCase().trim()==='olegendorphine@gmail.com')
  })""")
  out["owner_verified"]=bool(r and r.status==200 and is_fl_url(p.url) and sign["settings"] and sign["owner"])
  if out["owner_verified"]:
   for id,title,url in JOBS:
    item={"id":id,"free_verified":False,"status":"unavailable"}
    out["projects"].append(item)
    try:
     r=p.goto(url,wait_until="domcontentloaded",timeout=23000)
     p.wait_for_timeout(550)
     if not r or r.status!=200 or not is_fl_url(p.url) or urlsplit(p.url).path!=urlsplit(url).path:
      item["status"]="http_or_url_mismatch";continue
     s=p.evaluate("""() => {
       const title=(document.querySelector('h1')?.innerText||'').trim();
       const t=document.body?.innerText||'';
       const ix=t.indexOf(title),seg=t.slice(Math.max(ix,0),Math.max(ix,0)+7000);
       const btn=document.querySelector('#el-submit');
       return {title,free:/Для всех/i.test(seg),closed:/исполнитель определ[её]н|исполнитель выбран|проект закрыт|проект заверш[её]н|заказ закрыт/i.test(seg),
        already:/вы уже откликнулись|ваш отклик отправлен|редактировать отклик|изменить отклик/i.test(seg),
        pay:/оплатите отклик|купить отклики|недостаточно откликов|требуется платный отклик/i.test(seg),
        captcha:!!document.querySelector('[class*="smartcaptcha"],[id*="captcha"]'),
        form:!!document.querySelector('form textarea#el-descr'),
        button:btn?.innerText?.trim()==='Отправить отклик',
        segment:seg.slice(0,1100)
       };
     }""")
     item.update({"status":"checked","title_match":s["title"].casefold()==title.casefold(),"free_badge":s["free"],
       "closed":s["closed"],"already_sent":s["already"],"payment_prompt":s["pay"],"captcha":s["captcha"],
       "form_present":s["form"],"submit_present":s["button"],
       "free_verified":bool(s["title"].casefold()==title.casefold() and s["free"] and s["form"] and s["button"] and not s["closed"] and not s["already"] and not s["pay"] and not s["captcha"]),
       "excerpt":s["segment"].replace("\n"," ")[:850]})
    except Exception as e:
     item["status"]="browser_exception"
     item["error_class"]=type(e).__name__
finally:
 b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
