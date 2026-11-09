#!/usr/bin/env python3
"""Read-only form metadata for owner FL profile editing; no account writes."""
from pathlib import Path
from urllib.parse import urlsplit
import sys,json,tempfile
root=Path.home()/".fl-agent";sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
out={"schema":"fl.owner.profile.edit.preflight.v1","owner_verified":False,"writes":False,"pages":[]}
urls=[
("main","https://www.fl.ru/users/olegendorphine/setup/main/"),
("about","https://www.fl.ru/users/olegendorphine/setup/portfolio/"),
("prices","https://www.fl.ru/users/olegendorphine/price-list/"),
("works","https://www.fl.ru/users/olegendorphine/portfolio/"),
("services","https://www.fl.ru/users/olegendorphine/uslugi-freelancera/"),
]
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-profile-preflight-",dir=root) as t:
  b.open(Path(t));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=18000)
  v=p.evaluate("""() => ({settings:(document.body?.innerText||'').includes('Основные настройки'),owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com')})""")
  out["owner_verified"]=bool(v["settings"] and v["owner"] and is_fl_url(p.url))
  if out["owner_verified"]:
   for name,url in urls:
    d={"name":name}
    try:
     rsp=p.goto(url,wait_until="domcontentloaded",timeout=20000)
     p.wait_for_timeout(500)
     d["http"]=rsp.status if rsp else None
     d["same_fl"]=is_fl_url(p.url)
     d["dom"]=p.evaluate("""() => {
      const text=(e)=>(e?.innerText||'').trim().replace(/\\s+/g,' ').slice(0,120);
      const inputs=Array.from(document.querySelectorAll('input,textarea,select')).filter(e=>!['hidden','password','file'].includes(e.type||'') && e.getBoundingClientRect().width>0);
      const formInfo=Array.from(document.querySelectorAll('form')).map(f=>({
        id:(f.id||'').slice(0,40),
        method:(f.getAttribute('method')||'').slice(0,16),
        action:(f.getAttribute('action')||'').split('?')[0].slice(0,120),
        fields:Array.from(f.querySelectorAll('input,textarea,select')).map(x=>x.name).filter(Boolean).slice(0,28),
        buttons:Array.from(f.querySelectorAll('button,input[type=submit]')).map(text).filter(Boolean).slice(0,12)
      }));
      const focus=inputs.filter(e=>['pname','ab_text','title','price','days','exp','cost_hour','cost_month'].includes(e.name)).map(e=>({
        name:e.name,tag:e.tagName,type:e.type,id:e.id,
        maxlength:e.maxLength,minlength:e.minLength,required:e.required,
        placeholder:(e.getAttribute('placeholder')||'').slice(0,130),
        initial_length:String(e.value||'').length,
        outer:e.outerHTML.slice(0,350).replace(/value="[^"]*"/g,'value="[redacted]"').replace(/>[^<]{40,}</g,'>[redacted]<'),
        formAction:e.closest('form')?.getAttribute('action')||null,
        nearbyText:text(e.closest('label')||e.closest('[class*=form-group]')||e.parentElement?.parentElement)
      }));
      const buttons=Array.from(document.querySelectorAll('button,[role=button],input[type=submit],a')).filter(e=>/добавить работу|добавить услугу|сохранить|изменить/i.test(text(e))).slice(0,14).map(e=>({text:text(e),tag:e.tagName,type:e.type||null,href:e.getAttribute('href'),outer:e.outerHTML.slice(0,370)}));
      const body=(document.body?.innerText||'').slice(-3000).replace(/(?:[a-z0-9._%+-]+)@(?:[a-z0-9.-]+\\.[a-z]{2,})/ig,'[REDACTED_EMAIL]');
      return {title:document.title.slice(0,110),focus,forms:formInfo.slice(-10),buttons,footer:body.slice(-1000)};
     }""")
    except Exception as ex:
     d["error"]="timeout" if "timeout" in str(ex).lower() else "other"
    out["pages"].append(d)
finally:b.close()
print(json.dumps(out,ensure_ascii=False))
