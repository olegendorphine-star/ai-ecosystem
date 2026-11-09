#!/usr/bin/env python3
"""Read-only followup on FL public profile and price-list; no personal data in outputs."""
from pathlib import Path
import sys,json,tempfile
root=Path.home()/".fl-agent";sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
o={"schema":"fl.owner.public.profile.after-update.v1","verified_owner":False,
"pages":[],"no_account_writes":True}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-profile-verify-",dir=root) as t:
  b.open(Path(t));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=22000)
  a=p.evaluate("""()=>({
    owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
    settings:(document.body?.innerText||'').includes('Основные настройки')
  })""")
  o["verified_owner"]=bool(a["owner"] and a["settings"] and is_fl_url(p.url))
  if o["verified_owner"]:
   for label,url in [
    ("main","https://www.fl.ru/users/olegendorphine/setup/main/"),
    ("about","https://www.fl.ru/users/olegendorphine/setup/portfolio/"),
    ("public","https://www.fl.ru/users/olegendorphine/portfolio/"),
    ("price","https://www.fl.ru/users/olegendorphine/price-list/")
   ]:
    r=p.goto(url,wait_until="domcontentloaded",timeout=22000)
    p.wait_for_timeout(350)
    data=p.evaluate("""() => {
      const text=document.body?.innerText||'';
      const field=document.querySelector('input[name=pname]');
      const about=document.querySelector('textarea[name=ab_text]');
      const forms=Array.from(document.querySelectorAll('form')).filter(f=>f.querySelector('input[name=pname]'));
      const fields=forms.flatMap(f=>Array.from(f.querySelectorAll('input,select,textarea')).map(e=>({
          name:e.name,tag:e.tagName,type:e.type,
          parentText:(e.parentElement?.parentElement?.innerText||'').trim().slice(0,70),
          present:!!(e.value||'').trim()
      }))).filter(f=>f.name&&f.type!=='hidden'&&f.type!=='password').slice(0,20);
      const errors=Array.from(document.querySelectorAll('[class*=error],[role=alert]')).map(e=>(e.innerText||'').trim()).filter(e=>e.length>3&&e.length<140).slice(0,8);
      return {
         heading:(document.querySelector('h1')?.innerText||'').slice(0,100),
         pname_len:field?.value?.length ?? null,
         pname_is_target:field?.value==='ИИ-ассистенты и автоматизация бизнеса | API, VPS',
         about_len:about?.value?.length ?? null,
         about_is_target:about?.value?.startsWith('Создаю ИИ-ассистентов и автономные ИИ-экосистемы')??false,
         title_labels:fields,
         public_mentions_ai_staff:text.includes('персональный ИИ-«Штаб»')||text.includes('действующий персональный ИИ'),
         public_mentions_prices:text.includes('150 000 ₽'),
         shows_payment:text.includes('Сумма к оплате'),
         errors
      };
    }""")
    o["pages"].push({"page":label,"http":r.status if r else None,"result":data})
finally:b.close()
print(json.dumps(o,ensure_ascii=False))
