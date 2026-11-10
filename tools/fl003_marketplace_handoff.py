#!/usr/bin/env python3
"""Ephemeral, owner-operated public-marketplace browser handoff on VPS.

Restricted to two allowlisted public product cards. Screenshot and manual
mouse/keyboard actions use an isolated Chromium session (no FL/Telegram cookies).
No automatic CAPTCHA solving, buying, messaging, login, or credential logging.
"""
from __future__ import annotations
import hmac, json, os, re, secrets, signal, subprocess, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PORT = 8993
TTL_SECONDS = 1200
ROOT = Path.home() / '.fl003-handoff'
CARDS = {
    'ozon': 'https://www.ozon.ru/product/logitech-m185-m186-besprovodnaya-mysh-sinyaya-7231897/',
    'avito': 'https://www.avito.ru/sankt-peterburg/tovary_dlya_kompyutera/besprovodnaya_mysh_logitech_m185_8049018171',
}
ALLOWED = {'www.ozon.ru', 'ozon.ru', 'www.avito.ru', 'avito.ru', 'm.avito.ru'}
KEYS = {'Tab', 'Enter', 'Escape', 'Backspace', 'Space', 'ArrowUp', 'ArrowDown'}
VIEW = {'width': 1200, 'height': 820}
PAGE = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FL003: безопасное продолжение в браузере VPS</title>
<style>body{font:15px/1.5 system-ui,sans-serif;background:#142131;color:#f4f6fb;padding:12px;max-width:900px;margin:auto}button{font:inherit;border:1px solid #718397;background:#2e4d6c;color:#fff;padding:11px;margin:4px;border-radius:7px}button:disabled{opacity:.5}img{display:block;width:100%;max-width:900px;border:1px solid #aac;border-radius:6px;touch-action:manipulation}small{color:#ced9e8}.ok{color:#abd7c0}.bad{color:#ffd6c6}</style>
<h2>Демо FL-003 · серверный браузер</h2>
<p><small>Доступ только к двум публичным карточкам Ozon/Авито. Браузер расположен на VPS. Ни вход в другие аккаунты, ни покупки, ни сообщения недоступны. Если маркетплейс требует проверку, пройдите её самостоятельно, без автоматического обхода.</small></p>
<div id="status">Проверка доступа…</div>
<button onclick="go('ozon')">Открыть Ozon</button><button onclick="go('avito')">Открыть Авито</button><button onclick="read()">Проверить карточку</button><button onclick="refresh()">Обновить экран</button>
<img id="screen" alt="Изображение текущей страницы удалённого браузера" onclick="clickScreen(event)">
<div><button onclick="key('Tab')">Tab</button><button onclick="key('Enter')">Enter</button><button onclick="key('Space')">Пробел</button><button onclick="key('Backspace')">⌫</button></div>
<div id="evidence"></div><p><small>Экран доступен только в течение ограниченной сессии. Данные вне двух разрешённых сайтов вводить нельзя. При блокировке сообщите результат: это честная граница текущей инфраструктуры.</small></p>
<script>
let csrf='';let ready=false;
async function req(path,obj){try{let r=await fetch('/api/'+path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF':csrf},body:JSON.stringify(obj)});let v=await r.json();if(!r.ok){document.getElementById('status').textContent='Ошибка: '+(v.error||r.status);}return v}catch(e){document.getElementById('status').textContent='Нет связи';return {ok:false}}}
async function claim(){const hash=location.hash.slice(1);history.replaceState(null,'','/');if(hash.length>24){const d=await req('claim',{token:hash});if(d.ok)csrf=d.csrf;}await refresh()}
async function refresh(){let x=await fetch('/api/status',{credentials:'same-origin'}),d=await x.json();ready=!!(x.ok&&d.ok);if(ready&&d.csrf)csrf=d.csrf;document.getElementById('status').textContent=ready?'VPS работает · '+(d.page||'начальная страница')+' · осталось '+d.minutes+' мин':'Доступ закрыт или истёк';if(ready)document.getElementById('screen').src='/shot?t='+Date.now();}
async function go(which){await req('act',{op:'go',which});await refresh()}
async function clickScreen(e){if(!ready)return;let r=e.target.getBoundingClientRect(),x=Math.round((e.clientX-r.left)/r.width*1200),y=Math.round((e.clientY-r.top)/r.height*820);const v=await req('act',{op:'click',x,y});if(v.evidence)document.getElementById('evidence').textContent=JSON.stringify(v.evidence);setTimeout(refresh,400)}
async function key(k){const v=await req('act',{op:'key',key:k});if(v.evidence)document.getElementById('evidence').textContent=JSON.stringify(v.evidence);await refresh()}
async function read(){const r=await req('act',{op:'inspect'});if(r.ok)document.getElementById('evidence').textContent='Проверка: '+JSON.stringify(r.evidence);await refresh()}
claim();
</script></html>'''

def valid_url(url):
    try:
        p=urlsplit(url)
        return p.scheme=='https' and p.hostname in ALLOWED and p.username is None and p.password is None and p.port is None
    except (ValueError,TypeError): return False

class State:
    def __init__(self):
        from playwright.sync_api import sync_playwright
        ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
        ROOT.chmod(0o700)
        self.secret=secrets.token_urlsafe(36)
        self.sid=secrets.token_urlsafe(32)
        self.csrf=secrets.token_urlsafe(32)
        self.claimed=False
        self.deadline=time.monotonic()+TTL_SECONDS
        self.pw=sync_playwright().start()
        profile=ROOT/'marketplace-profile'
        if profile.is_symlink():raise RuntimeError('unsafe_profile')
        profile.mkdir(mode=0o700,exist_ok=True)
        profile.chmod(0o700)
        self.ctx=self.pw.chromium.launch_persistent_context(str(profile),headless=True,args=['--no-sandbox'],viewport=VIEW,locale='ru-RU',timezone_id='Europe/Moscow')
        self.page=self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        if not self.url_ok():self.page.goto('about:blank')
        self.last={}
        self.verified={}
        self.resumed_once=False
        path=ROOT/'handoff_token'
        fd=os.open(path,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f:f.write(self.secret)
    def close(self):
        try:self.ctx.close()
        finally:self.pw.stop()
        try:(ROOT/'handoff_token').unlink()
        except FileNotFoundError:pass
    def url_ok(self):
        return self.page.url=='about:blank' or valid_url(self.page.url)
    def navigate(self,which):
        if which not in CARDS: return {'error':'not_allowlisted'}
        try:
            resp=self.page.goto(CARDS[which],wait_until='domcontentloaded',timeout=19000)
            self.page.wait_for_timeout(700)
            return {'ok':True,'http':resp.status if resp else None,'manual_gate_may_be_required':True}
        except Exception:return {'error':'navigate_failed'}
    def inspect(self):
        if not valid_url(self.page.url):return {'status':'invalid_or_empty_page'}
        try:
            title=self.page.title()[:120]
            body=self.page.locator('body').inner_text(timeout=3500)[:5000].lower()
            gate=any(s in body for s in ('капча','captcha','проверьте, что вы человек','нужна небольшая проверка браузера','страница не загрузилась','пройти проверку','access denied'))
            if gate:
                self.last={'status':'manual_gate','title':title,'url':self.page.url}
                return self.last
            domain=urlsplit(self.page.url).hostname or ''
            marketplace='Ozon' if 'ozon.ru' in domain else 'Avito'
            verified=None
            for script in self.page.locator('script[type="application/ld+json"]').all()[:12]:
                try:
                    root=json.loads(script.inner_text(timeout=1500))
                except Exception:
                    continue
                pending=root if isinstance(root,list) else [root]
                while pending:
                    item=pending.pop()
                    if isinstance(item,list):pending.extend(item)
                    if not isinstance(item,dict):continue
                    if '@graph' in item:pending.append(item['@graph'])
                    t=item.get('@type')
                    if t!='Product' and not (isinstance(t,list) and 'Product' in t):continue
                    name=str(item.get('name') or '')[:150]
                    if 'm185' not in name.lower():continue
                    offers=item.get('offers') or []
                    if isinstance(offers,dict):offers=[offers]
                    for offer in offers[:8]:
                        if not isinstance(offer,dict):continue
                        if offer.get('priceCurrency') not in ('RUB','RUR'):continue
                        price=offer.get('price') or offer.get('lowPrice')
                        try:value=float(str(price).replace(' ','').replace(',','.'))
                        except (TypeError,ValueError):continue
                        if not 1<=value<=200000:continue
                        seller=offer.get('seller')
                        seller_name=str(seller.get('name') or '')[:100] if isinstance(seller,dict) else None
                        verified={'status':'verified_product_price','marketplace':marketplace,'title':name,
                                  'price_rub':value,'seller':seller_name,'url':self.page.url,
                                  'price_evidence':'product_jsonld_rub',
                                  'checked_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
                        break
                    if verified:break
                if verified:break
            if verified:
                self.verified[marketplace]=verified
                payload={'schema':'fl003.marketplace.manual.evidence.v2','products':self.verified,
                         'both_prices_verified':len(self.verified)==2}
                target=ROOT/'verified_evidence.json'
                flags=os.O_CREAT|os.O_TRUNC|os.O_WRONLY
                if hasattr(os,'O_NOFOLLOW'):flags|=os.O_NOFOLLOW
                fd=os.open(target,flags,0o600)
                with os.fdopen(fd,'w',encoding='utf-8') as stream:
                    json.dump(payload,stream,ensure_ascii=False,indent=2)
                if len(self.verified)==2 and not self.resumed_once:
                    self.resumed_once=True
                    runner=Path.home()/'.fl003-demo'/'app'/'fl003_task_engine.py'
                    if runner.is_file() and not runner.is_symlink():
                        try:
                            subprocess.Popen([sys.executable,str(runner),'--resume'],
                                             cwd=str(runner.parent),
                                             stdin=subprocess.DEVNULL,
                                             stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL,
                                             start_new_session=True)
                        except OSError:
                            pass
                self.last={**verified,'both_prices_verified':len(self.verified)==2,
                           'server_task_resume_requested':self.resumed_once}
                return self.last
            self.last={'status':'visible_page_price_not_verified','title':title,'url':self.page.url}
            return self.last
        except Exception:
            return {'status':'page_read_failed'}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,format,*args):pass
    def reply(self,code,data,headers=None):
        payload=json.dumps(data,ensure_ascii=False).encode('utf8')
        self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store')
        if headers:
            for k,v in headers.items():self.send_header(k,v)
        self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    def ok(self):
        if time.monotonic()>=self.server.s.deadline:return False
        cookie=self.headers.get('Cookie','')
        values=[v.strip() for v in cookie.split(';')]
        return self.server.s.claimed and any(hmac.compare_digest(v,'fl003='+self.server.s.sid) for v in values)
    def do_GET(self):
        s=self.server.s
        if self.path=='/health':return self.reply(200,{'ready':True,'ttl_max_seconds':TTL_SECONDS,'authenticated':False})
        if self.path=='/':
            out=PAGE.encode('utf8');self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(out)));self.end_headers();self.wfile.write(out);return
        if not self.ok():return self.reply(403,{'ok':False,'error':'not_authorized'})
        if self.path=='/api/status':
            return self.reply(200,{'ok':True,'page':s.page.url if s.url_ok() else 'restricted','minutes':max(0,int((s.deadline-time.monotonic())/60)),'csrf':s.csrf})
        if self.path.startswith('/shot'):
            try: shot=s.page.screenshot(type='jpeg',quality=55,timeout=6000)
            except Exception:return self.reply(500,{'error':'screenshot_failed'})
            self.send_response(200);self.send_header('Content-Type','image/jpeg');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(shot)));self.end_headers();self.wfile.write(shot);return
        self.reply(404,{'error':'not_found'})
    def do_POST(self):
        s=self.server.s
        if self.path not in ('/api/claim','/api/act'):return self.reply(404,{'error':'not_found'})
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 1<=n<=512:raise ValueError()
            obj=json.loads(self.rfile.read(n))
            if not isinstance(obj,dict):raise ValueError()
        except Exception:return self.reply(400,{'error':'bad_request'})
        if self.path=='/api/claim':
            if s.claimed or time.monotonic()>=s.deadline:return self.reply(403,{'error':'closed'})
            if not isinstance(obj.get('token'),str) or not hmac.compare_digest(obj['token'],s.secret):return self.reply(403,{'error':'denied'})
            s.claimed=True
            return self.reply(200,{'ok':True,'csrf':s.csrf}, {'Set-Cookie':'fl003='+s.sid+'; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=1200'})
        if not self.ok() or not hmac.compare_digest(self.headers.get('X-CSRF',''),s.csrf):return self.reply(403,{'error':'not_authorized'})
        if not s.url_ok():return self.reply(403,{'error':'off_allowlist'})
        op=obj.get('op')
        if op=='go':return self.reply(200 if (v:=s.navigate(obj.get('which'))).get('ok') else 400,v)
        if op=='inspect':return self.reply(200,{'ok':True,'evidence':s.inspect()})
        try:
            if op in ('click','key') and s.inspect().get('status')!='manual_gate':return self.reply(403,{'error':'manual_gate_only'})
            if op=='click':
                x,y=obj.get('x'),obj.get('y')
                if not isinstance(x,int) or not isinstance(y,int) or not 0<=x<VIEW['width'] or not 0<=y<VIEW['height']:raise ValueError()
                s.page.mouse.click(x,y,timeout=4500)
            elif op=='key' and obj.get('key') in KEYS:
                s.page.keyboard.press(obj['key'],timeout=4500)
            else:raise ValueError()
            ev=s.inspect()
            return self.reply(200,{'ok':True,'evidence':ev})
        except Exception:return self.reply(400,{'error':'action_failed_or_not_allowed'})

def main():
    if '--selftest' in sys.argv:
        assert valid_url(CARDS['ozon']) and valid_url(CARDS['avito'])
        assert not valid_url('http://avito.ru/example') and not valid_url('https://evil.example/')
        assert not valid_url('https://avito.ru.evil.example/')
        print(json.dumps({'schema':'fl003.marketplace.handoff.v1','selftest':True}))
        return
    s=State();server=HTTPServer(('127.0.0.1',PORT),Handler);server.s=s;server.timeout=1
    def handle_signal(sig,frm):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,handle_signal)
    try:
        while time.monotonic()<s.deadline:server.handle_request()
    except KeyboardInterrupt:pass
    finally:server.server_close();s.close()

if __name__=='__main__':main()
