#!/usr/bin/env python3
"""Inspect FL typical service stage 2 after filling local step one. No publish."""
from pathlib import Path
import sys,json,tempfile
root=Path.home()/".fl-agent";sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
URL="https://www.fl.ru/users/olegendorphine/uslugi-freelancera/"
TITLE="Аудит одного процесса и карта ИИ-автоматизации"
DESC=("Разберу один рабочий процесс и покажу возможности применения ИИ. Включено: анализ описания процесса до 2 страниц и до 5 обезличенных примеров; карта этапов, источников и узких мест; три гипотезы автоматизации; приоритетный план на 2–4 страницах. Одна корректировка фактических неточностей включена. Не входят программирование, интеграции, API-подписки и внедрение. Итог — документ с понятными рекомендациями и следующими шагами.")
REQ="Описание одного процесса до 2 страниц, ожидаемый результат, до 5 обезличенных примеров. Пароли, доступы и персональные данные не требуются."
RESULT="PDF или Google Doc (2–4 стр.): карта процесса, три гипотезы и план."
o={"schema":"fl.owner.typical.service.step4.v1","owner":False,"published":False}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-service-step2-",dir=root) as t:
  b.open(Path(t));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=19000)
  a=p.evaluate("""()=>({h:(document.body?.innerText||'').includes('Основные настройки'),owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com')})""")
  o["owner"]=bool(a["h"] and a["owner"] and is_fl_url(p.url))
  if o["owner"]:
   p.goto(URL,wait_until="domcontentloaded",timeout=22000);p.wait_for_timeout(350)
   p.locator('button[data-id="typical-services-block_add_button"]').click(timeout=6000)
   p.wait_for_timeout(380)
   p.locator('#ui-input-example-name-input').fill(TITLE)
   p.locator('#ui-textarea-description-input').fill(DESC)
   p.locator('#ui-textarea-emp_requirement-input').fill(REQ)
   p.locator('#ui-input-emp_result-input').fill(RESULT)
   btn=p.get_by_role("button",name="Продолжить")
   o["next_count"]=btn.count()
   if btn.count()!=1:
    o["status"]="ambiguous_next"
   else:
    btn.click(timeout=8000);p.wait_for_timeout(650)
    o["status"]="step_two_open"
    p.locator("#ui-input-price").fill("5000")
    p.locator("#ui-input-days").fill("3")
    p.get_by_role("button",name="Продолжить").click(timeout=8000)
    p.wait_for_timeout(550)
    o["status"]="step_three_open"
    try:
     cat=p.get_by_text("AI — искусственный интеллект",exact=True)
     o["cat_count"]=cat.count()
     cat.last.click(timeout=5000)
     p.wait_for_timeout(500)
     o["status"]="ai_category_opened"
     opt=p.get_by_text("AI-агенты",exact=True)
     o["subcategory_matches"]=opt.count()
     opt.last.click(timeout=6000)
     p.wait_for_timeout(250)
     p.get_by_role("button",name="Продолжить").click(timeout=8000)
     p.wait_for_timeout(550)
     o["status"]="files_step_or_validation"
    except Exception:
     o["status"]="ai_category_not_opened"
    o["fields"]=p.evaluate("""()=>{
     const q=document.body?.innerText||'';
     const n=q.lastIndexOf('Добавление услуги');
     const body=n>=0?q.slice(n):q.slice(-2500);
     return {text:body.slice(-1900),fields:Array.from(document.querySelectorAll('input,select,textarea,[contenteditable=true]')).filter(e=>e.getBoundingClientRect().width>0&& !['hidden','password','file'].includes(e.type||'')).slice(-35).map(e=>({
      tag:e.tagName,id:(e.id||'').slice(0,85),name:(e.name||'').slice(0,65),
      type:e.type||'',placeholder:(e.getAttribute('placeholder')||'').slice(0,95),
      near:(e.closest('label')?.innerText||'').trim().slice(0,80),valueLength:(e.value||'').length
     })),buttons:Array.from(document.querySelectorAll('button')).filter(e=>e.getBoundingClientRect().width>0).map(e=>(e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,65)).filter(Boolean).slice(-18)}
    }""")
finally:b.close()
print(json.dumps(o,ensure_ascii=False))
