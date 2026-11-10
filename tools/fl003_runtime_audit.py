#!/usr/bin/env python3
"""Private VPS capability audit for FL-003. Presence only; no secrets or account content."""
import json, os, socket, stat
from pathlib import Path
from datetime import datetime,timezone

home=Path.home()
def safe_dir_exists(p):
    return p.is_dir() and not p.is_symlink()
def safe_file_exists(p):
    return p.is_file() and not p.is_symlink()
checks={
    "schema":"fl003.capability.audit.v1",
    "checked_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "vps_python_running":True,
    "existing_chromium_cache":safe_dir_exists(home/".cache"/"ms-playwright"),
    "vps_cyrillic_font_present":safe_file_exists(home/".fl003-screencast"/"fonts"/"DejaVuSans.ttf"),
    "existing_marketplace_handoff_code":safe_file_exists(home/".fl003-handoff"/"app.py"),
    "existing_marketplace_handoff_profile":safe_dir_exists(home/".fl003-handoff"/"profile"),
    "existing_telegram_resident_socket":False,
    "existing_telegram_resident_active":False,
    "existing_telegram_resident_authorized":False,
    "existing_telegram_app":safe_file_exists(home/".telegram-agent"/"app"/"tools"/"telegram_resident_daemon.py"),
    "demo_specific_bot_token_set":bool(os.environ.get("FL003_TELEGRAM_BOT_TOKEN")),
    "demo_specific_llm_key_set":bool(os.environ.get("FL003_LLM_API_KEY")),
    "demo_specific_mail_oauth_set":bool(os.environ.get("FL003_MAIL_OAUTH_FILE")),
    "demo_specific_imap_login_set":bool(os.environ.get("FL003_IMAP_USER") and os.environ.get("FL003_IMAP_APP_PASSWORD")),
}
sock=home/".telegram-agent"/"browser"/"resident"/"operator.sock"
try:
    if sock.exists() and not sock.is_symlink() and stat.S_ISSOCK(sock.stat().st_mode) and not sock.stat().st_mode & 0o077 and sock.stat().st_uid==os.getuid():
        checks["existing_telegram_resident_socket"]=True
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(str(sock))
            client.sendall(b'{"internal_control":"status"}')
            client.shutdown(socket.SHUT_WR)
            data=client.recv(8192)
        r=json.loads(data)
        checks["existing_telegram_resident_active"]=r.get("status")=="running" and r.get("browser_alive") is True
        checks["existing_telegram_resident_authorized"]=r.get("authorized") is True
except Exception:
    pass
try:
    import PIL
    checks["vps_pillow_available"]=True
except ImportError:
    checks["vps_pillow_available"]=False
try:
    evidence=home/".fl003-handoff"/"verified_evidence.json"
    if evidence.is_file() and not evidence.is_symlink():
        record=json.loads(evidence.read_text(encoding="utf8"))
        products=record.get("products") or {}
        verified=sorted(
            k for k,v in products.items()
            if k in ("Ozon","Avito") and isinstance(v,dict) and
               v.get("status")=="verified_product_price" and
               isinstance(v.get("price_rub"),(int,float)))
        checks["verified_live_marketplaces"]=verified
        checks["both_prices_verified"]=len(verified)==2
    else:
        checks["verified_live_marketplaces"]=[]
        checks["both_prices_verified"]=False
except Exception:
    checks["verified_live_marketplaces"]=[]
    checks["both_prices_verified"]=False
print(json.dumps(checks,sort_keys=True))
