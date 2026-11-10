#!/usr/bin/env python3
"""Read ONLY the owner's FL.ru service 43343 moderation details; no writes."""
import json,re,sys,tempfile
from pathlib import Path

ROOT=Path.home()/".fl-agent"
OWNER_SETTINGS="https://www.fl.ru/users/olegendorphine/setup/main/"
OWNER_SERVICES="https://www.fl.ru/users/olegendorphine/uslugi-freelancera/"
TARGET_TITLE="Настрою учёт заявок и уведомления в Telegram"
def compact(s,n=2200):
    s=re.sub(r"[\r\n\t]+"," ",str(s or ""))
    s=re.sub(r"\s{2,}"," ",s).strip()
    s=re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}","[email redacted]",s)
    s=re.sub(r"(?<!\d)\+?\d[\d ()-]{8,}\d","[number redacted]",s)
    return s[:n]
out={"schema":"fl.service.43343.moderation.readonly.v1","verified_owner":False,
     "status":"unknown","target_present":False,"review_excerpt":"","editor_excerpt":"",
     "moderation_excerpt":"","current_description":"","edit_page_opened":False,
     "write_actions":0,"messages_opened":0}
browser=None
try:
    sys.path.insert(0,str(ROOT))
    from fl_rootless_owner_desktop import Browser,is_fl_url
    browser=Browser()
    with tempfile.TemporaryDirectory(prefix="fl-mod-43343-",dir=ROOT) as tmp:
        browser.open(Path(tmp));page=browser.page
        r=page.goto(OWNER_SETTINGS,wait_until="domcontentloaded",timeout=25000)
        proof=page.evaluate("""() => ({
            own:[...document.querySelectorAll('input')].some(e=>(e.value||'').toLowerCase().trim()==='olegendorphine@gmail.com'),
            settings:(document.body?.innerText||'').includes('Основные настройки')
        })""")
        if not(r and r.status==200 and is_fl_url(page.url) and proof["own"] and proof["settings"]):
            out["status"]="owner_unverified"
        else:
            out["verified_owner"]=True
            r=page.goto(OWNER_SERVICES,wait_until="domcontentloaded",timeout=25000)
            if not(r and r.status==200 and is_fl_url(page.url)):
                out["status"]="owner_services_unavailable"
            else:
                page.wait_for_timeout(900)
                capture=page.evaluate("""(title) => {
                  const text=document.body?.innerText||'';
                  const exact=[...document.querySelectorAll('a,span,strong,h1,h2,h3,h4,p')]
                     .filter(e=>(e.textContent||'').trim()===title).slice(0,4);
                  const node=exact[0]||[...document.querySelectorAll('a')].find(e=>(e.href||'').includes('43343'));
                  const list=[];
                  for(let p=node,i=0;p&&i<6;p=p.parentElement,i++){
                     const t=(p.innerText||'').trim();
                     if(t.length>=title.length&&t.length<4500)list.push(t);
                  }
                  const linkrows=[...document.querySelectorAll('a[href]')].filter(e=>
                     (e.href||'').includes('43343')||(e.innerText||'').includes(title))
                     .slice(0,12).map(e=>({text:(e.innerText||'').trim().slice(0,100),href:e.href}));
                  return {present:!!node,rows:list,links:linkrows,
                          noTargetNotice:/На проверке|Отредактируйте|Не опубликовано|Отклонен|На доработке/i.test(text)}
                }""",TARGET_TITLE)
                out["target_present"]=bool(capture["present"])
                out["review_excerpt"]=compact(" | ".join(capture["rows"][:3]),2500)
                out["service_links"]=[{"text":compact(x.get("text"),70),"href":x.get("href")}
                                    for x in capture["links"] if str(x.get("href","")).startswith("https://www.fl.ru/")][:8]
                candidate=None
                for item in capture["links"]:
                    href=str(item.get("href") or "")
                    if "43343" in href and href.startswith("https://www.fl.ru/") and href!=page.url:
                        candidate=href;break
                if candidate:
                    r=page.goto(candidate,wait_until="domcontentloaded",timeout=20000)
                    if r and r.status==200 and is_fl_url(page.url):
                        out["edit_page_opened"]=True
                        details=page.evaluate("""() => {
                           const t=document.body?.innerText||'';
                           const fields=[...document.querySelectorAll('textarea,input')].filter(e=>e.value&&e.value.length>100).map(e=>e.value.slice(0,3500));
                           const patterns=/модератор|отредактир|рекомендац|замечани|ошибк|отклон|доработ|описани/i;
                           const lines=t.split(/\\n/).map(e=>e.trim()).filter(Boolean);
                           const indexes=lines.map((e,i)=>patterns.test(e)?i:-1).filter(i=>i>=0);
                           const blocks=indexes.slice(0,10).map(i=>lines.slice(Math.max(0,i-1),Math.min(lines.length,i+4)).join(' | '));
                           return {top:t.slice(0,2500),blocks,fields};
                        }""")
                        out["editor_excerpt"]=compact(details.get("top"),1800)
                        out["moderation_excerpt"]=compact(" || ".join(details.get("blocks",[])[:7]),3000)
                        out["current_description"]=compact(details.get("fields",[""])[0] if details.get("fields") else "",3000)
                        try:
                            menu=page.get_by_text("Управление услугой",exact=True).first
                            if menu.count()==1 and menu.is_visible():
                                menu.click(timeout=3000)
                                page.wait_for_timeout(250)
                            controls=page.evaluate("""() => [...document.querySelectorAll('a,button,[role=menuitem]')]
                              .map(e=>({text:(e.innerText||e.getAttribute('aria-label')||'').trim().slice(0,140),
                                       href:e.href||'',tag:e.tagName}))
                              .filter(e=>/редактир|изменить|отклон|управлен|доработ/i.test(e.text)||/edit/i.test(e.href))
                              .slice(0,20)""")
                            out["management_controls"]=controls
                            out["wizard_fields"]=page.evaluate("""() => ({
                                fields:['#ui-input-example-name-input','#ui-textarea-description-input',
                                        '#ui-textarea-emp_requirement-input','#ui-input-emp_result-input']
                                       .map(id=>({id,present:document.querySelector(id)!=null,
                                                  value:(document.querySelector(id)?.value||'').slice(0,3500)})),
                                progress:[...document.querySelectorAll('button')].filter(b=>(b.innerText||'').trim()==='Продолжить')
                                          .map(b=>({disabled:b.disabled,visible:b.getBoundingClientRect().width>0})),
                                pageUrl:location.href
                            })""")

                            try:
                                first=out["wizard_fields"]["fields"]
                                if (first[0]["value"]==TARGET_TITLE and
                                    "согласуем дополнительно" in first[1]["value"] and
                                    "Отклонена" in page.locator("body").inner_text()[:1800]):
                                    progress=[]
                                    for step in ("pricing","category","cover"):
                                        btn=page.get_by_role("button",name="Продолжить",exact=True)
                                        if btn.count()!=1 or not btn.is_enabled():
                                            progress.append({"step":step,"state":"continue_unavailable"})
                                            break
                                        btn.click(timeout=7000)
                                        page.wait_for_timeout(500)
                                        preview=page.evaluate("""() => ({
                                            price:document.querySelector('#ui-input-price')?.value||null,
                                            days:document.querySelector('#ui-input-days')?.value||null,
                                            visibleButtons:[...document.querySelectorAll('button')]
                                              .filter(x=>x.getBoundingClientRect().width>0&&x.getBoundingClientRect().height>0)
                                              .map(x=>(x.innerText||'').trim()).filter(Boolean).slice(-14),
                                            bodyTail:(document.body?.innerText||'').slice(-900),
                                            categoryPresent:(document.body?.innerText||'').includes('AI-автоматизация')
                                        })""")
                                        progress.append({"step":step,**preview})
                                    out["wizard_preflight_steps"]=progress
                            except Exception as e:
                                out["wizard_preflight_error"]=type(e).__name__
                            out["management_ui"]=page.evaluate("""() => {
                                const els=[...document.querySelectorAll('*')]
                                  .filter(e=>e.childElementCount<2&&(e.innerText||'').trim()==='Управление услугой').slice(0,3);
                                const near=els.map(e=>({tag:e.tagName,html:(e.parentElement?.outerHTML||'').slice(0,1100)}));
                                const controls=[...document.querySelectorAll('button,[role=button],a[href]')].filter(e=>e.getBoundingClientRect().width>0&&e.getBoundingClientRect().height>0)
                                  .map(e=>({t:(e.innerText||e.title||'').trim().slice(0,70),id:e.id||'',data:e.getAttribute('data-id')||'',
                                   href:e.getAttribute('href')||'',cls:String(e.className||'').slice(0,60)}))
                                  .filter(e=>/управ|редак|сервис|отклон|доработ|услуг/i.test(e.t+' '+e.id+' '+e.data+' '+e.href)).slice(0,20);
                                const body=(document.body?.innerText||'');
                                return {near,controls,tail:body.slice(-1800)};
                            }""")

                            edits=[e for e in controls if "редактир" in e["text"].lower() and
                                   e.get("href","").startswith("https://www.fl.ru/")]
                            if len(edits)==1:
                                editor_url=edits[0]["href"]
                                er=page.goto(editor_url,wait_until="domcontentloaded",timeout=15000)
                                if er and er.status==200 and is_fl_url(page.url):
                                    out["edit_form_readonly"]=True
                                    form=page.evaluate("""() => ({
                                       fields:[...document.querySelectorAll('textarea,input,[contenteditable=true]')]
                                        .map(e=>({tag:e.tagName,id:e.id,name:e.name||'',type:e.type||'',
                                            value:(e.value||e.innerText||'').slice(0,3800)}))
                                        .filter(e=>e.value&&e.value.length>40).slice(0,10),
                                       excerpt:(document.body?.innerText||'').slice(0,3500)
                                    })""")
                                    out["edit_form_fields"]=form["fields"]
                                    out["edit_form_excerpt"]=compact(form["excerpt"],2500)
                        except Exception as e:
                            out["management_status"]="read_only_menu_error_"+type(e).__name__

                out["status"]="ok"
except Exception as exc:
    out["status"]="technical_error_"+type(exc).__name__
finally:
    if browser is not None:
        try:browser.close()
        except Exception:pass
    print(json.dumps(out,ensure_ascii=False))
