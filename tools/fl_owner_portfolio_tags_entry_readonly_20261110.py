#!/usr/bin/env python3
"""Read-only audit of owner portfolio section tag edit entry points."""
import json,sys,tempfile
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,is_fl_url
MAIN="https://www.fl.ru/users/olegendorphine/setup/main/"
PORTFOLIO="https://www.fl.ru/users/olegendorphine/portfolio/"
out={"schema":"fl.owner.portfolio.tags.entry.readonly.v1","owner":False,"read_only":True,"write":False,"payments":False,"sections":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-owner-tags-entry-",dir=ROOT) as tmp:
  b.open(Path(tmp));p=b.page
  r=p.goto(MAIN,wait_until="domcontentloaded",timeout=25000)
  a=p.evaluate("""()=>({
    owner:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
    settings:(document.body?.innerText||'').includes('Основные настройки')
  })""")
  out["owner"]=bool(r and r.status==200 and is_fl_url(p.url) and a["owner"] and a["settings"])
  if out["owner"]:
   r=p.goto(PORTFOLIO,wait_until="domcontentloaded",timeout=25000)
   if r and r.status==200 and is_fl_url(p.url):
    out["sections"]=p.evaluate("""()=>{
      const edit=Array.from(document.querySelectorAll('a,button')).filter(e=>e.innerText.trim()==='Редактировать');
      return edit.slice(0,20).map((e,i)=>{
        const parent=e.parentElement;
        const grand=parent?.parentElement;
        const great=grand?.parentElement;
        return {i,tag:e.tagName,class:e.className?.toString().slice(0,130),
          href:e.getAttribute('href')?.split('?')[0]?.slice(0,120)||null,
          parent:(parent?.innerText||'').replace(/\\s+/g,' ').slice(0,170),
          grand:(grand?.innerText||'').replace(/\\s+/g,' ').slice(0,180),
          great:(great?.innerText||'').replace(/\\s+/g,' ').slice(0,220),
          parentTag:parent?.tagName,grandTag:grand?.tagName,grandClass:grand?.className?.toString().slice(0,120),
          dataKeys:Object.keys(e.dataset||{}).slice(0,15)
        };
      });
    }""")

    node=p.locator('a.admn').nth(2)
    if "AI-агенты" in node.evaluate("(e)=>e.parentElement?.parentElement?.innerText||''"):
     node.click(timeout=9000)
     p.wait_for_timeout(500)
     out["modal"]=p.evaluate("""()=>{
       const visible=e=>e.getBoundingClientRect().width>0&&e.getBoundingClientRect().height>0;
       const fields=Array.from(document.querySelectorAll('input,textarea,select')).filter(visible)
          .filter(x=>!['hidden','password','file'].includes(x.type||'')).slice(-32)
          .map(x=>({tag:x.tagName,name:x.name||'',id:x.id||'',type:x.type||'',placeholder:(x.placeholder||'').slice(0,90),
             valueLength:String(x.value||'').length,valueStarts:String(x.value||'').slice(0,60)}));
       const controls=Array.from(document.querySelectorAll('button,a,input[type=submit]')).filter(visible)
          .map(e=>({tag:e.tagName,text:(e.innerText||e.value||'').trim().slice(0,65),type:e.getAttribute('type')||''}))
          .filter(x=>/сохран|отмена|закры|измен|ключев|примен/i.test(x.text)).slice(-22);
       const forms=Array.from(document.forms).filter(visible).map(e=>({method:e.method,fields:Array.from(e.querySelectorAll('input,textarea')).map(x=>x.name).slice(0,18)})).slice(-8);
       return {fields,controls,forms,dialogText:Array.from(document.querySelectorAll('[role=dialog],.modal,.b-shadow,.b-popup')).filter(visible).map(x=>(x.innerText||'').replace(/\\s+/g,' ').slice(0,330)).slice(-3)};
     }""")
finally:
 b.close()
 print(json.dumps(out,ensure_ascii=False,sort_keys=True))
