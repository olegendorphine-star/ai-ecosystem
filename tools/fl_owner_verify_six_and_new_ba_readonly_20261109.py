#!/usr/bin/env python3
"""Read-only confirmation of six owner-reported bids plus one NEW candidate.
Never submits, edits, or reads customer correspondence; no passwords or cookies in output.
"""
import sys,json,tempfile
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
SENT={
"5527458":"https://www.fl.ru/projects/5527458/ai-agent-dlya-avtomaticheskogo-soprovojdeniya-stroitelnyih-dogovorov.html",
"5528049":"https://www.fl.ru/projects/5528049/integratsiya-api-konturlogistika-etrn--bot-v-max--google-tablitsyi.html",
"5528568":"https://www.fl.ru/projects/5528568/razrabotka-ai-sistemyi-na-n8n-dlya-ozon-wildberries-i-yandeks-marketa-pod-klyuch.html",
"5528574":"https://www.fl.ru/projects/5528574/razrabotka-kastomnoy-crm-i-mobilnogo-prilojeniya-dlya-servisnogo-tsentra-s-integratsiey-ii-openai-api.html",
"5527838":"https://www.fl.ru/projects/5527838/nastroit-mozgi-ii-video-konveeru-promt-injeneriya-moushn-dizayner-programmist-phyton-.html",
"5528616":"https://www.fl.ru/projects/5528616/ischu-nachinayuschego-marketologa-v-ai-startap-.html"}
CANDIDATES={
"5528567":"https://www.fl.ru/projects/5528567/biznes-analitik-dlya-podgotovki-tz-na-kartu-protsessov-s-golosovyim-ii.html"}
out={"schema":"fl.owner.readonly.verify.recent.v1","at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
"owner_verified":False,"read_only":True,"writes":False,"paid_actions":False,"captcha_interacted":False,"sent":[],"candidate":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-verification-20261109-",dir=ROOT) as tmp:
  b.open(Path(tmp));p=b.page
  response=p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=24000)
  signs=p.evaluate("""()=>({owner:Array.from(document.querySelectorAll('input')).some(i=>(i.value||'').toLowerCase().trim()==='olegendorphine@gmail.com'),settings:(document.body?.innerText||'').includes('Основные настройки'),login:!!document.querySelector('form[action*="/account/login"]')})""")
  out["owner_verified"]=bool(response and response.status==200 and is_fl_url(p.url) and signs["owner"] and signs["settings"] and not signs["login"])
  if out["owner_verified"]:
   for kind,jobs in [("sent",SENT),("candidate",CANDIDATES)]:
    for job_id,url in jobs.items():
     item={"id":job_id,"url":url,"http":None,"owner_reply_visible":False,
       "send_form_present":False,"free":False,"unavailable":False,"status":"error"}
     out[kind].append(item)
     try:
      response=p.goto(url,wait_until="domcontentloaded",timeout=20000)
      item["http"]=response.status if response else None
      if not response or response.status!=200 or not is_fl_url(p.url) or urlsplit(url).path!=urlsplit(p.url).path:
       item["status"]="wrong_url_or_http";continue
      p.wait_for_timeout(180)
      d=p.evaluate("""()=>{let h=(document.querySelector('h1')?.innerText||'').trim(),t=document.body?.innerText||'',
       i=t.indexOf(h),v=t.slice(Math.max(i,0),Math.max(i,0)+6300);
       return {h:h.slice(0,170),edit:/Редактировать отклик|Изменить отклик|Редактировать предложение/i.test(v),
       posted:/ваш отклик отправлен|вы откликнулись|отклик уже отправлен/i.test(v),
       free:/Для всех/i.test(v),send:document.querySelector('#el-submit')?.innerText?.trim()==='Отправить отклик',
       form:!!document.querySelector('textarea#el-descr'),
       closed:/исполнитель определ[её]н|проект закрыт|проект заверш[её]н|снят с публикации/i.test(v),
       paid:/Купить 1 отклик|Купить отклики|оплатите отклик|недостаточно откликов/i.test(v),
       description:v.slice(0,kind==='candidate'?1000:170)}}""")
      item.update({"title":d["h"],"owner_reply_visible":bool(d["edit"] or d["posted"]),
        "send_form_present":bool(d["send"] and d["form"]),"free":bool(d["free"]),
        "unavailable":bool(d["closed"] or d["paid"]),"status":"checked"})
      if kind=="candidate":item["description"]=d["description"]
     except Exception:item["status"]="navigation_or_parse_failed"
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
