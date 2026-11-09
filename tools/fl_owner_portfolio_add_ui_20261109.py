#!/usr/bin/env python3
"""Inspect owner portfolio 'Add work' UI without posting/creating work."""
from pathlib import Path
import sys,tempfile,json
from urllib.parse import urlsplit
root=Path.home()/".fl-agent";sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
out={"schema":"fl.owner.portfolio.add_ui.v1","owner":False,"read_only":True,"posted":False}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-add-work-ui-",dir=root) as t:
  b.open(Path(t));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  s=p.evaluate("""()=>({a:(document.body?.innerText||'').includes('Основные настройки'),b:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com')})""")
  out["owner"]=bool(s["a"] and s["b"] and is_fl_url(p.url))
  if out["owner"]:
   p.goto("https://www.fl.ru/users/olegendorphine/portfolio/",wait_until="domcontentloaded",timeout=24000)
   p.wait_for_timeout(500)
   out["before"]=p.evaluate("""()=>({
     buttons:Array.from(document.querySelectorAll('button')).filter(e=>/Добавить работу/i.test(e.innerText||'')).map(e=>({id:e.getAttribute('data-id'),text:e.innerText.trim(),visible:e.offsetParent!==null})),
     workSections:Array.from(document.querySelectorAll('h2,h3,h4')).map(e=>e.innerText.trim()).filter(Boolean).slice(-25)
   })""")
   buttons=p.locator('button:has-text("Добавить работу")')
   if buttons.count():
    first=buttons.first
    try:
     first.click(timeout=11000)
     p.wait_for_timeout(1200)
     out["status"]="clicked_open"
    except Exception as e:out["status"]="click_timeout" if "timeout" in str(e).lower() else "click_error"
    out["ui"]=p.evaluate("""()=>{
      const tail=(document.body?.innerText||'').slice(-3200);
      const fields=Array.from(document.querySelectorAll('input,select,textarea,[contenteditable=true]'))
       .filter(e=>e.getBoundingClientRect().width>0&& !['password','hidden'].includes(e.type||'')).slice(-35).map(e=>({tag:e.tagName,type:e.type||'',id:e.id||'',name:e.name||'',placeholder:(e.getAttribute('placeholder')||'').slice(0,130),required:e.required||false,
       maxLength:e.maxLength||null,near:(e.labels?.[0]?.innerText||'').trim().slice(0,80)}));
      const buttons=Array.from(document.querySelectorAll('button,[role=button]')).filter(e=>e.getBoundingClientRect().width>0).map(e=>(e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,70)).filter(Boolean).slice(-35);
      return {host:location.hostname,path:location.pathname,
       text:tail.replace(/(?:[a-z0-9._%+-]+)@(?:[a-z0-9.-]+\\.[a-z]{2,})/ig,'[email]'),
       fields,buttons,dialogs:document.querySelectorAll('[role=dialog]').length};
    }""")
    out["pages_count"]=len(b.context.pages)
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
