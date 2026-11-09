#!/usr/bin/env python3
"""Exact one-time owner-directed sales copy update. Never accesses messages,
other accounts, credentials, billing or project proposals. No blind retries.
"""
from pathlib import Path
from urllib.parse import urlsplit
import sys,json,tempfile,os,time
ROOT=Path.home()/".fl-agent"
sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser, ALLOWED_PAGES,is_fl_url
URL="https://www.fl.ru/users/olegendorphine/setup/portfolio/"
TARGET="""ИИ для реальных задач. Помогаю сократить ручную работу с документами, заявками, отчётами и контролем сроков.

Бизнесу: автоматизация процессов и разрешённые интеграции с CRM, таблицами и мессенджерами. Частным клиентам: ассистент с памятью и документами.

Использую действующий ИИ-«Штаб» — покажу обезличенный пример. Работаю по этапам: анализ → пилот → проверка → запуск.

Аудит от 5 000 ₽, ассистент от 30 000 ₽, бизнес-интеграции от 150 000 ₽.

Опишите задачу — предложу первый шаг и бюджет."""
assert len(TARGET)<=500
MARKER=ROOT/"fl_owner_sales_about_20261109.intent"
BACKUP=ROOT/"fl_owner_sales_about_20261109.backup.txt"
report={"schema":"fl.owner.sales.about.once.v1","login":"olegendorphine","owner_verified":False,"old_length":0,"new_length":len(TARGET),"status":"unstarted","clicked":False,"readback_verified":False,"payment":False,"messages_opened":False,"other_fields_changed":False,"passwords_read":False,"captcha":False}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-sales-about-once-",dir=ROOT) as t:
  b.open(Path(t));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=23000)
  signs=p.evaluate("""()=>({owner:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  report["owner_verified"]=bool(signs["owner"] and signs["settings"] and is_fl_url(p.url))
  if not report["owner_verified"]:
   report["status"]="not_owner"
  else:
   r=p.goto(URL,wait_until="domcontentloaded",timeout=23000)
   f=p.locator('form:has(textarea[name="ab_text"])')
   field=p.locator('textarea[name="ab_text"]')
   if not r or r.status!=200 or urlsplit(p.url).path!=urlsplit(URL).path or not is_fl_url(p.url):
    report["status"]="unexpected_page"
   elif f.count()!=1 or field.count()!=1:
    report["status"]="unexpected_form"
   else:
    old=field.input_value()
    report["old_length"]=len(old)
    if old==TARGET:
     report["status"]="already_updated";report["readback_verified"]=True
    elif MARKER.exists() or MARKER.is_symlink() or BACKUP.exists() or BACKUP.is_symlink():
     report["status"]="already_attempted_no_retry"
    elif not old.startswith("Создаю ИИ-ассистентов и автономные ИИ-экосистемы") or not (400<=len(old)<=650):
     report["status"]="unexpected_existing_copy"
    elif f.locator('button[type="submit"]').count()!=1 or f.locator('button[type="submit"]').inner_text().strip()!="Изменить":
     report["status"]="unexpected_submit"
    elif f.locator('input[type="password"],input[name*="payment"],input[name*="card"]').count()!=0:
     report["status"]="sensitive_fields_in_form"
    else:
     fd=os.open(BACKUP,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
     with os.fdopen(fd,"w",encoding="utf-8") as stream:
      stream.write(old);stream.flush();os.fsync(stream.fileno())
     field.fill(TARGET,timeout=8000)
     if field.input_value()!=TARGET:
      report["status"]="field_fill_failed"
     else:
      fd=os.open(MARKER,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
      with os.fdopen(fd,"w",encoding="utf-8") as stream:
       json.dump({"status":"intent_before_click","time":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())},stream)
       stream.flush();os.fsync(stream.fileno())
      try:
       f.locator('button[type="submit"]').click(timeout=12000)
       report["clicked"]=True
       p.wait_for_timeout(700)
       response=p.goto(URL,wait_until="domcontentloaded",timeout=22000)
       report["readback_verified"]=bool(response and response.status==200 and field.input_value()==TARGET and is_fl_url(p.url))
       report["status"]="saved_confirmed" if report["readback_verified"] else "outcome_uncertain_no_retry"
      except Exception:
       report["status"]="after_click_unknown_no_retry"
finally:
 b.close()
print(json.dumps(report,ensure_ascii=False,sort_keys=True))
