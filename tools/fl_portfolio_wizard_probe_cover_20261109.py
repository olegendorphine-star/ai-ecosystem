#!/usr/bin/env python3
"""Owner-only portfolio wizard read-only form inspection, with local generated cover."""
import tempfile,sys,json,html
from pathlib import Path
root=Path.home()/".fl-agent";sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
OUT={"schema":"fl.portfolio.wizard.probe.v1","owner":False,"published":False,"stages":[]}
def cover(ctx,path):
 page=ctx.new_page()
 page.set_viewport_size({"width":900,"height":900})
 svg='''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="900" viewBox="0 0 900 900">
 <defs><linearGradient id="b" x2="1" y2="1"><stop stop-color="#081a36"/><stop offset="1" stop-color="#10345a"/></linearGradient><linearGradient id="g"><stop stop-color="#16e1c2"/><stop offset="1" stop-color="#4da6ff"/></linearGradient></defs>
 <rect width="900" height="900" fill="url(#b)"/><circle cx="700" cy="280" r="270" fill="#135e8a" opacity=".25"/>
 <rect x="80" y="95" width="145" height="9" rx="4" fill="#00d7c5"/>
 <text x="80" y="210" font-family="DejaVu Sans,Arial" font-size="62" font-weight="bold" fill="#f6fbff">ПЕРСОНАЛЬНЫЙ</text>
 <text x="80" y="290" font-family="DejaVu Sans,Arial" font-size="68" font-weight="bold" fill="url(#g)">ИИ-ШТАБ</text>
 <text x="80" y="362" font-family="DejaVu Sans,Arial" font-size="29" fill="#b7d3ed">Память · Документы · Контроль</text>
 <g stroke="#57d3ee" stroke-width="5" fill="none"><rect x="215" y="500" width="480" height="190" rx="22"/><rect x="277" y="540" width="100" height="74" rx="12"/><rect x="515" y="540" width="100" height="74" rx="12"/>
 <path d="M377 577 H515 M445 577 V480 M445 690 V743"/><circle cx="445" cy="472" r="17" fill="#22dbc6"/><circle cx="445" cy="751" r="17" fill="#22dbc6"/></g>
 <text x="80" y="850" font-family="DejaVu Sans,Arial" font-size="23" fill="#9ebed6">МОДЕЛЬ-НЕЗАВИСИМАЯ АРХИТЕКТУРА</text></svg>'''
 page.set_content('<html><body style="margin:0;background:#081a36">'+svg+'</body></html>',wait_until="load")
 page.screenshot(path=str(path),animations="disabled",timeout=17000)
 page.close()
def fields(page):
 return page.evaluate("""()=>{
   const v=e=>(e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,85);
   const t=document.body?.innerText||'';
   return {dialogText:t.slice(Math.max(t.lastIndexOf('Добавление примера работы'),0)).slice(0,1900),
    fields:Array.from(document.querySelectorAll('input,select,textarea,[contenteditable=true]')).filter(e=>e.getBoundingClientRect().width>0).slice(-30).map(e=>({
      tag:e.tagName,id:e.id||'',name:e.name||'',type:e.type||'',placeholder:(e.getAttribute('placeholder')||'').slice(0,110),
      accept:e.accept||null,required:e.required||false
    })),
    files:Array.from(document.querySelectorAll('input[type=file]')).map(e=>({id:e.id||'',name:e.name||'',accept:e.accept||'',multiple:e.multiple,required:e.required,outer:e.outerHTML.slice(0,230)})),
    buttons:Array.from(document.querySelectorAll('button')).filter(e=>e.getBoundingClientRect().width>0).map(v).filter(Boolean).slice(-20)
   };
 }""")
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-portf-probe-",dir=root) as temp:
  b.open(Path(temp));p=b.page
  try:p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=21000)
  except Exception:p.goto(ALLOWED_PAGES["settings"],wait_until="commit",timeout=18000);p.wait_for_timeout(1600)
  sig=p.evaluate("""()=>({a:(document.body?.innerText||'').includes('Основные настройки'),b:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com')})""")
  OUT["owner"]=bool(sig["a"] and sig["b"] and is_fl_url(p.url))
  if OUT["owner"]:
   p.goto("https://www.fl.ru/users/olegendorphine/portfolio/",wait_until="domcontentloaded",timeout=22000)
   p.locator('button[data-id="fl-add-portfolio-button"]').first.click(timeout=7000)
   p.wait_for_timeout(350)
   OUT["stages"].append({"step":1,"detail":fields(p)})
   cover_file=Path(temp)/"cover.png";cover(b.context,cover_file)
   p.locator("#ui-input-example-name-input").fill("Персональный ИИ-Штаб — модель-независимая система")
   fileinputs=p.locator('input[type=file]')
   OUT["file_count"]=fileinputs.count()
   if fileinputs.count()>0:
    fileinputs.first.set_input_files(str(cover_file),timeout=12000)
    p.wait_for_timeout(800)
   nextbtn=p.get_by_role("button",name="Продолжить",exact=True)
   nextbtn.click(timeout=8500);p.wait_for_timeout(500)
   OUT["stages"].append({"step":2,"detail":fields(p)})
   # Try to fill only a recognized description field; do not publish.
   area=p.locator("textarea").filter(visible=True)
   OUT["textarea_count"]=area.count()
   if area.count()==1:
    area.fill("Собственный действующий проект: персональная ИИ-экосистема с внешней памятью, документами, API, серверными инструментами и контролем задач. Архитектура не зависит от одной модели. Система используется на реальных задачах; пример обезличен.")
    p.get_by_role("button",name="Продолжить",exact=True).click(timeout=8500)
    p.wait_for_timeout(450)
    OUT["stages"].append({"step":3,"detail":fields(p)})
finally:b.close()
print(json.dumps(OUT,ensure_ascii=False,sort_keys=True))
