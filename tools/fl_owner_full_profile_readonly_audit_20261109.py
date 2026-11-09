#!/usr/bin/env python3
"""Owner-authorized FULL FL freelancer profile inventory, strictly READ ONLY.

Never opens customer messages, edits, checkout, billing, login or bid pages.
Exports only fixed booleans and public product state. Fails closed without
independent confirmation of the freelancer (not the customer) account.
"""
from __future__ import annotations
from pathlib import Path
import json, sys, tempfile
ROOT=Path.home()/".fl-agent"
URLS={
 "settings":"https://www.fl.ru/users/olegendorphine/setup/main/",
 "about_edit":"https://www.fl.ru/users/olegendorphine/setup/portfolio/",
 "profile":"https://www.fl.ru/users/olegendorphine/portfolio/",
 "prices":"https://www.fl.ru/users/olegendorphine/price-list/",
 "services":"https://www.fl.ru/users/olegendorphine/uslugi-freelancera/",
}
out={
 "schema":"fl.owner.full.profile.readonly.audit.v1",
 "verified_owner":False,
 "account":"olegendorphine",
 "status":"technical_error",
 "write_actions":False,"payments":False,
 "messages_opened":False,"bids_submitted":False,
 "pages":{},
}
b=None
try:
 sys.path.insert(0,str(ROOT))
 from fl_rootless_owner_desktop import Browser,is_fl_url
 b=Browser()
 with tempfile.TemporaryDirectory(prefix="fl-owner-full-profile-audit-",dir=ROOT) as td:
  b.open(Path(td)); p=b.page
  r=p.goto(URLS["settings"],wait_until="domcontentloaded",timeout=24000)
  signs=p.evaluate("""() => {
   const t=document.body?.innerText||'';
   return {
      owner: Array.from(document.querySelectorAll('input')).some(
       e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
      settings:t.includes('Основные настройки')
   };
  }""")
  out["verified_owner"]=bool(r and r.status==200 and is_fl_url(p.url) and signs["owner"] and signs["settings"])
  if not out["verified_owner"]:
   out["status"]="owner_verification_failed"
  else:
   for label,url in URLS.items():
    row={"http":None,"on_fl":False}
    try:
     resp=p.goto(url,wait_until="domcontentloaded",timeout=24000)
     p.wait_for_timeout(350)
     row["http"]=resp.status if resp else None
     row["on_fl"]=bool(is_fl_url(p.url))
     if row["http"]!=200 or not row["on_fl"]:
      out["pages"][label]=row
      continue
     data=p.evaluate("""() => {
      const body=document.body?.innerText||'';
      const links=Array.from(document.querySelectorAll('a')).map(x=>(x.innerText||'').trim().toLowerCase());
      const btns=Array.from(document.querySelectorAll('button')).map(x=>(x.innerText||'').trim().toLowerCase());
      const pname=document.querySelector('input[name=pname]');
      const about=document.querySelector('textarea[name=ab_text]');
      const words=['Персональный ИИ-Штаб: память, документы и контроль',
       'Автономный браузер на VPS и контроль сессий',
       'ИИ-документооборот: связи, анализ и полезные сигналы'];
      const labels=['Аудит процесса и карта ИИ-автоматизации',
       'ТЗ на персонального ИИ-ассистента',
       'Персональный ИИ-ассистент с памятью и API'];
      const count = rx => (body.match(rx)||[]).length;
      return {
       heading_is_generic:(document.querySelector('h1')?.innerText||'').trim().toLowerCase()==='фрилансер',
       professional_heading_present:!!pname?.value?.trim(),
       about_present:about ? about.value.trim().length>50 : /Создаю ИИ-ассистентов|ИИ-экосистемы/.test(body),
       about_has_sales_cta:/Напишите.*задач|Опишите.*задач|Предложу.*решени/i.test(about?.value||body),
       price_items_found:labels.filter(x=>body.includes(x)).length,
       portfolio_items_found:words.filter(x=>body.includes(x)).length,
       services_pending_labels:count(/На проверке|На модерации|Ожидает модерации/gi),
       services_approved_labels:count(/Одобрено|Опубликовано/gi),
       services_rejected_labels:count(/Отклонено|Не прошло модерацию/gi),
       services_audit_present:/Аудит одного процесса|Аудит процесса и карта/.test(body),
       services_spec_present:/ТЗ на персонального ИИ-ассистента|техническое задание на персонального ИИ/.test(body),
       cover_change_control_visible:links.concat(btns).some(x=>/изменить обложку|сменить обложку|загрузить обложку|оформление профиля/i.test(x)),
       gallery_edit_control_visible:links.concat(btns).some(x=>/редактировать|изменить работу|редактировать работу/i.test(x)),
       pro_feature_mentioned:/аккаунт PRO|купить PRO|подключить PRO/i.test(body),
       services_prices_public:body.includes('6 500')&&body.includes('15 600'),
       public_specialty_software:/Интеграция API|Автоматизация процессов|AI\s*\/\s*Нейросети/.test(body),
       public_rating_field:body.includes('Часовая ставка')||body.includes('Месячная ставка'),
       title_nonempty:document.title.length>0
      };
     }""")
     row.update(data)
    except Exception:
     row["error"]="technical_error"
    out["pages"][label]=row
   out["status"]="ok" if all(v.get("http")==200 for v in out["pages"].values()) else "partial"
except Exception:
 out["status"]="technical_error"
finally:
 if b:
  try:b.close()
  except Exception:out["status"]="technical_error"
 print(json.dumps(out,ensure_ascii=False,sort_keys=True))
