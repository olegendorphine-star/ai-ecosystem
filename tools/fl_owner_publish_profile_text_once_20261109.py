#!/usr/bin/env python3
"""User-approved one-time owner FL public profile text update.

No payment, no avatar, no personal identity/contact/finance change.
No CAPTCHA/login automation. One attempt per field with read-after-write.
"""
import json,sys,os,tempfile,time
from pathlib import Path
from urllib.parse import urlsplit
root=Path.home()/".fl-agent"
sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
TITLE="ИИ-ассистенты и автоматизация бизнеса | API, VPS"
ABOUT=("Создаю ИИ-ассистентов и автономные ИИ-экосистемы для частных клиентов и бизнеса: "
"память, документы, API, браузер, VPS, мониторинг и контроль задач. "
"Мой действующий персональный ИИ-«Штаб» применяю для работы с информацией, документами и сроками. "
"Архитектура не привязана к одной нейросети: модель выбирается под задачу. "
"Развиваю решения под процессы клиента: интеграции, гипотезы улучшений, проверка результатов. "
"Аудит от 5 000 ₽, ассистент от 30 000 ₽, бизнес-интеграции от 150 000 ₽.")
assert len(ABOUT)<=500
JOBS=[
 {"name":"headline","url":"https://www.fl.ru/users/olegendorphine/setup/main/",
  "selector":'input[name="pname"]',"form":'form:has(input[name="pname"])',
  "value":TITLE,"button":"Сохранить"},
 {"name":"about","url":"https://www.fl.ru/users/olegendorphine/setup/portfolio/",
  "selector":'textarea[name="ab_text"]',"form":'form:has(textarea[name="ab_text"])',
  "value":ABOUT,"button":"Изменить"}
]
report={"schema":"fl.profile.safe-publication.v1","owner_verified":False,
"account":"olegendorphine","operations":[],"paid_actions":False,
"captcha_actions":False,"personal_fields_changed":False,"passwords_read":False,
"session_exported":False,"finance_changed":False}
b=Browser()
def prep(page,url,selector,form):
 response=page.goto(url,wait_until="domcontentloaded",timeout=22000)
 page.wait_for_timeout(450)
 parsed=urlsplit(page.url)
 if (not response or response.status!=200 or parsed.scheme!="https"
     or parsed.hostname not in ("www.fl.ru","fl.ru")
     or parsed.path!=urlsplit(url).path):
  raise RuntimeError("unexpected_fl_page")
 if page.locator(selector).count()!=1 or page.locator(form).count()!=1:
  raise RuntimeError("unexpected_form_layout")
 f=page.locator(form)
 if f.locator('button[type="submit"]').count()!=1:
  raise RuntimeError("submit_button_not_unique")
 if f.evaluate("(e)=>e.method.toLowerCase()")!="post":
  raise RuntimeError("form_not_post")
 fields=f.locator('input,textarea,select')
 if f.locator('input[name="oldpwd"]').count() and f.locator('input[name="oldpwd"]').input_value().strip():
  raise RuntimeError("password_field_nonempty")
 return f
def mark(path,info):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"w") as file:
  json.dump(info,file,ensure_ascii=False)
  file.flush();os.fsync(file.fileno())
try:
 with tempfile.TemporaryDirectory(prefix="fl-profile-publication-",dir=root) as tmp:
  b.open(Path(tmp))
  p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=19000)
  signs=p.evaluate("""()=>({
    h:(document.body?.innerText||'').includes('Основные настройки'),
    owner:Array.from(document.querySelectorAll('input')).some(
      e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
    loginForm:!!document.querySelector('form[action*="/account/login"]')
  })""")
  report["owner_verified"]=bool(signs["h"] and signs["owner"] and not signs["loginForm"] and is_fl_url(p.url))
  if report["owner_verified"]:
   for j in JOBS:
    x={"field":j["name"],"result":"not_started","clicked":False,"verified":False}
    report["operations"].append(x)
    marker=root/("fl_owner_profile_text_attempt_"+j["name"]+"_20261109.json")
    try:
     f=prep(p,j["url"],j["selector"],j["form"])
     current=p.locator(j["selector"]).input_value()
     if current==j["value"]:
      x["result"]="already_target";x["verified"]=True;continue
     # Skip if user has since changed a headline; keep user edits.
     if j["name"]=="headline" and current.strip():
      x["result"]="headline_nonempty_not_overwriting";continue
     if marker.exists() or marker.is_symlink():
      x["result"]="prior_attempt_exists_verify_manually";continue
     # Only target the exact site account fields.
     submit=f.locator('button[type="submit"]')
     if submit.inner_text().strip()!=j["button"] or not submit.is_enabled():
      x["result"]="submit_guard_failed";continue
     if j["name"]=="about" and len(current)<20:
      x["result"]="existing_about_unexpected";continue
     backup=root/("fl_profile_original_"+j["name"]+"_20261109.txt")
     fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
     with os.fdopen(fd,"w",encoding="utf-8") as ff:
      ff.write(current);ff.flush();os.fsync(ff.fileno())
     p.locator(j["selector"]).fill(j["value"],timeout=5000)
     if p.locator(j["selector"]).input_value()!=j["value"]:
      x["result"]="pre_submit_value_incorrect";continue
     # Owner-specific form and no visible payment challenge in the same form.
     if f.locator('input[name*="payment"], input[name*="card"], input[name="promo"]').count()>0:
      x["result"]="payment_input_in_target_form";continue
     mark(marker,{"field":j["name"],"time":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"status":"intent_before_click"})
     submit.click(timeout=12000)
     x["clicked"]=True
     p.wait_for_timeout(700)
     prep(p,j["url"],j["selector"],j["form"])
     x["verified"]=p.locator(j["selector"]).input_value()==j["value"]
     x["result"]="published_verified" if x["verified"] else "submitted_not_confirmed"
    except Exception as ex:
     x["result"]="error_after_attempt_do_not_retry" if marker.exists() else "error_before_attempt"
finally:
 b.close()
print(json.dumps(report,ensure_ascii=False,sort_keys=True))
