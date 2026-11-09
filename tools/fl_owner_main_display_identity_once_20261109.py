#!/usr/bin/env python3
"""Owner-directed FL freelancer profile name/surname and page heading, one guarded save.
Changes ONLY visible name/surname and page title; verifies result in a new read.
"""
import os,sys,json,time,tempfile
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent"
sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser, ALLOWED_PAGES, is_fl_url
URL="https://www.fl.ru/users/olegendorphine/setup/main/"
PUBLIC="https://www.fl.ru/users/olegendorphine/portfolio/"
NAME="Oleg"
SURNAME="Endorphine"
TITLE="ИИ-ассистенты и автоматизация"
MARKER=ROOT/"fl_identity_display_title_20261109_once.json"
out={"schema":"fl.owner.identity.title.once.v1","account":"olegendorphine",
 "owner_verified":False,"attempted":False,"verified":False,"paid_actions":False,"security_changed":False,
 "result":"not_started"}
def goto(page,url):
 try:r=page.goto(url,wait_until="domcontentloaded",timeout=24000)
 except Exception:
  r=page.goto(url,wait_until="commit",timeout=18000)
  page.wait_for_timeout(1400)
 if not is_fl_url(page.url) or urlsplit(page.url).path!=urlsplit(url).path:
  raise RuntimeError("unexpected_navigation")
 return r
def status(page):
 return page.evaluate("""()=>({
  name:document.querySelector('input[name="name"]')?.value||'',
  surname:document.querySelector('input[name="surname"]')?.value||'',
  title:document.querySelector('input[name="pname"]')?.value||''
 })""")
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-identity-once-",dir=ROOT) as work:
  b.open(Path(work))
  p=b.page
  try:p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  except Exception:p.goto(ALLOWED_PAGES["settings"],wait_until="commit",timeout=17000);p.wait_for_timeout(1300)
  auth=p.evaluate("""()=>({
   settings:(document.body?.innerText||'').includes('Основные настройки'),
   owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
   login:!!document.querySelector('form[action*="/account/login"]')})""")
  out["owner_verified"]=bool(auth["settings"] and auth["owner"] and not auth["login"] and is_fl_url(p.url))
  if out["owner_verified"]:
   goto(p,URL)
   fields=p.locator('form:has(input[name="pname"])')
   if fields.count()!=1:out["result"]="unexpected_form"
   else:
    current=status(p)
    if current=={"name":NAME,"surname":SURNAME,"title":TITLE}:
     out["result"]="already_correct";out["verified"]=True
    elif any(current[k].strip() and current[k] != v for k,v in
         [("name",NAME),("surname",SURNAME),("title",TITLE)]):
     out["result"]="nonempty_conflicting_owner_value_stop"
    elif MARKER.exists() or MARKER.is_symlink():
     out["result"]="prior_attempt_exists_stop"
    else:
     submit=fields.locator('button[type="submit"]')
     if submit.count()!=1 or submit.inner_text().strip()!="Сохранить":
      out["result"]="unexpected_submit"
     elif fields.locator('input[type="password"]').count() and any(x.strip() for x in
       fields.locator('input[type="password"]').evaluate_all("(els)=>els.map(e=>e.value||'')")):
      out["result"]="password_form_not_empty"
     elif fields.locator('input[name*="payment"], input[name*="card"], input[name="promo"]').count():
      out["result"]="payment_input_present"
     else:
      for key,value in [("name",NAME),("surname",SURNAME),("pname",TITLE)]:
       f=fields.locator('input[name="'+key+'"]')
       if f.count()!=1:raise RuntimeError("field_not_unique")
       f.fill(value,timeout=5000)
      if status(p)!={"name":NAME,"surname":SURNAME,"title":TITLE}:
       raise RuntimeError("pre_submit_values_mismatch")
      valid=fields.evaluate("(f)=>f.checkValidity()")
      if not valid:out["result"]="client_validation_failed"
      else:
       fd=os.open(MARKER,os.O_EXCL|os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW,0o600)
       with os.fdopen(fd,"w") as f:
        json.dump({"timestamp":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
         "form":"owner_main","status":"intent_before_one_click"},f)
        f.flush();os.fsync(f.fileno())
       try:
        with p.expect_response(lambda r:r.request.method=="POST" and is_fl_url(r.url),timeout=16000) as reply:
         submit.click(timeout=13000)
        out["post_status"]=reply.value.status
       except Exception:
        out["post_status"]="not_observed"
       out["attempted"]=True
       p.wait_for_timeout(750)
       out["server_feedback"]=p.evaluate("""()=>{
         const all=Array.from(document.querySelectorAll('[role=alert],[class*=error],.b-layout__txt_color_red'))
         .map(e=>(e.innerText||'').trim()).filter(x=>x.length>3&&x.length<200).slice(0,10);
         return all;
       }""")
       try:
        goto(p,URL)
        value=status(p)
        out["verified"]=value=={"name":NAME,"surname":SURNAME,"title":TITLE}
        out["field_check"]={k:(value[k]==v) for k,v in [("name",NAME),("surname",SURNAME),("title",TITLE)]}
        out["result"]="saved_verified" if out["verified"] else "not_saved_do_not_repeat"
       except Exception:
        out["result"]="uncertain_result_do_not_repeat"
finally:
 b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
