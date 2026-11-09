#!/usr/bin/env python3
"""Owner-approved one-time two fixed-price FL services WITH new local covers.
Explicit prior read-only check confirmed no listings visible. No paid actions and no blind retries.
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

def make_cover(ctx,path,service):
 import html
 esc=html.escape
 pg=ctx.new_page();pg.set_viewport_size({"width":1200,"height":800})
 if service["id"]=="audit":
  words=("КАРТА ИИ-","АВТОМАТИЗАЦИИ");small="Аудит одного процесса";cards=("Данные","Гипотезы","План");accent="#15d6c1"
 else:
  words=("ТЗ НА ПЕРСОНАЛЬНОГО","ИИ-АССИСТЕНТА");small="Сценарий, архитектура и критерии приёмки";cards=("Сценарий","Интеграции","MVP");accent="#4aabff"
 titles="".join('<text x="80" y="'+str(192+i*100)+'" fill="#f4fbff" font-size="68" font-weight="700" font-family="DejaVu Sans,Arial">'+esc(word)+'</text>' for i,word in enumerate(words))
 cardsvg="".join('<g transform="translate('+str(80+i*370)+',485)"><rect width="315" height="203" rx="25" fill="#123a5b" stroke="'+accent+'" stroke-width="3"/><circle cx="157" cy="68" r="29" fill="none" stroke="'+accent+'" stroke-width="5"/><path d="M145 68h24 M157 56v24" stroke="'+accent+'" stroke-width="4"/><text x="157" y="155" text-anchor="middle" fill="#edf8ff" font-family="DejaVu Sans,Arial" font-size="31" font-weight="700">'+esc(label)+'</text></g>' for i,label in enumerate(cards))
 svg='<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#06192f"/><stop offset="1" stop-color="#123d5d"/></linearGradient></defs><rect width="1200" height="800" fill="url(#bg)"/><circle cx="1020" cy="150" r="230" fill="'+accent+'" opacity=".12"/><rect x="80" y="62" width="210" height="10" rx="4" fill="'+accent+'"/>'+titles+'<text x="80" y="420" font-size="32" fill="#bcdbee" font-family="DejaVu Sans,Arial">'+esc(small)+'</text>'+cardsvg+'</svg>'
 pg.set_content('<html><body style="margin:0;background:#06192f">'+svg+'</body></html>',wait_until="load")
 pg.screenshot(path=str(path),type="jpeg",quality=85,animations="disabled",timeout=16000)
 pg.close()

o={"schema":"fl.owner.services.publish.cover.v2","owner":False,"account":"olegendorphine",
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
    marker=root/("fl_service_cover_v2_intent_"+svc["id"]+"_20261109.json")
    try:
     r=p.goto(URL,wait_until="domcontentloaded",timeout=24000);p.wait_for_timeout(400)
     u=urlsplit(p.url)
     if not r or r.status!=200 or u.scheme!="https" or u.hostname not in ("www.fl.ru","fl.ru") or u.path!=urlsplit(URL).path:
      entry["result"]="unexpected_site";break
     entry["stage"]="list_read"
     if svc["title"] in p.locator("body").inner_text():
      entry["result"]="already_visible";entry["verified"]=True;continue
     if marker.exists() or marker.is_symlink():
      entry["result"]="already_attempted_no_retry";break
     btn=p.locator('button[data-id="typical-services-block_add_button"]')
     if btn.count()!=1:
      entry["result"]="missing_add_button";break
     btn.click(timeout=7500);p.wait_for_timeout(270)
     entry["stage"]="step1_open"
     for css,value in [
       ("#ui-input-example-name-input",svc["title"]),
       ("#ui-textarea-description-input",svc["description"]),
       ("#ui-textarea-emp_requirement-input",svc["requirements"]),
       ("#ui-input-emp_result-input",svc["result"])
     ]:
      if p.locator(css).count()!=1:
       raise RuntimeError("unexpected_step_1")
      p.locator(css).fill(value,timeout=6000)
     entry["stage"]="step1_filled"
     nxt=p.get_by_role("button",name="Продолжить",exact=True)
     if nxt.count()!=1:raise RuntimeError("ambiguous_step1_continue")
     nxt.click(timeout=10000);p.wait_for_timeout(230)
     entry["stage"]="step2_open"
     p.locator("#ui-input-price").fill(str(svc["rub"]))
     p.locator("#ui-input-days").fill(str(svc["days"]))
     entry["stage"]="step2_filled"
     nxt=p.get_by_role("button",name="Продолжить",exact=True)
     nxt.click(timeout=10000);p.wait_for_timeout(230)
     entry["stage"]="step3_open"
     p.get_by_text("AI — искусственный интеллект",exact=True).last.click(timeout=6000)
     p.wait_for_timeout(550)
     entry["stage"]="category_open"
     p.get_by_text(svc["subcat"],exact=True).last.click(timeout=6000)
     entry["stage"]="subcategory_selected"
     nxt=p.get_by_role("button",name="Продолжить",exact=True)
     nxt.click(timeout=10000);p.wait_for_timeout(230)
     entry["stage"]="step4_open"
     asset=Path(t)/("service_"+svc["id"]+".jpg")
     make_cover(b.context,asset,svc)
     files=p.locator("input[type=file]")
     if files.count()<2 or "image/webp" not in (files.nth(1).get_attribute("accept") or ""):
      entry["result"]="service_cover_input_missing";break
     files.nth(1).set_input_files(str(asset),timeout=12000)
     p.wait_for_timeout(700)
     crop=p.get_by_role("button",name="Сохранить обложку",exact=True)
     if crop.count()!=1:
      entry["result"]="service_crop_missing";break
     crop.click(timeout=10000)
     p.wait_for_timeout(2600)
     if crop.is_visible():
      entry["result"]="service_crop_not_saved";break
     entry["stage"]="cover_saved"
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
     entry["stage"]="intent_saved"
     pub.click(timeout=12000)
     entry["clicked_publish"]=True
     p.wait_for_timeout(1500)
     # Read owner list fresh; do NOT retry even if browser times out.
     r=p.goto(URL,wait_until="domcontentloaded",timeout=24000);p.wait_for_timeout(400)
     entry["verified"]=(bool(r) and r.status==200 and svc["title"] in p.locator("body").inner_text())
     entry["result"]="published_visible" if entry["verified"] else "submitted_unverified_or_cover_required"
     if not entry["verified"]:break
    except Exception as ex:
     entry["error_class"]=type(ex).__name__
     entry["result"]="error_after_attempt_stop" if marker.exists() else "error_before_attempt"
     break
finally:b.close()
print(json.dumps(o,ensure_ascii=False,sort_keys=True))
