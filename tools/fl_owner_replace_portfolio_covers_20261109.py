#!/usr/bin/env python3
"""One-time replacement of THREE pre-existing owner portfolio covers.
No extra works, no messages, no billing; all assets hash-verified.
Fail closed on unexpected account, title, editor or changes. Never retry save.
"""
from pathlib import Path
import hashlib,sys,json,tempfile,os,time
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
URL="https://www.fl.ru/users/olegendorphine/portfolio/"
WORKS=[
 {"id":"8111943","title":"Персональный ИИ-Штаб: память, документы и контроль","file":"04_portfolio_staff_900x900.jpg","sha":"5894e919fdeddb5819487c106d02f2b28d5ae0deb52369d2afbf9bb07bed20c0"},
 {"id":"8111944","title":"Автономный браузер на VPS и контроль сессий","file":"05_portfolio_vps_900x900.jpg","sha":"514e3ff74d0ed0553294b4a439d618f1c1ed973f199a881a479707ad89be7f4b"},
 {"id":"8111945","title":"ИИ-документооборот: связи, анализ и полезные сигналы","file":"06_portfolio_docs_900x900.jpg","sha":"f8bfd592f4775a509ae9229552e361438f3f6051013d7da6acdcd43afd1f08ab"}
]
out={"schema":"fl.owner.portfolio.covers.replace.once.v1","owner":False,"payments":False,"messages_opened":False,"new_works_created":False,"other_account_changed":False,"results":[]}
b=Browser()
def ensure_page(p,url):
 r=p.goto(url,wait_until="domcontentloaded",timeout=25000)
 if not r or r.status!=200 or not is_fl_url(p.url) or urlsplit(p.url).path!=urlsplit(url).path:raise ValueError("unverified_page")
 p.wait_for_timeout(350)
def card(p,job):
 a=p.locator('a[href="/user/olegendorphine/portfolio/'+job["id"]+'/"]').first
 if a.count()!=1:raise ValueError("work_missing")
 c=a.locator("..")
 if job["title"] not in c.inner_text():raise ValueError("work_title_mismatch")
 return c
def image_sources(c):
 return c.evaluate("""e => {
  const images=Array.from(e.querySelectorAll('img')).map(x=>x.currentSrc||x.src||'').filter(Boolean);
  return images.filter(x=>x.startsWith('https://')||x.startsWith('http://')||x.startsWith('/')).slice(0,5);
 }""")
try:
 with tempfile.TemporaryDirectory(prefix="fl-portfolio-covers-once-",dir=ROOT) as temp:
  b.open(Path(temp));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=22000)
  s=p.evaluate("""()=>({o:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),s:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner"]=bool(s["o"] and s["s"] and is_fl_url(p.url))
  if out["owner"]:
   for work in WORKS:
    info={"id":work["id"],"status":"not_started","save_clicked":False,"verified":False}
    out["results"].append(info)
    file=ROOT/"artwork_20261109"/work["file"]
    marker=ROOT/("fl_work_cover_replace_"+work["id"]+"_20261109.intent")
    try:
     if not file.is_file() or file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest()!=work["sha"]:
      info["status"]="asset_not_verified";break
     ensure_page(p,URL)
     c=card(p,work)
     old_src=image_sources(c)
     info["before_image_count"]=len(old_src)
     if marker.exists() or marker.is_symlink():
      info["status"]="prior_intent_no_retry";break
     edit=c.get_by_text("Редактировать",exact=True)
     if edit.count()!=1:info["status"]="no_unique_editor";break
     edit.click(timeout=8000)
     title=p.locator("#ui-input-example-name-input")
     try: title.wait_for(state="visible",timeout=9000)
     except Exception: info["status"]="editor_load_timeout";break
     modal=p.locator('[role=dialog]').last
     info["editor_title_matches"]=bool(title.count()==1 and title.input_value()==work["title"])
     info["editor_has_delete"]=bool(modal.count()>0 and "Удалить работу" in modal.inner_text())
     if not (info["editor_title_matches"] and info["editor_has_delete"]):
      info["status"]="wrong_editor";break
     files=p.locator('input[type=file]')
     if files.count()<2 or "image/jpeg" not in (files.nth(1).get_attribute("accept") or ""):
      info["status"]="no_cover_input";break
     files.nth(1).set_input_files(str(file),timeout=10000)
     p.wait_for_timeout(650)
     crop=p.get_by_role("button",name="Сохранить обложку",exact=True)
     if crop.count()!=1:info["status"]="crop_missing";break
     crop.click(timeout=12000);p.wait_for_timeout(1400)
     # FL crop control remains in the wizard DOM after acceptance; verify using next stage instead.
     nxt=p.get_by_role("button",name="Продолжить",exact=True)
     if nxt.count()!=1:info["status"]="continue1_missing";break
     nxt.click(timeout=9500);p.wait_for_timeout(400)
     desc=p.locator("#ui-textarea-description-input")
     if desc.count()!=1 or len(desc.input_value())<60:
      info["status"]="existing_description_unexpected";break
     nxt=p.get_by_role("button",name="Продолжить",exact=True)
     if nxt.count()!=1:info["status"]="continue2_missing";break
     nxt.click(timeout=9500);p.wait_for_timeout(450)
     if work["id"]=="8111943" and "AI — искусственный интеллект / AI-агенты" not in modal.inner_text():
      info["status"]="category_changed";break
     save=p.get_by_role("button",name="Сохранить",exact=True)
     if save.count()!=1 or not save.is_enabled() or "Удалить работу" not in modal.inner_text():
      info["status"]="save_guard_failed";break
     fd=os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
     with os.fdopen(fd,"w") as f:
      json.dump({"id":work["id"],"status":"intent_before_save","time":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())},f)
      f.flush();os.fsync(f.fileno())
     save.click(timeout=12000);info["save_clicked"]=True
     p.wait_for_timeout(1200)
     ensure_page(p,URL)
     c=card(p,work)
     new_src=image_sources(c)
     info["after_image_count"]=len(new_src)
     info["image_source_changed"]=bool(old_src and new_src and old_src!=new_src)
     info["verified"]=bool(info["image_source_changed"])
     info["status"]="saved_image_changed" if info["verified"] else "save_clicked_unverified_do_not_retry"
     if not info["verified"]:break
    except Exception as e:
     info["status"]="error_after_intent_no_retry" if marker.exists() else "error_before_intent"
     info["error_class"]=type(e).__name__
     break
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
