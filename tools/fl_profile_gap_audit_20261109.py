#!/usr/bin/env python3
"""Private owner profile gap audit: read-only, no private values, no contacts, no cookies."""
from pathlib import Path
import sys,json,tempfile
from urllib.parse import urlsplit
root=Path.home()/".fl-agent";sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
urls=[
 ("notifications","https://www.fl.ru/users/olegendorphine/setup/mailer/"),
 ("portfolio_sections","https://www.fl.ru/users/olegendorphine/setup/portfsetup/"),
 ("services","https://www.fl.ru/users/olegendorphine/uslugi-freelancera/"),
 ("main","https://www.fl.ru/users/olegendorphine/setup/main/"),
 ("public_portfolio","https://www.fl.ru/users/olegendorphine/portfolio/")
]
out={"schema":"fl.owner.profile.gaps.v1","owner":False,"read_only":True,"payments":False,"pages":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-gap-readonly-",dir=root) as t:
  b.open(Path(t));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  s=p.evaluate("""()=>({
   owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
   settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner"]=bool(s["owner"] and s["settings"] and is_fl_url(p.url))
  if out["owner"]:
   for label,url in urls:
    x={"label":label,"status":"pending"}
    try:
     resp=p.goto(url,wait_until="domcontentloaded",timeout=24000)
     p.wait_for_timeout(450)
     if not is_fl_url(p.url):x["status"]="bad_redirect";out["pages"].append(x);continue
     x["status"]="ok";x["http"]=resp.status if resp else None
     x["view"]=p.evaluate("""() => {
      const trim=s=>(s||'').trim().replace(/\\s+/g,' ').slice(0,90);
      const text=document.body?.innerText||'';
      const all=Array.from(document.querySelectorAll('input[type=checkbox],input[type=radio]')).filter(e=>e.getBoundingClientRect().width>0)
        .map(e=>({name:e.name||'',id:e.id||'',checked:e.checked,disabled:e.disabled,label:trim(e.labels?.[0]?.innerText||e.parentElement?.innerText)})).slice(0,70);
      const btns=Array.from(document.querySelectorAll('button,[role=button],a')).filter(e=>e.getBoundingClientRect().width>0)
        .map(e=>({txt:trim(e.innerText),tag:e.tagName,path:e.tagName==='A'?(new URL(e.getAttribute('href')||'/',location.origin)).pathname:null})).filter(x=>/добавить|изменить|настроить|сохранить|создать|загрузить|публикац|разместить/i.test(x.txt)).slice(0,35);
      const payments=text.match(/\\d[\\d ]{2,}\s*руб\\./g)||[];
      const form=document.querySelector('form:has(input[name=pname])');
      let fm=form?{validation:form.checkValidity(),nameEmpty:!(form.querySelector('input[name=name]')?.value||'').trim(),
       surnameEmpty:!(form.querySelector('input[name=surname]')?.value||'').trim(),pnameEmpty:!(form.querySelector('input[name=pname]')?.value||'').trim(),
       hasOldPwd:!!form.querySelector('input[name=oldpwd]'),
       formAction:form.getAttribute('action'),submitDisabled:!!form.querySelector('button[type=submit]')?.disabled,
       controls:Array.from(form.querySelectorAll('input')).filter(e=>e.type!=='hidden'&&e.type!=='password').map(e=>({name:e.name,required:e.required,valid:e.checkValidity(),minLength:e.minLength,maxLength:e.maxLength})).slice(0,8)
       }:null;
      let entries=Array.from(document.querySelectorAll('[data-id*=typical-service], [class*=typical-service]')).length;
      return {h1:trim(document.querySelector('h1')?.innerText),checks:all,buttons:btns,
       serviceEmpty:text.includes('Здесь будет список ваших типовых услуг'),
       servicePending:/на модерации|ожидает модерации|проверка модератором/i.test(text),
       portfolioEmpty:/Создать работу для портфолио|Добавить работу/i.test(text),
       pricesBanner:payments.slice(0,3),form:fm,
       tabTitles:Array.from(document.querySelectorAll('h2,h3,h4')).map(e=>trim(e.innerText)).filter(Boolean).slice(0,25),
       serviceDOMEntries:entries};
     }""")
    except Exception as ex: x["status"]="timeout" if "timeout" in str(ex).lower() else "error"
    out["pages"].append(x)
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
