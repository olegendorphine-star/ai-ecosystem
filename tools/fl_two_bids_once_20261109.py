#!/usr/bin/env python3
"""Owner-authorized one-time submission of two selected FREE FL bids.

Safety: exactly 2 allowlisted jobs/terms, no purchases or retries, no leaked
cookies/passwords/PII, no account modifications outside the bid form.
"""
from __future__ import annotations
import json,os,stat,sys,tempfile,time
from pathlib import Path
from urllib.parse import urlsplit
root=Path.home()/".fl-agent"
sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
jobs=[
 {"id":"5528403",
  "title":"Требуется рабочий сценарий для ИИ для карточек товара в группе ювелирные серьги",
  "url":"https://www.fl.ru/projects/5528403/trebuetsya-rabochiy-stsenariy-dlya-ii-dlya-kartochek-tovara-v-gruppe-yuvelirnyie-sergi.html",
  "cost":7000,"days":3,
  "text":"""Здравствуйте. Могу разработать и проверить воспроизводимый ИИ-сценарий именно для серёг — не один универсальный промпт, а последовательность обработки с проверкой результата.

Основная задача — сохранить геометрию украшения, расположение камней, тип застёжки, фактуру и цвет металла, добившись естественного освещения без искажённых деталей.

Предлагаю начать с одного артикула по 2–3 исходным фотографиям, согласовать правильный вид изделия и перенести утверждённые правила на остальные 5–7 позиций. Передам промпты, параметры, чек-лист проверки и результаты тестирования.

Стоимость — 7 000 ₽, срок — 3 рабочих дня после получения исходников. Если потребуется дополнительная предметная ретушь или большое количество вариантов, объём согласуем заранее.

Можете прислать один проблемный исходник и пример удачной карточки другого украшения?"""},
 {"id":"5527732",
  "title":"Cоздание единого корпоративного стиля портретов (Нейрофотосессия)",
  "url":"https://www.fl.ru/projects/5527732/cozdanie-edinogo-korporativnogo-stilya-portretov-neyrofotosessiya.html",
  "cost":3000,"days":2,
  "text":"""Здравствуйте. Могу привести фотографии сотрудников к единому корпоративному стилю: одинаковое освещение, ракурс, кадрирование, деловая одежда и спокойный студийный фон.

Предлагаю сначала обработать два портрета, согласовать стиль на этих примерах и затем применить его ко всей серии. При обработке особое внимание уделю сохранению узнаваемости и индивидуальных черт сотрудников.

Итоговый формат — вертикальные PNG/JPG в высоком разрешении.

Ориентир — 1 500 ₽ за портрет. Тест из двух фотографий — 3 000 ₽, срок — 2 рабочих дня после получения материалов. Общий бюджет уточним по количеству сотрудников и качеству исходников.

Сколько портретов нужно обработать и есть ли образец желаемого результата?"""},
]
result={"schema":"fl.owner.2.bids.once.v1","owner_verified":False,
 "projects":[],"payment_actions":False,"captcha_interacted":False,
 "login_performed":False,"cookies_exported":False,"secrets_logged":False}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-2-approved-bids-",dir=root) as tmp:
  b.open(Path(tmp))
  page=b.page
  page.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  sig=page.evaluate("""() => ({
   settings:(document.body?.innerText||'').includes('Основные настройки'),
   owner:Array.from(document.querySelectorAll('input')).some(
     e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com')
  })""")
  result["owner_verified"]=bool(sig.get("settings") and sig.get("owner") and is_fl_url(page.url))
  if result["owner_verified"]:
   for job in jobs:
    entry={"id":job["id"],"cost":job["cost"],"days":job["days"],
           "free_verified":False,"clicked":False,"result":"not_started"}
    result["projects"].append(entry)
    marker=root/("fl_owner_bid_attempt_"+job["id"]+"_20261109.json")
    if marker.exists() or marker.is_symlink():
     entry["result"]="local_attempt_marker_present"
     continue
    try:
     response=page.goto(job["url"],wait_until="domcontentloaded",timeout=20000)
     page.wait_for_timeout(600)
     exact=(urlsplit(page.url)._replace(query="",fragment="").geturl()==job["url"])
     if not exact or response is None or response.status!=200 or not is_fl_url(page.url):
      entry["result"]="wrong_url_or_http";continue
     signal=page.evaluate("""() => {
       const h=(document.querySelector('h1')?.innerText||'').trim();
       const t=(document.body?.innerText||'');
       const pos=t.indexOf(h);
       const body=t.slice(Math.max(pos,0),Math.max(pos,0)+4500);
       return {title:h,free:/Для всех/.test(body),
          closed:/исполнитель определён|проект закрыт|заказ закрыт|проект завершён/i.test(body),
          already:/ваш отклик отправлен|вы откликнулись|редактировать отклик|отклик уже отправлен/i.test(body),
          captcha:!!document.querySelector('[class*="smartcaptcha"],[id*="captcha"]'),
          hasSubmit:document.querySelector('#el-submit')?.innerText?.trim()==='Отправить отклик',
          hasForm:!!document.querySelector('form textarea#el-descr')};
     }""")
     entry["free_verified"]=bool(signal.get("free"))
     if signal["title"]!=job["title"]:
      entry["result"]="title_mismatch";continue
     if signal.get("closed") or signal.get("already"):
      entry["result"]="closed_or_already_applied";continue
     if signal.get("captcha"):
      entry["result"]="captcha_required";continue
     if not (signal.get("free") and signal.get("hasSubmit") and signal.get("hasForm")):
      entry["result"]="not_confirmed_free_form";continue
     page.locator("#el-descr").fill(job["text"],timeout=5000)
     page.locator("#el-time_from").fill(str(job["days"]),timeout=5000)
     page.locator("#el-cost_from").fill(str(job["cost"]),timeout=5000)
     # Recheck exactly what is being sent and refuse offsite/payment flows.
     entered=page.evaluate("""() => ({
      text:document.querySelector('#el-descr')?.value||'',
      cost:document.querySelector('#el-cost_from')?.value||'',
      days:document.querySelector('#el-time_from')?.value||'',
      button:document.querySelector('#el-submit')?.innerText?.trim()||'',
      btnDisabled:!!document.querySelector('#el-submit')?.disabled,
      free:(document.body?.innerText||'').includes('Для всех'),
      paymentsVisible:!!document.querySelector('[role=dialog] [class*=payment], [role=dialog] [class*=purchase]')
     })""")
     if (entered["text"]!=job["text"] or entered["cost"]!=str(job["cost"])
          or entered["days"]!=str(job["days"]) or not entered["free"]
          or entered["button"]!="Отправить отклик" or entered["btnDisabled"]
          or entered["paymentsVisible"]):
      entry["result"]="pre_submit_guard_failed";continue
     # An exclusive durable intent marker BEFORE external side effect.
     fd=os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
     with os.fdopen(fd,"w") as out:
      json.dump({"job":job["id"],"attempted_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
                 "price":job["cost"],"days":job["days"],
                 "state":"intended_no_retry"},out)
      out.flush()
      os.fsync(out.fileno())
     page.locator("#el-submit").click(timeout=8000)
     entry["clicked"]=True
     page.wait_for_timeout(2000)
     # Signals only; never claim success solely because click returned.
     after=page.evaluate("""() => {
       const t=(document.body?.innerText||'').toLowerCase();
       return {
        confirmation:/отклик (отправлен|успешно отправлен)|ваше предложение (отправлено|опубликовано)|отклик успешно/i.test(t),
        editOffer:/редактировать отклик|изменить отклик|редактировать предложение/i.test(t),
        alreadyOffer:/вы уже откликнулись|вы откликнулись на проект/i.test(t),
        submitVisible:!!Array.from(document.querySelectorAll('button')).find(
          e=>(e.innerText||'').trim()==='Отправить отклик' && e.offsetParent!==null),
        paymentScreen:/нужно купить отклики|недостаточно откликов|оплатите отклик/i.test(t),
        onFl:location.protocol==='https:' && ['fl.ru','www.fl.ru'].includes(location.hostname)
       }
     }""")
     if not after.get("onFl"):
      entry["result"]="unexpected_redirect_no_retry"
     elif after.get("paymentScreen"):
      entry["result"]="payment_screen_no_purchase"
     elif after.get("confirmation") or after.get("editOffer") or after.get("alreadyOffer"):
      entry["result"]="submitted_confirmed_ui"
     else:
      entry["result"]="clicked_unconfirmed_do_not_retry"
    except Exception:
     entry["result"]="error_do_not_retry" if marker.exists() else "error_before_attempt"
finally:
 b.close()
print(json.dumps(result,ensure_ascii=False,sort_keys=True))
