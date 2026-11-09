#!/usr/bin/env python3
"""One owner-approved follow-up: set public page headline AFTER valid display name/surname were saved.
Strictly one new attempt, no personal or paid change, read-after-write independent navigation.
"""
import json,sys,os,tempfile,time
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
URL="https://www.fl.ru/users/olegendorphine/setup/main/"
TITLE="ИИ-ассистенты и автоматизация"
MARKER=ROOT/"fl_headline_after_owner_name_once_20261109.json"
out={"schema":"fl.owner.headline.after_names.once.v1","owner":False,"attempted":False,"verified":False,"status":"not_started","paid_actions":False}
b=Browser()
def navigate(p,url):
 try:r=p.goto(url,wait_until="domcontentloaded",timeout=24000)
 except Exception:
  r=p.goto(url,wait_until="commit",timeout=20000);p.wait_for_timeout(1400)
 if not r or r.status!=200 or not is_fl_url(p.url) or urlsplit(p.url).path!=urlsplit(url).path:
  raise RuntimeError("wrong_page")
try:
 with tempfile.TemporaryDirectory(prefix="fl-owner-title-corrected-",dir=ROOT) as temp:
  b.open(Path(temp));p=b.page
  try:p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=22000)
  except Exception:p.goto(ALLOWED_PAGES["settings"],wait_until="commit",timeout=18000);p.wait_for_timeout(1300)
  a=p.evaluate("""()=>({a:(document.body?.innerText||'').includes('Основные настройки'),b:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com')})""")
  out["owner"]=bool(a["a"] and a["b"] and is_fl_url(p.url))
  if out["owner"]:
   navigate(p,URL)
   form=p.locator('form:has(input[name="pname"])')
   if form.count()!=1:out["status"]="unexpected_form"
   else:
    fields=p.evaluate("""()=>({name:document.querySelector('input[name="name"]')?.value,
     surname:document.querySelector('input[name="surname"]')?.value,
     title:document.querySelector('input[name="pname"]')?.value})""")
    if (fields["name"],fields["surname"])!=("Oleg","Endorphine"):
     out["status"]="display_name_not_expected"
    elif fields["title"]==TITLE:out["status"]="already_target";out["verified"]=True
    elif fields["title"].strip():out["status"]="other_title_present"
    elif MARKER.exists() or MARKER.is_symlink():out["status"]="previous_attempt_stop"
    else:
     submit=form.locator('button[type="submit"]')
     if submit.count()!=1 or submit.inner_text().strip()!="Сохранить":
      out["status"]="wrong_submit"
     elif form.locator('input[name*="payment"],input[name*="card"],input[name="promo"]').count():
      out["status"]="payment_input_present"
     else:
      form.locator('input[name="pname"]').fill(TITLE)
      if not form.evaluate("(e)=>e.checkValidity()"):
       out["status"]="invalid_local_form"
      else:
       fd=os.open(MARKER,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
       with os.fdopen(fd,"w") as f:
        json.dump({"created_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"action":"one_public_title_attempt"},f);f.flush();os.fsync(f.fileno())
       try:
        with p.expect_response(lambda r:r.request.method=="POST" and is_fl_url(r.url),timeout=16000) as reply:
         submit.click(timeout=14000)
        out["post_status"]=reply.value.status
       except Exception:
        out["post_status"]="unknown"
       out["attempted"]=True
       p.wait_for_timeout(900)
       out["error_messages"]=p.evaluate("""()=>Array.from(document.querySelectorAll('[role=alert],[class*=error],.b-layout__txt_color_red')).map(e=>(e.innerText||'').trim()).filter(x=>x.length>3&&x.length<170).slice(0,8)""")
       try:
        navigate(p,URL)
        new=p.locator('input[name="pname"]').input_value()
        out["verified"]=new==TITLE
        out["result_title_present"]=bool(new.strip())
        out["status"]="saved_verified" if out["verified"] else "not_persisted_no_retry"
       except Exception:
        out["status"]="uncertain_do_not_retry"
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
