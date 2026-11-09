#!/usr/bin/env python3
"""Read-only identify exact owner portfolio case IDs and edit-entry controls."""
from pathlib import Path
from urllib.parse import urlsplit
import sys,json,tempfile,re
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
URL="https://www.fl.ru/users/olegendorphine/portfolio/"
out={"schema":"fl.owner.works.edit.preflight.v1","owner":False,"writes":False,"works":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-works-edit-inspect-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=21000)
  s=p.evaluate("""()=>({o:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),s:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner"]=bool(s["o"] and s["s"] and is_fl_url(p.url))
  if out["owner"]:
   r=p.goto(URL,wait_until="domcontentloaded",timeout=22000)
   if r and r.status==200 and is_fl_url(p.url):
    links=p.evaluate("""()=>{
     const a=Array.from(document.querySelectorAll('a[href]')).filter(x=>/\/user\/olegendorphine\/portfolio\/\d+\//.test(new URL(x.href).pathname));
     const r=[];
     for(const x of a) {
       const path=new URL(x.href).pathname;
       if(!r.some(z=>z.path===path))r.push({path,text:(x.innerText||x.parentElement?.innerText||'').trim().slice(0,130)});
     }
     return r.slice(0,12);
    }""")
    for link in links:
     if not re.fullmatch(r"/user/olegendorphine/portfolio/\d+/",link["path"]):continue
     row={"path":link["path"],"listing_text":link["text"]}
     try:
      r=p.goto("https://www.fl.ru"+link["path"],wait_until="domcontentloaded",timeout=21000)
      if not r or r.status!=200 or not is_fl_url(p.url):row["status"]="not_open";out["works"].append(row);continue
      row["status"]="ok"
      row["editor"]=p.evaluate("""()=>{
        const b=Array.from(document.querySelectorAll('a,button,[role=button]')).filter(x=>/редактир|изменить работу|обложку/i.test(x.innerText||x.title||'')).slice(0,15).map(x=>({label:(x.innerText||x.title||'').trim().slice(0,60),tag:x.tagName,href:x.getAttribute('href'),id:x.id,className:String(x.className).slice(0,100)}));
        const files=Array.from(document.querySelectorAll('input[type=file]')).map(x=>({accept:x.accept,id:x.id,name:x.name}));
        return {title:(document.querySelector('h1')?.innerText||'').slice(0,130),buttons:b,files};
      }""")
     except Exception:row["status"]="technical_error"
     out["works"].append(row)
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
