#!/usr/bin/env python3
"""Inventory of OWN FL freelancer account; READ ONLY. No credentials, form values, personal messages or cookies in output."""
from pathlib import Path
from urllib.parse import urlsplit
import sys,tempfile,json,re
root=Path.home()/".fl-agent"
sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
PUBLIC="https://www.fl.ru/users/olegendorphine/"
out={"schema":"fl.owner.profile.free.inventory.v1","owner_verified":False,
     "write_actions":False,"payments":False,"profile_pages":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-profile-readonly-",dir=root) as tempdir:
  b.open(Path(tempdir))
  page=b.page
  page.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  sign=page.evaluate("""() => ({
    settings: (document.body?.innerText||'').includes('Основные настройки'),
    owner: Array.from(document.querySelectorAll('input')).some(
      e => (e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com')
  })""")
  out["owner_verified"]=bool(sign.get("settings") and sign.get("owner") and is_fl_url(page.url))
  if out["owner_verified"]:
   def inspect(label,url):
    record={"label":label,"status":"unavailable"}
    try:
     response=page.goto(url,wait_until="domcontentloaded",timeout=24000)
     page.wait_for_timeout(400)
     if not is_fl_url(page.url): record["status"]="non_fl_domain";return record
     d=page.evaluate("""() => {
       const t=(document.body?.innerText||'');
       const h1=(document.querySelector('h1')?.innerText||'').trim();
       const getName=e=>(e.innerText||e.textContent||'').trim().replace(/\\s+/g,' ').slice(0,75);
       const links=Array.from(document.querySelectorAll('a[href]')).map(a=>({
         text:getName(a),url:new URL(a.getAttribute('href'),location.href)
       })).filter(o=>o.text.length>1&&o.url.hostname.endsWith('fl.ru')&&!o.url.search)
       .filter(o=>/настройк|портфолио|услуг|цен|прайс|профил|контакт|информац|специализ|работ|финанс|бизнес|уведомл|подпис|PRO/i.test(o.text))
       .slice(0,90).map(o=>({text:o.text,path:o.url.pathname.slice(0,130)}));
       const fields=Array.from(document.querySelectorAll('main input,main textarea,main select,form input,form textarea,form select')).filter(e=>!['hidden','password','file'].includes(e.type||'')&&e.getBoundingClientRect().width>0)
       .slice(0,50).map(e=>{
          const labels=e.labels?Array.from(e.labels).map(getName):[];
          const parent=e.closest('label') || e.parentElement?.parentElement;
          return {type:(e.type||e.tagName).slice(0,18),
            id:(e.id||'').slice(0,70),name:(e.name||'').slice(0,70),
            label:labels.join(' ').slice(0,95) || (parent?.innerText||'').trim().slice(0,100),
            value_present:!!String(e.value||'').trim(),value_length:String(e.value||'').length,
            placeholder:(e.getAttribute('placeholder')||'').slice(0,85),
            readonly:!!e.readOnly,disabled:!!e.disabled};
       });
       const buttons=Array.from(document.querySelectorAll('button,input[type="submit"],[role="button"]')).map(getName)
       .filter(Boolean).filter(v=>/сохран|добав|редакт|измен|загруз|удал|созда|покуп|оформ|PRO|верифиц|выбр|обнов|оплат|портфолио|услуг/i.test(v))
       .slice(0,48);
       const headings=Array.from(document.querySelectorAll('h1,h2,h3')).map(getName).filter(Boolean).slice(0,35);
       const sectionwords=['Портфолио','О себе','Обо мне','Специализация','Услуги и цены','Прайс-лист','Типовые услуги','Магазин услуг','PRO','Отзывы'];
       return {title:document.title.slice(0,140),h1:h1.slice(0,140),
         headings,links,fields,buttons,
         sectionWords:Object.fromEntries(sectionwords.map(s=>[s,t.includes(s)])),
         bodyLength:t.length,mainLength:(document.querySelector('main')?.innerText||'').length,
         alertTexts:Array.from(document.querySelectorAll('[role=alert],.alert,.ui-alert')).map(getName).filter(Boolean).slice(0,8)};
     }""")
     record.update({"status":"ok","http":response.status if response else None,
                    "path":urlsplit(page.url).path,"page":d})
    except Exception as e:
     record["status"]="timeout" if "timeout" in str(e).lower() else "error"
    return record
   targets=[("public_profile",PUBLIC),("main_settings",ALLOWED_PAGES["settings"]),
            ("portfolio","https://www.fl.ru/users/olegendorphine/portfolio/"),
            ("services","https://www.fl.ru/users/olegendorphine/tu/"),
            ("price_list","https://www.fl.ru/users/olegendorphine/prices/")]
   for label,url in targets: out["profile_pages"].append(inspect(label,url))
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
