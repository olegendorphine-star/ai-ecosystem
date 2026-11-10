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
finally:
 b.close()
 print(json.dumps(out,ensure_ascii=False,sort_keys=True))
