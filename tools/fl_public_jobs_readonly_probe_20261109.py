#!/usr/bin/env python3
"""One-time FL public job discovery in existing owner browser. No account actions."""
from pathlib import Path
import json,os,sys,tempfile
ROOT=Path.home()/".fl-agent"
sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser
urls=[
("ai","https://www.fl.ru/projects/category/ai-iskusstvenniy-intellekt/"),
("python","https://www.fl.ru/projects/category/programmirovanie/python/"),
("automation","https://www.fl.ru/projects/category/avtomatizaciya-biznesa/"),
]
result={"schema":"fl.public.work.discovery.v1","pages":[],"error":"none","account_writes":False,"passwords_read":False,"cookie_contents_read":False,"paid_actions":False,"captcha_interacted":False}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-work-discovery-",dir=ROOT) as tmp:
  b.open(Path(tmp))
  page=b.page
  for label,url in urls:
   try:
    response=page.goto(url,wait_until="domcontentloaded",timeout=16000)
    cards=page.evaluate("""() => {
      let links=Array.from(document.querySelectorAll('a[href*="/projects/"]'));
      let out=[],seen=new Set();
      for(let a of links){
        let url=new URL(a.href,location.href);
        if(url.hostname!=='www.fl.ru'&&url.hostname!=='fl.ru')continue;
        if(!/^\\/projects\\/\\d+\\/[^/]+\\.html$/.test(url.pathname))continue;
        if(seen.has(url.pathname))continue;
        seen.add(url.pathname);
        let item=a.closest('article,li,[class*="card"],[class*="item"],[class*="project"]')||a.parentElement?.parentElement;
        let summary=(item?.innerText||a.innerText||'').replace(/\\s+/g,' ').slice(0,430);
        let text=(a.innerText||a.getAttribute('title')||'').trim().replace(/\\s+/g,' ').slice(0,160);
        out.push({title:text,url:url.origin+url.pathname,summary:summary,
          free_badge_explicit:/для всех/i.test(summary),
          visible_apply:/Откликнуться/i.test(summary),
          stated_price:((summary.match(/(?:\\d[\\s\\u00a0]*)+\\s*₽/i)||[])[0]||null)});
        if(out.length>=18)break;
      }
      return out;
    }""")
    result["pages"].append({"type":label,"http":response.status if response else None,"items":cards})
   except Exception:
    result["pages"].append({"type":label,"error":"navigate_or_parse_failed","items":[]})
finally:
 b.close()
print(json.dumps(result,ensure_ascii=False,sort_keys=True))
