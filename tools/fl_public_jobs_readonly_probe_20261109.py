#!/usr/bin/env python3
"""One-time FL public job discovery in existing owner browser. No account actions."""
from pathlib import Path
import json,os,sys,tempfile
ROOT=Path.home()/".fl-agent"
sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser
urls=[
("design","https://www.fl.ru/projects/category/dizajn/"),
("marketplace","https://www.fl.ru/projects/category/marketplace-management/"),
("texts_more","https://www.fl.ru/projects/category/teksty/page-1/"),
("ai","https://www.fl.ru/projects/category/ai-iskusstvenniy-intellekt/"),
("sites","https://www.fl.ru/projects/category/saity/"),
]
result={"schema":"fl.public.work.discovery.v1","details":[],"pages":[],"error":"none","account_writes":False,"passwords_read":False,"cookie_contents_read":False,"paid_actions":False,"captcha_interacted":False}
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
        if(out.length>=28)break;
      }
      return out;
    }""")
    result["pages"].append({"type":label,"http":response.status if response else None,"items":cards})
   except Exception:
    result["pages"].append({"type":label,"error":"navigate_or_parse_failed","items":[]})

  details=[]
  for kind,url in details:
   try:
    response=page.goto(url,wait_until="domcontentloaded",timeout=18000)
    page.wait_for_timeout(350)
    detail=page.evaluate("""() => {
      const body=(document.body?.innerText||'').replace(/\\r/g,'');
      const h=document.querySelector('h1');
      const name=(h?.innerText||'').trim().slice(0,200);
      const at=body.indexOf(name);
      const segment=body.slice(Math.max(0,at), Math.max(0,at)+6800);
      const free=/для всех/i.test(segment);
      const banned=/снят[а]? с публикации|проект заверш[её]н|исполнитель определ[её]н/i.test(segment);
      const html=Array.from(document.querySelectorAll('button,a')).map(x=>(x.innerText||'').trim()).filter(x=>/отклик|ответить|снять с публикации|для всех/i.test(x)).slice(0,12);
      const bounded=segment.replace(/[a-z0-9._%+-]+@[a-z0-9.-]+\\.[a-z]{2,}/ig,'[email hidden]');
      return {title:name,excerpt:bounded,free_text_present:free,closed_text_present:banned,cta_labels:html};
    }""")
    result["details"].append({"type":kind,"url":url,"http":response.status if response else None,"detail":detail})
   except Exception:
    result["details"].append({"type":kind,"error":"navigate_or_parse_failed"})
finally:
 b.close()
print(json.dumps(result,ensure_ascii=False,sort_keys=True))
