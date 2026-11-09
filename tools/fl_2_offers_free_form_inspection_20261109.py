#!/usr/bin/env python3
"""Owner-authorized FL free-response form inventory; dry-run, no writes."""
import json,sys,tempfile
from pathlib import Path
root=Path.home()/".fl-agent"
sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
urls=[
("fl005","https://www.fl.ru/projects/5528403/trebuetsya-rabochiy-stsenariy-dlya-ii-dlya-kartochek-tovara-v-gruppe-yuvelirnyie-sergi.html"),
("fl006","https://www.fl.ru/projects/5527732/cozdanie-edinogo-korporativnogo-stilya-portretov-neyrofotosessiya.html")]
out={"schema":"fl.owner.safe_response_inspection.v1","owner_verified":False,"projects":[],"no_post_actions":True}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-offer-inventory-",dir=root) as tmp:
  b.open(Path(tmp))
  page=b.page
  page.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  signs=page.evaluate("""() => ({
    owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
    settings:(document.body?.innerText||'').includes('Основные настройки')
  })""")
  out["owner_verified"]=bool(signs["owner"] and signs["settings"] and is_fl_url(page.url))
  if out["owner_verified"]:
   for label,url in urls:
    item={"id":label}
    try:
     response=page.goto(url,wait_until="domcontentloaded",timeout=20000)
     page.wait_for_timeout(600)
     item["http"]=response.status if response else None
     item["same_url"]=page.url.split("#")[0].split("?")[0]==url
     d=page.evaluate("""() => {
       const t=(document.body?.innerText||'');
       const h=(document.querySelector('h1')?.innerText||'').trim();
       const x=t.indexOf(h);
       const body=t.slice(Math.max(x,0),Math.max(x,0)+4200);
       const forbidden= /исполнитель определён|проект закрыт|заказ закрыт|вы откликнулись|ваш отклик отправлен|отклик уже отправлен/i.test(body);
       const fields=Array.from(document.querySelectorAll('textarea,input,select')).filter(e=>{
         const parent=e.closest('form')||e.closest('[class*="response"],[class*="reply"],[class*="bid"],[class*="offer"]');
         const type=e.getAttribute('type')||'';
         return (parent||['textarea','number'].includes(type)||e.tagName==='TEXTAREA') &&
            !['hidden','password','email'].includes(type);
       }).slice(-28).map(e=>({
         tag:e.tagName.toLowerCase(),type:(e.getAttribute('type')||'').slice(0,35),
         name:(e.name||'').slice(0,90),id:(e.id||'').slice(0,90),
         placeholder:(e.getAttribute('placeholder')||'').slice(0,90),
         aria:(e.getAttribute('aria-label')||'').slice(0,90),required:!!e.required,
         outer:e.outerHTML.slice(0,280).replace(/value="[^"]*"/g,'value="[redacted]"')
       }));
       const forms=Array.from(document.querySelectorAll('form')).slice(-12).map(f=>({
           method:(f.method||'').slice(0,15),
           buttons:Array.from(f.querySelectorAll('button,input[type=submit]')).map(e=>(e.innerText||e.value||'').trim().slice(0,70)).slice(0,8),
           hastextarea:!!f.querySelector('textarea'),
           text:(f.innerText||'').slice(0,180)
       }));
       const btns=Array.from(document.querySelectorAll('button,input[type=submit]')).filter(e=>/отправить отклик/i.test(e.innerText||e.value||'')).map(e=>({
           text:(e.innerText||e.value||'').trim(),disabled:!!e.disabled,
           type:(e.getAttribute('type')||'').slice(0,25),
           outer:e.outerHTML.slice(0,340)
       }));
       return {title:h,free:body.includes('Для всех'),closed:forbidden,
         posted_text:(body.match(/.{0,50}ваш отклик.{0,120}/i)||[])[0]||null,
         fields,forms,buttons:btns};
     }""")
     item["dom"]=d
    except Exception:
     item["error"]="page_navigation_or_dom_error"
    out["projects"].append(item)
finally:
 b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
