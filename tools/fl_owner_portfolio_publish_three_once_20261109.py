#!/usr/bin/env python3
"""One-time owner-authorized posting of own redacted portfolio examples (not client work).
Three allowlisted unique titles and sections, no payments, credentials or account settings.
"""
from pathlib import Path
import sys,os,json,html,tempfile,time
from urllib.parse import urlsplit
root=Path.home()/".fl-agent";sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
URL="https://www.fl.ru/users/olegendorphine/portfolio/"
WORK=[
 {"id":"shab","title":"Персональный ИИ-Штаб: память, документы и контроль",
  "lines":("ПЕРСОНАЛЬНЫЙ","ИИ-ШТАБ"),"subtitle":"Память · Документы · Контроль","features":["Память","Интеграции","Контроль"],"color":"#18d6c2",
  "cat":"AI — искусственный интеллект / AI-агенты","btn":2,
  "desc":("Собственный практический проект, не клиентский заказ. Цель — объединить документы, переписку, задачи, сроки и накопленные решения в личную ИИ-экосистему. Построен «Штаб»: пользовательский интерфейс, внешний сервер и API, долговременное хранилище материалов, код и версии в GitHub, процедуры контроля и проверки результатов. Система применяется для работы с реальными документами и задачами владельца. Архитектура разделяет данные, инструменты и интеллектуальный движок: конкретная ИИ-модель может быть заменена после проверки совместимости. Конфиденциальные материалы не демонстрируются.")},
 {"id":"vps","title":"Автономный браузер на VPS и контроль сессий",
  "lines":("АВТОНОМНЫЙ","ИИ-КОНТУР VPS"),"subtitle":"Сервер · Браузер · Мониторинг","features":["Сервер","API","Проверка"],"color":"#4ca8fd",
  "cat":"Автоматизация бизнеса / AI-автоматизация","btn":4,
  "desc":("Собственный инженерный проект на VPS. Цель — работать с серверными инструментами без постоянно включённого локального компьютера. Настроены изолированный графический Chromium, пользовательский запуск без прав root, защищённый ввод владельца, приватное сохранение и восстановление браузерной сессии, периодический контроль состояния через GitHub Actions. Отдельно проверяется результат внешних действий, а не только факт запуска скрипта. Решение рассчитано на разрешённые владельцу интеграции; не является инструментом обхода ограничений сайтов и не заявляется как круглосуточный коммерческий SaaS.")},
 {"id":"docs","title":"ИИ-документооборот: связи, анализ и полезные сигналы",
  "lines":("УМНЫЕ","ДОКУМЕНТЫ"),"subtitle":"Источники · Связи · Результат","features":["Данные","Связи","Проверка"],"color":"#a084f6",
  "cat":"AI — искусственный интеллект / RAG / Базы знаний","btn":3,
  "desc":("Обезличенный пример части собственной персональной ИИ-экосистемы. Задача — сократить ручной поиск сведений в документах и переписке, сохранять историю решений, замечать противоречия и готовить структурированные материалы. Рабочий сценарий: получить источники → связать с делом или процессом → выделить факты и сроки → подготовить проект решения → проверить и обновить историю. Данные и проверяемые выводы хранятся отдельно от конкретной ИИ-модели. Это демонстрация прикладного подхода к информации, а не реклама гарантированной юридической или медицинской экспертизы.")}
]
assert len(set(x["title"] for x in WORK))==3
out={"schema":"fl.owner.portfolio.publish3.v1","owner_verified":False,"payment_actions":False,
"personal_data_changed":False,"captcha":False,"results":[]}
def cover(ctx,path,job):
  import html
  e=html.escape
  pg=ctx.new_page()
  pg.set_viewport_size({"width":900,"height":900})
  lines=job["lines"]
  title=''.join(f'<text x="72" y="{205+i*82}" fill="#f6fbff" font-size="60" font-weight="700" font-family="DejaVu Sans,Arial">{e(line)}</text>' for i,line in enumerate(lines))
  labels=''.join(f'<g transform="translate({74+idx*274},514)"><rect width="238" height="211" rx="22" fill="#143b59" stroke="{job["color"]}" stroke-width="3"/><circle cx="119" cy="73" r="27" fill="none" stroke="{job["color"]}" stroke-width="5"/><path d="M107 73h24 M119 61v24" stroke="{job["color"]}" stroke-width="4"/><text x="119" y="156" text-anchor="middle" fill="#f1f8ff" font-size="27" font-weight="700" font-family="DejaVu Sans,Arial">{e(feat)}</text></g>' for idx,feat in enumerate(job["features"]))
  svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="900" viewBox="0 0 900 900">
   <defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#06192e"/><stop offset="1" stop-color="#123d59"/></linearGradient></defs>
   <rect width="900" height="900" fill="url(#bg)"/>
   <circle cx="790" cy="135" r="200" fill="{job["color"]}" opacity=".12"/>
   <rect x="72" y="68" width="168" height="10" rx="5" fill="{job["color"]}"/>
   {title}<text x="72" y="396" fill="#bddef0" font-family="DejaVu Sans,Arial" font-size="27">{e(job["subtitle"])}</text>
   {labels}<path d="M72 808h756" stroke="{job["color"]}" stroke-width="2"/>
   <text x="72" y="851" fill="#a4bdd3" font-size="21" font-family="DejaVu Sans,Arial">СОБСТВЕННАЯ РАЗРАБОТКА · ИИ-ЭКОСИСТЕМА</text></svg>'''
  pg.set_content('<html><body style="margin:0;background:#06192e">'+svg+'</body></html>',wait_until="load")
  pg.screenshot(path=str(path),type="jpeg",quality=82,animations="disabled",timeout=16000)
  pg.close()
def intent(path,job):
 fd=os.open(path,os.O_WRONLY|os.O_EXCL|os.O_CREAT|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"w") as f:
  json.dump({"job_id":job["id"],"created":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"state":"publish_once"},f)
  f.flush();os.fsync(f.fileno())
def page_reopen(p):
 try:r=p.goto(URL,wait_until="domcontentloaded",timeout=23000)
 except Exception:
  r=p.goto(URL,wait_until="commit",timeout=20000)
  p.wait_for_timeout(1500)
 if not r or not is_fl_url(p.url) or urlsplit(p.url).path!=urlsplit(URL).path:raise RuntimeError("wrong_public_profile")
 p.wait_for_timeout(350)
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-portfolio-three-",dir=root) as temp:
  b.open(Path(temp));p=b.page
  try:p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=22000)
  except Exception:p.goto(ALLOWED_PAGES["settings"],wait_until="commit",timeout=20000);p.wait_for_timeout(1300)
  o=p.evaluate("""()=>({a:(document.body?.innerText||'').includes('Основные настройки'),b:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com')})""")
  out["owner_verified"]=bool(o["a"] and o["b"] and is_fl_url(p.url))
  if out["owner_verified"]:
   for job in WORK:
    info={"id":job["id"],"title":job["title"],"category":job["cat"],"clicked":False,"verified":False,"status":"not_started"}
    out["results"].append(info)
    marker=root/("fl_portfolio_work_publish_"+job["id"]+"_20261109.json")
    try:
     page_reopen(p)
     if job["title"] in p.locator("body").inner_text():
      info["status"]="already_present";info["verified"]=True;continue
     if marker.exists() or marker.is_symlink():info["status"]="previous_attempt_no_retry";break
     adds=p.locator('button[data-id="fl-add-portfolio-button"]')
     if adds.count()!=5:info["status"]="unexpected_section_buttons";break
     adds.nth(job["btn"]).click(timeout=8000)
     p.wait_for_timeout(300)
     title=p.locator("#ui-input-example-name-input")
     if title.count()!=1:raise RuntimeError("wrong_form_first_step")
     title.fill(job["title"],timeout=5500)
     cover_path=Path(temp)/("cover_"+job["id"]+".jpg");cover(b.context,cover_path,job)
     file_inputs=p.locator("input[type=file]")
     if file_inputs.count()<2 or "image/webp" not in (file_inputs.nth(1).get_attribute("accept") or ""):
      raise RuntimeError("cover_input_missing")
     file_inputs.nth(1).set_input_files(str(cover_path),timeout=9000)
     p.wait_for_timeout(600)
     crop=p.get_by_role("button",name="Сохранить обложку",exact=True)
     if crop.count()!=1:raise RuntimeError("crop_step_missing")
     crop.click(timeout=8500);p.wait_for_timeout(2200)
     if crop.is_visible():raise RuntimeError("crop_not_saved")
     p.get_by_role("button",name="Продолжить",exact=True).click(timeout=8500)
     p.wait_for_timeout(450)
     description=p.locator("#ui-textarea-description-input")
     if description.count()!=1:raise RuntimeError("description_step_missing")
     description.fill(job["desc"])
     if description.input_value()!=job["desc"]:raise RuntimeError("description_not_filled")
     p.get_by_role("button",name="Продолжить",exact=True).click(timeout=8500)
     p.wait_for_timeout(470)
     search=p.get_by_placeholder("Специализация",exact=True)
     if search.count()!=1:raise RuntimeError("category_field_missing")
     search.click(timeout=6000);p.wait_for_timeout(380)
     options=p.locator('[role=option], [class*=dropdown] li, [class*=multiselect] li')
     target=options.filter(has_text=job["cat"])
     if target.count()!=1:
      info["status"]="category_not_unique";break
     target.click(timeout=7000);p.wait_for_timeout(300)
     # Category must appear in selected category control; use data, not transient dropdown.
     shown=p.evaluate("""()=>{const txt=(document.body?.innerText||''); const k=txt.lastIndexOf('Добавление примера работы');return txt.slice(k,k+650);}""")
     if job["cat"] not in shown:info["status"]="category_selection_unconfirmed";break
     pub=p.get_by_role("button",name="Опубликовать",exact=True)
     if pub.count()!=1 or not pub.is_enabled():info["status"]="publish_button_invalid";break
     intent(marker,job)
     pub.click(timeout=11000)
     info["clicked"]=True
     p.wait_for_timeout(1200)
     page_reopen(p)
     info["verified"]=job["title"] in p.locator("body").inner_text()
     info["status"]="published_and_verified" if info["verified"] else "clicked_outcome_unknown_do_not_retry"
     if not info["verified"]:break
    except Exception as e:
     info["status"]="error_after_intent_no_retry" if marker.exists() else "error_before_intent"
     info["error_type"]=type(e).__name__
     break
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
