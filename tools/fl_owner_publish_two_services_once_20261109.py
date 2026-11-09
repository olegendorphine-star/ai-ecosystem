#!/usr/bin/env python3
"""Owner-approved one-time publish of two fixed-price FL services if NO cover needed.
No payment, no token export; prevent duplicates and stop on missing cover/validation.
"""
from pathlib import Path
from urllib.parse import urlsplit
import os,sys,json,tempfile,time
root=Path.home()/".fl-agent";sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
URL="https://www.fl.ru/users/olegendorphine/uslugi-freelancera/"
services=[
 {"id":"audit",
  "title":"Аудит одного процесса и карта ИИ-автоматизации",
  "rub":5000,"days":3,
  "description":("Разберу один ваш рабочий процесс и покажу возможности применения ИИ. "
   "Включено: анализ описания процесса до 2 страниц и до 5 обезличенных примеров; "
   "карта этапов, источников информации и узких мест; три гипотезы автоматизации; "
   "приоритетный план на 2–4 страницах. Одна корректировка фактических неточностей включена. "
   "Не входят программирование, интеграции, API-подписки и внедрение. "
   "Итог — документ с рекомендациями и конкретными следующими шагами."),
  "requirements":("Описание одного процесса до 2 страниц, ожидаемый результат, "
                  "до пяти обезличенных примеров. Пароли, доступы и персональные данные не требуются."),
  "result":"PDF или Google Doc (2–4 стр.): карта процесса, 3 гипотезы и план.",
  "subcat":"AI-агенты"},
 {"id":"spec",
  "title":"Разработаю ТЗ на персонального ИИ-ассистента",
  "rub":12000,"days":4,
  "description":("Подготовлю техническое задание на персонального ИИ-ассистента для одного "
   "основного рабочего сценария. Включено: роли пользователя и ИИ, архитектура памяти, "
   "инструменты и до трёх интеграций, требования безопасности, критерии приёмки "
   "и план MVP. Результат — 5–7 страниц в PDF или Google Doc, одна итерация уточнений. "
   "Не входят программирование, запуск сервера, подписки на API, внедрение и "
   "неограниченное расширение требований."),
  "requirements":("Описание одного рабочего сценария, ожидаемые результаты, "
                  "до трёх сервисов для интеграции, ограничения и бюджет. Доступы/пароли не нужны."),
  "result":"ТЗ в PDF/Google Doc (5–7 стр.) + критерии приёмки и дорожная карта MVP.",
  "subcat":"AI-агенты"}
]
o={"schema":"fl.owner.services.publish.once.v1","owner":False,"account":"olegendorphine",
"payment_performed":False,"other_profile_changed":False,"captcha_interacted":False,
"results":[]}
def mark(path,service):
 fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"w") as f:
  json.dump({"id":service["id"],"title":service["title"],"time":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"state":"intent_no_retry"},f,ensure_ascii=False)
  f.flush();os.fsync(f.fileno())
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-services-publish-",dir=root) as t:
  b.open(Path(t));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  sig=p.evaluate("""()=>({owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
   settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  o["owner"]=bool(sig["owner"] and sig["settings"] and is_fl_url(p.url))
  if o["owner"]:
   for svc in services:
    entry={"id":svc["id"],"result":"not_started","clicked_publish":False,"verified":False}
    o["results"].append(entry)
    marker=root/("fl_service_publish_intent_"+svc["id"]+"_20261109.json")
    try:
     r=p.goto(URL,wait_until="domcontentloaded",timeout=24000);p.wait_for_timeout(400)
     u=urlsplit(p.url)
     if not r or r.status!=200 or u.scheme!="https" or u.hostname not in ("www.fl.ru","fl.ru") or u.path!=urlsplit(URL).path:
      entry["result"]="unexpected_site";break
     if svc["title"] in p.locator("body").inner_text():
      entry["result"]="already_visible";entry["verified"]=True;continue
     if marker.exists() or marker.is_symlink():
      entry["result"]="already_attempted_no_retry";break
     btn=p.locator('button[data-id="typical-services-block_add_button"]')
     if btn.count()!=1:
      entry["result"]="missing_add_button";break
     btn.click(timeout=7500);p.wait_for_timeout(270)
     for css,value in [
       ("#ui-input-example-name-input",svc["title"]),
       ("#ui-textarea-description-input",svc["description"]),
       ("#ui-textarea-emp_requirement-input",svc["requirements"]),
       ("#ui-input-emp_result-input",svc["result"])
     ]:
      if p.locator(css).count()!=1:
       raise RuntimeError("unexpected_step_1")
      p.locator(css).fill(value,timeout=6000)
     nxt=p.get_by_role("button",name="Продолжить",exact=True)
     if nxt.count()!=1:raise RuntimeError("ambiguous_step1_continue")
     nxt.click(timeout=10000);p.wait_for_timeout(230)
     p.locator("#ui-input-price").fill(str(svc["rub"]))
     p.locator("#ui-input-days").fill(str(svc["days"]))
     nxt=p.get_by_role("button",name="Продолжить",exact=True)
     nxt.click(timeout=10000);p.wait_for_timeout(230)
     p.get_by_text("AI — искусственный интеллект",exact=True).last.click(timeout=6000)
     p.get_by_text(svc["subcat"],exact=True).last.click(timeout=6000)
     nxt=p.get_by_role("button",name="Продолжить",exact=True)
     nxt.click(timeout=10000);p.wait_for_timeout(230)
     pub=p.get_by_role("button",name="Опубликовать",exact=True)
     if pub.count()!=1 or not pub.is_enabled():
      entry["result"]="cannot_publish_no_extra_actions";break
     state=p.evaluate("""()=>({
      correctStep:(document.body?.innerText||'').includes('Изображения и файлы с примерами'),
      payment:/нужно оплатить услугу|оплатить публикацию|купить размещение услуги/i.test(
        (document.querySelector('[role=dialog]')?.innerText||'').slice(-1800))
     })""")
     if not state["correctStep"] or state["payment"]:
      entry["result"]="pre_submit_guard";break
     mark(marker,svc)
     pub.click(timeout=12000)
     entry["clicked_publish"]=True
     p.wait_for_timeout(1250)
     # Read owner list fresh; do NOT retry even if browser times out.
     r=p.goto(URL,wait_until="domcontentloaded",timeout=24000);p.wait_for_timeout(400)
     entry["verified"]=(bool(r) and r.status==200 and svc["title"] in p.locator("body").inner_text())
     entry["result"]="published_visible" if entry["verified"] else "submitted_unverified_or_cover_required"
     if not entry["verified"]:break
    except Exception:
     entry["result"]="error_after_attempt_stop" if marker.exists() else "error_before_attempt"
     break
finally:b.close()
print(json.dumps(o,ensure_ascii=False,sort_keys=True))
