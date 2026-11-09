#!/usr/bin/env python3
"""FL freelancer owner completeness audit. READ-ONLY. No messages or order actions."""
import json,sys,tempfile
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,is_fl_url
URLS={
 "main":"https://www.fl.ru/users/olegendorphine/setup/main/",
 "about":"https://www.fl.ru/users/olegendorphine/setup/portfolio/",
 "specializations":"https://www.fl.ru/users/olegendorphine/setup/specsetup/",
 "portfolio_sections":"https://www.fl.ru/users/olegendorphine/setup/portfsetup/",
 "public_profile":"https://www.fl.ru/users/olegendorphine/portfolio/",
 "public_info":"https://www.fl.ru/users/olegendorphine/info/",
 "pricing":"https://www.fl.ru/users/olegendorphine/price-list/",
 "services":"https://www.fl.ru/users/olegendorphine/uslugi-freelancera/",
 "service_audit":"https://www.fl.ru/uslugi-freelancera/42901/audit-odnogo-processa-i-karta-ii-avtomatizacii.html",
 "service_tz":"https://www.fl.ru/uslugi-freelancera/42902/razrabotayu-tz-na-personalnogo-ii-assistenta.html",
}
out={"schema":"fl.owner.final.gaps.readonly.v1","owner":False,"writes":False,"payments":False,"messages":False,"pages":{}}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-final-gaps-readonly-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  r=p.goto(URLS["main"],wait_until="domcontentloaded",timeout=23000)
  auth=p.evaluate("""()=>({owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner"]=bool(r and r.status==200 and is_fl_url(p.url) and auth["owner"] and auth["settings"])
  if out["owner"]:
   for label,url in URLS.items():
    row={}
    try:
     r=p.goto(url,wait_until="domcontentloaded",timeout=24000)
     p.wait_for_timeout(330)
     row["status"]="ok" if r and r.status==200 and is_fl_url(p.url) and urlsplit(p.url).path==urlsplit(url).path else "unexpected_page"
     if row["status"]=="ok":
      data=p.evaluate("""kind=>{
       const t=(document.body?.innerText||'');
       const a=s=>t.includes(s);
       const v=(s)=>document.querySelector(s);
       const cover=v('button')?Array.from(document.querySelectorAll('button')).filter(e=>(e.innerText||'').includes('Загрузить обложку для ПК')).length:0;
       const fields=Array.from(document.querySelectorAll('input,textarea,select')).filter(e=>e.name&&e.type!=='hidden'&&e.type!=='password'&&e.type!=='file'&&e.getBoundingClientRect().width>0);
       const opts=Array.from(document.querySelectorAll('input[type=checkbox]')).filter(x=>x.checked).map(x=>((x.labels?.[0]?.innerText||x.parentElement?.innerText||'').trim().replace(/\\s+/g,' ').slice(0,64))).filter(Boolean).slice(0,28);
       const list=Array.from(document.querySelectorAll('a,button,[role=button]')).filter(x=>/редактир|заменить изображение|сменить обложку|на проверке/i.test((x.innerText||'')+' '+(x.title||''))).slice(0,14).map(x=>({text:(x.innerText||x.title||'').trim().slice(0,60),tag:x.tagName}));
       const noPersonal=fields.filter(e=>/^(name|surname|pname|exp|cost_hour|cost_month|ab_text)$/.test(e.name)).map(x=>({field:x.name,present:!!x.value?.trim(),length:(x.value||'').length}));
       return {kind,title:(document.title||'').slice(0,110),
        h1:(document.querySelector('h1')?.innerText||'').trim().slice(0,85),
        owner_profile_header_field:(v('input[name=pname]')?.value||'').trim().length>0,
        new_about_copy:((v('textarea[name=ab_text]')?.value||t).includes('ИИ для реальных задач.')),
        has_sales_cta:((v('textarea[name=ab_text]')?.value||t).includes('Опишите задачу')),
        has_stated_prices:a('30 000 ₽')&&a('150 000 ₽'),
        portfolio_count:['Персональный ИИ-Штаб: память, документы и контроль','Автономный браузер на VPS и контроль сессий','ИИ-документооборот: связи, анализ и полезные сигналы'].filter(a).length,
        prices_count:['Аудит процесса и карта ИИ-автоматизации','ТЗ на персонального ИИ-ассистента','Персональный ИИ-ассистент с памятью и API'].filter(a).length,
        review_labels:(t.match(/На проверке/g)||[]).length,
        service_price_visible:a('6 500')||a('15 600'),
        service_edit_controls:list,
        profile_cover_control:cover>0,
        visible_fields:noPersonal,
        selected_checkboxes:opts,
        checkbox_total:document.querySelectorAll('input[type=checkbox]').length,
        section_count:document.querySelectorAll('input[name="prof[]"]:checked').length,
        has_payment_prompt:/Купить PRO|Купить размещение в каталоге/.test(t),
        selected_specialization_count:opts.length
       };
      }""",label)
      row["view"]=data
    except Exception as e:
     row["status"]="timeout" if "timeout" in str(e).lower() else "technical_error"
    out["pages"][label]=row
finally:
 b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
