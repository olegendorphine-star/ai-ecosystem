#!/usr/bin/env python3
"""One-time owner-authorized FL profile business headline update; no other changes."""
import sys,os,time,json,tempfile
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,is_fl_url
SETTINGS="https://www.fl.ru/users/olegendorphine/setup/main/"
TARGET="ИИ-автоматизация бизнеса"
assert len(TARGET)<=30
PREVIOUS={"ИИ-ассистенты и автоматизация бизнеса","ИИ-ассистенты и автоматизация"}
MARKER=ROOT/"fl_owner_title_business_refresh_20261110.intent"
BACKUP=ROOT/"fl_owner_title_business_refresh_20261110.backup.txt"
out={"schema":"fl.owner.business.title.refresh.v1","owner":False,"status":"not_started","clicked":False,
"readback":False,"paid":False,"messages":False,"other_fields_changed":False,"security_changed":False}
b=Browser()
def save_file(path,val):
 f=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 with os.fdopen(f,"w",encoding="utf-8") as file:
  file.write(val);file.flush();os.fsync(file.fileno())
try:
 with tempfile.TemporaryDirectory(prefix="fl-owner-title-refresh-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  r=p.goto(SETTINGS,wait_until="domcontentloaded",timeout=25000)
  v=p.evaluate("""()=>({owner:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner"]=bool(r and r.status==200 and is_fl_url(p.url) and urlsplit(p.url).path==urlsplit(SETTINGS).path and v["owner"] and v["settings"])
  if not out["owner"]:out["status"]="owner_or_settings_not_available"
  else:
   form=p.locator('form:has(input[name="pname"])')
   field=p.locator('input[name="pname"]')
   if form.count()!=1 or field.count()!=1:out["status"]="form_not_unique"
   else:
    old=field.input_value().strip()
    if old==TARGET:out["status"]="already_desired";out["readback"]=True
    elif old not in PREVIOUS:out["status"]="unexpected_existing_title_stop"
    elif MARKER.exists() or BACKUP.exists():out["status"]="previous_attempt_stop"
    elif form.locator('button[type=submit]').count()!=1 or form.locator('button[type=submit]').inner_text().strip()!="Сохранить":out["status"]="unexpected_save_button"
    elif form.locator('input[name="oldpwd"]').count() and form.locator('input[name="oldpwd"]').input_value().strip():out["status"]="password_input_in_use"
    elif form.locator('input[name*="payment"],input[name*="card"]').count():out["status"]="payment_fields_present"
    else:
     save_file(BACKUP,old)
     field.fill(TARGET)
     if field.input_value()!=TARGET or not form.evaluate("(f)=>f.checkValidity()"):out["status"]="form_validation_failed"
     else:
      save_file(MARKER,json.dumps({"action":"title_only","time":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}))
      try:
       form.locator('button[type=submit]').click(timeout=15000)
       out["clicked"]=True
       p.wait_for_timeout(900)
       resp=p.goto(SETTINGS,wait_until="domcontentloaded",timeout=23000)
       out["readback"]=bool(resp and resp.status==200 and is_fl_url(p.url) and field.input_value().strip()==TARGET)
       out["status"]="saved_verified" if out["readback"] else "uncertain_after_click_no_retry"
      except Exception:out["status"]="uncertain_after_click_no_retry"
finally:
 b.close()
 print(json.dumps(out,ensure_ascii=False,sort_keys=True))
