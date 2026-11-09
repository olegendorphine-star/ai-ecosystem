#!/usr/bin/env python3
"""Read-only inspect portfolio section selector for user-owned FL, no personal values."""
from pathlib import Path
import sys,tempfile,json
root=Path.home()/".fl-agent";sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
out={"schema":"fl.owner.portfolio.section.detail.v1","owner":False,"readonly":True}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-section-detail-",dir=root) as t:
  b.open(Path(t));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  s=p.evaluate("""()=>({a:(document.body?.innerText||'').includes('Основные настройки'),b:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com')})""")
  out["owner"]=s["a"] and s["b"] and is_fl_url(p.url)
  if out["owner"]:
   p.goto("https://www.fl.ru/users/olegendorphine/setup/portfsetup/",wait_until="domcontentloaded",timeout=24000)
   out["view"]=p.evaluate("""() => {
    let checkboxes=Array.from(document.querySelectorAll('input[name="prof[]"]')).map(e=>({
      id:e.id,checked:e.checked,label:(e.labels?.[0]?.innerText||e.parentElement?.innerText||'').trim().replace(/\\s+/g,' ').slice(0,100),
      v:e.value,
    }));
    let target=checkboxes.filter(e=>/нейрон|AI|ии|бот|автоматиз|API|баз|знани|n8n|консалт|Python|интеграц|данных|обработк|технич|систем|программир|разработ/i.test(e.label));
    let forms=Array.from(document.forms).map(f=>({method:f.method,action:f.getAttribute('action')?.split('?')[0]||'',inputs:f.querySelectorAll('input[name="prof[]"]').length,buttons:Array.from(f.querySelectorAll('button,[type=submit]')).map(e=>e.innerText?.trim()).filter(Boolean)})).filter(x=>x.inputs);
    let saves=Array.from(document.querySelectorAll('a,button,input[type=submit]')).filter(e=>/сохранить изменения/i.test(e.innerText||e.value||'')).map(e=>({tag:e.tagName,href:e.getAttribute('href')||'',type:e.getAttribute('type')||'',id:e.id,outer:e.outerHTML.slice(0,500).replace(/u_token_key[^&" ]+/g,'[redacted]')})); 
    return {total:checkboxes.length,checkedTotal:checkboxes.filter(x=>x.checked).length,checked:checkboxes.filter(x=>x.checked).slice(0,80),
      matches:target,forms,saves};
   }""")
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
