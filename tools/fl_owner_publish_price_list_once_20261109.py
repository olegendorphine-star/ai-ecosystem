#!/usr/bin/env python3
"""One-time user-approved own FL price list update, 3 scoped offers. No purchases."""
from pathlib import Path
from urllib.parse import urlsplit
import sys,json,tempfile,os,time
root=Path.home()/".fl-agent";sys.path.insert(0,str(root))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
URL="https://www.fl.ru/users/olegendorphine/price-list/"
offers=[
 {"id":"audit","title":"Аудит процесса и карта ИИ-автоматизации","rub":5000,"days":3},
 {"id":"spec","title":"ТЗ на персонального ИИ-ассистента","rub":12000,"days":4},
 {"id":"assistant","title":"Персональный ИИ-ассистент с памятью и API","rub":30000,"days":10}
]
out={"schema":"fl.owner.price-list.publish.v1","owner_verified":False,"paid_actions":False,
 "other_profile_changes":False,"captcha_actions":False,"offers":[]}
b=Browser()
def goto(page):
 response=page.goto(URL,wait_until="domcontentloaded",timeout=21000)
 page.wait_for_timeout(450)
 u=urlsplit(page.url)
 if not response or response.status!=200 or u.scheme!="https" or u.hostname not in ("www.fl.ru","fl.ru") or u.path!=urlsplit(URL).path:
  raise RuntimeError("wrong_page")
 return page.locator('form:has(input[name="title"]):has(input[name="price"]):has(input[name="days"])')
def intent(marker,offer):
 fd=os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"w") as f:
  json.dump({"id":offer["id"],"title":offer["title"],"price":offer["rub"],
     "days":offer["days"],"time":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())},f,ensure_ascii=False)
  f.flush();os.fsync(f.fileno())
try:
 with tempfile.TemporaryDirectory(prefix="fl-prices-once-",dir=root) as t:
  b.open(Path(t));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=19000)
  signs=p.evaluate("""()=>({h:(document.body?.innerText||'').includes('Основные настройки'),
    owner:Array.from(document.querySelectorAll('input')).some(e=>(e.value||'').trim().toLowerCase()==='olegendorphine@gmail.com')})""")
  out["owner_verified"]=bool(signs["h"] and signs["owner"] and is_fl_url(p.url))
  if out["owner_verified"]:
   for offer in offers:
    x={"id":offer["id"],"rub":offer["rub"],"days":offer["days"],"result":"not_started","clicked":False,"verified":False}
    out["offers"].append(x)
    marker=root/("fl_price_intent_"+offer["id"]+"_20261109.json")
    try:
     f=goto(p)
     if f.count()!=1 or f.locator('button[type="submit"]').count()!=1 or f.locator('button[type="submit"]').inner_text().strip()!="Сохранить":
      x["result"]="unexpected_form";break
     if f.locator('input[name="u_token_key"]').count()<1:
      x["result"]="anti_csrf_token_missing";break
     if f.locator('input[name="payment"],input[name="card"],input[name="promo"]').count()>0:
      x["result"]="payment_in_target_form";break
     body=p.locator("body").inner_text()
     if offer["title"] in body:
      x["result"]="already_present";x["verified"]=True;continue
     if marker.exists() or marker.is_symlink():
      x["result"]="prior_attempt_exists_no_retry";break
     f.locator('input[name="title"]').fill(offer["title"],timeout=5000)
     f.locator('input[name="price"]').fill(str(offer["rub"]),timeout=5000)
     f.locator('input[name="days"]').fill(str(offer["days"]),timeout=5000)
     if (f.locator('input[name="title"]').input_value()!=offer["title"]
          or f.locator('input[name="price"]').input_value()!=str(offer["rub"])
          or f.locator('input[name="days"]').input_value()!=str(offer["days"])):
      x["result"]="pre_submit_guard_failed";break
     intent(marker,offer)
     f.locator('button[type="submit"]').click(timeout=13000)
     x["clicked"]=True
     p.wait_for_timeout(500)
     goto(p)
     body=p.locator("body").inner_text()
     x["verified"]=offer["title"] in body
     x["result"]="published_verified" if x["verified"] else "clicked_not_verified_stop"
     if not x["verified"]: break
    except Exception:
     x["result"]="error_after_intent_stop" if marker.exists() else "error_before_intent"
     break
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
