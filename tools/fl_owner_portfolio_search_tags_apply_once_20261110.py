#!/usr/bin/env python3
"""One-time owner directed search keyword additions to THREE existing FL portfolio sections.
No portfolio work edits, no payments, no account, password, message or bid actions.
"""
import json,os,sys,re,tempfile,time
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,is_fl_url
SETTINGS="https://www.fl.ru/users/olegendorphine/setup/main/"
PORTFOLIO="https://www.fl.ru/users/olegendorphine/portfolio/"
SECTIONS=[
 (2,"803","AI-агенты","ИИ-агенты, ИИ-ассистенты, автоматизация задач, персональный ИИ-Штаб, API-интеграции, Telegram, Python, память ИИ"),
 (3,"805","RAG / Базы знаний","RAG, базы знаний, ИИ-поиск по документам, анализ файлов, Google Drive, PDF, документооборот, поиск информации, ИИ-ассистент"),
 (4,"810","AI-автоматизация","AI-автоматизация, автоматизация бизнеса, API, Python, VPS, Telegram, Google Таблицы, GitHub Actions, мониторинг процессов, контроль задач")
]
out={"schema":"fl.owner.portfolio.search.tags.write.v1","owner":False,"writes":[],"paid":False,
 "messages":False,"bids":False,"security":False,"identity_changed":False}
def own_file(path,content):
 fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"w",encoding="utf-8") as f:
  f.write(content);f.flush();os.fsync(f.fileno())
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-owner-portfolio-tag-apply-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  r=p.goto(SETTINGS,wait_until="domcontentloaded",timeout=25000)
  signs=p.evaluate("""()=>({
    owner:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
    settings:(document.body?.innerText||'').includes('Основные настройки')
  })""")
  out["owner"]=bool(r and r.status==200 and is_fl_url(p.url) and urlsplit(p.url).path==urlsplit(SETTINGS).path and signs["owner"] and signs["settings"])
  if out["owner"]:
   for index,identifier,name,target in SECTIONS:
    v={"section":name,"status":"not_started","clicked":False,"verified":False}
    out["writes"].append(v)
    marker=ROOT/("fl_owner_search_tags_"+identifier+"_20261110.intent")
    backup=ROOT/("fl_owner_search_tags_"+identifier+"_20261110.backup.txt")
    try:
     r=p.goto(PORTFOLIO,wait_until="domcontentloaded",timeout=25000)
     if not r or r.status!=200 or not is_fl_url(p.url) or urlsplit(p.url).path!=urlsplit(PORTFOLIO).path:
      v["status"]="portfolio_not_available";break
     node=p.locator("a.admn").nth(index)
     section=node.evaluate("(e)=>e.parentElement?.parentElement?.innerText||''")
     params=node.get_attribute("data-function-params") or ""
     digits=re.findall(r"\\d{1,8}",params)
     if name not in section or len(digits)<2 or digits[-1]!=identifier:
      v["status"]="wrong_category_guard";break
     node.click(timeout=9000)
     p.wait_for_timeout(750)
     field=p.locator('textarea[name="user_keys"]')
     if field.count()!=1 or not field.is_visible():
      v["status"]="keyword_field_missing";break
     dialog=field.evaluate("(e)=>e.closest('.b-shadow,.b-popup,.modal,[role=dialog]')?.innerText||''")
     if name not in dialog:
      v["status"]="editor_category_mismatch";break
     old=field.input_value().strip()
     if old==target:
      v["status"]="already_desired";v["verified"]=True;continue
     if old or marker.exists() or marker.is_symlink() or backup.exists() or backup.is_symlink():
      v["status"]="existing_keywords_or_previous_attempt_stop";break
     save=p.locator('a.b-button_flat_green:visible').filter(has_text="Сохранить изменения")
     if save.count()!=1:
      v["status"]="save_not_unique";break
     own_file(backup,old)
     field.fill(target,timeout=6000)
     if field.input_value()!=target:
      v["status"]="pre_save_mismatch";break
     own_file(marker,json.dumps({"section":identifier,"time":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}))
     save.click(timeout=15000)
     v["clicked"]=True
     p.wait_for_timeout(600)
     r=p.goto(PORTFOLIO,wait_until="domcontentloaded",timeout=24000)
     if not r or r.status!=200 or not is_fl_url(p.url):
      v["status"]="after_save_navigation_uncertain";break
     node=p.locator("a.admn").nth(index)
     node.click(timeout=9000)
     p.wait_for_timeout(450)
     fresh=p.locator('textarea[name="user_keys"]')
     v["verified"]=bool(fresh.count()==1 and fresh.input_value().strip()==target)
     v["status"]="saved_verified" if v["verified"] else "saved_but_readback_uncertain"
     if not v["verified"]:break
    except Exception:
     v["status"]="technical_error_do_not_retry" if marker.exists() else "technical_error_before_write"
     break
finally:
 b.close()
 print(json.dumps(out,ensure_ascii=False,sort_keys=True))
