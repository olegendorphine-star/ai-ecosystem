#!/usr/bin/env python3
"""Read-only Freelancehunt browser probe using existing VPS graphical runtime; no FL cookies."""
import json,os,sys,tempfile
from pathlib import Path
from urllib.parse import urlsplit
FH=Path.home()/".freelancehunt-agent"
FL=Path.home()/".fl-agent"
URLS={"home":"https://freelancehunt.com/","editor":"https://freelancehunt.com/my/freelancer","skills":"https://freelancehunt.com/my/skills","login":"https://freelancehunt.com/profile/login"}
def probe():
 report={"schema":"fh.browser.readonly.v1","status":"error","fl_cookies_used":False,"write_actions":False,"pages":{}}
 b=None
 try:
  FH.mkdir(mode=0o700,parents=True,exist_ok=True)
  if FH.is_symlink() or FH.stat().st_uid!=os.getuid():raise RuntimeError("unsafe_dir")
  sys.path.insert(0,str(FL))
  import fl_rootless_owner_desktop as rt
  rt.STATE=FH/"nonexistent-fh-only-storage.json"
  rt.ALLOWED_PAGES={"login":URLS["home"]}
  b=rt.Browser()
  with tempfile.TemporaryDirectory(prefix="fh-browser-probe-",dir=FL) as tmp:
   b.open(Path(tmp))
   p=b.page
   for label,url in URLS.items():
    row={"status":None,"result":"unavailable"}
    try:
     r=p.goto(url,wait_until="domcontentloaded",timeout=22000)
     p.wait_for_timeout(500)
     status=r.status if r else None
     flags=p.evaluate("""() => {
       const t=(document.body?.innerText||'').toLowerCase();
       return {
        blocked:/sorry, you have been blocked|attention required|access denied|cloudflare ray id/.test(t),
        login:!!document.querySelector('input[type="password"]'),
        editor:!!document.querySelector('textarea,[contenteditable="true"]'),
        settings:/профиль|редактировать|специализац|резюме|profile settings/.test(t.slice(0,2500))
       };
     }""")
     host=urlsplit(p.url).hostname
     if host not in ("freelancehunt.com","www.freelancehunt.com"):kind="outside_host"
     elif status in (401,403,429) or flags["blocked"]:kind="blocked"
     elif flags["login"]:kind="login_required"
     elif flags["editor"] and flags["settings"]:kind="editor_visible"
     elif status==200:kind="public_page"
     else:kind="unavailable"
     row={"status":status,"result":kind,"redirected":urlsplit(p.url).path!=urlsplit(url).path}
    except Exception:row["result"]="navigation_error"
    report["pages"][label]=row
   report["status"]="checked"
 except Exception:
  report["status"]="browser_runtime_error"
 finally:
  if b:
   try:b.close()
   except Exception:pass
 return report
if __name__=="__main__":print(json.dumps(probe(),sort_keys=True))
