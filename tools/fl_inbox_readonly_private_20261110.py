#!/usr/bin/env python3
"""FL owner inbox read-only snapshot; ONLY for recipient-encrypted transport.
No click/send/account mutation, no session tokens, no external destinations.
"""
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime,timezone
import tempfile,sys,json,re
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
out={"schema":"fl.owner.inbox.private.snapshot.v1","observed_at":datetime.now(timezone.utc).isoformat(),
"owner_verified":False,"read_only":True,"http":None,"status":"not_checked","inbox_url":"",
"inbox_text":"","dialog_links":[],"visible_elements":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-inbox-private-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  r=p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=22000)
  flags=p.evaluate("""()=>({owner:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner_verified"]=bool(r and r.status==200 and flags["owner"] and flags["settings"] and is_fl_url(p.url))
  if out["owner_verified"]:
   r=p.goto("https://www.fl.ru/messages",wait_until="domcontentloaded",timeout=28000)
   p.wait_for_timeout(2200)
   out["http"]=r.status if r else None
   if not is_fl_url(p.url):out["status"]="unexpected_domain"
   else:
    out["inbox_url"]=p.url
    data=p.evaluate("""()=>{
      const text=(document.body?.innerText||'').replace(/\\r/g,'');
      let anchors=Array.from(document.querySelectorAll('a[href]')).map(a=>({
        href:a.href,
        title:(a.innerText||a.getAttribute('title')||'').replace(/\\s+/g,' ').trim().slice(0,130)
      })).filter(a=>(/dialogId=|\/messages|\/messages\//i.test(a.href)||/сообщени|переписк|заказчик|непрочит/i.test(a.title))).slice(0,95);
      let els=Array.from(document.querySelectorAll('[class*="dialog"],[class*="unread"],[class*="message"],[data-dialog-id]'))
        .filter(e=>{let r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.width<1500})
        .slice(0,65).map(e=>({tag:e.tagName,cl:String(e.className||'').slice(0,100),
        id:(e.id||'').slice(0,70),t:(e.innerText||'').trim().slice(0,440)}));
      return{text:text.slice(0,18000),links:anchors,els};
    }""")
    out["inbox_text"]=data["text"]
    out["dialog_links"]=data["links"]
    out["visible_elements"]=data["els"]
    out["status"]="ok"
finally:b.close()
print(json.dumps(out,ensure_ascii=False))
