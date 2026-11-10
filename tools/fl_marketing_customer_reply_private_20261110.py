#!/usr/bin/env python3
"""Read only the owner's recent FL marketing customer chat. Private encrypted CI output."""
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime,timezone
import tempfile,sys,json,re
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
out={"schema":"fl.owner.marketing.private.chat.v1","observed_at":datetime.now(timezone.utc).isoformat(),
"owner_verified":False,"read_only":True,"http":None,"status":"not_checked","chat_url":"",
"chat_text":"","links":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-marketing-chat-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  res=p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=22000)
  flags=p.evaluate("""()=>({owner:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner_verified"]=bool(res and res.status==200 and flags["owner"] and flags["settings"] and is_fl_url(p.url))
  if out["owner_verified"]:
   r=p.goto("https://www.fl.ru/messages",wait_until="domcontentloaded",timeout=26000)
   p.wait_for_timeout(1300)
   out["http"]=r.status if r else None
   if not is_fl_url(p.url):out["status"]="unexpected_domain"
   else:
    try:
     loc=p.get_by_text("Ищу начинающего маркетолога в AI-стартап",exact=False).first
     loc.click(timeout=13000)
     p.wait_for_timeout(2200)
     if not is_fl_url(p.url):out["status"]="unexpected_chat_domain"
     else:
      out["chat_url"]=p.url
      d=p.evaluate("""()=>{
        let t=(document.body?.innerText||'').replace(/\\r/g,'');
        let links=[...document.querySelectorAll('a[href]')].map(a=>({
         href:a.href,txt:(a.innerText||'').trim().slice(0,120)}))
         .filter(a=>/projects\\/|messages|users\\//.test(a.href)).slice(0,65);
        return {text:t.slice(0,18000),links};
      }""")
      out["chat_text"]=d["text"]
      out["links"]=d["links"]
      out["status"]="opened"
    except Exception:out["status"]="marketing_dialogue_not_opened"
finally:b.close()
print(json.dumps(out,ensure_ascii=False))
