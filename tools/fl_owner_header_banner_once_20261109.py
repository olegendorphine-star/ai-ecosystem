#!/usr/bin/env python3
"""One owner-requested desktop banner replacement. No payments or messages.
Use only the actual existing FL profile editor and exact private JPEG.
"""
import sys,os,json,hashlib,tempfile,time
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
ASSET=ROOT/"artwork_20261109"/"01_banner_FL_1920x400.jpg"
SHA="45ba506ed1a7bcf726b0de35a6572e9d1787c77f8f844b1375c8d0750ac05377"
MARKER=ROOT/"fl_header_banner_20261109.intent"
URL="https://www.fl.ru/users/olegendorphine/portfolio/"
out={"schema":"fl.owner.header.banner.once.v1","owner":False,"status":"not_started",
"file_verified":False,"input_found":False,"preview_opened":False,"save_button_present":False,
"save_clicked":False,"readback_has_banner":False,
"payments":False,"messages_opened":False,"other_profile_changed":False,"captcha":False}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-banner-once-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  s=p.evaluate("""()=>({o:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),s:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner"]=bool(s["o"] and s["s"] and is_fl_url(p.url))
  out["file_verified"]=bool(ASSET.is_file() and not ASSET.is_symlink() and hashlib.sha256(ASSET.read_bytes()).hexdigest()==SHA)
  if not out["owner"]:out["status"]="owner_mismatch"
  elif not out["file_verified"]:out["status"]="asset_mismatch"
  elif MARKER.exists() or MARKER.is_symlink():out["status"]="prior_attempt_do_not_retry"
  else:
   r=p.goto(URL,wait_until="domcontentloaded",timeout=22000)
   if not r or r.status!=200 or not is_fl_url(p.url):out["status"]="profile_unavailable"
   else:
    button=p.get_by_role("button",name="Загрузить обложку для ПК")
    files=p.locator("input[type=file]")
    out["input_found"]=files.count()==1 and "image/jpeg" in (files.first.get_attribute("accept") or "")
    if button.count()!=1 or not out["input_found"]:out["status"]="unexpected_cover_control"
    else:
     before=p.evaluate("""() => ({bg:Array.from(document.querySelectorAll('[class*=cover],[class*=banner]')).some(e=>getComputedStyle(e).backgroundImage!=='none'&&e.getBoundingClientRect().width>600)})""")
     button.click(timeout=8000)
     files.first.set_input_files(str(ASSET),timeout=10000)
     p.wait_for_timeout(850)
     state=p.evaluate("""()=>({
      visible:Array.from(document.querySelectorAll('[role=dialog],[class*=modal]')).filter(x=>x.getBoundingClientRect().width>150&&x.getBoundingClientRect().height>100).map(x=>(x.innerText||'').slice(0,220)),
      saveBtns:Array.from(document.querySelectorAll('button')).filter(e=>e.getBoundingClientRect().width>0&&/сохран|примен/i.test(e.innerText||'')).map(e=>(e.innerText||'').trim()).slice(-10),
      paymentVisible:Array.from(document.querySelectorAll('[role=dialog]')).some(x=>x.getBoundingClientRect().width>100&&/оплатить|PRO|купить/i.test(x.innerText||''))
     })""")
     out["preview_opened"]=bool(state["visible"] or state["saveBtns"])
     if state["paymentVisible"]:out["status"]="payment_gated_no_action"
     else:
      save=p.get_by_role("button",name="Сохранить обложку",exact=True)
      out["save_button_present"]=save.count()==1
      if not out["save_button_present"]:
       out["status"]="preview_requires_manual_edit"
       out["observed_buttons"]=state["saveBtns"]
      elif not save.is_enabled():out["status"]="save_disabled"
      else:
       fd=os.open(MARKER,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
       with os.fdopen(fd,"w") as f:
        json.dump({"time":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"state":"intent_before_save"},f)
        f.flush();os.fsync(f.fileno())
       try:
        save.click(timeout=16000)
        out["save_clicked"]=True
        p.wait_for_timeout(1400)
        r=p.goto(URL,wait_until="domcontentloaded",timeout=24000)
        after=p.evaluate("""() => ({
          bg:Array.from(document.querySelectorAll('[class*=cover],[class*=banner]')).some(e=>getComputedStyle(e).backgroundImage!=='none'&&e.getBoundingClientRect().width>600),
          images:Array.from(document.querySelectorAll('[class*=cover],[class*=banner] img')).some(e=>e.getBoundingClientRect().width>600&&e.src&&!e.src.startsWith('data:'))
        })""")
        out["readback_has_banner"]=bool(r and r.status==200 and is_fl_url(p.url) and (after["bg"] or after["images"]))
        out["status"]="banner_saved_visible" if out["readback_has_banner"] else "outcome_uncertain_no_retry"
       except Exception:out["status"]="after_save_unknown_no_retry"
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
