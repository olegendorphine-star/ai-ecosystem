#!/usr/bin/env python3
"""One-time change of descriptions only for 3 existing owner FL portfolio items.
No edits to titles, covers, sections, personal data, billing or other works.
"""
from pathlib import Path
from urllib.parse import urlsplit
import json,sys,os,tempfile,time
ROOT=Path.home()/".fl-agent"
sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,is_fl_url
SETTINGS="https://www.fl.ru/users/olegendorphine/setup/main/"
PORT="https://www.fl.ru/users/olegendorphine/portfolio/"
WORKS=[
 ("8111943","Персональный ИИ-Штаб: память, документы и контроль","Собственный практический проект",
  """ЗАДАЧА. Документы, переписка и сроки разбросаны по разным источникам. Из-за этого сложнее находить решения и контролировать следующие действия.

РЕШЕНИЕ. Собственный действующий проект «ИИ-Штаб»: внешний сервер, память в Google Drive, связка документов и задач, процедуры проверки выводов. Система помогает находить связанный контекст, готовить проекты действий и сохранять историю решений.

ПОЛЬЗА ДЛЯ ЗАКАЗЧИКА. Тот же подход можно применить к базе знаний компании, контролю заявок и рабочим отчётам — начав с одного ограниченного пилота и проверенных интеграций.

Это собственная разработка, не оплаченный заказ. Экономия времени в часах не измерялась. Личные документы в примерах не раскрываются."""),
 ("8111945","ИИ-документооборот: связи, анализ и полезные сигналы","Обезличенный пример",
  """ЗАДАЧА. В папках и переписке трудно быстро найти нужный документ, сопоставить факты, сроки и принятые решения.

РЕШЕНИЕ. Собственный модуль персональной ИИ-экосистемы: организует информационные источники, помогает связывать факты, находить выдержки и готовить структурированные проекты ответов.

СЦЕНАРИЙ. Получить обезличенные материалы → найти нужные сведения → проверить источник и контекст → отметить срок или противоречие → сохранить результат.

ПОЛЬЗА ДЛЯ ЗАКАЗЧИКА. Так можно создать единый поиск и историю решений для рабочих документов вместо разрозненных папок. Доступы, конфиденциальность и качество ответов проверяются отдельно.

Это собственная демонстрация, не клиентское внедрение. ИИ не заменяет юридическую, медицинскую и иную профессиональную экспертизу."""),
 ("8111944","Автономный браузер на VPS и контроль сессий","Собственный инженерный проект",
  """ЗАДАЧА. Работа с заявками и регулярными проверками не должна зависеть от постоянно включённого личного компьютера.

РЕШЕНИЕ. Собственный серверный контур на VPS: изолированный Chromium, авторизация владельца, запуск проверок через GitHub Actions, журнал ошибок и независимая проверка результата действия.

ЧТО ПРОВЕРЕНО. Браузер реально запускается на VPS, открывает разрешённые собственные страницы и позволяет проверять состояние рабочих процессов. Успешный запуск задачи не считается успешным бизнес-результатом без повторной проверки.

ПОЛЬЗА ДЛЯ ЗАКАЗЧИКА. Можно автоматизировать один разрешённый повторяемый процесс: мониторинг статусов, сбор отчёта или уведомления — затем расширять по результатам пилота.

Это собственный инженерный кейс, не коммерческий SaaS. Не предполагает обход CAPTCHA, ограничений сервиса или гарантию бесперебойной работы без сопровождения.""")
]
out={"schema":"fl.owner.portfolio.benefit.descriptions.v1","owner":False,"results":[],
     "payments":False,"customer_messages":False,"identity_changes":False,"covers_changed":False,
     "sections_changed":False,"new_works":False}
b=Browser()
def open_edit(p,id):
 r=p.goto(PORT,wait_until="domcontentloaded",timeout=24000)
 if not r or r.status!=200 or not is_fl_url(p.url) or urlsplit(p.url).path!=urlsplit(PORT).path:
  raise RuntimeError("portfolio_unavailable")
 card=p.locator(".portfolio-item").filter(has=p.locator('a[href*="/portfolio/'+id+'/"]'))
 if card.count()!=1:raise RuntimeError("wrong_work_card")
 edit=card.get_by_text("Редактировать",exact=True)
 if edit.count()!=1:raise RuntimeError("edit_button_not_unique")
 edit.click(timeout=9000)
 p.wait_for_timeout(450)
 return card
def continue_step(p):
 btn=p.get_by_role("button",name="Продолжить",exact=True)
 if btn.count()!=1 or not btn.is_enabled():raise RuntimeError("continue_not_available")
 btn.click(timeout=12000)
 p.wait_for_timeout(350)
def mark(path,text):
 fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"w",encoding="utf-8") as f:f.write(text);f.flush();os.fsync(f.fileno())
try:
 with tempfile.TemporaryDirectory(prefix="fl-owner-work-desc-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  r=p.goto(SETTINGS,wait_until="domcontentloaded",timeout=24000)
  a=p.evaluate("""()=>({
   owner:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
   settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner"]=bool(r and r.status==200 and is_fl_url(p.url) and a["owner"] and a["settings"])
  if out["owner"]:
   for id,title,old_prefix,new_text in WORKS:
    x={"id":id,"status":"not_started","clicked":False,"verified":False}
    out["results"].append(x)
    marker=ROOT/("fl_owner_work_desc_"+id+"_20261110.intent")
    backup=ROOT/("fl_owner_work_desc_"+id+"_20261110.backup.txt")
    try:
     open_edit(p,id)
     title_field=p.locator("#ui-input-example-name-input")
     if title_field.count()!=1 or title_field.input_value().strip()!=title:
      x["status"]="title_mismatch";break
     continue_step(p)
     desc=p.locator("#ui-textarea-description-input")
     if desc.count()!=1: x["status"]="description_field_missing";break
     old=desc.input_value().strip()
     if old==new_text:x["status"]="already_desired";x["verified"]=True;continue
     if not old.startswith(old_prefix) or not 300<=len(old)<=1200:
      x["status"]="unexpected_existing_description";break
     if marker.exists() or marker.is_symlink() or backup.exists() or backup.is_symlink():
      x["status"]="previous_attempt_no_retry";break
     mark(backup,old)
     desc.fill(new_text)
     if desc.input_value()!=new_text:
      x["status"]="pre_save_mismatch";break
     continue_step(p)
     save=p.get_by_role("button",name="Сохранить",exact=True)
     if save.count()!=1 or not save.is_enabled():x["status"]="final_save_missing";break
     # Save exact owner description only; cover, title, category untouched.
     mark(marker,json.dumps({"work_id":id,"action":"replace_description_only","time":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}))
     save.click(timeout=14000)
     x["clicked"]=True
     p.wait_for_timeout(700)
     # Read again from the editing wizard. Never re-submit after uncertain click.
     open_edit(p,id)
     title_again=p.locator("#ui-input-example-name-input")
     if title_again.count()!=1 or title_again.input_value().strip()!=title:
      x["status"]="title_changed_or_unavailable";break
     continue_step(p)
     fresh=p.locator("#ui-textarea-description-input")
     x["verified"]=fresh.count()==1 and fresh.input_value().strip()==new_text
     x["status"]="saved_verified" if x["verified"] else "after_save_uncertain_no_retry"
     if not x["verified"]:break
    except Exception as e:
     x["status"]="error_after_attempt_no_retry" if marker.exists() else "error_before_attempt"
     x["error_type"]=type(e).__name__
     break
finally:
 b.close()
 print(json.dumps(out,ensure_ascii=False,sort_keys=True))
