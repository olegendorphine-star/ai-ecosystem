#!/usr/bin/env python3
"""Verify exact professional FL headline, selected specialties and public visual profile; no writes."""
from pathlib import Path
import json,sys,tempfile
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,is_fl_url
main="https://www.fl.ru/users/olegendorphine/setup/main/"
urls={
 "specializations":"https://www.fl.ru/users/olegendorphine/setup/specsetup/",
 "profile":"https://www.fl.ru/users/olegendorphine/portfolio/",
 "portfolio_sections":"https://www.fl.ru/users/olegendorphine/setup/portfsetup/"
}
out={"schema":"fl.owner.final.headline.specialization.readonly.v1","owner":False,"no_writes":True,"no_messages":True,"no_payments":True}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-final-headline-read-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  r=p.goto(main,wait_until="domcontentloaded",timeout=22000)
  d=p.evaluate("""()=>({
    user:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
    main:(document.body?.innerText||'').includes('Основные настройки'),
    title:(document.querySelector('input[name=pname]')?.value||'')==='ИИ-ассистенты и автоматизация бизнеса',
    titleLen:(document.querySelector('input[name=pname]')?.value||'').length,
    name:!!document.querySelector('input[name=name]')?.value?.trim(),
    surname:!!document.querySelector('input[name=surname]')?.value?.trim()
  })""")
  out["owner"]=bool(r and r.status==200 and is_fl_url(p.url) and d["user"] and d["main"])
  if out["owner"]:
   out["headline_exact_target"]=d["title"]
   out["headline_length"]=d["titleLen"]
   out["name_set"]=d["name"];out["surname_set"]=d["surname"]
   for name,url in urls.items():
    try:
     r=p.goto(url,wait_until="domcontentloaded",timeout=23000);p.wait_for_timeout(330)
     if not r or r.status!=200 or not is_fl_url(p.url):out[name]={"status":"unavailable"};continue
     out[name]=p.evaluate("""name=>{
      const text=document.body?.innerText||'';
      const desc=(e)=>(e?.innerText||e?.textContent||'').trim().replace(/\\s+/g,' ').slice(0,100);
      return {
       status:"ok",pageTitle:document.title.slice(0,105),
       visibleHeadings:Array.from(document.querySelectorAll('h1,h2,h3')).map(desc).filter(Boolean).slice(0,9),
       selects:Array.from(document.querySelectorAll('select')).map(x=>({name:x.name,selectedText:x.selectedOptions?.[0]?.textContent?.trim()?.slice(0,70),value_present:!!x.value})).slice(0,10),
       checked:Array.from(document.querySelectorAll('input[type=checkbox]:checked')).map(x=>desc(x.labels?.[0]||x.parentElement)).filter(Boolean).slice(0,12),
       inputs:Array.from(document.querySelectorAll('input[type=text]')).filter(x=>x.getBoundingClientRect().width>0).slice(0,10).map(x=>({placeholder:x.placeholder?.slice(0,70),filled:!!x.value,name:x.name})),
       specNames:["AI-агенты","RAG / Базы знаний","AI-автоматизация","Разработка ботов","Интеграция API"].filter(x=>text.includes(x)),
       aboutSales:text.includes("ИИ для реальных задач.")&&text.includes("Опишите задачу"),
       publicHeadline:text.includes("ИИ-ассистенты и автоматизация бизнеса"),
       avatarImages:Array.from(document.querySelectorAll('img')).filter(x=>/avatar|userpic/i.test(String(x.className)+' '+x.src)).length,
       bannerPossible:Array.from(document.querySelectorAll('[class*=cover],[class*=banner]')).some(x=>getComputedStyle(x).backgroundImage!=='none'&&x.getBoundingClientRect().width>600)
      };
     }""",name)
    except Exception:out[name]={"status":"technical_error"}
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
