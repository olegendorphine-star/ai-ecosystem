#!/usr/bin/env python3
"""Read-only pixel comparison of the 3 public owner portfolio cover thumbnails.
Only safe numeric similarity scores; never outputs image or private data.
"""
from pathlib import Path
import hashlib,sys,json,tempfile,base64
from urllib.parse import urlsplit
ROOT=Path.home()/".fl-agent";sys.path.insert(0,str(ROOT))
from fl_rootless_owner_desktop import Browser,ALLOWED_PAGES,is_fl_url
URL="https://www.fl.ru/users/olegendorphine/portfolio/"
WORKS=[
 ("8111943","04_portfolio_staff_900x900.jpg"),
 ("8111944","05_portfolio_vps_900x900.jpg"),
 ("8111945","06_portfolio_docs_900x900.jpg")
]
out={"schema":"fl.owner.portfolio.cover.pixels.readonly.v1","owner":False,"writes":False,"results":[]}
b=Browser()
try:
 with tempfile.TemporaryDirectory(prefix="fl-covers-pixel-check-",dir=ROOT) as td:
  b.open(Path(td));p=b.page
  p.goto(ALLOWED_PAGES["settings"],wait_until="domcontentloaded",timeout=24000)
  s=p.evaluate("""()=>({o:Array.from(document.querySelectorAll('input')).some(x=>(x.value||'').trim().toLowerCase()==='olegendorphine@gmail.com'),s:(document.body?.innerText||'').includes('Основные настройки')})""")
  out["owner"]=bool(s["o"] and s["s"] and is_fl_url(p.url))
  if out["owner"]:
   p.goto(URL,wait_until="domcontentloaded",timeout=24000)
   for wid,filename in WORKS:
    row={"id":wid,"thumbnail_present":False,"pixel_mae":None,"new_cover_probable":False}
    out["results"].append(row)
    try:
     a=p.locator('a[href="/user/olegendorphine/portfolio/'+wid+'/"]').first
     if a.count()!=1:row["status"]="work_not_found";continue
     card=a.locator("..")
     imgs=card.locator("img")
     if imgs.count()!=1:row["status"]="expected_one_thumbnail";continue
     src=imgs.first.evaluate("(e)=>e.currentSrc||e.src||''")
     u=urlsplit(src)
     if u.scheme!="https" or not u.hostname or not (u.hostname.endswith(".fl.ru") or u.hostname in {"fl.ru","cdn.fl.ru"}):
      row["status"]="not_approved_cdn";continue
     response=p.request.get(src,timeout=18000)
     if not response.ok:row["status"]="img_fetch_failed";continue
     remote=response.body()
     asset=(ROOT/"artwork_20261109"/filename).read_bytes()
     if remote[:3]!=bytes.fromhex("ffd8ff") and remote[:8]!=bytes.fromhex("89504e470d0a1a0a"):
      row["status"]="unexpected_image_content";continue
     row["thumbnail_present"]=True
     b64a=base64.b64encode(asset).decode()
     b64b=base64.b64encode(remote).decode()
     result=p.evaluate("""async ({a,b}) => {
       function load(u){return new Promise((resolve,reject)=>{
        let x=new Image();x.onload=()=>resolve(x);x.onerror=()=>reject(Error('img load'));x.src=u;
       })}
       let aa=await load('data:image/jpeg;base64,'+a);
       let bb=await load('data:image/jpeg;base64,'+b);
       function pix(img){let c=document.createElement('canvas');c.width=c.height=64;
        let ctx=c.getContext('2d',{willReadFrequently:true});ctx.drawImage(img,0,0,64,64);
        return ctx.getImageData(0,0,64,64).data;}
       let pa=pix(aa),pb=pix(bb),err=0;
       for(let i=0;i<pa.length;i+=4)for(let k=0;k<3;k++)err+=Math.abs(pa[i+k]-pb[i+k]);
       return {mae:Math.round(err/(64*64*3)*10)/10, newDimensions:[bb.width,bb.height]};
      }""",{"a":b64a,"b":b64b})
     row["pixel_mae"]=result["mae"]
     row["new_cover_probable"]=result["mae"]<35
     row["dimensions"]=result["newDimensions"]
     row["status"]="ok"
    except Exception as e:
     row["status"]="technical_error"
     row["error_type"]=type(e).__name__
finally:b.close()
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
