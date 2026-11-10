#!/usr/bin/env python3
"""Inspect only own portfolio work editing wizard: click Edit, never save."""
import json,sys,tempfile
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,is_fl_url
HOME="https://www.fl.ru/users/olegendorphine/setup/main/"
PORT="https://www.fl.ru/users/olegendorphine/portfolio/"
WORK_ID="8111943"
out={"schema":"fl.owner.work.edit.wizard.readonly.v1","owner":False,"write":False,"status":"initial","edit_count":0}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-owner-workedit-inspect-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  r=p.goto(HOME,wait_until="domcontentloaded",timeout=25000)
  o=p.evaluate("""()=>({owner:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner"]=bool(r and r.status==200 and is_fl_url(p.url) and o["owner"] and o["settings"])
  if out["owner"]:
   r=p.goto(PORT,wait_until="domcontentloaded",timeout=25000);p.wait_for_timeout(500)
   card=p.locator(".portfolio-item").filter(has=p.locator('a[href*="/portfolio/'+WORK_ID+'/"]'))
   out["cards"]=card.count()
   if card.count()!=1:out["status"]="card_count_unexpected"
   else:
    edit=card.get_by_text("Редактировать",exact=True)
    out["edit_count"]=edit.count()
    if edit.count()!=1:out["status"]="edit_count_unexpected"
    else:
     out["status"]="editor_click_preflight"
     out["control"]=edit.evaluate("""e=>({tag:e.tagName,cls:String(e.className||'').slice(0,95),parentTag:e.parentElement?.tagName,parents:Array.from({length:3},(_,i)=>{let v=e;for(let n=0;n<i;n++)v=v?.parentElement;return {tag:v?.tagName||'',cls:String(v?.className||'').slice(0,70),attrs:Array.from(v?.attributes||[]).map(x=>x.name).slice(0,14)}})})""")
     edit.click(timeout=12000)
     p.wait_for_timeout(1400)
     out["status"]="editor_open_attempted"
     out["editor"]=p.evaluate("""()=>{
        const visible=e=>!!(e.getBoundingClientRect().width&&e.getBoundingClientRect().height);
        const fields=Array.from(document.querySelectorAll('input,textarea,select')).filter(e=>visible(e)&&!['hidden','password','file'].includes(e.type||'')).slice(-30)
         .map(e=>({tag:e.tagName,name:e.name||'',id:e.id||'',type:e.type||'',place:(e.placeholder||'').slice(0,80),length:String(e.value||'').length}));
        const btns=Array.from(document.querySelectorAll('button,[role=button]')).filter(visible).map(e=>(e.innerText||'').trim().slice(0,65)).filter(Boolean).slice(-25);
        return {pageHost:location.hostname,fields,btns,dialogs:document.querySelectorAll('[role=dialog]').length,
           words:(document.body?.innerText||'').slice(-1400)};
     }""")
     out["pages"]=len(b.context.pages)
finally:
 b.close()
 print(json.dumps(out,ensure_ascii=False,sort_keys=True))
