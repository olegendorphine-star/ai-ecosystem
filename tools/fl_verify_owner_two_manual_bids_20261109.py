#!/usr/bin/env python3
"""Read-only confirmation of two owner-reported manually sent offers, no site writes."""
import json,sys,tempfile
from pathlib import Path
root=Path.home()/".fl-agent"
sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
targets=[
 ("5528431","https://www.fl.ru/projects/5528431/senior-ai-injener-personalnyiy-assistent-s-brauzerom-i-telegram-na-vps.html"),
 ("5528498","https://www.fl.ru/projects/5528498/avtomatizatsiya-zakaz-naryadov-n8n--ocr--ii--google-sheets.html")
]
out={"schema":"fl.owner.user.sent.verify.v1","verified_owner":False,"sites":[],"account_writes":False,"secrets_read":False,"cookies_exfiltrated":False}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-owner-manual-bid-check-",dir=root) as tmp:
  b.open(Path(tmp))
  page=b.page
  page.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  p=page.evaluate("""() => ({
    owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
    settings:(document.body?.innerText||'').includes('Основные настройки')
  })""")
  out["verified_owner"]=bool(p["owner"] and p["settings"] and is_fl_url(page.url))
  if out["verified_owner"]:
   for identifier,url in targets:
    item={"id":identifier,"marker_exists":(root/("fl_owner_bid_attempt_"+identifier+"_20261109.json")).exists(),"navigation":"not_started"}
    out["sites"].append(item)
    try:
     r=page.goto(url,wait_until="domcontentloaded",timeout=24000)
     page.wait_for_timeout(850)
     x=page.evaluate("""() => {
       const txt=document.body?.innerText||'';
       const title=document.querySelector('h1')?.innerText||'';
       const idx=txt.indexOf(title);
       const segment=txt.slice(Math.max(idx,0),Math.max(idx,0)+6500);
       const m=(q)=>new RegExp(q,'i').test(segment);
       const form=document.querySelector('#el-descr');
       const bid=document.querySelector('#el-submit');
       return {
         title_present:!!title,
         free:m('для всех'),
         owner_offer_header:m('ваш отклик'),
         submitted_statement:m('вы уже откликнулись|отклик отправлен|вы откликнулись|ваш отклик на проект|отклик успешно'),
         own_edit_action:m('изменить отклик|редактировать отклик|удалить отклик|снять отклик'),
         text_form_exists:!!form,
         text_form_visible:!!form && form.getBoundingClientRect().height>0,
         text_form_has_value:!!form?.value,
         submit_exists:!!bid,
         submit_visible:!!bid && bid.getBoundingClientRect().height>0,
         form_status_text:segment.match(/.{0,70}(ваш отклик|отправить отклик|редактировать отклик|вы уже откликнулись).{0,85}/gi)?.slice(0,7).map(x=>x.trim().replace(/[\\w.+-]+@[\\w.-]+/g,'[email]'))||[],
         captcha:!!document.querySelector('[class*="smartcaptcha"],[id*="smartcaptcha"]'),
         fullurlpath:location.pathname,
         onfl:location.protocol==='https:'&&['fl.ru','www.fl.ru'].includes(location.hostname)
       }
     }""")
     item["navigation"]="ok"
     item["http"]=r.status if r else None
     item["view"]=x
    except Exception as exc:
     msg=str(exc).lower()
     item["navigation"]="timeout" if "timeout" in msg else "error"
finally:
 b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
