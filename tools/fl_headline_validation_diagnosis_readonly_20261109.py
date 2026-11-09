#!/usr/bin/env python3
"""FL owner title diagnosis; only inspect and validate local form, DO NOT submit."""
import json,sys,tempfile
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent"
sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
TITLE="ИИ-ассистенты и автоматизация бизнеса | API, VPS"
OUT={"schema":"fl.headline.diagnosis.readonly.v1","owner_verified":False,"writes":False,"diagnostics":{},"status":"not_started"}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-headline-validate-",dir=ROOT) as tmp:
  b.open(Path(tmp))
  p=b.page
  try:
   p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=23000)
  except Exception:
   p.goto(ALLOWED_PAGES["settings"],wait_until="commit",timeout=20000)
   p.wait_for_timeout(1400)
  data=p.evaluate("""() => ({
    owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
    settings:(document.body?.innerText||'').includes('Основные настройки')
  })""")
  OUT["owner_verified"]=bool(data["owner"] and data["settings"] and is_fl_url(p.url))
  if OUT["owner_verified"]:
   url="https://www.fl.ru/users/olegendorphine/setup/main/"
   try:
    p.goto(url,wait_until="domcontentloaded",timeout=25000)
   except Exception:
    p.goto(url,wait_until="commit",timeout=18000)
    p.wait_for_timeout(1500)
   if urlsplit(p.url).path!=urlsplit(url).path or not is_fl_url(p.url):
    OUT["status"]="redirected"
   else:
    OUT["diagnostics"]=p.evaluate("""(title) => {
      const field=document.querySelector('input[name=pname]');
      const form=field?.closest('form');
      const getLabel=(e)=>{
        const labels=e.labels?Array.from(e.labels).map(x=>x.innerText.trim()).filter(Boolean):[];
        return labels.join(' / ').slice(0,120) || (e.closest('div.form-group,div[class*=input],label')?.innerText||'').trim().slice(0,120);
      };
      if(!form)return {error:"form_missing"};
      const initial={formValid:form.checkValidity(),titleLength:(field.value||'').length};
      const individual=Array.from(form.elements).filter(e=>e.matches?.('input,textarea,select')&&e.type!=='hidden'&&e.type!=='password').map(e=>({
        name:e.name||'',type:e.type||'',label:getLabel(e),required:e.required,
        maxlength:e.maxLength||null,minlength:e.minLength||null,pattern:(e.pattern||'').slice(0,140),
        present:!!String(e.value||'').trim(),valid:e.checkValidity(),
        validity:{valueMissing:e.validity?.valueMissing||false,patternMismatch:e.validity?.patternMismatch||false,
        tooLong:e.validity?.tooLong||false,tooShort:e.validity?.tooShort||false,typeMismatch:e.validity?.typeMismatch||false},
        disabled:e.disabled,readOnly:e.readOnly
      }));
      const original=field.value;
      field.value=title;
      const candidate={titleValid:field.checkValidity(),formValid:form.checkValidity(),
        titleValidityMessage:field.validationMessage.slice(0,140),
        titleMaxLength:field.maxLength, titlePattern:field.pattern, titleRequired:field.required,
        invalidFields:Array.from(form.elements).filter(e=>e.matches?.('input,textarea,select')&&!e.checkValidity()).map(e=>({name:e.name||'',type:e.type||'',
        validation:e.validationMessage.slice(0,160),required:e.required,label:getLabel(e)})).slice(0,15)};
      field.value=original;
      return {initial,individual,candidate,formAction:form.getAttribute('action'),method:form.method,
        submitButtons:Array.from(form.querySelectorAll('button,input[type=submit]')).map(e=>({text:(e.innerText||e.value||'').trim().slice(0,50),disabled:e.disabled,type:e.type})),
        onpageNotices:Array.from(document.querySelectorAll('[role=alert],.alert,[class*=error]')).map(e=>(e.innerText||'').trim()).filter(x=>x.length>2&&x.length<180).slice(0,12),
        pageHeader:(document.querySelector('h1')?.innerText||'').slice(0,110)};
    }""",TITLE)
    OUT["status"]="checked"
finally:
 b.close()
print(json.dumps(OUT,ensure_ascii=False))
