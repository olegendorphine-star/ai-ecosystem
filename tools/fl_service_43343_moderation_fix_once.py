#!/usr/bin/env python3
"""One bounded update of the owner's existing rejected FL.ru service #43343.

Only title/description/requirements/result fields of this existing service may
be touched. Price, duration, category, media, profile and buyer messaging must
remain unchanged. Never create a service, buy anything, or bypass an anti-bot gate.
If the review wizard is not unambiguously editable, fail closed.
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path.home()/".fl-agent"
sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,is_fl_url
OWNER="olegendorphine"
SETTINGS="https://www.fl.ru/users/olegendorphine/setup/main/"
CARD="https://www.fl.ru/uslugi-freelancera/43343/nastroyu-uchet-zayavok-i-uvedomleniya-v-telegram.html"
TITLE="Настрою учёт заявок и уведомления в Telegram"
REMOVE="а развёртывание в отдельной инфраструктуре согласуем дополнительно"
DESC=(
    "Настрою один рабочий сценарий контроля заявок из одной Google Таблицы "
    "на одном сервере заказчика. Сценарий учитывает статусы и ответственных, "
    "обнаруживает новые и просроченные заявки, отправляет уведомления в один "
    "Telegram-чат через существующего бота и ведёт журнал обработки и ошибок. "
    "В стоимость входят: настройка одной таблицы и одного автоматического "
    "сценария, развёртывание этого сценария на одном сервере заказчика, "
    "проверка на трёх тестовых заявках, инструкция по эксплуатации и одна "
    "корректировка по результатам проверки. Для постоянной работы используется "
    "сервер заказчика. Сервер, его эксплуатацию и необходимые платные API "
    "заказчик оплачивает самостоятельно; эти расходы не входят в стоимость услуги. "
    "Не входят: CRM, 1С, несколько независимых источников заявок, дополнительные "
    "сценарии, предоставление сервера, приобретение API-подписок и неограниченная поддержка."
)
REQ=(
    "Одна Google Таблица с обезличенными тестовыми заявками, список статусов "
    "и ответственных, существующий Telegram-бот и чат для уведомлений, "
    "доступ к одному серверу заказчика для установки сценария. "
    "Учётные данные передаются безопасным способом при исполнении заказа."
)
RESULT=(
    "Рабочий сценарий на сервере заказчика, уведомления в Telegram, "
    "журнал ошибок, тест на трёх заявках и инструкция."
)
MARKER=ROOT/"fl_service_43343_fix_20261110_intent.json"
OUT={"schema":"fl.service.43343.once.fix.v1","account":OWNER,"owner_verified":False,
     "target_existing_card_verified":False,"price_unchanged":False,"duration_unchanged":False,
     "fields_filled":False,"submitted":False,"post_submit_checked":False,
     "new_card_created":False,"customer_messages_sent":False,"payment_actions":False,
     "status":"not_started","stage":"init"}
def fail(status,**kwargs):
    OUT.update(status=status,**kwargs)
    return False
def check_url(url):
    p=urlsplit(url)
    return p.scheme=="https" and p.hostname in ("www.fl.ru","fl.ru")
def check_user(page):
    data=page.evaluate("""() => ({
        settings:(document.body?.innerText||'').includes('Основные настройки'),
        owner:[...document.querySelectorAll('input')].some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com')
    })""")
    return data["settings"] is True and data["owner"] is True and check_url(page.url)
def unique(selector, page):
    field=page.locator(selector)
    if field.count()!=1:
        raise RuntimeError("ambiguous_field")
    return field
def click_continue(page, expected_stage):
    btn=page.get_by_role("button",name="Продолжить",exact=True)
    if btn.count()!=1 or not btn.is_enabled():
        return fail("missing_or_disabled_continue",stage=expected_stage)
    try:
        cookie=page.get_by_role("button",name="Соглашаюсь с условиями",exact=True)
        if cookie.count()==1 and cookie.is_visible():
            cookie.click(timeout=4000)
            page.wait_for_timeout(350)
            OUT["cookie_banner_dismissed"]=True
        btn.scroll_into_view_if_needed(timeout=2500)
        btn.click(timeout=9500)
        page.wait_for_timeout(750)
        return True
    except Exception as e:
        try:
            if expected_stage=="description_to_price" and page.locator("#ui-input-price").count()==1:
                OUT["click_late_navigation"]=True
                return True
            OUT["click_debug"]=page.evaluate("""() => {
                const b=[...document.querySelectorAll('button')].find(e=>(e.innerText||'').trim()==='Продолжить');
                if(!b)return {reason:'button_not_in_dom'};
                const r=b.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;
                const top=document.elementFromPoint(x,y);
                const t=(top?.innerText||'').trim();
                return {rect:{x:Math.round(x),y:Math.round(y),w:Math.round(r.width),h:Math.round(r.height)},
                  disabled:b.disabled,hitSelf:b===top||b.contains(top),
                  topTag:top?.tagName||'',topClass:String(top?.className||'').slice(0,110),
                  topText:t.slice(0,50),pointerEvents:getComputedStyle(b).pointerEvents,
                  priceFieldCount:document.querySelectorAll('#ui-input-price').length,
                  pageFormCount:document.querySelectorAll('#ui-textarea-description-input').length};
            }""")
        except Exception:
            OUT["click_debug"]={"reason":"diagnostic_unavailable"}
        lowered=str(e).lower()
        OUT["click_failure_codes"]=[word for word in
            ("intercepts pointer events","not stable","not visible","outside of the viewport",
             "element is detached","waiting for scheduled navigations") if word in lowered]
        return fail("wizard_navigation_blocked",stage=expected_stage,
                    error_class=type(e).__name__)
def write_intent_once():
    if MARKER.exists() or MARKER.is_symlink():
        return False
    obj={"service_id":43343,"account":OWNER,"state":"one_time_submission_intent",
         "created_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"):flags|=os.O_NOFOLLOW
    fd=os.open(MARKER,flags,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        json.dump(obj,f,ensure_ascii=False)
        f.flush();os.fsync(f.fileno())
    return True

def main():
    if MARKER.exists() or MARKER.is_symlink():
        return fail("once_marker_present_no_retry")
    if any(x in DESC.lower() for x in ("согласуем дополнительно","уточним после","стоимость обсуждается")):
        return fail("new_description_validation_failed")
    if len(RESULT)>120 or len(REQ)>500 or len(DESC)>4500:
        return fail("new_fields_length_invalid")
    browser=Browser()
    try:
        with tempfile.TemporaryDirectory(prefix="fl-service-43343-repair-",dir=ROOT) as td:
            browser.open(Path(td))
            page=browser.page
            out=page.goto(SETTINGS,wait_until="domcontentloaded",timeout=23000)
            if not out or out.status!=200 or not check_user(page):
                return fail("owner_verification_failed")
            OUT["owner_verified"]=True
            OUT["stage"]="existing_card"
            out=page.goto(CARD,wait_until="domcontentloaded",timeout=26000)
            if not out or out.status!=200 or not check_url(page.url) or "/43343/" not in urlsplit(page.url).path:
                return fail("existing_card_unavailable")
            page.wait_for_timeout(600)
            text=page.locator("body").inner_text(timeout=4000)
            if "Отклонена" not in text or "не прошла модерацию" not in text:
                return fail("card_not_currently_rejected_no_write")
            if TITLE not in text:
                return fail("target_title_not_found")
            if REMOVE not in text:
                return fail("obsolete_description_absent_no_blind_write")
            tab=page.get_by_text("Управление услугой",exact=True)
            if tab.count()!=1:
                return fail("manage_tab_unavailable")
            tab.click(timeout=6500)
            page.wait_for_timeout(500)
            if page.locator("#ui-textarea-description-input").count()!=1:
                return fail("manage_editor_did_not_open")
            fields={
                "title":unique("#ui-input-example-name-input",page),
                "desc":unique("#ui-textarea-description-input",page),
                "req":unique("#ui-textarea-emp_requirement-input",page),
                "result":unique("#ui-input-emp_result-input",page),
            }
            if fields["title"].input_value(timeout=3000)!=TITLE:
                return fail("form_target_title_mismatch")
            if REMOVE not in fields["desc"].input_value(timeout=3000):
                return fail("form_does_not_contain_rejected_phrase")
            OUT["target_existing_card_verified"]=True
            OUT["stage"]="description"
            # Only the currently rejected service, no new service wizard or edits elsewhere.
            fields["desc"].fill(DESC,timeout=6500)
            fields["req"].fill(REQ,timeout=6500)
            fields["result"].fill(RESULT,timeout=6500)
            if (fields["desc"].input_value()!=DESC or fields["req"].input_value()!=REQ
                or fields["result"].input_value()!=RESULT):
                return fail("new_field_readback_failed")
            OUT["fields_filled"]=True
            if not click_continue(page,"description_to_price"):
                return False
            OUT["stage"]="price"
            page.wait_for_timeout(250)
            price=page.locator("#ui-input-price")
            days=page.locator("#ui-input-days")
            if price.count()!=1 or days.count()!=1:
                return fail("price_stage_missing")
            price_now=price.input_value(timeout=2500).strip().replace(" ","")
            days_now=days.input_value(timeout=2500).strip().replace(" ","")
            if price_now!="30000" or days_now!="7":
                return fail("unexpected_price_or_days_no_changes",price_match=price_now=="30000",days_match=days_now=="7")
            OUT["price_unchanged"]=True
            OUT["duration_unchanged"]=True
            if not click_continue(page,"price_to_category"):
                return False
            OUT["stage"]="category"
            page.wait_for_timeout(300)
            cattext=page.locator("body").inner_text(timeout=4500)
            if "AI-автоматизация" not in cattext or "Автоматизация бизнеса" not in cattext:
                return fail("current_category_unverified")
            if not click_continue(page,"category_to_media"):
                return False
            OUT["stage"]="media"
            page.wait_for_timeout(350)
            button_labels=page.evaluate("""() => [...document.querySelectorAll('button')]
                .filter(e=>e.getBoundingClientRect().width>0&&e.getBoundingClientRect().height>0)
                .map(e=>(e.innerText||'').trim()).filter(Boolean).slice(-20)""")
            OUT["final_button_labels"]=button_labels
            forms=page.locator("body").inner_text(timeout=4500)
            if "Изображения и файлы с примерами" not in forms and "Файлы" not in forms:
                return fail("unexpected_final_stage")
            if any(x in forms for x in ("Оплатить размещение","Купить размещение","Пополнить баланс")):
                return fail("payment_gate_detected_no_action")
            available=[]
            for label in ("Опубликовать","Сохранить изменения","Сохранить"):
                b=page.get_by_role("button",name=label,exact=True)
                if b.count()==1 and b.is_visible() and b.is_enabled():available.append((label,b))
            if len(available)!=1:
                return fail("final_save_not_unambiguous_no_write",
                            choices=[x[0] for x in available])
            if "Отклонена" not in page.locator("body").inner_text(timeout=4500):
                return fail("rejection_status_lost_before_submit")
            # This marker makes any interrupted or ambiguous submission at-most-once.
            if not write_intent_once():
                return fail("once_marker_present_no_retry")
            OUT["stage"]="submit_attempt"
            label,pub=available[0]
            OUT["final_action"]=label
            try:
                pub.click(timeout=14000)
                OUT["submitted"]=True
            except Exception as e:
                return fail("submission_ambiguous_no_retry",error_class=type(e).__name__)
            page.wait_for_timeout(1400)
            check=page.goto(CARD,wait_until="domcontentloaded",timeout=23000)
            if not check or check.status!=200 or not check_url(page.url):
                return fail("submitted_but_readback_failed_no_retry")
            newtext=page.locator("body").inner_text(timeout=4000)
            OUT["post_submit_checked"]=True
            OUT["new_description_visible"]=(DESC[:110] in newtext and REMOVE not in newtext)
            OUT["review_status"]=(
                "rejected" if "Отклонена" in newtext else
                "under_review" if "На проверке" in newtext or "На модерации" in newtext else
                "published_or_pending_unknown")
            if not OUT["new_description_visible"]:
                return fail("submitted_but_new_text_unverified_no_retry")
            return fail("updated_existing_card_verified",status_detail=OUT["review_status"])
    except Exception as e:
        return fail("technical_error",stage=OUT.get("stage"),error_class=type(e).__name__)
    finally:
        try:browser.close()
        except Exception:OUT["browser_close_error"]=True

if __name__=="__main__":
    try:main()
    finally:print(json.dumps(OUT,ensure_ascii=False,sort_keys=True))
