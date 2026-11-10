#!/usr/bin/env python3
"""One-time owner-directed FL.ru public About update; no other account actions.
Not a bid, message, payment, CAPTCHA bypass, or session export.
"""
import os, sys, time, json, tempfile
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent"
sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,is_fl_url,ALLOWED_PAGES

ABOUT="""Автоматизирую бизнес-рутину: заявки, документы, отчёты, контроль задач. Сначала выясняю, где теряется время, затем предлагаю пилот с проверяемым результатом.

Решения: ИИ-поиск по документам, ассистенты с памятью, уведомления, интеграции Telegram, таблиц и API — после проверки доступов.

В портфолио — собственные проекты: ИИ-Штаб, документооборот, браузер на VPS.

Аудит — 6 500 ₽, ТЗ ИИ-ассистента — 15 600 ₽. Внедрение оцениваю отдельно. Опишите задачу — предложу первый шаг."""
assert len(ABOUT)==479
TARGET_URL="https://www.fl.ru/users/olegendorphine/setup/portfolio/"
PUBLIC_URL="https://www.fl.ru/users/olegendorphine/"
MARKER=ROOT/"fl_owner_about_sales_refresh_20261110.intent"
BACKUP=ROOT/"fl_owner_about_sales_refresh_20261110.backup.txt"
report={"schema":"fl.owner.about.sales.refresh.v1","account":"olegendorphine",
 "verified_owner":False,"before_expected":False,"clicked":False,"readback":False,
 "public_readback":False,"payment":False,"commercial_messages":False,
 "credentials_read":False,"captcha":False,"other_fields_changed":False,
 "status":"not_started"}
browser=Browser()
def navigate(p,url):
    r=p.goto(url,wait_until="domcontentloaded",timeout=25000)
    if not r or r.status!=200 or not is_fl_url(p.url) or urlsplit(p.url).path!=urlsplit(url).path:
        raise RuntimeError("unexpected_navigation")
    return r
def safe_file(path,value):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        f.write(value);f.flush();os.fsync(f.fileno())
try:
  with tempfile.TemporaryDirectory(prefix="fl-own-about-refresh-",dir=ROOT) as tmp:
    browser.open(Path(tmp));p=browser.page
    navigate(p,ALLOWED_PAGES["settings"])
    s=p.evaluate("""()=>({
       own:Array.from(document.querySelectorAll('input')).some(
         x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
       settings:(document.body?.innerText||'').includes('Основные настройки'),
       login:!!document.querySelector('form[action*="/account/login"]')
    })""")
    report["verified_owner"]=bool(s["own"] and s["settings"] and not s["login"])
    if not report["verified_owner"]:
        report["status"]="not_authenticated_as_owner"
    else:
        navigate(p,TARGET_URL)
        field=p.locator('textarea[name="ab_text"]')
        form=p.locator('form:has(textarea[name="ab_text"])')
        if field.count()!=1 or form.count()!=1:
            report["status"]="form_layout_changed"
        else:
            old=field.input_value()
            if old==ABOUT:
                report["readback"]=True;report["status"]="already_desired"
            elif not (old.startswith("ИИ для реальных задач.") and
                    "Аудит от 5 000 ₽" in old and "ИИ-«Штаб»" in old):
                report["status"]="existing_text_not_our_expected_copy"
            elif MARKER.exists() or MARKER.is_symlink() or BACKUP.exists() or BACKUP.is_symlink():
                report["status"]="prior_attempt_stop"
            elif (form.locator('button[type="submit"]').count()!=1
               or form.locator('button[type="submit"]').inner_text().strip()!="Изменить"):
                report["status"]="unexpected_save_control"
            elif form.locator('input[type="password"],input[name*="payment"],input[name*="card"]').count():
                report["status"]="sensitive_field_in_form"
            else:
                report["before_expected"]=True
                safe_file(BACKUP,old)
                field.fill(ABOUT)
                if field.input_value()!=ABOUT:
                    report["status"]="pre_submit_mismatch"
                else:
                    safe_file(MARKER,json.dumps({"time":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"action":"one_owner_about_change"}))
                    try:
                        form.locator('button[type="submit"]').click(timeout=14000)
                        report["clicked"]=True
                        p.wait_for_timeout(700)
                        navigate(p,TARGET_URL)
                        report["readback"]=field.input_value()==ABOUT
                        report["status"]="saved_readback" if report["readback"] else "after_click_uncertain_no_retry"
                    except Exception:
                        report["status"]="after_click_uncertain_no_retry"
            if report["readback"]:
                try:
                    navigate(p,PUBLIC_URL)
                    report["public_readback"]=ABOUT[:110] in p.locator("body").inner_text()
                except Exception:
                    report["public_readback"]=False
finally:
    browser.close()
    print(json.dumps(report,ensure_ascii=False,sort_keys=True))
