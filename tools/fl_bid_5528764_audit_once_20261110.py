#!/usr/bin/env python3
"""Owner-approved exact one-time FREE proposal to FL.ru project #5528764.

Prechecks: account identity, job ID/title, no prior bid, open project, free
proposal form, no CAPTCHA/payment. A local fsynced O_EXCL intent marker
prevents duplicate submissions even if the browser or SSH times out.
No other chats, customer accounts, profile settings or billing touched.
"""
from __future__ import annotations
import json,os,sys,tempfile,time
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent"
sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url

JOB_ID="5528764"
TITLE="независимый технический аудит ИИ-системы"
URL="https://www.fl.ru/projects/5528764/nezavisimyiy-tehnicheskiy-audit-ii-sistemyi.html"
PRICE=85000
DAYS=10
TEXT="""Здравствуйте. Готов провести независимый технический аудит вашего Claude/API-агента с проверяемыми замечаниями и планом исправлений.

Мой релевантный опыт — собственная действующая серверная агентная инфраструктура: Python/VPS, ИИ/API-интеграции, Telegram, браузерные исполнители, GitHub Actions, журналы, разграничение доступов и контроль повторов. Отдельно разрабатываю воспроизводимый тестовый контур для оценки поведения моделей и регрессионных проверок. Это собственные инженерные проекты, не буду выдавать их за 1–2 коммерческих внедрения в инвестиционных компаниях: таких подтверждённых кейсов в моём портфолио нет.

Предлагаю аудит по всем 8 блокам вашего задания:
1) системные инструкции и контекст;
2) агент, инструменты и права выполнения;
3) эталоны, eval-наборы и регрессии;
4) порядок изменений, версии и откат;
5) мониторинг и разбор ошибок;
6) безопасность: prompt injection, утечки и права на данные;
7) стоимость токенов, задержки, выбор и кэширование модели;
8) устойчивость к сбоям и сопровождение.

Подход: NDA → доступ только на просмотр к архитектуре, конфигурациям и обезличенным трассам → выборка ключевых сценариев → воспроизведение проблем на тестовых данных → сверка с практиками production LLM agents.

Результат: 1-страничное резюме для руководителя; матрица 8 блоков; реестр замечаний (критично/важно/желательно) с фактами и сценариями воспроизведения; приоритеты исправлений и оценка трудоёмкости; итоговый созвон. Пример структуры отчёта могу прислать до начала работ. Исходники, настройки и данные не меняю; доработка системы не входит в аудит.

Фиксированная стоимость — 85 000 ₽; срок — 10 рабочих дней после NDA и предоставления согласованных материалов. Для точной фиксации объёма потребуется перечень инструментов, версия промптов, 10–20 обезличенных трасс и описание текущих регрессионных тестов. Готов обсудить критерии приёмки отчёта."""
MARK=ROOT/"fl_owner_bid_attempt_5528764_20261110.json"
RESULT={"schema":"fl.owner.bid.5528764.once.v1","job":JOB_ID,"price_rub":PRICE,"duration_days":DAYS,
        "owner_verified":False,"free_verified":False,"already_applied":False,
        "attempted":False,"submitted_confirmed":False,"payment_actions":0,
        "captchas":0,"other_messages":0,"status":"not_started"}

def classify(page):
    return page.evaluate("""() => {
        const title=(document.querySelector('h1')?.innerText||'').trim();
        const body=document.body?.innerText||'';
        const ix=body.indexOf(title);
        const seg=body.slice(Math.max(0,ix),Math.max(0,ix)+6500);
        const btn=document.querySelector('#el-submit');
        return {
            title,
            free:/Для всех/i.test(seg),
            already:/редактировать отклик|ваш отклик отправлен|вы уже откликнулись|изменить отклик/i.test(seg),
            closed:/проект закрыт|проект завершен|исполнитель определён|исполнитель выбран|проект завершён/i.test(seg),
            pay:/купить отклики|оплатите отклик|недостаточно откликов/i.test(seg),
            captcha:!!document.querySelector('[class*="smartcaptcha"],[id*="captcha"]'),
            form:!!document.querySelector('form textarea#el-descr'),
            button:btn?.innerText?.trim()||''
        };
    }""")

def unique(page,selector):
    field=page.locator(selector)
    if field.count()!=1:raise RuntimeError("form_selector_not_unique")
    return field

b=Browser()
try:
    with tempfile.TemporaryDirectory(prefix="fl-5528764-free-audit-",dir=ROOT) as td:
        b.open(Path(td));p=b.page
        r=p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=23000)
        sign=p.evaluate("""() => ({
            settings:(document.body?.innerText||'').includes('Основные настройки'),
            owner:[...document.querySelectorAll('input')].some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com')
        })""")
        RESULT["owner_verified"]=bool(r and r.status==200 and is_fl_url(p.url) and sign["owner"] and sign["settings"])
        if not RESULT["owner_verified"]:
            RESULT["status"]="owner_identity_unverified"
        else:
            r=p.goto(URL,wait_until="domcontentloaded",timeout=24000)
            p.wait_for_timeout(550)
            exact=(urlsplit(p.url)._replace(query="",fragment="").geturl()==URL)
            if not(r and r.status==200 and exact and is_fl_url(p.url)):
                RESULT["status"]="job_page_unexpected"
            else:
                sig=classify(p)
                RESULT["free_verified"]=bool(sig["free"] and sig["form"] and sig["button"]=="Отправить отклик")
                RESULT["already_applied"]=bool(sig["already"])
                if sig["title"]!=TITLE:
                    RESULT["status"]="job_title_mismatch"
                elif sig["already"]:
                    RESULT["status"]="already_applied_no_duplicate"
                elif sig["closed"]:
                    RESULT["status"]="project_closed"
                elif MARK.exists() or MARK.is_symlink():
                    RESULT["status"]="prior_attempt_marker_no_retry"
                elif sig["pay"]:
                    RESULT["status"]="payment_required_no_purchase"
                elif sig["captcha"]:
                    RESULT["status"]="captcha_required_human_only"
                elif not RESULT["free_verified"]:
                    RESULT["status"]="free_form_not_verified"
                else:
                    unique(p,"#el-descr").fill(TEXT,timeout=9000)
                    unique(p,"#el-cost_from").fill(str(PRICE),timeout=6000)
                    unique(p,"#el-time_from").fill(str(DAYS),timeout=6000)
                    final=p.evaluate("""() => ({
                        text:document.querySelector('#el-descr')?.value||'',
                        price:document.querySelector('#el-cost_from')?.value||'',
                        days:document.querySelector('#el-time_from')?.value||'',
                        submit:document.querySelector('#el-submit')?.innerText?.trim()||'',
                        disabled:!!document.querySelector('#el-submit')?.disabled,
                        free:(document.body?.innerText||'').includes('Для всех'),
                        payment:!!document.querySelector('[role=dialog] [class*=payment], [role=dialog] [class*=purchase]'),
                        captcha:!!document.querySelector('[class*="smartcaptcha"],[id*="captcha"]')
                    })""")
                    valid=(final["text"]==TEXT and final["price"]==str(PRICE)
                        and final["days"]==str(DAYS) and final["submit"]=="Отправить отклик"
                        and not final["disabled"] and final["free"]
                        and not final["payment"] and not final["captcha"])
                    if not valid:
                        RESULT["status"]="pre_submit_guard_failed"
                    else:
                        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
                        if hasattr(os,"O_NOFOLLOW"):flags|=os.O_NOFOLLOW
                        fd=os.open(MARK,flags,0o600)
                        with os.fdopen(fd,"w",encoding="utf8") as out:
                            json.dump({"job":JOB_ID,"price":PRICE,"days":DAYS,
                                       "state":"intent_before_one_click",
                                       "time":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())},out)
                            out.flush();os.fsync(out.fileno())
                        RESULT["attempted"]=True
                        try:
                            p.locator("#el-submit").click(timeout=11000)
                            p.wait_for_timeout(1300)
                            post=classify(p)
                            if post["already"]:
                                RESULT["submitted_confirmed"]=True
                                RESULT["status"]="submitted_confirmed_ui"
                            elif post["pay"]:
                                RESULT["status"]="payment_gate_no_payment"
                            else:
                                # Independent readback without retrying.
                                check=p.goto(URL,wait_until="domcontentloaded",timeout=22000)
                                p.wait_for_timeout(400)
                                verified=bool(check and check.status==200 and classify(p)["already"])
                                RESULT["submitted_confirmed"]=verified
                                RESULT["status"]="submitted_confirmed_reloaded" if verified else "submission_uncertain_no_retry"
                        except Exception as e:
                            RESULT["status"]="click_or_readback_ambiguous_do_not_retry"
                            RESULT["error_class"]=type(e).__name__
except Exception as e:
    RESULT["status"]="technical_error_no_retry"
    RESULT["error_class"]=type(e).__name__
finally:
    try:b.close()
    except Exception:pass
    print(json.dumps(RESULT,ensure_ascii=False,sort_keys=True))
