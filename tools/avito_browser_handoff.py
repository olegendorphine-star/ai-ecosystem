#!/usr/bin/env python3
"""Local-only Playwright browser handoff for one-time manual authorization.

Binds to 127.0.0.1 only. Use an SSH local port forward from the phone.
No credentials or action payloads are logged.
"""
from __future__ import annotations

import base64
import json
import os
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

HOST = "127.0.0.1"
PORT = int(os.environ.get("AVITO_HANDOFF_PORT", "8787"))
PROFILE = Path(os.environ.get("AVITO_BROWSER_PROFILE_DIR", Path.home() / ".avito-agent" / "profile")).expanduser()
MAX_BODY = 64 * 1024

INDEX = r"""<!doctype html>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Avito browser handoff</title>
<style>
body{font:16px sans-serif;background:#171722;color:#eee;max-width:900px;margin:12px auto;padding:0 10px}
input,button{font:16px;padding:10px;margin:4px 0;border-radius:6px;border:1px solid #555}
input{background:#222;color:#fff;width:70%}button{background:#2d75c9;color:#fff}
img{max-width:100%;border:1px solid #555;margin-top:8px}#status{white-space:pre-wrap;color:#b7d9ff}
.row{display:flex;gap:6px;flex-wrap:wrap}
</style>
<h2>Browser handoff</h2>
<p>Локальная сессия. Вводимые данные не записываются в логи.</p>
<div id="status">Загрузка…</div>
<div class="row"><input id="url" placeholder="https://www.avito.ru/"><button onclick="go()">Перейти</button></div>
<div class="row"><input id="sel" placeholder="CSS-селектор"><button onclick="clickSel()">Клик по селектору</button><button onclick="focusSel()">Фокус</button></div>
<div class="row"><input id="txt" placeholder="Текст для ввода"><button onclick="typeText()">Ввести</button></div>
<div class="row"><input id="key" placeholder="Enter / Tab / Escape"><button onclick="pressKey()">Клавиша</button><button onclick="refresh()">Обновить</button><button onclick="stop()">Остановить</button></div>
<img id="shot" alt="screenshot">
<script>
async function post(path, body){let r=await fetch(path,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body||{})});let j=await r.json();if(!r.ok) alert(j.error||"Ошибка");return j}
async function go(){await post("/api/navigate",{url:document.querySelector("#url").value});refresh()}
async function clickSel(){await post("/api/click",{selector:document.querySelector("#sel").value});refresh()}
async function focusSel(){await post("/api/focus",{selector:document.querySelector("#sel").value});refresh()}
async function typeText(){await post("/api/type",{selector:document.querySelector("#sel").value,text:document.querySelector("#txt").value});refresh()}
async function pressKey(){await post("/api/key",{key:document.querySelector("#key").value});refresh()}
async function stop(){await post("/api/stop",{});refresh()}
async function refresh(){let r=await fetch("/api/status");let j=await r.json();document.querySelector("#status").textContent=JSON.stringify(j,null,2);document.querySelector("#shot").src="/screenshot?t="+Date.now()}
refresh();setInterval(refresh,5000)
</script>
"""

def startup_error_code(exc: Exception) -> str:
    """Return only a known, non-sensitive startup error category."""
    msg = str(exc).lower()
    if "libatk-1.0.so.0" in msg:
        return "missing_libatk"
    if "cannot open shared object file" in msg:
        return "missing_shared_library"
    if "remote debugging endpoint" in msg or "connect_over_cdp" in msg:
        return "browser_debugging_unavailable"
    if "chrome exited" in msg:
        return "browser_process_exited"
    if "executable doesn't exist" in msg:
        return "browser_executable_missing"
    return "browser_start_failed"


class Browser:
    def __init__(self):
        self.lock = threading.RLock()
        self.p = None
        self.browser = None
        self.context = None
        self.page = None
        self.chrome_proc = None
        self.stopped = False
        self.startup_error = ""

    def start(self):
        from playwright.sync_api import sync_playwright
        PROFILE.mkdir(parents=True, exist_ok=True)
        self.p = sync_playwright().start()
        PROFILE.mkdir(parents=True, exist_ok=True)
        launch_kwargs = {"headless": False, "args": ["--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--no-zygote"]}
        # Playwright may prefer the incompatible headless-shell binary. Prefer
        # a full Chrome binary when one is installed in the user cache.
        cache_root = Path.home() / ".cache" / "ms-playwright"
        chrome_candidates = sorted(
            p for p in cache_root.rglob("chrome")
            if p.is_file() and os.access(p, os.X_OK)
        ) if cache_root.exists() else []
        if chrome_candidates:
            launch_kwargs["executable_path"] = str(chrome_candidates[-1])
        # Launch Chrome outside Playwright, then attach over CDP. This avoids
        # BrowserType.launch failures on restricted VPS kernels.
        if chrome_candidates:
            debug_port = int(os.environ.get("AVITO_CHROME_DEBUG_PORT", "9222"))
            user_data = PROFILE / "chrome-user-data"
            user_data.mkdir(parents=True, exist_ok=True)
            cmd = [
                str(chrome_candidates[-1]), "--headless=new", "--no-sandbox",
                "--disable-dev-shm-usage", "--disable-gpu", "--no-zygote",
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={debug_port}",
                f"--user-data-dir={user_data}",
                "about:blank",
            ]
            self.chrome_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            for _ in range(30):
                try:
                    import urllib.request
                    with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json/version", timeout=1):
                        break
                except Exception:
                    if self.chrome_proc.poll() is not None:
                        err = self.chrome_proc.stderr.read().decode("utf-8", "replace")[-1000:]
                        raise RuntimeError(f"Chrome exited: {err}")
                    time.sleep(0.2)
            else:
                raise RuntimeError("Chrome remote debugging endpoint did not start")
            self.browser = self.p.chromium.connect_over_cdp(f"http://127.0.0.1:{debug_port}")
        else:
            self.browser = self.p.chromium.launch(**launch_kwargs)
        state_path = PROFILE / "storage_state.json"
        context_kwargs = {"viewport": {"width": 1280, "height": 900}}
        if state_path.exists():
            context_kwargs["storage_state"] = str(state_path)
        self.context = self.browser.new_context(**context_kwargs)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def close(self):
        with self.lock:
            self.stopped = True
            try:
                if self.context:
                    self.context.storage_state(path=str(PROFILE / "storage_state.json"))
                    self.context.close()
                if self.browser: self.browser.close()
                if self.chrome_proc and self.chrome_proc.poll() is None:
                    self.chrome_proc.terminate()
            finally:
                if self.p: self.p.stop()

    def status(self):
        with self.lock:
            ready = not self.stopped and not self.startup_error and self.page is not None
            if ready:
                try:
                    ready = not self.page.is_closed()
                except Exception:
                    ready = False
            return {"ok": bool(ready), "url": self.page.url if ready else "", "title": "", "startup_error": self.startup_error or ("browser_not_ready" if not ready else "")}

    def screenshot(self):
        with self.lock:
            return self.page.screenshot(type="png") if self.page else b""

    def navigate(self, url):
        if not isinstance(url, str) or not (url.startswith("https://") or url.startswith("http://")):
            raise ValueError("url must use http or https")
        with self.lock:
            if self.page is None or self.stopped or self.startup_error:
                raise RuntimeError("browser_not_ready")
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)

    def click(self, selector=None, x=None, y=None):
        with self.lock:
            if selector:
                self.page.locator(selector).first.click(timeout=15000)
            elif x is not None and y is not None:
                self.page.mouse.click(float(x), float(y))
            else:
                raise ValueError("selector or x,y required")

    def focus(self, selector):
        with self.lock:
            self.page.locator(selector).first.focus(timeout=15000)

    def type_text(self, selector, text):
        if not isinstance(text, str) or len(text) > 10000:
            raise ValueError("text too long")
        with self.lock:
            loc = self.page.locator(selector).first
            loc.fill(text, timeout=15000)

    def key(self, key):
        if not isinstance(key, str) or len(key) > 40:
            raise ValueError("invalid key")
        with self.lock:
            self.page.keyboard.press(key)

browser = Browser()

def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length < 0 or length > MAX_BODY:
        raise ValueError("request too large")
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8")) if raw else {}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            data = INDEX.encode()
            self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data); return
        if path == "/api/status":
            self.send_json(200, browser.status()); return
        if path == "/screenshot":
            data = browser.screenshot()
            self.send_response(200); self.send_header("Content-Type","image/png")
            self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(data)))
            self.end_headers(); self.wfile.write(data); return
        self.send_json(404, {"error":"not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = read_json(self)
            if path == "/api/navigate": browser.navigate(body.get("url"))
            elif path == "/api/click": browser.click(body.get("selector"), body.get("x"), body.get("y"))
            elif path == "/api/focus": browser.focus(body.get("selector"))
            elif path == "/api/type": browser.type_text(body.get("selector"), body.get("text", ""))
            elif path == "/api/key": browser.key(body.get("key"))
            elif path == "/api/stop": browser.close()
            else: self.send_json(404, {"error":"not found"}); return
            self.send_json(200, {"ok":True})
        except Exception as exc:
            self.send_json(400, {"ok":False, "error":type(exc).__name__ + ": " + str(exc)[:300]})

def main():
    try:
        browser.start()
    except Exception as exc:
        browser.startup_error = startup_error_code(exc)
    server = HTTPServer((HOST, PORT), Handler)
    print(json.dumps({"ok": not browser.startup_error, "bind": f"{HOST}:{PORT}", "profile": str(PROFILE), "startup_error": browser.startup_error}), flush=True)
    try:
        server.serve_forever()
    finally:
        browser.close()

if __name__ == "__main__":
    main()
