#!/usr/bin/env python3
"""Owner-directed one-time free portfolio section selection. No payment, no PII."""
from pathlib import Path
from urllib.parse import urlsplit
import sys,os,json,tempfile,time
root=Path.home()/".fl-agent";sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
URL="https://www.fl.ru/users/olegendorphine/setup/portfsetup/"
SELECTED={"803":"AI-агенты","805":"RAG / Базы знаний","810":"AI-автоматизация"}
MARKER=root/"fl_portfolio_sections_submit_20261109.json"
out={"schema":"fl.owner.portfolio.sections.once.v1","owner_verified":False,
  "posted":False,"verified":False,"paid":False,"other_profile_changed":False,
  "status":"not_started","selected":list(SELECTED.values())}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-portfolio-sections-",dir=root) as t:
  b.open(Path(t));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  s=p.evaluate("""()=>({settings:(document.body?.innerText||'').includes('Основные настройки'),owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com')})""")
  out["owner_verified"]=bool(s["settings"] and s["owner"] and is_fl_url(p.url))
  if out["owner_verified"]:
   r=p.goto(URL,wait_until="domcontentloaded",timeout=24000)
   if not r or r.status!=200 or not is_fl_url(p.url) or urlsplit(p.url).path!=urlsplit(URL).path:
    out["status"]="wrong_page"
   else:
    checks=p.locator('form#frm input[name="prof[]"]')
    total=checks.count()
    for identifier,label in SELECTED.items():
     css=f'form#frm input[name="prof[]"][value="{identifier}"]'
     if p.locator(css).count()!=1:raise RuntimeError("expected_section_missing")
     actual=p.locator(css).evaluate("""e=>(e.labels?.[0]?.innerText||'').trim().replace(/\\s+/g,' ')""")
     if actual!=label:raise RuntimeError("section_mismatch")
    already=set(p.locator('form#frm input[name="prof[]"]:checked').evaluate_all("(els)=>els.map(e=>e.value)"))
    if total<400:out["status"]="unexpected_section_count"
    elif already==set(SELECTED):out["status"]="already_selected";out["verified"]=True
    elif already:out["status"]="other_sections_already_selected_stop"
    elif MARKER.exists() or MARKER.is_symlink():out["status"]="prior_submission_marker_stop"
    else:
     for identifier in SELECTED:
      p.locator(f'form#frm input[name="prof[]"][value="{identifier}"]').check(timeout=6000)
     got=set(p.locator('form#frm input[name="prof[]"]:checked').evaluate_all("(els)=>els.map(e=>e.value)"))
     if got!=set(SELECTED):raise RuntimeError("checkbox_pre_submit_failed")
     save=p.locator('a.b-button:has-text("Сохранить изменения")')
     if save.count()!=1:raise RuntimeError("save_button_not_unique")
     if p.locator("form#frm").count()!=1:raise RuntimeError("save_form_missing")
     fd=os.open(MARKER,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
     with os.fdopen(fd,"w") as f:
      json.dump({"created":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
       "category_values":sorted(SELECTED),"status":"about_to_submit"},f)
      f.flush();os.fsync(f.fileno())
     save.click(timeout=11000)
     out["posted"]=True
     p.wait_for_timeout(500)
     rp=p.goto(URL,wait_until="domcontentloaded",timeout=22000)
     if rp and rp.status==200:
      now=set(p.locator('form#frm input[name="prof[]"]:checked').evaluate_all("(els)=>els.map(e=>e.value)"))
      out["verified"]=now==set(SELECTED)
     out["status"]="saved_verified" if out["verified"] else "save_attempted_unknown_no_retry"
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
