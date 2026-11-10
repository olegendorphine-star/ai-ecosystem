#!/usr/bin/env python3
"""Check ONLY owner free-bid eligibility on confirmed public FL jobs.
Read-only, no form changes, no bids, no payment or private conversation.
"""
import json,sys,tempfile
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent"
sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url

JOBS={
 "5528747":"https://www.fl.ru/projects/5528747/razrabotka-telegram-bota-s-iskustyiennyim-intelektom--ai---parser-.html",
 "5528764":"https://www.fl.ru/projects/5528764/nezavisimyiy-tehnicheskiy-audit-ii-sistemyi.html",
 "5528712":"https://www.fl.ru/projects/5528712/ai-agent.html",
 "5528587":"https://www.fl.ru/projects/5528587/razrabotchik-dlya-razvrtyivaniya-ai-platformyi.html",
 "5528547":"https://www.fl.ru/projects/5528547/sozdat-ii-agenta.html",
 "5528632":"https://www.fl.ru/projects/5528632/integratsiya-zakazyi-iz-avito-i-vk-v-telegram.html",
 "5528119":"https://www.fl.ru/projects/5528119/razrabotka-veb-servisa-s-ii-assistentom-na-yandex-ai-studio.html"
}
out={"schema":"fl.owner.job.bids.readonly.v1","owner_verified":False,"read_only":True,"bids_sent":0,"payments":0,"messages_read":0,"checked":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-free-jobs-night-",dir=ROOT) as tmp:
  b.open(Path(tmp));p=b.page
  r=p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=21000)
  proof=p.evaluate("""()=>({owner:[...document.querySelectorAll('input')].some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),
                    settings:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner_verified"]=bool(r and r.status==200 and is_fl_url(p.url) and proof["owner"] and proof["settings"])
  if out["owner_verified"]:
   for id,url in JOBS.items():
    row={"id":id,"url":url,"status":"unknown","free_bid_verified":False,"already_replied":False}
    out["checked"].append(row)
    try:
     r=p.goto(url,wait_until="domcontentloaded",timeout=13500)
     if not r or r.status!=200 or not is_fl_url(p.url) or urlsplit(url).path!=urlsplit(p.url).path:
      row["status"]="page_unavailable";continue
     p.wait_for_timeout(450)
     state=p.evaluate("""()=>{const h=(document.querySelector('h1')?.innerText||'').trim();
        const t=document.body?.innerText||'';
        const start=t.indexOf(h),seg=t.slice(Math.max(0,start),Math.max(0,start)+5200);
        const send=[...document.querySelectorAll('#el-submit,button,input[type=submit]')].some(x=>(x.innerText||x.value||'').includes('Отправить отклик'));
        const form=document.querySelector('textarea#el-descr')!==null;
        return {title:h.slice(0,160),free:/Для всех/i.test(seg),
        sent:/Редактировать отклик|Ваш отклик отправлен|Вы уже откликнулись/i.test(seg),
        closed:/Исполнитель определ[её]н|Проект закрыт|Проект заверш[её]н|Снят с публикации/i.test(seg),
        purchase:/Купить отклик|оплатите отклик|недостаточно откликов/i.test(seg),
        form,send,price80:/80\s*₽/.test(seg)};
      }""")
     row.update({"status":"checked","title":state["title"],"free_badge":state["free"],
       "form_visible":state["form"],"send_visible":state["send"],
       "already_replied":state["sent"],"closed":state["closed"],"payment_prompt":state["purchase"],
       "free_bid_verified":bool(state["free"] and state["form"] and state["send"] and not(state["sent"] or state["closed"] or state["purchase"]))})
    except Exception as e:
     row["status"]="technical_"+type(e).__name__
finally:
 try:b.close()
 except Exception:pass
print(json.dumps(out,ensure_ascii=False))
