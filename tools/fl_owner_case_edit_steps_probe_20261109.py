#!/usr/bin/env python3
"""Owner work existing-case edit preview, never clicks final publish/save."""
from pathlib import Path
import sys,json,tempfile,hashlib
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
FILE=ROOT/"artwork_20261109"/"04_portfolio_staff_900x900.jpg"
EXPECTED="5894e919fdeddb5819487c106d02f2b28d5ae0deb52369d2afbf9bb07bed20c0"
TITLE="Персональный ИИ-Штаб: память, документы и контроль"
out={"schema":"fl.owner.case.edit.steps.v1","owner":False,"final_submit":False,"file_verified":False,"opened_existing":False,"stages":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-case-edit-probe-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=22000)
  s=p.evaluate("""()=>({o:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),s:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner"]=bool(s["o"] and s["s"] and is_fl_url(p.url))
  out["file_verified"]=bool(FILE.is_file() and hashlib.sha256(FILE.read_bytes()).hexdigest()==EXPECTED)
  if out["owner"] and out["file_verified"]:
   p.goto("https://www.fl.ru/users/olegendorphine/portfolio/",wait_until="domcontentloaded",timeout=22000)
   card=p.locator('a[href*="/user/olegendorphine/portfolio/8111943/"]').first.locator("..")
   edit=card.get_by_text("Редактировать",exact=True)
   if edit.count()==1:
    edit.click(timeout=7500)
    p.wait_for_timeout(450)
    title=p.locator("#ui-input-example-name-input")
    modal=p.locator('[role=dialog]').last
    out["opened_existing"]=bool(title.count()==1 and title.input_value()==TITLE and "Удалить работу" in modal.inner_text())
    if out["opened_existing"]:
     f=p.locator("input[type=file]")
     out["stages"].append({"stage":"start","inputs":f.count(),"cover_accept":f.nth(1).get_attribute("accept") if f.count()>1 else None})
     if f.count()>1 and "image/jpeg" in (f.nth(1).get_attribute("accept") or ""):
      f.nth(1).set_input_files(str(FILE),timeout=11000)
      p.wait_for_timeout(650)
      crop=p.get_by_role("button",name="Сохранить обложку",exact=True)
      out["stages"].append({"stage":"crop","button_count":crop.count()})
      if crop.count()==1:
       crop.click(timeout=12000)
       p.wait_for_timeout(1700)
       nxt=p.get_by_role("button",name="Продолжить",exact=True)
       out["stages"].append({"stage":"step1_after_crop","continue_count":nxt.count()})
       if nxt.count()==1:
        nxt.click(timeout=9500)
        p.wait_for_timeout(450)
        out["stages"].append({"stage":"step2","fields":p.evaluate("""()=>Array.from(document.querySelectorAll('textarea,input')).filter(x=>x.getBoundingClientRect().width>0&&x.type!=='password').map(x=>({name:x.name,id:x.id,chars:(x.value||'').length})).slice(-10)""")})
        nxt=p.get_by_role("button",name="Продолжить",exact=True)
        if nxt.count()==1:
         nxt.click(timeout=9500)
         p.wait_for_timeout(450)
         out["stages"].append({"stage":"step3","buttons":p.evaluate("""()=>Array.from(document.querySelectorAll('button')).filter(x=>x.getBoundingClientRect().width>0).map(x=>(x.innerText||'').trim()).filter(Boolean).slice(-12)"""),"dialog":modal.inner_text()[-420:]})
finally:b.close()
print(json.dumps(out,ensure_ascii=False))
