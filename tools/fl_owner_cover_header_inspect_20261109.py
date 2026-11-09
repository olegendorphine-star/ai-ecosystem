#!/usr/bin/env python3
"""Read-only inspect owner FL header cover controls and whether a cover already exists."""
import json,sys,tempfile
from pathlib import Path
root=Path.home()/".fl-agent";sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
d={"schema":"fl.owner.cover.header.inspect.v1","owner":False,"readonly":True}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-cover-header-read-",dir=root) as t:
  b.open(Path(t));p=b.page
  try:p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=22000)
  except Exception:p.goto(ALLOWED_PAGES["settings"],wait_until="commit",timeout=20000);p.wait_for_timeout(1500)
  s=p.evaluate("""()=>({a:(document.body?.innerText||'').includes('Основные настройки'),b:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com')})""")
  d["owner"]=s["a"] and s["b"] and is_fl_url(p.url)
  if d["owner"]:
   p.goto("https://www.fl.ru/users/olegendorphine/portfolio/",wait_until="domcontentloaded",timeout=20000)
   d["view"]=p.evaluate("""()=>{
    const bs=Array.from(document.querySelectorAll('button')).filter(e=>/Загрузить обложку для ПК/i.test(e.innerText||'')).map(e=>({text:e.innerText.trim(),id:e.id||'',class:e.className||'',parentClass:e.parentElement?.className||'',disabled:e.disabled,ancestorClass:e.parentElement?.parentElement?.className||''}));
    const nodes=Array.from(document.querySelectorAll('[class*=cover], [class*=banner], [class*=header]')).filter(e=>e.getBoundingClientRect().width>600&&e.getBoundingClientRect().height>70).slice(0,35).map(e=>({
      tag:e.tagName,cls:(e.className?.baseVal||e.className||'').toString().slice(0,135),
      width:Math.round(e.getBoundingClientRect().width),height:Math.round(e.getBoundingClientRect().height),
      bg:!!getComputedStyle(e).backgroundImage&&getComputedStyle(e).backgroundImage!=='none',
      images:e.querySelectorAll('img').length
    }));
    return {buttons:bs,candidates:nodes};
   }""")
finally:b.close()
print(json.dumps(d,ensure_ascii=False,sort_keys=True))
