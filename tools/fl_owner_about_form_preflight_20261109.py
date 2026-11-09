#!/usr/bin/env python3
"""Owner-only preflight of FL profile text form; never writes or reads messages."""
from pathlib import Path
import sys,json,tempfile
root=Path.home()/".fl-agent";sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
out={"schema":"fl.owner.about.preflight.v1","owner":False,"status":"unknown","fields":{},"changed":False}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-about-preflight-",dir=root) as t:
  b.open(Path(t));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=23000)
  a=p.evaluate("""()=>({owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner"]=bool(a["owner"] and a["settings"] and is_fl_url(p.url))
  if out["owner"]:
   p.goto("https://www.fl.ru/users/olegendorphine/setup/portfolio/",wait_until="domcontentloaded",timeout=23000)
   out["fields"]=p.evaluate("""()=>{
    const a=document.querySelector('textarea[name=ab_text]');if(!a)return {found:false};
    const form=a.closest('form');const btns=Array.from(form.querySelectorAll('button')).map(b=>({label:(b.innerText||'').trim(),type:b.type,enabled:!b.disabled}));
    return {found:true, maxlength:a.maxLength,length:a.value.length, prefix:a.value.slice(0,90), is_sales_copy:(a.value.length===494 && a.value.startsWith('ИИ для реальных задач.') && a.value.endsWith('Опишите задачу — предложу первый шаг и бюджет.')),
       formmethod:form.method,formaction:new URL(form.action,location.href).pathname,buttons:btns,
       fields:Array.from(form.querySelectorAll('input,textarea')).map(x=>({name:x.name,type:x.type,length:(x.value||'').length})).filter(x=>x.name)};
   }""")
   out["status"]="ok"
finally:b.close()
print(json.dumps(out,ensure_ascii=False))
