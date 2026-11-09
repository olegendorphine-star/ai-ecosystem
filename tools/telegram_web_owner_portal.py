#!/usr/bin/env python3
"""Owner-only short-lived handoff to persistent Telegram Web on VPS.

No public unauthenticated access. All browser operations are local on the VPS.
No server-side body, password, cookie, screenshot or user-input logging.
Link token and TLS tunnel originate only after owner-initiated workflow.
"""
from __future__ import annotations

import base64
import signal
import shutil
import fcntl
import hmac
import json
import os
import secrets
import socket
import stat
import subprocess
import tempfile
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

LOGIN = "telegram-owner"
ROOT = Path.home() / ".telegram-agent" / "browser"
PROFILE = ROOT / "profile"
STATE = PROFILE / "storage_state.json"  # legacy unused: persistent Chromium saves IndexedDB itself
TOKEN_FILE = ROOT / "rootless_owner_token"
PORT = int(os.getenv("TG_HANDOFF_PORT", "8992"))
TTL = min(900, max(180, int(os.getenv("TG_HANDOFF_TTL_SECONDS", "600"))))
VIEWPORT = {"width": 1280, "height": 850}
ALLOWED_PAGES = {
    "login": "https://web.telegram.org/k/",
    "settings": "https://web.telegram.org/k/",
}


PAGE = """<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Личный браузер Telegram Web на VPS</title>
<style>
body{font:15px system-ui;background:#151a23;color:#f4f6fa;max-width:980px;margin:auto;padding:12px}
button{font:inherit;padding:10px;margin:3px;border-radius:6px;border:1px solid #627186;background:#25446a;color:white}
button:disabled{opacity:.5} #shot{width:100%;max-width:960px;border:2px solid #63788e;display:block;touch-action:manipulation}
.row{display:flex;flex-wrap:wrap;gap:2px;align-items:center;margin:8px 0}
small{color:#d5deeb} .key{min-width:31px;padding:8px 6px} #status{margin:9px 0;min-height:22px}
</style>
<h3>Telegram Web · личный удалённый браузер</h3>
<p><small>Это закрытое окно браузера VPS, а НЕ сайт Telegram Web. Для входа используйте только официальный интерфейс Telegram.
Перед вводом проверьте, что открыт web.telegram.org. Не передавайте эту ссылку.</small></p>
<div id="status">Подключение…</div>
<button id="refresh" onclick="refresh()">Обновить экран</button>
<button onclick="go('login')">Telegram Web</button>
<button onclick="go('settings')">Список чатов</button>
<img id="shot" alt="Экран серверного Chromium" onclick="point(event)">
<small>Нажатия по экрану направляются в реальный Chromium на VPS. Для ручного ввода используйте кнопки ниже.
На шлюзе нет поля для пароля и кодов. CAPTCHA проходит только человек, без автоматического решения.</small>
<div class="row" id="keyboard"></div>
<div class="row">
<button onclick="special('Tab')">Tab</button><button onclick="special('Enter')">Enter</button>
<button onclick="special('Backspace')">⌫</button><button onclick="special('Space')">Пробел</button>
<button onclick="special('Escape')">Esc</button><button onclick="flip()">⇧ Регистр</button>
</div>
<button id="save" onclick="save()">Сохранить профиль и закрыть доступ</button>
<script>
const csrf="__CSRF__";
let upper=false, authorized=false;
async function request(op,body={},refreshAfter=true){
 const r=await fetch('/api/'+op,{method:'POST',credentials:'same-origin',
   headers:{'Content-Type':'application/json','X-TG-CSRF':csrf},body:JSON.stringify(body)});
 const d=await r.json();
 if(!r.ok){document.querySelector('#status').textContent='Ошибка: '+(d.error||r.status);return d;}
 if(refreshAfter) await refresh();return d;
}
function keyboard(){
 const target=document.querySelector('#keyboard');target.replaceChildren();
 for(const char of "1234567890qwertyuiopasdfghjklzxcvbnm@._-!#$%&*()+/:;?="){
  const b=document.createElement('button');
  b.className='key';b.textContent=upper?char.toUpperCase():char;
  b.onclick=()=>request('char',{char:upper?char.toUpperCase():char},false);
  target.appendChild(b);
 }
}
function flip(){upper=!upper;keyboard();}
async function special(key){await request('key',{key},false);}
async function go(route){await request('go',{route});}
async function point(e){
 const r=e.target.getBoundingClientRect();
 const x=Math.round((e.clientX-r.left)/r.width*1280),y=Math.round((e.clientY-r.top)/r.height*850);
 await request('click',{x,y},false);setTimeout(refresh,400);
}
async function refresh(){
 try{
  const r=await fetch('/api/status',{credentials:'same-origin'});
  const d=await r.json();
  authorized=r.ok&&d.ready;
  const name=d.on_tg_domain?'web.telegram.org':'не Telegram Web';
  document.querySelector('#status').textContent=authorized?
   ('Браузер: '+name+'. Времени: '+d.expires_in_minutes+' мин.'):
   'Закрытая сессия: требуется ваша личная ссылка';
  document.querySelector('#shot').src=authorized?'/shot?nonce='+Date.now():'';
 }catch(err){document.querySelector('#status').textContent='Нет связи с сервером';}
}
async function save(){
 const d=await request('save',{},false);
 if(d.ok){document.querySelector('#status').textContent='Профиль браузера сохранён. Доступ закрывается; авторизация проверяется отдельно.';}
}
async function init(){
 keyboard();const hash=location.hash.substring(1);
 if(hash&&hash.length<=150){
  const r=await fetch('/api/claim',{method:'POST',credentials:'same-origin',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({token:hash})});
  history.replaceState(null,'','/');
  if(r.ok){location.reload();return;}
 }
 await refresh();
}
init();
</script></html>"""


def private_dir(path: Path):
    if path.is_symlink():
        raise RuntimeError("unsafe_symlink")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.stat().st_uid != os.getuid():
        raise RuntimeError("wrong_owner")
    path.chmod(0o700)


def chrome_executable() -> Path:
    root = Path.home() / ".cache" / "ms-playwright"
    choices = sorted(p for p in root.rglob("chrome")
                     if p.is_file() and os.access(p, os.X_OK)) if root.exists() else []
    if not choices:
        raise RuntimeError("chromium_missing")
    return choices[-1]


def save_state(context):
    """Deliberately unused: persistent context saves Telegram IndexedDB itself."""
    raise RuntimeError("telegram_persistent_profile_only")


def is_telegram_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return parsed.scheme == "https" and parsed.hostname == "web.telegram.org"
    except (TypeError, ValueError):
        return False


def valid_host(value: str) -> bool:
    host = (value or "").split(":")[0].lower()
    return host.endswith(".trycloudflare.com") or host in {"127.0.0.1", "localhost"}


class HandoffHandler(BaseHTTPRequestHandler):
    server_version = "TelegramOwnerDesktop/1.0"
    sys_version = ""

    def log_message(self, *args):
        # The URL query, passwords, screenshots and session data are never logged.
        return

    def headers_private(self, content_type: str, length: int):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()

    def response(self, code: int, data: bytes, mime: str):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

    def json_response(self, code: int, data: dict):
        self.response(code, json.dumps(data, separators=(",", ":")).encode(), "application/json")

    def cookie_authenticated(self) -> bool:
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            key, sep, value = part.strip().partition("=")
            if key == "tg_handoff" and sep and hmac.compare_digest(value, self.server.secret):
                return True
        return False

    def do_GET(self):
        if not valid_host(self.headers.get("Host", "")):
            self.json_response(403, {"error": "unrecognized_host"})
            return
        path = urlsplit(self.path).path
        if path == "/ready":
            # A live browser and a verified screenshot are prerequisites
            # before giving the owner a login link.
            self.json_response(200, self.server.browser.live_status(test_screenshot=True))
            return
        if path == "/" and not self.cookie_authenticated():
            page = PAGE.replace("__CSRF__", self.server.csrf).encode()
            self.response(200, page, "text/html; charset=utf-8")
            return
        if not self.cookie_authenticated():
            self.json_response(403, {"error": "authorization_required"})
            return
        if path == "/":
            page = PAGE.replace("__CSRF__", self.server.csrf).encode()
            self.response(200, page, "text/html; charset=utf-8")
        elif path == "/shot":
            if not self.server.browser.live_status()["ready"]:
                self.json_response(503, {"error": "browser_not_ready"})
                return
            try:
                shot = self.server.browser.screenshot_png()
                self.response(200, shot, "image/png")
            except Exception:
                self.json_response(503, {"error": "screenshot_unavailable"})
        elif path == "/api/status":
            live = self.server.browser.live_status()
            self.json_response(200, {"ready": live["ready"],
                                     "chrome_alive": live["chrome_alive"],
                                     "on_tg_domain": is_telegram_url(self.server.browser.page.url) if live["ready"] else False,
                                     "saved": self.server.saved,
                                     "expires_in_minutes": max(0, int(
                                         (self.server.expiry-time.monotonic())/60))})
        else:
            self.json_response(404, {"error": "unknown_action"})

    def do_POST(self):
        if not valid_host(self.headers.get("Host", "")):
            self.json_response(403, {"error": "unrecognized_host"})
            return
        if urlsplit(self.path).path == "/api/claim":
            origin = self.headers.get("Origin", "")
            if origin != f"https://{self.headers.get('Host', '')}":
                self.json_response(403, {"error": "bad_origin"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json" or not 1 <= length <= 180:
                    raise ValueError("bad_body")
                token = json.loads(self.rfile.read(length)).get("token", "")
                if not isinstance(token,str) or not hmac.compare_digest(token,self.server.secret):
                    self.json_response(403, {"error": "authorization_required"})
                    return
                self.send_response(200)
                self.send_header("Set-Cookie", f"tg_handoff={self.server.secret}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=900")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
            except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
                self.json_response(400, {"error": "bad_claim"})
            return
        if not valid_host(self.headers.get("Host", "")) or not self.cookie_authenticated():
            self.json_response(403, {"error": "authorization_required"})
            return
        origin = self.headers.get("Origin", "")
        if origin and origin != f"https://{self.headers.get('Host', '')}":
            self.json_response(403, {"error": "bad_origin"})
            return
        if not hmac.compare_digest(self.headers.get("X-TG-CSRF", ""), self.server.csrf):
            self.json_response(403, {"error": "csrf_required"})
            return
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self.json_response(415, {"error": "invalid_content_type"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 2048:
                raise ValueError("body_too_large")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("invalid_payload")
            op = urlsplit(self.path).path
            if not self.server.browser.live_status()["ready"]:
                self.json_response(503, {"error": "browser_not_ready"})
                return
            page = self.server.browser.page
            if op in {"/api/click", "/api/char", "/api/key", "/api/save"} and not is_telegram_url(page.url):
                self.json_response(403, {"error": "not_on_telegram_site"})
                return
            if op == "/api/go":
                route = payload.get("route")
                if route not in ALLOWED_PAGES:
                    raise ValueError("invalid_route")
                page.goto(ALLOWED_PAGES[route], wait_until="commit", timeout=20000)
            elif op == "/api/click":
                x, y = payload.get("x"), payload.get("y")
                if type(x) is not int or type(y) is not int or not (0 <= x <= 1280 and 0 <= y <= 850):
                    raise ValueError("invalid_coordinates")
                page.mouse.click(x, y)
            elif op == "/api/char":
                char = payload.get("char")
                # No gateway login form: each manual key press is forwarded to
                # the genuine FL page. Never log, persist or echo character data.
                if not isinstance(char, str) or len(char) != 1 or not char.isascii() or ord(char) < 32:
                    raise ValueError("invalid_character")
                page.keyboard.insert_text(char)
            elif op == "/api/key":
                key = payload.get("key")
                if key not in {"Enter", "Tab", "Backspace", "Escape", "ArrowUp", "ArrowDown", "Space"}:
                    raise ValueError("invalid_key")
                page.keyboard.press(key)
            elif op == "/api/save":
                # Chromium persistent profile saves cookies, localStorage,
                # IndexedDB and service-worker state automatically. This
                # action safely closes the expiring handoff; it MUST NOT
                # falsely claim Telegram login was independently verified.
                if not is_telegram_url(page.url):
                    self.json_response(409, {"error": "telegram_site_required"})
                    return
                self.server.saved = True
                self.server.shutdown_requested = True
            else:
                self.json_response(404, {"error": "unknown_action"})
                return
            self.json_response(200, {"ok": True})
        except ValueError as exc:
            self.json_response(400, {"error": "invalid_request"})
        except Exception:
            self.json_response(500, {"error": "browser_action_failed"})


class Browser:
    def __init__(self):
        self.p = None
        self.proc = None
        self.browser = None
        self.context = None
        self.page = None
        self.xkb_root = None

    def open(self, runpath: Path):
        """Rootless Xvfb from existing FL graphical runtime; independent TG Chromium profile."""
        from playwright.sync_api import sync_playwright
        base = Path.home() / ".fl-agent" / "xvfb-runtime"
        private_xvfb = base / "usr/bin/Xvfb"
        private_compiler = base / "usr/bin/xkbcomp"
        private_data = base / "usr/share/X11/xkb/rules/evdev"
        fontconf = Path.home() / ".fl-agent" / "fontconfig/fonts.conf"
        if not (private_xvfb.is_file() and private_compiler.is_file()
                and private_data.is_file() and fontconf.is_file()):
            raise RuntimeError("rootless_fl_graphics_not_ready")
        root = Path.home() / ".cache/ms-playwright"
        choices = sorted(p for p in root.rglob("chrome") if p.is_file()
                         and os.access(p, os.X_OK)) if root.is_dir() else []
        if not choices:
            raise RuntimeError("full_chrome_missing")
        image = private_xvfb.read_bytes()
        old = bytes((47,117,115,114,47,98,105,110,0))
        if image.count(old) != 1:
            raise RuntimeError("private_xvfb_binary_unexpected")
        # Same-length patch of *private temporary copy* only; never patch the
        # OS or downloaded runtime. /tmp/abc has same length as /usr/bin.
        for _ in range(50):
            name = "".join(secrets.choice("abcdefghjkmnpqrstuvwxyz23456789")
                           for _ in range(3))
            link_root = Path("/tmp") / name
            try:
                link_root.mkdir(mode=0o700)
                self.xkb_root = link_root
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError("short_private_xkb_path_unavailable")
        (self.xkb_root / "xkbcomp").symlink_to(private_compiler)
        replacement = str(self.xkb_root).encode("ascii") + bytes((0,))
        if len(replacement) != len(old):
            raise RuntimeError("private_xvfb_patch_length")
        executable = runpath / "Xvfb"
        executable.write_bytes(image.replace(old, replacement))
        executable.chmod(0o700)
        libs = [base / "usr/lib/x86_64-linux-gnu",
                Path.home() / ".local/usr/lib/x86_64-linux-gnu",
                Path.home() / ".local/lib"]
        environment = os.environ.copy()
        environment["LD_LIBRARY_PATH"] = ":".join(map(str, libs)) + (
            ":" + environment["LD_LIBRARY_PATH"] if environment.get("LD_LIBRARY_PATH") else "")
        environment["PATH"] = str(base / "usr/bin") + ":" + environment.get("PATH", "")
        environment["XKB_CONFIG_ROOT"] = str(base / "usr/share/X11/xkb")
        environment["FONTCONFIG_FILE"] = str(fontconf)
        environment["FONTCONFIG_PATH"] = str(fontconf.parent)
        chosen = None
        for i in range(1950, 2100):
            if (not Path(f"/tmp/.X11-unix/X{i}").exists()
                    and not Path(f"/tmp/.X{i}-lock").exists()):
                chosen = i
                break
        if chosen is None:
            raise RuntimeError("x_display_unavailable")
        with (runpath / "xvfb.stderr").open("wb") as err:
            self.proc = subprocess.Popen(
                [str(executable), f":{chosen}", "-screen", "0", "1280x850x24",
                 "-nolisten", "tcp"], env=environment,
                stdout=subprocess.DEVNULL, stderr=err,
                start_new_session=True)
        for _ in range(40):
            if self.proc.poll() is not None:
                raise RuntimeError("xvfb_start_failed")
            if Path(f"/tmp/.X11-unix/X{chosen}").exists():
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("xvfb_socket_not_ready")
        environment["DISPLAY"] = f":{chosen}"
        self.p = sync_playwright().start()
        # Persistent user_data_dir retains Telegram IndexedDB/auth across
        # browser restarts. A Playwright storage_state JSON is NOT enough.
        if PROFILE.is_symlink():
            raise RuntimeError("unsafe_browser_profile_symlink")
        self.context = self.p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            executable_path=str(choices[-1]), headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            env=environment, viewport=VIEWPORT, timeout=20000)
        self.browser = self.context  # persistent context owns Chromium
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.goto(ALLOWED_PAGES["login"], wait_until="commit", timeout=20000)

    def screenshot_png(self):
        """Capture only for the authenticated owner. Never persist or log pixels.

        A direct CDP capture avoids Playwright's document.fonts.ready wait when
        third-party font requests keep Telegram Web's page in a loading state.
        """
        if not self.live_status()["chrome_alive"]:
            raise RuntimeError("chrome_process_not_alive")
        if self.page is None or self.page.is_closed():
            raise RuntimeError("browser_page_closed")
        try:
            image = self.page.screenshot(
                type="png", timeout=4000, animations="disabled",
            )
            if image.startswith(b"\x89PNG\r\n\x1a\n"):
                return image
        except Exception:
            pass
        if self.context is None:
            raise RuntimeError("playwright_context_unavailable")
        cdp = self.context.new_cdp_session(self.page)
        try:
            data = cdp.send("Page.captureScreenshot", {
                "format": "png", "captureBeyondViewport": False,
                "fromSurface": True,
            })
            image = base64.b64decode(data.get("data", ""), validate=True)
            if not image.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("invalid_screenshot")
            return image
        finally:
            try:
                cdp.detach()
            except Exception:
                pass

    def live_status(self, *, test_screenshot=False):
        """Do not equate a non-None Playwright page with a running Chrome."""
        result = {"ready": False, "chrome_alive": False, "screenshot_ready": False}
        try:
            process_alive = self.proc is not None and self.proc.poll() is None
            playwright_alive = (
                self.browser is not None and not self.browser.is_closed()
            )
            result["chrome_alive"] = (
                process_alive if self.proc is not None else playwright_alive
            )
            if not result["chrome_alive"] or self.page is None or self.page.is_closed():
                return result
            if test_screenshot:
                # Read only, bounded. Never store or emit screenshot bytes.
                raw = self.screenshot_png()
                result["screenshot_ready"] = raw.startswith(b"\x89PNG\r\n\x1a\n")
                result["ready"] = result["screenshot_ready"]
            else:
                result["ready"] = True
            return result
        except Exception:
            return result

    def close(self):
        if self.context:
            try: self.context.close()
            except Exception: pass
        if self.browser:
            try: self.browser.close()
            except Exception: pass
        if self.p:
            try: self.p.stop()
            except Exception: pass
        if self.proc and self.proc.poll() is None:
            try: os.killpg(self.proc.pid, signal.SIGTERM)
            except OSError: pass
            try: self.proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                try: os.killpg(self.proc.pid, signal.SIGKILL)
                except OSError: pass
        if self.xkb_root is not None:
            try:
                (self.xkb_root / "xkbcomp").unlink(missing_ok=True)
                self.xkb_root.rmdir()
            except OSError:
                pass


def main():
    private_dir(ROOT)
    private_dir(PROFILE)
    lockfd = os.open(ROOT / "rootless_owner.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    browser = Browser()
    with os.fdopen(lockfd, "r+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix="handoff-runtime-", dir=ROOT) as runtime:
            try:
                browser.open(Path(runtime))
                # A responding port or page handle is not proof of a usable browser.
                # Fail before issuing ANY one-time owner credential link.
                for _ in range(2):
                    if browser.live_status(test_screenshot=True)["ready"]:
                        break
                    time.sleep(0.5)
                else:
                    print("TG_ROOTLESS_OWNER_DESKTOP_RENDER_NOT_READY", flush=True)
                    return
                token = secrets.token_urlsafe(32)
                csrf = secrets.token_urlsafe(24)
                fd = os.open(TOKEN_FILE, os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "w") as out:
                    out.write(token)
                server = HTTPServer(("127.0.0.1", PORT), HandoffHandler)
                server.timeout = 1
                server.secret = token
                server.csrf = csrf
                server.saved = False
                server.shutdown_requested = False
                server.browser = browser
                server.expiry = time.monotonic() + TTL
                print("TG_ROOTLESS_OWNER_DESKTOP_PRIVATE_READY", flush=True)
                try:
                    while time.monotonic() < server.expiry and not server.shutdown_requested:
                        server.handle_request()
                finally:
                    server.server_close()
            finally:
                browser.close()
                if TOKEN_FILE.exists() and not TOKEN_FILE.is_symlink():
                    TOKEN_FILE.unlink()


if __name__ == "__main__":
    main()
