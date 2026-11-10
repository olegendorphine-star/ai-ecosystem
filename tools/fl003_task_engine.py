#!/usr/bin/env python3
"""FL-003 isolated task engine: Telegram Saved Messages -> VPS -> safe evidence.

No Telegram sending, purchasing, email sending or private account token export.
Only explicit FL003 test commands in the owner's personal Saved Messages can
create tasks. All task input/output stays in owner-only storage on the VPS.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import socket
import sqlite3
import stat
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from fl003_client_demo import CARD_SOURCES, parse_mail, create_synthetic_mail, draft_reply, shop_live

ROOT=Path.home()/".fl003-demo"
DATABASE=ROOT/"state"/"tasks.sqlite3"
TELEGRAM_SOCKET=Path.home()/".telegram-agent"/"browser"/"resident"/"operator.sock"
EVIDENCE=Path.home()/".fl003-handoff"/"verified_evidence.json"
TEST_MARKERS={"FL003: ТОВАР M185":"shop_m185","FL003: ПИСЬМО ТЕСТ":"mail_test"}
DOC_VERSION="fl003.task.engine.v1"

def utc_now():
    return dt.datetime.now(dt.timezone.utc)

def safe_dir(p:Path):
    if p.is_symlink():raise ValueError("unsafe_directory_symlink")
    p.mkdir(mode=0o700,parents=True,exist_ok=True)
    p.chmod(0o700)

def prepare_storage():
    safe_dir(ROOT)
    safe_dir(DATABASE.parent)
    if DATABASE.is_symlink():raise ValueError("unsafe_database_symlink")
    if DATABASE.exists() and DATABASE.stat().st_mode & 0o077:
        raise ValueError("unsafe_database_permissions")

class Store:
    def __init__(self,db=DATABASE):
        self.db=Path(db)
        safe_dir(self.db.parent)
        if self.db.is_symlink():raise ValueError("unsafe_database_symlink")
        self.conn=sqlite3.connect(str(self.db),timeout=10)
        os.chmod(self.db,0o600)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("CREATE TABLE IF NOT EXISTS tasks (source_key TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL, created_utc TEXT NOT NULL, result_json TEXT)")
        self.conn.commit()

    def enqueue(self,source_key:str,kind:str)->bool:
        if kind not in ("shop_m185","mail_test") or not re.fullmatch(r"[0-9a-zA-Z:_-]{4,120}",source_key):
            raise ValueError("invalid_task")
        with self.conn:
            cur=self.conn.execute("INSERT OR IGNORE INTO tasks (source_key,kind,state,created_utc) VALUES (?,?,?,?)",
                (source_key,kind,"queued",utc_now().isoformat()))
        return cur.rowcount==1

    def pending(self):
        return self.conn.execute("SELECT source_key,kind FROM tasks WHERE state='queued' ORDER BY created_utc LIMIT 10").fetchall()

    def finish(self,key,state,result:dict):
        if state not in ("waiting_human","draft_ready","blocked","failed"):
            raise ValueError("invalid_state")
        with self.conn:
            self.conn.execute("UPDATE tasks SET state=?,result_json=? WHERE source_key=? AND state='queued'",
                (state,json.dumps(result,ensure_ascii=False),key))

    def requeue_waiting_shopping(self):
        """Resume only after a fresh independently captured owner-browser comparison."""
        if read_verified_products() is None:
            return 0
        with self.conn:
            cur=self.conn.execute("UPDATE tasks SET state='queued' WHERE kind='shop_m185' AND state='waiting_human'")
        return cur.rowcount

    def summary(self):
        rows=self.conn.execute("SELECT kind,state,count(*) FROM tasks GROUP BY kind,state").fetchall()
        return [{"kind":k,"state":s,"count":n} for k,s,n in rows]

    def close(self):self.conn.close()

def _telegram_socket_call(command:dict)->dict:
    p=TELEGRAM_SOCKET
    if p.is_symlink() or not p.exists():return {"status":"resident_unavailable"}
    info=p.stat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode & 0o077:
        return {"status":"resident_socket_unsafe"}
    now=utc_now()
    payload={
        "schema":"tg.owner.command.v1",
        "command_id":str(uuid.uuid4()),
        "action":command["action"],
        "issued_at":now.isoformat(),
        "expires_at":(now+dt.timedelta(seconds=60)).isoformat(),
        "params":command["params"],
    }
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
        conn.settimeout(25)
        conn.connect(str(p))
        conn.sendall(json.dumps(payload,ensure_ascii=False,separators=(",",":")).encode())
        conn.shutdown(socket.SHUT_WR)
        data=b""
        while len(data)<=65536:
            part=conn.recv(4096)
            if not part:break
            data+=part
        if len(data)>65536:raise ValueError("resident_reply_too_large")
    return json.loads(data)

def read_saved_message_tests(store:Store)->dict:
    """Fail closed; do not process arbitrary chats or copy their messages."""
    status={"saved_dialog_verified":False,"new_test_commands":0,"read_only":True,"telegram_sent":False}
    try:
        listing=_telegram_socket_call({"action":"web_dialogs","params":{"limit":20}})
        if listing.get("status")!="ok":return {**status,"status":"dialogs_unavailable"}
        matches=[i for i in listing.get("dialogs",[]) if
                 i.get("title","").casefold().strip() in ("избранное","saved messages","сохранённые сообщения")]
        if len(matches)!=1:return {**status,"status":"saved_dialog_not_unique_or_hidden"}
        peer=matches[0].get("peer_id")
        if type(peer) is not int or peer<=0:return {**status,"status":"invalid_saved_peer"}
        status["saved_dialog_verified"]=True
        data=_telegram_socket_call({"action":"web_read","params":{"peer_id":peer,"limit":12}})
        if data.get("status")!="ok":return {**status,"status":"saved_read_not_verified"}
        for msg in data.get("messages",[]):
            body=msg.get("text","").strip().upper()
            kind=TEST_MARKERS.get(body)
            mid=msg.get("message_id")
            if kind and type(mid) is int and mid>0:
                digest=hashlib.sha256((str(peer)+":"+str(mid)+":"+kind).encode()).hexdigest()[:40]
                if store.enqueue("tg_"+digest,kind):
                    status["new_test_commands"]+=1
        status["status"]="saved_commands_checked"
        return status
    except Exception:
        return {**status,"status":"telegram_read_failed"}

def read_verified_products(evidence=EVIDENCE,max_age_minutes=35):
    """Accept only recent evidence produced by the owner-only same-browser handoff."""
    if evidence.is_symlink() or not evidence.is_file():return None
    st=evidence.stat()
    if st.st_uid!=os.getuid() or st.st_mode&0o077 or st.st_size>35000:return None
    try:
        data=json.loads(evidence.read_text(encoding="utf-8"))
        if data.get("schema")!="fl003.marketplace.manual.evidence.v2":return None
        products=data.get("products") or {}
        if set(products)!=set(("Ozon","Avito")):return None
        output=[]
        for market in ("Ozon","Avito"):
            p=products[market]
            parsed=urlsplit(p["url"])
            expected="ozon.ru" if market=="Ozon" else "avito.ru"
            if parsed.scheme!="https" or not(parsed.hostname==expected or parsed.hostname.endswith("."+expected)):
                return None
            if p.get("status")!="verified_product_price" or p.get("price_evidence")!="product_jsonld_rub":
                return None
            if "m185" not in str(p.get("title","")).lower():return None
            value=p.get("price_rub")
            if type(value) not in (int,float) or not 1<=value<=200000:return None
            when=dt.datetime.fromisoformat(p["checked_utc"])
            if when.tzinfo is None:return None
            delta=(utc_now()-when.astimezone(dt.timezone.utc)).total_seconds()
            if delta<0 or delta>max_age_minutes*60:return None
            output.append({"marketplace":market,"source_url":p["url"],
                           "title":p["title"],"price_rub":value,"status":"verified_price_and_card",
                           "checked_at_utc":p["checked_utc"],"price_evidence":"same_browser_jsonld"})
        return {"source":"owner_manually_unblocked_same_browser","products":output,
                "full_comparison_verified":True,"browser_on_server":True}
    except (OSError,KeyError,ValueError,TypeError,OverflowError):
        return None

def execute_tasks(store:Store,offline=False):
    result=[]
    for key,kind in store.pending():
        try:
            if kind=="shop_m185":
                if offline:
                    shop={"source":"offline","products":[{"marketplace":s["marketplace"],
                          "source_url":s["url"],"price_rub":None,"status":"not_checked_offline"}
                          for s in CARD_SOURCES],"full_comparison_verified":False}
                else:
                    shop=read_verified_products() or shop_live()
                ready=bool(shop["full_comparison_verified"])
                state="draft_ready" if ready else "waiting_human"
                content={"kind":kind,"status":state,"shopping":shop,
                         "action":"offer_comparison" if ready else "manual_marketplace_gate",
                         "message_sent":False}
            else:
                mail=parse_mail(create_synthetic_mail())
                shop={"products":[{"marketplace":s["marketplace"],"source_url":s["url"],"price_rub":None,
                                   "status":"not_part_of_mail_test"} for s in CARD_SOURCES]}
                reply=draft_reply(mail,shop)
                ready=bool(mail["structured_requirements"]) and any(a["status"]=="parsed_docx" for a in mail["attachments"])
                state="draft_ready" if ready else "failed"
                content={"kind":kind,"status":state,"test_email":True,"attachment_count":len(mail["attachments"]),
                         "structured_requirements":mail["structured_requirements"],
                         "docx_verified":any(a["status"]=="parsed_docx" for a in mail["attachments"]),
                         "draft":reply,"message_sent":False}
            store.finish(key,state,content)
            result.append({"kind":kind,"state":state})
        except Exception:
            store.finish(key,"failed",{"kind":kind,"status":"failed","message_sent":False})
            result.append({"kind":kind,"state":"failed"})
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--fixture",action="store_true",help="Two test commands; never reads Telegram")
    p.add_argument("--telegram-read",action="store_true",help="Read ONLY explicit markers in Saved Messages")
    p.add_argument("--offline",action="store_true",help="No browser network")
    p.add_argument("--resume",action="store_true",help="Resume gated shopping after owner-solved site challenge")
    args=p.parse_args()
    prepare_storage()
    store=Store()
    try:
        if args.fixture:
            # Repeatable idempotent test IDs, no uncontrolled creation on retries.
            store.enqueue("fixture_shop_m185_v1","shop_m185")
            store.enqueue("fixture_mail_docx_v1","mail_test")
        telegram={"status":"not_requested"}
        if args.telegram_read:
            telegram=read_saved_message_tests(store)
        resumed=store.requeue_waiting_shopping() if args.resume and not args.offline else 0
        completed=execute_tasks(store,offline=args.offline)
        print(json.dumps({"schema":DOC_VERSION,"transport":"VPS","telegram":telegram,
                          "resumed_after_human":resumed,"executed":completed,"summary":store.summary(),
                          "external_messages_sent":0,"mail_sent":False,
                          "purchase_performed":False},ensure_ascii=False,sort_keys=True))
    finally:
        store.close()
if __name__=="__main__":
    main()
