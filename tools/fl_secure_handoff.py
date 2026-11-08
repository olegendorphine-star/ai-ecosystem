#!/usr/bin/env python3
"""Owner-only, expiring browser handoff to activate FL freelancer account.

No public unauthenticated access. All browser operations are local on the VPS.
No server-side body, password, cookie, screenshot or user-input logging.
Link token and TLS tunnel originate only after owner-initiated workflow.
"""
from __future__ import annotations

import base64
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

LOGIN = "olegendorphine"
ROOT = Path.home() / ".fl-agent"
PROFILE = ROOT / "profile"
STATE = PROFILE / "storage_state.json"
TOKEN_FILE = ROOT / "handoff_token"
PORT = int(os.getenv("FL_HANDOFF_PORT", "8990"))
TTL = min(1200, max(180, int(os.getenv("FL_HANDOFF_TTL_SECONDS", "900"))))
VIEWPORT = {"width": 1280, "height": 850}
ALLOWED_PAGES = {
    "login": "https://www.fl.ru/account/login/",
    "settings": "https://www.fl.ru/profile/setup/main/",
    "portfolio": "https://www.fl.ru/profile/setup/portfolio/",
    "profile": "https://www.fl.ru/users/olegendorphine/",
    "projects": "https://www.fl.ru/projects/",
}

PAGE = """<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FL.ru — ручное подтверждение владельца</title>
<style>
body{font:15px system-ui;background:#161b22;color:white;max-width:900px;margin:0 auto;padding:14px}
button,input,select{font:inherit;padding:10px;margin:3px;border-radius:6px;border:1px solid #555}
button{background:#174ea6;color:white;cursor:pointer}
input{background:#222;color:white}
#shot{max-width:100%;border:1px solid #555;display:block;cursor:crosshair}
small{color:#c6d2db}.row{display:flex;flex-wrap:wrap;gap:5px;align-items:center}
</style><h2>FL.ru — вход владельца olegendorphine</h2>
<p>Это временная защищённая панель браузера на вашем VPS, а не официальный сайт FL.ru.
Она отключится автоматически. Проверяйте страницу на снимке перед вводом данных.
Не передавайте ссылку другим людям.</p>
<div id="status">Проверка браузера…</div>
<div class="row"><select id="route"><option value="login">Вход</option><option value="settings">Настройки</option>
<option value="profile">Мой профиль</option><option value="projects">Заказы</option>
<option value="portfolio">Портфолио</option></select><button onclick="go()">Перейти</button>
<button onclick="refresh()">Обновить экран</button></div>
<small>Нажимайте на элементы непосредственно на снимке браузера. Вводите текст в активное поле.</small>
<img id="shot" alt="Текущий экран Chromium" onclick="point(event)">
<div class="row"><input id="entry" placeholder="Текст для активного поля" autocomplete="off">
<button onclick="typeText()">Ввести</button><button onclick="key('Tab')">Tab</button>
<button onclick="key('Enter')">Enter</button><button onclick="key('Backspace')">⌫</button></div>
<div class="row"><button onclick="save()">Сохранить сессию и отключить доступ</button></div>
<script>
const csrf="__CSRF__";
async function post(op,body){let r=await fetch("/api/"+op,{method:"POST",credentials:"same-origin",
headers:{"content-type":"application/json","x-fl-csrf":csrf},body:JSON.stringify(body||{})});
let j=await r.json();if(!r.ok)alert(j.error||"Ошибка");else await refresh();return j}
async function go(){await post("go",{route:document.querySelector("#route").value})}
async function typeText(){let input=document.querySelector("#entry");await post("type",{text:input.value});input.value=""}
async function key(name){await post("key",{key:name})}
async function point(e){let box=e.target.getBoundingClientRect();
let x=Math.floor((e.clientX-box.left)/box.width*1280);
let y=Math.floor((e.clientY-box.top)/box.height*850);await post("click",{x,y})}
async function save(){let r=await post("save",{});if(r.ok){alert("Состояние сохранено. Разовый доступ закрыт.")}}
async function refresh(){try{let r=await fetch("/api/status",{credentials:"same-origin"});
let j=await r.json();document.querySelector("#status").textContent=j.ready?
(j.on_fl_domain?"Браузер открыт на FL.ru. После входа нажмите «Сохранить сессию».":"Внимание: открыта НЕ страница FL.ru!"):
"Браузер недоступен";
document.querySelector("#shot").src=j.ready?"/shot?t="+Date.now():"";}catch(e){}}
refresh();
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
    """Atomic save of browser state, owner-only, no output."""
    private_dir(PROFILE)
    if STATE.is_symlink():
        raise RuntimeError("state_symlink_rejected")
    fd, temporary = tempfile.mkstemp(prefix=".state-", dir=PROFILE)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as dst:
            json.dump(context.storage_state(), dst, separators=(",", ":"))
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(temporary, STATE)
        STATE.chmod(0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def is_fl_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return parsed.scheme == "https" and parsed.hostname in {"www.fl.ru", "fl.ru"}
    except (TypeError, ValueError):
        return False


def valid_host(value: str) -> bool:
    host = (value or "").split(":")[0].lower()
    return host.endswith(".trycloudflare.com") or host in {"127.0.0.1", "localhost"}


class HandoffHandler(BaseHTTPRequestHandler):
    server_version = "FLOwnerHandoff/1.0"
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
            if key == "fl_handoff" and sep and hmac.compare_digest(value, self.server.secret):
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
        if path == "/start":
            token = parse_qs(urlsplit(self.path).query).get("token", [""])[0]
            if len(token) <= 100 and hmac.compare_digest(token, self.server.secret):
                self.send_response(303)
                self.send_header("Set-Cookie", f"fl_handoff={self.server.secret}; HttpOnly; Secure; SameSite=Strict; Path=/")
                self.send_header("Location", "/")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
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
                                     "on_fl_domain": is_fl_url(self.server.browser.page.url) if live["ready"] else False,
                                     "saved": self.server.saved,
                                     "expires_in_minutes": max(0, int(
                                         (self.server.expiry-time.monotonic())/60))})
        else:
            self.json_response(404, {"error": "unknown_action"})

    def do_POST(self):
        if not valid_host(self.headers.get("Host", "")) or not self.cookie_authenticated():
            self.json_response(403, {"error": "authorization_required"})
            return
        origin = self.headers.get("Origin", "")
        if origin and origin != f"https://{self.headers.get('Host', '')}":
            self.json_response(403, {"error": "bad_origin"})
            return
        if not hmac.compare_digest(self.headers.get("X-FL-CSRF", ""), self.server.csrf):
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
            if op in {"/api/click", "/api/type", "/api/key", "/api/save"} and not is_fl_url(page.url):
                self.json_response(403, {"error": "not_on_fl_site"})
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
            elif op == "/api/type":
                text = payload.get("text")
                if not isinstance(text, str) or not 0 < len(text) <= 1024:
                    raise ValueError("invalid_text")
                page.keyboard.type(text, delay=8)
            elif op == "/api/key":
                key = payload.get("key")
                if key not in {"Enter", "Tab", "Backspace", "Escape", "ArrowUp", "ArrowDown"}:
                    raise ValueError("invalid_key")
                page.keyboard.press(key)
            elif op == "/api/save":
                save_state(self.server.browser.context)
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

    def open(self, runpath: Path):
        from playwright.sync_api import sync_playwright
        chrome = chrome_executable()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.proc = subprocess.Popen(
            [str(chrome), "--headless=new", "--no-sandbox",
             "--disable-dev-shm-usage", "--disable-gpu", "--no-zygote",
             "--no-first-run", "--remote-debugging-address=127.0.0.1",
             f"--remote-debugging-port={port}", f"--user-data-dir={runpath}",
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
        )
        endpoint = f"http://127.0.0.1:{port}/json/version"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(40):
            if self.proc.poll() is not None:
                raise RuntimeError("chrome_exited")
            try:
                with opener.open(endpoint, timeout=1) as resp:
                    if resp.status == 200:
                        break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("browser_unavailable")
        self.p = sync_playwright().start()
        self.browser = self.p.chromium.connect_over_cdp(
            f"http://127.0.0.1:{port}", timeout=7000
        )
        opts = {"viewport": VIEWPORT}
        if STATE.is_file() and not STATE.is_symlink():
            meta = STATE.stat()
            if (meta.st_uid == os.getuid() and (meta.st_mode & 0o077) == 0
                    and 2 <= meta.st_size < 2*1024*1024):
                opts["storage_state"] = str(STATE)
        self.context = self.browser.new_context(**opts)
        self.page = self.context.new_page()
        self.page.goto(ALLOWED_PAGES["login"], wait_until="commit", timeout=20000)

    def screenshot_png(self):
        """Capture only for the authenticated owner. Never persist or log pixels.

        A direct CDP capture avoids Playwright's document.fonts.ready wait when
        third-party font requests keep FL.ru's page in a loading state.
        """
        if self.proc is None or self.proc.poll() is not None:
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
            result["chrome_alive"] = (
                self.proc is not None and self.proc.poll() is None
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
            self.proc.terminate()
            try: self.proc.wait(timeout=4)
            except subprocess.TimeoutExpired: self.proc.kill()


def main():
    private_dir(ROOT)
    private_dir(PROFILE)
    lockfd = os.open(ROOT / "handoff.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
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
                    print("FL_HANDOFF_RENDER_NOT_READY", flush=True)
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
                print("FL_HANDOFF_PRIVATE_READY", flush=True)
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
