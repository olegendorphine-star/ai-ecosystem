#!/usr/bin/env python3
"""Determine semantic meaning of owner main settings fields. Read only, no values."""
import sys,tempfile,json,re
from pathlib import Path
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
out={"schema":"fl.main.field.semantic.v1","verified_owner":False,"read_only":True}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-fields-semantic-",dir=ROOT) as temp:
  b.open(Path(temp))
  p=b.page
  try:p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=22000)
  except Exception:p.goto(ALLOWED_PAGES["settings"],wait_until="commit",timeout=19000);p.wait_for_timeout(1300)
  s=p.evaluate("""()=>({owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["verified_owner"]=s["owner"] and s["settings"] and is_fl_url(p.url)
  if out["verified_owner"]:
   p.goto("https://www.fl.ru/users/olegendorphine/setup/main/",wait_until="domcontentloaded",timeout=22000)
   out["details"]=p.evaluate("""()=> {
     const fields=['name','surname','pname'];
     return fields.map(n=>{
       const e=document.querySelector('input[name="'+n+'"]');
       if(!e)return {field:n,notFound:true};
       let cur=e;const parents=[];
       for(let level=0;level<4;level++){
         if(!cur)break;
         const clone=cur.cloneNode(true);
         clone.querySelectorAll?.('input,textarea,select')?.forEach(v=>{
           v.removeAttribute('value');
           v.textContent='';
         });
         const txt=(cur.innerText||'').trim().replace(/\\s+/g,' ').slice(0,380);
         parents.push({tag:cur.tagName,classes:(cur.className||'').toString().slice(0,150),
           text:txt, outerHead:clone.outerHTML.slice(0,600).replace(/value="[^"]*"/g,'value="[private]"')});
         cur=cur.parentElement;
       }
       return {field:n,placeholder:e.getAttribute('placeholder'),title:e.getAttribute('title'),
         ariaLabel:e.getAttribute('aria-label'),
         labels:Array.from(e.labels||[]).map(x=>(x.innerText||'').trim()),
         beforeText:(e.previousElementSibling?.innerText||'').trim().slice(0,200),
         afterText:(e.nextElementSibling?.innerText||'').trim().slice(0,200),
         rowText:(e.closest("tr")?.innerText||"").trim().replace(/\\s+/g," ").slice(0,380),
         previousCellText:(e.closest("td")?.previousElementSibling?.innerText||"").trim().replace(/\\s+/g," ").slice(0,200),
         parents};
     })
   }""")
finally:b.close()
print(json.dumps(out,ensure_ascii=False))
