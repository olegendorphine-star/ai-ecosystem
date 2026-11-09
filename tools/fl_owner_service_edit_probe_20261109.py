#!/usr/bin/env python3
"""Inspect own two already-existing FL services and available edit controls.
Never submits, edits, duplicates, pays, or opens communications.
"""
import sys,json,tempfile
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
URL="https://www.fl.ru/users/olegendorphine/uslugi-freelancera/"
out={"schema":"fl.owner.services.edit.probe.v1","owner":False,"writes":False,"services":{}}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-service-editor-probe-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=22000)
  s=p.evaluate("""()=>({o:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),s:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner"]=bool(s["o"] and s["s"] and is_fl_url(p.url))
  if out["owner"]:
   response=p.goto(URL,wait_until="domcontentloaded",timeout=23000)
   if response and response.status==200 and is_fl_url(p.url):
    out["services"]=p.evaluate("""()=>{
      const body=(document.body?.innerText||'');
      const links=Array.from(document.querySelectorAll('a[href]')).filter(a=>
       /услуг|service|typical|редактир/i.test(a.href+' '+(a.innerText||'')))
       .slice(0,45).map(a=>({text:(a.innerText||'').trim().slice(0,100),path:new URL(a.href).pathname,host:new URL(a.href).hostname}));
      const controls=Array.from(document.querySelectorAll('button,[role=button]')).filter(a=>
       /редактир|измен|обложк|провер|добав|управл/i.test((a.innerText||'')+' '+(a.title||'')))
       .slice(0,40).map(a=>({text:(a.innerText||'').trim().slice(0,100),title:(a.title||'').slice(0,100),dataid:a.getAttribute('data-id'),className:String(a.className).slice(0,120)}));
      const cards=Array.from(document.querySelectorAll('a,div,section')).filter(e=>e.children.length<12&&/Аудит одного процесса и карта ИИ-автоматизации|Разработаю ТЗ на персонального ИИ-ассистента/.test(e.innerText||'')&&e.getBoundingClientRect().width>150&&e.getBoundingClientRect().height>100).slice(-18).map(e=>({tag:e.tagName,cls:String(e.className).slice(0,110),text:(e.innerText||'').trim().slice(0,190),html:e.outerHTML.slice(0,550).replace(/\S+@\S+/g,'[redacted]')}));
      return {pending:(body.match(/На проверке|На модерации/g)||[]).length,
          cards,links,controls,
          inputs:Array.from(document.querySelectorAll('input[type=file]')).map(e=>({accept:e.accept}))};
    }""")
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
