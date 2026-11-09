#!/usr/bin/env python3
"""Read-only inspection after opening FL typical service composer. Never submit."""
from pathlib import Path
import sys,json,tempfile
from urllib.parse import urlsplit
root=Path.home()/".fl-agent";sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
URL="https://www.fl.ru/users/olegendorphine/uslugi-freelancera/"
out={"schema":"fl.owner.service.composer.inspect.v1","owner_verified":False,
"no_writes":True,"no_purchases":True,"clicked_open_editor":False}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-service-inspect-",dir=root) as t:
  b.open(Path(t));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=19000)
  s=p.evaluate("""()=>({owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner_verified"]=bool(s["owner"] and s["settings"] and is_fl_url(p.url))
  if out["owner_verified"]:
   p.goto(URL,wait_until="domcontentloaded",timeout=22000)
   p.wait_for_timeout(500)
   button=p.locator('button[data-id="typical-services-block_add_button"]')
   if button.count()!=1:out["status"]="button_not_unique"
   else:
    button.click(timeout=7000)
    out["clicked_open_editor"]=True
    p.wait_for_timeout(950)
    out["location_scope"]=urlsplit(p.url).hostname
    out["status"]="opened"
    out["editor"]=p.evaluate("""() => {
      const tx=e=>(e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,100);
      const fields=Array.from(document.querySelectorAll('input,select,textarea,[contenteditable=true]')).filter(e=>e.getBoundingClientRect().width>0 && !['hidden','password','file'].includes(e.type||'')).slice(0,75).map(e=>({
        tag:e.tagName,type:e.type||'',id:(e.id||'').slice(0,65),
        name:(e.name||'').slice(0,65),maxLength:e.maxLength||null,
        placeholder:(e.getAttribute('placeholder')||'').slice(0,110),
        valuePresent:!!(e.value||'').trim(),
        nearby:(e.closest('label')?.innerText||'').trim().slice(0,100)
      }));
      const buttons=Array.from(document.querySelectorAll('button,[role=button]')).filter(e=>e.getBoundingClientRect().width>0).map(tx).filter(Boolean).slice(-35);
      const t=(document.body?.innerText||'');
      const terms=['Стоимость','Цена','Название','Описание','Срок','Изображение','Создать','Опубликовать','PRO','Оплатить'];
      return {fields,buttons,terms:Object.fromEntries(terms.map(x=>[x,t.includes(x)])),
        recentText:t.slice(-1800).replace(/(?:[a-z0-9._%+-]+)@(?:[a-z0-9.-]+\\.[a-z]{2,})/ig,'[REDACTED]')};
    }""")
finally:b.close()
print(json.dumps(out,ensure_ascii=False))
