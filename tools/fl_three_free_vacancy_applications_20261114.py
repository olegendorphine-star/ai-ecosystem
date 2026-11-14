#!/usr/bin/env python3
"""Owner-approved exactly-once FREE responses to three vetted FL.ru vacancies.

Only explicit allowlisted vacancies. No email, paid responses, phone calls,
CAPTCHA handling, profile changes, or account credentials in output.
"""
from __future__ import annotations
import json,os,sys,tempfile,time
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent"
sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url,LOGIN

JOBS=[
 {
  "id":"5528153","title":"Редактор-корректор текстовых материалов",
  "url":"https://www.fl.ru/projects/5528153/redaktor-korrektor-tekstovyih-materialov.html",
  "text":"""Здравствуйте! Могу выполнять корректуру и редактуру готовых статей и материалов: орфография, пунктуация, стиль, логика изложения, повторы, заголовки и оформление. Работаю с Word и Google Docs; использую ИИ-инструменты для предварительной проверки и отдельно контролирую смысл, термины и спорные исправления. Готов показать качество на коротком тестовом фрагменте, предложить единый чек-лист редактуры и отмечать внесённые изменения.

Рассматриваю удалённое сотрудничество с оплатой за согласованный объём материалов. Коммуникация — текстом на площадке, без звонков. Подскажите средний объём статьи и желаемые сроки проверки?"""
 },
 {
  "id":"5528141","title":"Специалист по рерайтингу текстов",
  "url":"https://www.fl.ru/projects/5528141/spetsialist-po-reraytingu-tekstov.html",
  "text":"""Здравствуйте! Могу перерабатывать готовые статьи, инструкции и обзоры с сохранением фактов и исходного смысла, улучшать структуру, стиль и читаемость, удалять повторы и ошибки. Работаю с текстовыми редакторами, использую ИИ-инструменты для черновой обработки и контролирую итоговую версию. Не обещаю искусственных показателей «уникальности» без проверки по согласованной методике.

Готов выполнить небольшой оплачиваемый тестовый фрагмент и затем работать пакетами материалов со сроками и понятными критериями приёмки. Предпочитаю письменную коммуникацию, без созвонов. Каковы тематика и средний объём исходных текстов?"""
 },
 {
  "id":"5528198","title":"Специалист по транскрибации записей",
  "url":"https://www.fl.ru/projects/5528198/spetsialist-po-transkribatsii-zapisey.html",
  "text":"""Здравствуйте! Могу переводить аудио- и видеозаписи в структурированный текст: дословная или литературная расшифровка, разделение по говорящим, тайм-коды при необходимости, проверка имён и терминов, оформление в DOCX/Google Docs. Для ускорения использую инструменты распознавания речи с последующей редакторской проверкой; участки с неразборчивой речью отмечаю, не придумываю содержание.

Предлагаю начать с тестового короткого файла и согласовать формат, стоимость и сроки по объёму записи. Работаю удалённо; общение — письменно здесь, без созвонов."""
 }
]
RESULT={"schema":"fl.free.vacancy.three.once.v1","owner_verified":False,
        "payments":0,"emails":0,"captcha_interactions":0,"jobs":[]}
def classify(p):
 return p.evaluate("""() => {
  const h=(document.querySelector('h1')?.innerText||'').trim();
  const t=document.body?.innerText||'';
  const ix=t.indexOf(h),s=t.slice(Math.max(0,ix),Math.max(0,ix)+9500);
  const editors=[...document.querySelectorAll('textarea[id^="ui-textarea-"]')]
    .filter(e=>e.offsetParent!==null);
  const buttons=[...document.querySelectorAll('button')]
    .filter(e=>e.offsetParent!==null && (e.innerText||'').trim()==='Отправить отклик');
  return {
   title:h,
   vacancy:/Ссылка на вакансию/i.test(s),
   closed:/вакансия закрыта|вакансия завершена|проект закрыт|заказчик выбрал исполнителя/i.test(s),
   applied:/вы откликнулись|ваш отклик отправлен|отклик успешно отправлен|вы уже оставили отклик|редактировать отклик|изменить отклик/i.test(s),
   paid:/купить отклики|купить 1 отклик|оплатите отклик|недостаточно откликов/i.test(s),
   captcha:!!document.querySelector('[class*="smartcaptcha"],[id*="captcha"]'),
   editorCount:editors.length,
   editorNear:editors[0]?.parentElement?.parentElement?.innerText?.includes('Ваш отклик')||false,
   editorValue:editors[0]?.value||'',
   buttonCount:buttons.length,
   disabled:buttons[0]?.disabled||false,
   onFl:['www.fl.ru','fl.ru'].includes(location.hostname)
  };
 }""")
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-free-editor-applications-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  a=p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  sign=p.evaluate("""(expected)=>({
   settings:(document.body?.innerText||'').includes('Основные настройки'),
   owner:[...document.querySelectorAll('input')].some(e=>(e.value||'').toLowerCase().trim().split('@')[0]===expected)
  })""", LOGIN)
  RESULT["owner_verified"]=bool(a and a.status==200 and is_fl_url(p.url) and sign["settings"] and sign["owner"])
  if RESULT["owner_verified"]:
   for job in JOBS:
    id=job["id"]
    row={"id":id,"status":"not_started","attempted":False,"sent_confirmed":False,"free_verified":False}
    RESULT["jobs"].append(row)
    marker=ROOT/("fl_free_vacancy_attempt_"+id+"_20261114.json")
    if marker.exists() or marker.is_symlink():
     row["status"]="prior_attempt_marker_no_retry";continue
    try:
     r=p.goto(job["url"],wait_until="domcontentloaded",timeout=21000)
     p.wait_for_timeout(400)
     if not r or r.status!=200 or not is_fl_url(p.url) or urlsplit(p.url).path!=urlsplit(job["url"]).path:
      row["status"]="http_or_url_mismatch";continue
     s=classify(p)
     if s["title"]!=job["title"] or not s["vacancy"]:
      row["status"]="wrong_title_or_not_vacancy";continue
     if s["applied"]:
      row["status"]="already_applied";continue
     if s["closed"]:
      row["status"]="closed";continue
     if s["paid"]:
      row["status"]="paid_gate_no_payment";continue
     if s["captcha"]:
      row["status"]="captcha_required_no_action";continue
     if not (s["editorCount"]==1 and s["editorNear"] and s["buttonCount"]==1 and not s["disabled"]):
      row["status"]="free_form_unverified";continue
     row["free_verified"]=True
     editor=p.locator('textarea[id^="ui-textarea-"]')
     editor.fill(job["text"],timeout=7500)
     after=classify(p)
     if not(after["editorValue"]==job["text"] and after["editorCount"]==1 and after["buttonCount"]==1
            and not after["paid"] and not after["captcha"] and not after["disabled"] and not after["applied"]):
      row["status"]="form_guard_failed";continue
     flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
     if hasattr(os,"O_NOFOLLOW"): flags|=os.O_NOFOLLOW
     fd=os.open(marker,flags,0o600)
     with os.fdopen(fd,"w",encoding="utf-8") as dst:
      json.dump({"job":id,"state":"attempt_started_no_retry","utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())},dst)
      dst.flush();os.fsync(dst.fileno())
     row["attempted"]=True
     try:
      p.get_by_role("button",name="Отправить отклик",exact=True).click(timeout=10000)
      p.wait_for_timeout(1800)
      a=classify(p)
      if a["applied"]:
       row["status"]="submitted_confirmed_ui";row["sent_confirmed"]=True
      elif a["paid"]:
       row["status"]="payment_gate_no_payment"
      else:
       rp=p.goto(job["url"],wait_until="domcontentloaded",timeout=20000)
       p.wait_for_timeout(450)
       if rp and rp.status==200 and classify(p)["applied"]:
        row["status"]="submitted_confirmed_readback";row["sent_confirmed"]=True
       else:
        row["status"]="clicked_unconfirmed_do_not_retry"
     except Exception:
      row["status"]="click_or_readback_error_do_not_retry"
    except Exception as e:
     row["status"]="technical_error_no_retry" if marker.exists() else "technical_error_before_attempt"
     row["error_class"]=type(e).__name__
finally:
 b.close()
 print(json.dumps(RESULT,ensure_ascii=False,sort_keys=True))
