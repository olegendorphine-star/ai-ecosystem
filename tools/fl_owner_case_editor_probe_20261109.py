#!/usr/bin/env python3
"""Read-only open existing FL portfolio work editor for known owner work ID."""
from pathlib import Path
import sys,json,tempfile
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
out={"schema":"fl.owner.work.editor.probe.v1","owner":False,"writes":False,"clicked_edit":False,"detail":{}}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-work-editor-probe-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=21000)
  s=p.evaluate("""()=>({o:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),s:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner"]=bool(s["o"] and s["s"] and is_fl_url(p.url))
  if out["owner"]:
   p.goto("https://www.fl.ru/users/olegendorphine/portfolio/",wait_until="domcontentloaded",timeout=22000)
   anchor=p.locator('a[href*="/user/olegendorphine/portfolio/8111943/"]').first
   if anchor.count()==1:
    node=anchor
    for depth in range(6):
     edits=node.get_by_text("Редактировать",exact=True)
     out["detail"]["depth_"+str(depth)]={"edit_count":edits.count(),"text":node.inner_text()[:150]}
     if edits.count()==1 and depth>=1:
      edits.click(timeout=7500);out["clicked_edit"]=True
      p.wait_for_timeout(500)
      out["detail"]["dialog"]=p.evaluate("""()=>{
       const inputs=Array.from(document.querySelectorAll('input,textarea,select')).filter(x=>x.getBoundingClientRect().width>0&&x.type!=='password').slice(-35).map(x=>({tag:x.tagName,name:x.name,id:x.id,type:x.type,accept:x.accept||'',length:(x.value||'').length}));
       const files=Array.from(document.querySelectorAll('input[type=file]')).map(x=>({accept:x.accept,id:x.id,name:x.name}));
       const buttons=Array.from(document.querySelectorAll('button')).filter(x=>x.getBoundingClientRect().width>0).map(x=>(x.innerText||'').trim()).filter(x=>/сохран|продолжить|отменить|удалить|обложку|опубликовать/i.test(x)).slice(-20);
       const dialogs=Array.from(document.querySelectorAll('[role=dialog]')).filter(x=>x.getBoundingClientRect().width>0).map(x=>x.innerText.slice(0,420));
       return {inputs,files,buttons,dialogs};
      }""")
      break
     node=node.locator("..")
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
