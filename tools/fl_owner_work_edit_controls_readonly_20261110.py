#!/usr/bin/env python3
"""Owner-only read-only inspection of published portfolio work edit controls."""
import json,sys,tempfile
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,is_fl_url
HOME="https://www.fl.ru/users/olegendorphine/setup/main/"
WORKS="https://www.fl.ru/users/olegendorphine/portfolio/"
IDS=("8111943","8111944","8111945")
out={"schema":"fl.owner.work.edit.controls.v1","owner":False,"write":False,"work_controls":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-works-controls-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  r=p.goto(HOME,wait_until="domcontentloaded",timeout=23000)
  s=p.evaluate("""()=>({owner:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner"]=bool(r and r.status==200 and is_fl_url(p.url) and s["owner"] and s["settings"])
  if out["owner"]:
   r=p.goto(WORKS,wait_until="domcontentloaded",timeout=23000)
   if r and r.status==200 and is_fl_url(p.url):
    out["work_controls"]=p.evaluate("""(ids)=>{
       return ids.map(id=>{
         const a=Array.from(document.querySelectorAll('a[href]')).find(x=>{
           try{return new URL(x.href).pathname==='/user/olegendorphine/portfolio/'+id+'/'}catch(e){return false}
         });
         if(!a)return {id,found:false};
         const par=a.parentElement, ancestors=[par,par?.parentElement,par?.parentElement?.parentElement,par?.parentElement?.parentElement?.parentElement];
         const container=ancestors.find(x=>x?.querySelectorAll('a,button')?.length>1 && /Редактировать/.test(x.innerText||''));
         const controls=Array.from(container?.querySelectorAll('a,button')||[]).filter(x=>/Редактировать|Удалить/.test(x.innerText||'')).map(x=>({
           label:(x.innerText||'').trim().slice(0,35),tag:x.tagName,cls:String(x.className||'').slice(0,85),
           safeHref:(x.getAttribute('href')||'').split('?')[0].slice(0,100),dataId:(x.getAttribute('data-id')||'').slice(0,60),
           dataKeys:Object.keys(x.dataset||{}).slice(0,9)}));
         const ancestry=Array.from({length:7},(_,k)=>{let el=a;for(let n=0;n<k;n++)el=el?.parentElement;
            const items=Array.from(el?.querySelectorAll('a,button,[role=button]')||[])
              .filter(y=>/редакт|удал/i.test((y.innerText||y.title||'')+' '+y.className)).slice(0,8)
              .map(y=>({tag:y.tagName,label:(y.innerText||y.title||'').trim().slice(0,55),
                cls:String(y.className||'').slice(0,75),dataKeys:Object.keys(y.dataset||{}).slice(0,8)}));
            return {k,tag:el?.tagName||'',cls:String(el?.className||'').slice(0,90),
              text:(el?.innerText||'').replace(/\\s+/g,' ').slice(0,140),items};
          });
         return {id,found:true,container:container?.tagName||'',class:String(container?.className||'').slice(0,80),controls,ancestry};
       });
    }""",list(IDS))
finally:
 b.close()
 print(json.dumps(out,ensure_ascii=False,sort_keys=True))
