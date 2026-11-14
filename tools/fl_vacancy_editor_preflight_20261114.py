#!/usr/bin/env python3
"""Read-only preflight of FL.ru owner vacancy application UI for text/data work."""
import json,sys,tempfile
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url,LOGIN
JOBS=[
 ("5528153","Редактор-корректор текстовых материалов","https://www.fl.ru/projects/5528153/redaktor-korrektor-tekstovyih-materialov.html"),
 ("5528141","Специалист по рерайтингу текстов","https://www.fl.ru/projects/5528141/spetsialist-po-reraytingu-tekstov.html"),
 ("5528198","Специалист по транскрибации записей","https://www.fl.ru/projects/5528198/spetsialist-po-transkribatsii-zapisey.html")
]
out={"schema":"fl.vacancy.editor.preflight.v1","owner_verified":False,"read_only":True,"applications_sent":False,"jobs":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-vacancy-editor-preflight-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  r=p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  s=p.evaluate("""(expected)=>({
     owner:[...document.querySelectorAll('input')].some(e=>(e.value||'').trim().toLowerCase().split('@')[0]===expected),
     settings:(document.body?.innerText||'').includes('Основные настройки')
  })""", LOGIN)
  out["owner_verified"]=bool(r and r.status==200 and is_fl_url(p.url) and s["owner"] and s["settings"])
  if out["owner_verified"]:
   for id,title,url in JOBS:
    row={"id":id,"status":"unavailable"};out["jobs"].append(row)
    try:
     r=p.goto(url,wait_until="domcontentloaded",timeout=20000)
     if not r or r.status!=200 or not is_fl_url(p.url) or urlsplit(p.url).path!=urlsplit(url).path:
      row["status"]="http_or_redirect";continue
     s=p.evaluate("""()=> {
      const h=(document.querySelector('h1')?.innerText||'').trim();
      const txt=document.body?.innerText||'';
      const i=txt.indexOf(h),seg=txt.slice(Math.max(i,0),Math.max(i,0)+9000);
      const controls=[...document.querySelectorAll('textarea,button,input[type="submit"],input[type="text"],input[type="number"],input[type="file"]')]
        .filter(e=>e.offsetParent!==null).map(e=>({tag:e.tagName.toLowerCase(),id:e.id||'',name:e.getAttribute('name')||'',
         placeholder:(e.getAttribute('placeholder')||'').slice(0,70),
         type:(e.getAttribute('type')||'').slice(0,20),
         text:(e.innerText||e.getAttribute('value')||'').trim().slice(0,75),
         class:(e.className||'').toString().slice(0,110),form:(e.closest('form')?.id||'').slice(0,50),near:(e.parentElement?.parentElement?.innerText||'').trim().slice(0,135),maxlength:e.getAttribute('maxlength')||'',disabled:!!e.disabled})).slice(0,20);
      return {title:h,vacancy:/Ссылка на вакансию/i.test(seg),already:/вы откликнулись|ваш отклик отправлен|редактировать отклик|отклик уже отправлен/i.test(seg),
        closed:/вакансия закрыта|вакансия завершена|исполнитель определен|исполнитель выбран/i.test(seg),
        pay:/купить отклики|оплатить отклик|платн.*отклик/i.test(seg),
        captcha:!!document.querySelector('[class*="smartcaptcha"],[id*="captcha"]'),
        controls,excerpt:seg.slice(0,650),
        remote:/удал[её]н|из дома|дистанцион/i.test(seg),
        calls:/обязательн.{0,40}(созвон|звонок|собеседован)/i.test(seg)};
      }""")
     row.update({"status":"checked","title_match":s["title"].lower()==title.lower(),"vacancy":s["vacancy"],
       "already":s["already"],"closed":s["closed"],"paid":s["pay"],"captcha":s["captcha"],"remote":s["remote"],
       "mandatory_calls":s["calls"],"controls":s["controls"],"excerpt":s["excerpt"].replace("\n"," ")})
    except Exception as e:
     row["status"]="exception";row["error_type"]=type(e).__name__
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
