#!/usr/bin/env python3
"""Safely inspect FL owner visual editors, no upload, no writes, no messages."""
from pathlib import Path
import sys,json,tempfile
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
URL="https://www.fl.ru/users/olegendorphine/portfolio/"
out={"schema":"fl.owner.visual.editor.preflight.v1","verified_owner":False,"writes":False,"portfolio":{},"cover":{}}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-visual-edit-preflight-",dir=ROOT) as d:
  b.open(Path(d));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=23000)
  s=p.evaluate("""()=>({o:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),s:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["verified_owner"]=bool(s["o"] and s["s"] and is_fl_url(p.url))
  if out["verified_owner"]:
   r=p.goto(URL,wait_until="domcontentloaded",timeout=24000)
   out["portfolio"]=p.evaluate("""()=>{
    let names=['Персональный ИИ-Штаб: память, документы и контроль','Автономный браузер на VPS и контроль сессий','ИИ-документооборот: связи, анализ и полезные сигналы'];
    let anchors=Array.from(document.querySelectorAll('a[href]')).filter(x=>(x.href||'').includes('olegendorphine')&&(x.href.includes('/portfolio/')||x.href.includes('/users/'))).slice(0,50).map(a=>({label:(a.innerText||'').trim().slice(0,80),path:new URL(a.href).pathname}));
    let buttons=Array.from(document.querySelectorAll('button,[role=button],a')).filter(x=>/редактир|изменить|обложку|сделать главной|портфолио/i.test(x.innerText||x.getAttribute('title')||'')).slice(0,45).map(x=>({label:(x.innerText||x.title||'').trim().slice(0,70),tag:x.tagName,href:x.getAttribute('href'),dataid:x.getAttribute('data-id'),disabled:!!x.disabled}));
    return {name_presence:names.map(x=>document.body.innerText.includes(x)),anchors,buttons};
   }""")
   h=p.get_by_role("button",name="Загрузить обложку для ПК")
   out["cover"]["button_count"]=h.count()
   if h.count()==1:
    h.click(timeout=8000);p.wait_for_timeout(350)
    out["cover"]["dialog"]=p.evaluate("""()=>{
      let q=Array.from(document.querySelectorAll('[role=dialog], [class*=modal]')).filter(x=>x.getBoundingClientRect().width>300&&x.getBoundingClientRect().height>100);
      let text=(q.at(-1)?.innerText||'').slice(0,600);
      let files=Array.from(document.querySelectorAll('input[type=file]')).map(x=>({accept:x.accept,name:x.name,visible:x.getBoundingClientRect().width>0}));
      let controls=Array.from(document.querySelectorAll('button')).filter(x=>/сохран|загруз|купить|PRO|оплат|закрыть/i.test(x.innerText||'')).slice(-12).map(x=>({text:x.innerText.trim().slice(0,50),disabled:x.disabled}));
      return {text,files,controls};
    }""")
finally:b.close()
print(json.dumps(out,ensure_ascii=False))
