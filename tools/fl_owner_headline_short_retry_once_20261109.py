#!/usr/bin/env python3
"""One final owner-approved public PAGE TITLE update, no private fields or paid actions.

Try a shorter semantic title once; inspect validation and read-after-write.
A prior attempt with longer title had no persistence, but this uses a NEW marker.
"""
import os,sys,json,tempfile,time
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
TITLE="ИИ-ассистенты, AI-агенты и автоматизация"
URL="https://www.fl.ru/users/olegendorphine/setup/main/"
PUBLIC="https://www.fl.ru/users/olegendorphine/portfolio/"
MARK=ROOT/"fl_headline_short_v2_intent_20261109.json"
OUT={"schema":"fl.owner.headline.short.v2","owner":False,"tried":False,"confirmed":False,"paid":False,"changed_personal":False,"status":"not_started"}
def checked_goto(page,url):
 try:resp=page.goto(url,wait_until="domcontentloaded",timeout=24000)
 except Exception:
  resp=page.goto(url,wait_until="commit",timeout=18000)
  page.wait_for_timeout(1500)
 if not resp or resp.status!=200 or not is_fl_url(page.url) or urlsplit(page.url).path not in (urlsplit(url).path,"/users/olegendorphine/setup/main/"):
  raise RuntimeError("wrong_page")
 return resp
def mark():
 fd=os.open(MARK,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600)
 with os.fdopen(fd,"w") as f:
  json.dump({"created":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"action":"one_public_title_submit","text":TITLE},f,ensure_ascii=False)
  f.flush();os.fsync(f.fileno())
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-short-headline-",dir=ROOT) as tmp:
  b.open(Path(tmp));p=b.page
  checked_goto(p,ALLOWED_PAGES["settings"])
  o=p.evaluate("""()=>({
    owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
    settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  OUT["owner"]=o["owner"] and o["settings"] and is_fl_url(p.url)
  if OUT["owner"]:
   checked_goto(p,URL)
   field=p.locator('input[name="pname"]')
   form=p.locator('form:has(input[name="pname"])')
   if field.count()!=1 or form.count()!=1:OUT["status"]="wrong_form"
   elif field.input_value().strip():OUT["status"]="title_already_changed_by_owner"
   elif MARK.exists() or MARK.is_symlink():OUT["status"]="prior_attempt_no_retry"
   else:
    if form.locator('button[type=submit]').count()!=1 or form.locator('button[type=submit]').inner_text().strip()!="Сохранить":
     OUT["status"]="submit_mismatch"
    else:
     field.fill(TITLE,timeout=5000)
     verification=form.evaluate("""f=>({valid:f.checkValidity(),
       titleValid:f.querySelector('input[name=pname]')?.checkValidity(),
       buttonEnabled:!f.querySelector('button[type=submit]')?.disabled,
       noPayment:!f.querySelector('input[name*=payment],input[name*=card],input[name=promo]')})""")
     if not all(verification.values()):
      OUT["status"]="validation_failed"
     else:
      mark()
      submit=form.locator('button[type=submit]')
      try:
       with p.expect_response(lambda r:r.request.method=="POST" and is_fl_url(r.url),timeout=14000) as reply:
        submit.click(timeout=12500)
       response=reply.value
       OUT["response_status"]=response.status
       OUT["post_path"]=urlsplit(response.url).path
       OUT["tried"]=True
      except Exception as e:
       OUT["tried"]=True
       OUT["response_status"]="unobserved"
      p.wait_for_timeout(750)
      OUT["feedback"]=p.evaluate("""()=>{
       const errors=Array.from(document.querySelectorAll('[role=alert],[class*=error],.b-layout__txt_color_red'))
       .map(e=>(e.innerText||'').trim()).filter(x=>x.length>2&&x.length<200).slice(0,10);
       const toast=Array.from(document.querySelectorAll('[class*=success],[class*=notice]'))
       .map(e=>(e.innerText||'').trim()).filter(x=>x.length>2&&x.length<120).slice(0,6);
       return {errors,toast};
      }""")
      try:
       checked_goto(p,URL)
       OUT["confirmed"]=p.locator('input[name=pname]').input_value()==TITLE
       OUT["persisted_length"]=len(p.locator('input[name=pname]').input_value())
       OUT["status"]="saved_verified" if OUT["confirmed"] else "not_persisted_no_retry"
       checked_goto(p,PUBLIC)
       OUT["public_doc_title_contains"]=TITLE in p.title()
      except Exception:
       OUT["status"]="result_unknown_do_not_retry"
finally:b.close()
print(json.dumps(OUT,ensure_ascii=False))
