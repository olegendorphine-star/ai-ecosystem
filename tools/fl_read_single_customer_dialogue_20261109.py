#!/usr/bin/env python3
"""Read the exact FL customer dialogue via saved owner session. No account writes."""
from pathlib import Path
from urllib.parse import urlsplit
import tempfile,sys,json,re
ROOT=Path.home()/".fl-agent"
sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
DEST="https://www.fl.ru/messages?dialogId=75953631&dialogType=offer"
o={"schema":"fl.single.message.read.v1","owner_verified":False,"dialog":75953631,"read_only":True,"message_found":False,"dialogue_excerpt":"","http":None,"status":"not_checked"}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-owner-msg-read-",dir=ROOT) as runpath:
  b.open(Path(runpath))
  p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=20000)
  owner=p.evaluate("""() => ({
    settings: (document.body?.innerText||'').includes('Основные настройки'),
    owner: Array.from(document.querySelectorAll('input')).some(
      e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com')})""")
  o["owner_verified"]=owner["settings"] and owner["owner"] and is_fl_url(p.url)
  if o["owner_verified"]:
   resp=p.goto(DEST,wait_until="domcontentloaded",timeout=25000)
   p.wait_for_timeout(1800)
   o["http"]=resp.status if resp else None
   host=urlsplit(p.url)
   if host.scheme!="https" or host.hostname not in ("fl.ru","www.fl.ru"):
    o["status"]="unexpected_domain"
   else:
    data=p.evaluate("""() => {
      const text=(document.body?.innerText||'').replace(/\\r/g,'');
      const patterns=['Что в вашем', 'Важно, чтобы помощник', 'Здравствуйте. Важно'];
      let ix=-1;
      for(const phrase of patterns){ix=text.indexOf(phrase);if(ix>=0)break;}
      if(ix<0)return {found:false,body_text_length:text.length,window:text.slice(0,3500)};
      return {found:true,body_text_length:text.length,window:text.slice(Math.max(0,ix-300),ix+4900)};
    }""")
    o["message_found"]=bool(data.get("found"))
    excerpt=data.get("window","")
    excerpt=re.sub(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}","[EMAIL]",excerpt)
    excerpt=re.sub(r"(?:\\+?7|8)[\\s()\\-]*\\d[\\d\\s()\\-]{9,}","[PHONE]",excerpt)
    o["dialogue_excerpt"]=excerpt[:5200]
    o["status"]="ok" if o["message_found"] else "message_not_found"
finally:
 b.close()
print(json.dumps(o,ensure_ascii=False))
