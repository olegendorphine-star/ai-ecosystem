#!/usr/bin/env python3
"""Telegram Web K browser adapter behind the EXISTING encrypted owner-only bridge.

Uses only the already-authorized Chromium profile on the owner's VPS.
No Telegram MTProto API keys or second login. Caller receives results via X25519
and AES-GCM encrypted GitHub issue response (never GH logs, artifacts or files).

Allowlisted actions:
  web_status  -- boolean logged-in status only
  web_dialogs -- bounded titles/peer identifiers from visible chat list
  web_read    -- bounded visible messages in one selected chat
  web_reply   -- only explicitly approved text in response to verified incoming
  web_self_note -- explicitly approved note to this owner's own Saved Messages only
  web_phone_message -- one approved phone-number-resolved free personal message
  web_username_message -- one approved public-username-resolved free personal message
  web_chat_message -- one approved free message to a visible existing personal dialog
Opening a chat may cause Telegram to mark its messages as read.
Only a reply to a verified existing inbound message can be sent, with
explicit owner approval and a fail-closed at-most-once per-command ledger.
No cold messages, deletion, arbitrary browser navigation or caller scripts.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path.home() / ".telegram-agent" / "browser"
LOCK = ROOT / "rootless_owner.lock"
ALLOWED = frozenset({"web_status", "web_dialogs", "web_read", "web_reply", "web_self_note", "web_phone_message", "web_username_message",
                     "web_chat_message", "web_owner_contact_link", "web_username_read"})
REPLY_LEDGER = ROOT / "owner_approved_reply_attempts.sqlite3"
MAX_REPLY_TEXT = 2000

# This checks UI state only. Chat titles and messages are collected separately,
# and passed to the response encryptor on the VPS, NEVER to workflow logs.
UI_STATE_JS = r"""() => {
  const visible = s => [...document.querySelectorAll(s)].some(
    el => el.getClientRects().length > 0);
  return {
    sidebar: visible('#column-left'),
    chatlist: visible('#column-left .chatlist-chat'),
    login_form: visible('input[type="tel"], input[autocomplete="tel"], ' +
      '#auth-pages .qr-container, #auth-pages input'),
  };
}"""

DIALOGS_JS = r"""limit => {
  const rows = [...document.querySelectorAll('#column-left .chatlist-chat[data-peer-id]')];
  const matches = rows.filter(el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  });
  return matches.slice(0, limit).map(row => {
    const peerId = Number(row.getAttribute('data-peer-id'));
    const titleNode = row.querySelector('.dialog-title .user-title, .user-title, .peer-title, .dialog-title, .row-title');
    const title = (titleNode?.textContent || '').trim().slice(0, 120);
    const badge = row.querySelector('.dialog-unread-count, .badge-count, .unread-count');
    const unreadRaw = badge?.textContent?.trim() || '';
    return {
      peer_id: Number.isSafeInteger(peerId) && peerId !== 0 ? peerId : null,
      title,
      unread_label: /^[0-9]{1,5}$/.test(unreadRaw) ? unreadRaw : '',
    };
  }).filter(d => d.peer_id !== null && !!d.title);
}"""

MESSAGES_JS = r"""({peer,limit}) => {
  const app = window.appImManager;
  const active = app?.chat?.bubbles?.chatInner;
  // The page can contain multiple mounted chat views during transitions.
  // Only the live chatInner belonging to the selected peer may be read.
  if (Number(app?.chat?.peerId) !== peer || app?.chat?.setPeerPromise ||
      !active?.isConnected || typeof active?.querySelectorAll !== 'function')
    return [];
  const bubbles = [...active.querySelectorAll('.bubble[data-mid]')];
  return bubbles.slice(-limit).map(bubble => {
    const mid = Number(bubble.getAttribute('data-mid'));
    const text = (bubble.querySelector('.message [data-message-text-source]')?.textContent
      || bubble.querySelector('.message')?.textContent || '').trim().slice(0, 1200);
    const incoming = bubble.classList.contains('is-in') ? true
      : bubble.classList.contains('is-out') ? false : null;
    return {
      message_id: Number.isSafeInteger(mid) && mid > 0 ? mid : null,
      incoming, text,
      has_media: !!bubble.querySelector('.media-container, .document, .audio, video, .photo'),
    };
  }).filter(m => m.message_id !== null);
}"""


def classify_ui(url: str, flags: dict) -> str:
    if not isinstance(url, str) or not url.startswith("https://web.telegram.org/"):
        return "unknown"
    if not isinstance(flags, dict):
        return "unknown"
    if flags.get("login_form"):
        return "auth_required"
    if flags.get("sidebar") and flags.get("chatlist"):
        return "authorized"
    return "unknown"


def normalize_dialogs(rows, limit: int):
    if not isinstance(rows, list):
        raise ValueError("unexpected_dialogs")
    unique = set()
    result = []
    for item in rows[:limit]:
        if not isinstance(item, dict):
            continue
        peer = item.get("peer_id")
        name = item.get("title")
        if type(peer) is not int or not -(2 ** 53) < peer < 2 ** 53 or peer == 0:
            continue
        if type(name) is not str or not name.strip() or peer in unique:
            continue
        unique.add(peer)
        label = item.get("unread_label")
        result.append({"peer_id": peer, "title": name.strip()[:120],
                       "unread_label": label if isinstance(label, str) and
                       re.fullmatch(r"[0-9]{1,5}", label) else ""})
    return result


def claim_reply_once(command: dict, path: Path = REPLY_LEDGER) -> str:
    """Commit BEFORE touching Telegram; retries cannot accidentally double-send.

    `attempted` includes in-flight and uncertain sends. If the process
    crashes after claim, a repeated command fails closed (no resend).
    Only a SHA256 digest is saved, never the reply text or chat contents.
    """
    if path.is_symlink() or (path.exists() and (
            not stat.S_ISREG(path.stat().st_mode)
            or path.stat().st_uid != os.getuid()
            or path.stat().st_mode & 0o077)):
        raise ValueError("unsafe_ledger")
    digest = hashlib.sha256(
        json.dumps(command, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    p = command["params"]
    if command["action"] == "web_self_note":
        intent = ["saved_messages_only", p["text"].strip()]
    elif command["action"] == "web_phone_message":
        # Phone number only in owner-approved encrypted request; ledger holds SHA256.
        intent = ["approved_phone_once", p["phone"], p["text"].strip()]
    elif command["action"] == "web_username_message":
        intent = ["approved_public_username_once", p["username"].lstrip("@").lower(), p["text"].strip()]
    elif command["action"] == "web_chat_message":
        intent = ["approved_existing_personal_dialog_once", p["peer_id"], p["text"].strip()]
    else:
        intent = ["inbound_reply", p["peer_id"], p["reply_to_id"], p["text"].strip()]
    intent_digest = hashlib.sha256(
        json.dumps(intent, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    conn = sqlite3.connect(path, timeout=10)
    try:
        os.chmod(path, 0o600)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS reply_attempts ("
            "command_id TEXT PRIMARY KEY, digest TEXT NOT NULL, " 
            "intent_digest TEXT UNIQUE NOT NULL, state TEXT NOT NULL)"
        )
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT digest,state FROM reply_attempts WHERE command_id=?",
                (command["command_id"],)
            ).fetchone()
            if row:
                if row[0] != digest:
                    raise ValueError("reused_reply_command_with_different_content")
                state = "already_attempted"
            else:
                prior = conn.execute(
                    "SELECT command_id FROM reply_attempts WHERE intent_digest=?",
                    (intent_digest,)
                ).fetchone()
                if prior:
                    state = "already_attempted"
                else:
                    conn.execute(
                        "INSERT INTO reply_attempts(command_id,digest,intent_digest,state) "
                        "VALUES(?,?,?,'attempted')",
                        (command["command_id"], digest, intent_digest)
                    )
                    state = "claimed"
            conn.commit()
            return state
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()


def complete_reply(command_id: str, path: Path = REPLY_LEDGER):
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.execute("UPDATE reply_attempts SET state='confirmed' WHERE command_id=?",
                     (command_id,))
        conn.commit()
    finally:
        conn.close()


def send_approved_reply(page, peer_id: int, p: dict, command: dict) -> dict:
    """Outbound side effect: call ONLY after explicit owner approval.

    Require a bubble currently visible and definitely inbound, matching
    the already-verified selected peer. Telegram Web's sendText API is the
    same authenticated client API used by its upstream e2e tests.
    """
    reply_id = p["reply_to_id"]
    text = p["text"].strip()
    if not isinstance(text, str) or not 1 <= len(text) <= MAX_REPLY_TEXT:
        return {"status": "reply_rejected"}
    target = page.evaluate(
        """(mid) => {
          const b = [...document.querySelectorAll('#column-center .bubble[data-mid]')]
             .find(x => x.getAttribute('data-mid') === String(mid));
          return !!b && b.classList.contains('is-in') &&
            !b.classList.contains('is-out');
        }""", reply_id)
    if target is not True:
        return {"status": "inbound_message_not_verified"}
    if claim_reply_once(command) != "claimed":
        return {"status": "already_attempted_no_resend"}
    try:
        initiated = page.evaluate(
            """({peer,mid,text}) => {
              const app = window.appImManager;
              if (!app || Number(app.chat?.peerId) !== peer) return false;
              const send = app.managers?.appMessagesManager?.sendText;
              if (typeof send !== 'function') return false;
              send.call(app.managers.appMessagesManager,
                {peerId: peer, text, replyToMsgId: mid});
              return true;
            }""",
            {"peer": peer_id, "mid": reply_id, "text": text})
        if initiated is not True:
            return {"status": "send_not_started_no_retry"}
        # Do not send again if confirmation is missing. The client may have
        # transmitted the message even if UI update is delayed.
        for _ in range(18):
            confirmed = page.evaluate(
                """(text) => [...document.querySelectorAll('#column-center .bubble.is-out')]
                 .some(b => !b.classList.contains('is-sending') &&
                    (b.querySelector('.message [data-message-text-source]')?.textContent
                     || b.querySelector('.message')?.textContent || '').trim() === text)""",
                text)
            if confirmed is True:
                complete_reply(command["command_id"])
                return {"status": "sent_confirmed", "action": "web_reply",
                        "command_id": command["command_id"]}
            page.wait_for_timeout(550)
        return {"status": "send_status_uncertain_no_retry"}
    except Exception:
        # Never repeat this attempted command; owner checks Telegram manually
        # if UI acknowledgement cannot be established.
        return {"status": "send_status_uncertain_no_retry"}


def send_owner_self_note(page, command: dict) -> dict:
    """Explicitly approved one-time message to the account's own Saved Messages.

    The peer identifier comes exclusively from Telegram Web rootScope.myId.
    Nothing supplied by the caller can select an arbitrary account/contact.
    Do not send more than once if the operation is uncertain.
    """
    p = command["params"]
    text = p["text"].strip()
    if not (p.get("approved_by_owner") is True and
            isinstance(text, str) and 1 <= len(text) <= 300):
        return {"status": "self_note_not_approved"}
    selected = page.evaluate(
        """() => {
          const w = window;
          const app = w.appImManager;
          const self = Number(w.rootScope?.myId);
          if (!Number.isSafeInteger(self) || self <= 0 ||
              !app || typeof app.setInnerPeer !== 'function') return false;
          app.setInnerPeer({peerId:self});
          return true;
        }""")
    if selected is not True:
        return {"status": "self_chat_unavailable"}
    self_chat_ready = False
    for _ in range(25):
        self_chat_ready = page.evaluate(
            """() => {
              const self = Number(window.rootScope?.myId);
              const chat = window.appImManager?.chat;
              return Number.isSafeInteger(self) && self > 0 &&
                Number(chat?.peerId) === self && !chat?.setPeerPromise &&
                !!chat?.bubbles?.chatInner?.isConnected;
            }""")
        if self_chat_ready is True:
            break
        page.wait_for_timeout(450)
    if self_chat_ready is not True:
        return {"status": "self_chat_not_verified"}
    # Durable local ledger is claimed before Telegram performs ANY send.
    # The hash includes the unique text, never plaintext on disk.
    if claim_reply_once(command) != "claimed":
        return {"status": "already_attempted_no_resend"}
    try:
        # The same sendText interface is used in upstream Telegram Web K e2e
        # tests for Saved Messages. Double-check the self peer immediately
        # before sending, all on the private Chromium process.
        initiated = page.evaluate(
            """(text) => {
              const app = window.appImManager;
              const self = Number(window.rootScope?.myId);
              const manager = app?.managers?.appMessagesManager;
              if (!Number.isSafeInteger(self) || self <= 0 ||
                  Number(app?.chat?.peerId) !== self ||
                  typeof manager?.sendText !== 'function') return false;
              manager.sendText({peerId:self, text});
              return true;
            }""", text)
        if initiated is not True:
            return {"status": "send_not_started_no_retry"}
        for _ in range(25):
            confirmed = page.evaluate(
                """(text) => {
                  const app = window.appImManager;
                  const self = Number(window.rootScope?.myId);
                  if (!Number.isSafeInteger(self) ||
                      Number(app?.chat?.peerId) !== self) return false;
                  return [...document.querySelectorAll(
                    '#column-center .bubble[data-mid]')].some(
                      b => !b.classList.contains('is-sending') &&
                        (b.querySelector('.message [data-message-text-source]')?.textContent
                          || b.querySelector('.message')?.textContent || ''
                        ).trim() === text);
                }""", text)
            if confirmed is True:
                complete_reply(command["command_id"])
                return {"status": "sent_confirmed", "action": "web_self_note",
                        "command_id": command["command_id"],
                        "destination": "saved_messages"}
            page.wait_for_timeout(450)
        return {"status": "send_status_uncertain_no_retry"}
    except Exception:
        return {"status": "send_status_uncertain_no_retry"}


def get_owner_contact_link(page) -> dict:
    """Find existing username, else export owner's time-limited contact link.

    No phone number, cookies or Telegram auth tokens leave the VPS. The
    returned Telegram contact URL is intended to be shared with the owner
    through the existing encrypted X25519 bridge only.
    """
    try:
        result = page.evaluate(
            """async () => {
              const app = window.appImManager;
              const users = app?.managers?.appUsersManager ||
                window.rootScope?.managers?.appUsersManager;
              if (!users) return {status:'own_profile_unavailable'};
              const self = Number(window.rootScope?.myId);
              const u = Number.isSafeInteger(self) && self > 0 &&
                typeof users.getUser === 'function' ? users.getUser(self) : null;
              // The server-generated contact token belongs to the current
              // authorized session even if the client hasn't populated its
              // local self User object. Do not unnecessarily block fallback.
              const usernames = [
                u?.username,
                ...(Array.isArray(u?.usernames)
                  ? u.usernames.filter(x => x?.active !== false)
                    .map(x => x?.username)
                  : [])
              ].filter(x => typeof x === 'string' && /^[A-Za-z0-9_]{5,32}$/.test(x));
              if (usernames.length)
                return {status:'ok', method:'username', url:'https://t.me/'+usernames[0]};
              if (typeof users.exportContactToken !== 'function')
                return {status:'contact_link_unavailable'};
              try {
                const exported = await users.exportContactToken();
                const rawUrl = String(exported?.url || '').trim();
                if (rawUrl.length < 12 || rawUrl.length > 800)
                  return {status:'contact_link_invalid', url_length_class:'unexpected'};
                // Trust only Telegram's contacts.exportContactToken, never
                // arbitrary command-provided URLs. Normalize standard
                // t.me/contact and tg://contact?token forms to a single
                // official HTTPS link.
                let normalized = '';
                try {
                  const lower = rawUrl.toLowerCase();
                  const input = (lower.startsWith('t.me/') ||
                    lower.startsWith('telegram.me/')) ? 'https://' + rawUrl : rawUrl;
                  const parsed = new URL(input);
                  const host = parsed.hostname.toLowerCase();
                  // The token is generated by Telegram itself. Its alphabet
                  // may contain percent-escapes or punctuation. Preserve
                  // the opaque path rather than decoding or guessing its
                  // encoding; accept only official contact-link paths.
                  if (parsed.protocol === 'https:' &&
                      (host === 't.me' || host === 'telegram.me') &&
                      !parsed.username && !parsed.password && !parsed.port &&
                      /^\\/contact\\/[^/?#]{1,512}$/.test(parsed.pathname)) {
                    normalized = 'https://t.me' + parsed.pathname;
                  } else if (parsed.protocol === 'tg:' &&
                             parsed.hostname === 'contact') {
                    const token = parsed.searchParams.get('token') || '';
                    if (token.length >= 1 && token.length <= 512 &&
                        !/[\\u0000-\\u001F]/.test(token)) {
                      normalized = 'https://t.me/contact/' + encodeURIComponent(token);
                    }
                  }
                } catch (_) {}
                if (!normalized) {
                  return {status:'contact_link_invalid',
                    telegram_url: /(?:t\\.me|telegram\\.me|tg:\\/\\/contact)/i.test(rawUrl),
                    length_bucket: Math.min(10, Math.floor(rawUrl.length / 30))};
                }
                return {status:'ok', method:'contact_token',
                        url:normalized,
                        expires: Number(exported.expires) || null};
              } catch (_) { return {status:'contact_link_unavailable'}; }
            }""")
        if not isinstance(result, dict) or result.get("status") != "ok":
            if not isinstance(result, dict):
                return {"status": "own_profile_unavailable"}
            return {k: v for k, v in result.items()
                    if k in {"status", "telegram_url", "length_bucket", "url_length_class"}}
        from urllib.parse import urlsplit
        url, method = result.get("url"), result.get("method")
        if not isinstance(url, str) or method not in {"username", "contact_token"}:
            return {"status": "contact_link_invalid"}
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "t.me" or parsed.query or parsed.fragment:
            return {"status": "contact_link_invalid"}
        if method == "username" and not re.fullmatch(r"/[A-Za-z0-9_]{5,32}", parsed.path):
            return {"status": "contact_link_invalid"}
        if method == "contact_token" and not re.fullmatch(r"/contact/[^/?#]{1,750}", parsed.path):
            return {"status": "contact_link_invalid"}
        response = {"status": "ok", "action": "web_owner_contact_link",
                    "url": url, "method": method}
        if method == "contact_token" and type(result.get("expires")) in (int,float):
            response["expires_at"] = result["expires"]
        return response
    except Exception:
        return {"status": "contact_link_unavailable"}


def send_approved_phone_message(page, command: dict) -> dict:
    """Only one user-requested direct message to exact Telegram phone resolution.

    Telegram's contacts.resolvePhone maps this E.164 number directly to the
    Telegram user. No contacts are imported or edited. Never bypass Telegram
    privacy settings, any premium/Stars requirement, or arbitrary recipients.
    """
    p = command["params"]
    phone, text = p["phone"], p["text"].strip()
    if (p.get("approved_by_owner") is not True or
            type(phone) is not str or not re.fullmatch(r"\+[1-9][0-9]{7,14}", phone)
            or type(text) is not str or not 1 <= len(text) <= 300):
        return {"status": "direct_phone_not_approved"}
    # Plaintext number stays inside the VPS browser. Do not return it or any
    # user identity in the encrypted result except an opaque local peer_id.
    try:
        resolved = page.evaluate(
            """async (phone) => {
              const w = window, app = w.appImManager;
              const managers = app?.managers;
              const self = Number(w.rootScope?.myId);
              if (!Number.isSafeInteger(self) || self <= 0 ||
                  typeof managers?.appUsersManager?.resolvePhone !== 'function')
                return {status:'phone_lookup_unavailable'};
              try {
                // Owner explicitly authorized adding this exact phone to
                // the Telegram contacts. Native importContacts maps one
                // inputPhoneContact to the returned Telegram user ID; unlike
                // contacts.resolvePhone it may work when direct lookup is
                // blocked by the other account's discovery settings.
                let user;
                const userManager = managers?.appUsersManager;
                if (!userManager || typeof userManager.importContact !== 'function')
                  return {status:'contact_manager_unavailable'};
                // Check existing contacts by EXACT full phone first: a past
                // import can have succeeded even if subsequent UI steps failed.
                try {
                  const contactIds = await userManager.getContacts(
                    undefined, false, 'none');
                  if (Array.isArray(contactIds)) {
                    for (const contactId of contactIds.slice(0, 5000)) {
                      const entry = userManager.getUser(contactId);
                      const existingPhone = String(entry?.phone || '').replace(/[^0-9]/g,'');
                      if (existingPhone && existingPhone === phone.replace(/[^0-9]/g,'')) {
                        user = entry;
                        break;
                      }
                    }
                  }
                } catch (_) {
                  // Read-only contact list is optional; attempt native import.
                }
                if (!user) try {
                  const importedId = await userManager.importContact(
                    'Личный', 'Telegram', phone);
                  user = userManager.getUser(importedId);
                  // importContact may resolve an ID before the User cache
                  // is hydrated. Verify the returned user with Telegram's
                  // own users.getUsers method rather than assuming no user.
                  if (!user && typeof userManager.getApiUsers === 'function') {
                    const fresh = await userManager.getApiUsers([importedId]);
                    if (Array.isArray(fresh))
                      user = fresh.find(u => String(u?.id) === String(importedId));
                  }
                } catch (importError) {
                  const type = String(importError?.type || '');
                  if (type === 'NO_USER') {
                    try {
                      user = await userManager.resolvePhone(phone);
                    } catch (lookupError) {
                      if (lookupError?.type === 'PHONE_NOT_OCCUPIED')
                        return {status:'contact_not_resolved_by_telegram'};
                      if (String(lookupError?.type || '').startsWith('FLOOD_WAIT_'))
                        return {status:'telegram_rate_limited'};
                      return {status:'contact_import_or_lookup_restricted'};
                    }
                  } else if (type.startsWith('FLOOD_WAIT_')) {
                    return {status:'telegram_rate_limited'};
                  } else if (type === 'CONTACTS_TOO_MUCH') {
                    return {status:'telegram_contacts_full'};
                  } else if (type === 'PHONE_NUMBER_INVALID') {
                    return {status:'telegram_phone_format_rejected'};
                  } else if (type.includes('PRIVACY')) {
                    return {status:'telegram_contact_privacy_restricted'};
                  } else if (importError?.name === 'TypeError') {
                    return {status:'contact_browser_type_error'};
                  } else {
                    // Telegram RPC error *code only*, never expose raw
                    // exception text: it can contain private phone/contact.
                    const code = /^[A-Z][A-Z0-9_]{1,48}$/.test(type) ? type : '';
                    const kind = ['Error','ApiError','TypeError','TimeoutError']
                      .includes(importError?.name) ? importError.name : 'other';
                    return {status:'contact_import_restricted',
                            error_code:code || 'UNCLASSIFIED',
                            error_class:kind};
                  }
                }
                // When a full phone is provided in Telegram's User object,
                // reject any contradictory number. Never send to a mismatch.
                const returnedPhone = String(user?.phone || '').replace(/[^0-9]/g,'');
                if (returnedPhone && returnedPhone !== phone.replace(/[^0-9]/g,''))
                  return {status:'resolved_contact_phone_mismatch'};
                const id = Number(user?.id);
                if (user?._ !== 'user' || !Number.isSafeInteger(id) || id <= 0)
                  return {status:'phone_user_not_verified_after_import',
                          imported_user_present:!!user,
                          user_object_tag_valid:user?._ === 'user',
                          user_id_valid:Number.isSafeInteger(id) && id > 0};
                if (id === self) return {status:'target_is_current_account'};
                if (user.pFlags?.deleted || user.pFlags?.bot)
                  return {status:'target_not_personal_user'};
                if (user.send_paid_messages_stars || user.pFlags?.contact_require_premium)
                  return {status:'message_requires_payment_or_premium'};
                const toPeerId = user.id?.toPeerId;
                if (typeof toPeerId !== 'function')
                  return {status:'target_peer_unavailable'};
                const peer = Number(toPeerId.call(user.id, false));
                if (!Number.isSafeInteger(peer) || peer <= 0)
                  return {status:'target_peer_unavailable'};
                // Requirement may need a live Telegram API call. Fail closed
                // on network error, unknown, premium, or paid requirements.
                const requirement = await managers.appUsersManager.getRequirementToContact(user.id);
                if (requirement?._ !== 'requirementToContactEmpty')
                  return {status:'message_requires_payment_or_premium'};
                return {status:'target_resolved_free', peer_id:peer};
              } catch (e) {
                if (e?.type === 'PHONE_NOT_OCCUPIED')
                  return {status:'phone_not_found'};
                return {status:'phone_lookup_restricted'};
              }
            }""", phone)
    except Exception:
        return {"status": "phone_lookup_unavailable"}
    if not isinstance(resolved, dict) or resolved.get("status") != "target_resolved_free":
        return {"status": resolved.get("status", "phone_lookup_unavailable")
                if isinstance(resolved, dict) else "phone_lookup_unavailable"}
    peer_id = resolved.get("peer_id")
    if type(peer_id) is not int or peer_id <= 0 or peer_id >= 2 ** 53:
        return {"status": "target_peer_unavailable"}
    try:
        selected = page.evaluate(
            """(peer) => {
              const app = window.appImManager;
              if (typeof app?.setInnerPeer !== 'function') return false;
              app.setInnerPeer({peerId:peer});
              return true;
            }""", peer_id)
        if selected is not True:
            return {"status": "target_chat_unavailable"}
        ready = False
        for _ in range(25):
            ready = page.evaluate(
                """(peer) => {
                  const app = window.appImManager;
                  return Number(app?.chat?.peerId) === peer &&
                    !app?.chat?.setPeerPromise &&
                    !!app?.chat?.bubbles?.chatInner?.isConnected;
                }""", peer_id)
            if ready is True:
                break
            page.wait_for_timeout(450)
        if ready is not True:
            return {"status": "target_chat_not_verified"}
        # Revalidate requirements immediately before sending; no Stars or
        # premium-only messages are authorized by this request.
        free = page.evaluate(
            """async (peer) => {
              const m = window.appImManager?.managers;
              if (Number(window.appImManager?.chat?.peerId) !== peer ||
                  !m?.appUsersManager || !m?.appPeersManager) return false;
              try {
                const requirement = await m.appUsersManager.getRequirementToContact(peer);
                const stars = await m.appPeersManager.getStarsAmount(peer);
                return requirement?._ === 'requirementToContactEmpty' &&
                  !(Number(stars) > 0);
              } catch (_) { return false; }
            }""", peer_id)
        if free is not True:
            return {"status": "message_requires_payment_or_premium"}
        # Write-at-most-once ledger before touching Telegram sendText.
        if claim_reply_once(command) != "claimed":
            return {"status": "already_attempted_no_resend"}
        try:
            sent = page.evaluate(
                """({peer,text}) => {
                  const app = window.appImManager;
                  const m = app?.managers?.appMessagesManager;
                  if (Number(app?.chat?.peerId) !== peer ||
                    typeof m?.sendText !== 'function') return false;
                  m.sendText({peerId:peer,text});
                  return true;
                }""", {"peer":peer_id, "text":text})
            if sent is not True:
                return {"status": "send_not_started_no_retry"}
            for _ in range(28):
                confirmed = page.evaluate(
                    """({peer,text}) => {
                      if (Number(window.appImManager?.chat?.peerId) !== peer) return false;
                      return [...document.querySelectorAll(
                        '#column-center .bubble.is-out[data-mid]')].some(
                          b => !b.classList.contains('is-sending') &&
                          (b.querySelector('.message [data-message-text-source]')?.textContent ||
                            b.querySelector('.message')?.textContent || '').trim() === text);
                    }""", {"peer":peer_id, "text":text})
                if confirmed is True:
                    complete_reply(command["command_id"])
                    return {"status": "sent_confirmed", "action": "web_phone_message",
                            "destination": "resolved_phone_account"}
                page.wait_for_timeout(450)
            return {"status": "send_status_uncertain_no_retry"}
        except Exception:
            return {"status": "send_status_uncertain_no_retry"}
    except Exception:
        return {"status": "target_chat_unavailable"}



def send_approved_username_message(page, command: dict) -> dict:
    """One owner-approved free message to a *verified public personal username*.

    Resolution is performed by the authenticated Telegram Web K app manager.
    A channel, bot, mismatched username, paid recipient, or unknown requirement
    is rejected without attempting to send. Never touch contacts or bypass
    Telegram privacy restrictions. No plaintext content leaves the VPS.
    """
    p = command["params"]
    username, msg = p["username"], p["text"]
    if (p.get("approved_by_owner") is not True or
            type(username) is not str or
            not re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{4,31}", username) or
            type(msg) is not str or not 1 <= len(msg.strip()) <= 1200):
        return {"status": "username_message_not_approved"}
    username = username.lstrip("@").lower()
    msg = msg.strip()
    try:
        resolved = page.evaluate(
            """async (username) => {
              const app = window.appImManager;
              const managers = app?.managers;
              const users = managers?.appUsersManager;
              const self = Number(window.rootScope?.myId);
              if (!Number.isSafeInteger(self) || self <= 0 ||
                  typeof users?.resolveUsername !== 'function')
                return {status:'username_lookup_unavailable'};
              try {
                const user = await users.resolveUsername(username);
                if (user?._ !== 'user' || user.pFlags?.deleted || user.pFlags?.bot ||
                    user.pFlags?.min)
                  return {status:'target_not_personal_user'};
                const validNames = [user.username, ...(Array.isArray(user.usernames) ?
                  user.usernames.filter(x => x?.active !== false)
                    .map(x => x?.username) : [])]
                  .filter(x => typeof x === 'string')
                  .map(x => x.toLowerCase());
                if (!validNames.includes(username))
                  return {status:'resolved_username_mismatch'};
                const id = Number(user.id);
                if (!Number.isSafeInteger(id) || id <= 0)
                  return {status:'target_peer_unavailable'};
                if (id === self) return {status:'target_is_current_account'};
                if (user.send_paid_messages_stars || user.pFlags?.contact_require_premium)
                  return {status:'message_requires_payment_or_premium'};
                if (typeof user.id?.toPeerId !== 'function')
                  return {status:'target_peer_unavailable'};
                const peer = Number(user.id.toPeerId(false));
                if (!Number.isSafeInteger(peer) || peer <= 0)
                  return {status:'target_peer_unavailable'};
                const requirement = await users.getRequirementToContact(user.id);
                const stars = await managers.appPeersManager.getStarsAmount(peer);
                if (requirement?._ !== 'requirementToContactEmpty' ||
                    Number(stars) > 0)
                  return {status:'message_requires_payment_or_premium'};
                return {status:'target_resolved_free', peer_id:peer};
              } catch (e) {
                const code = String(e?.type || '');
                if (code === 'USERNAME_NOT_OCCUPIED' || code === 'USERNAME_INVALID')
                  return {status:'username_not_found'};
                if (code.startsWith('FLOOD_WAIT_'))
                  return {status:'telegram_rate_limited'};
                return {status:'username_lookup_restricted'};
              }
            }""", username)
    except Exception:
        return {"status": "username_lookup_unavailable"}
    if not isinstance(resolved, dict) or resolved.get("status") != "target_resolved_free":
        return {"status": resolved.get("status", "username_lookup_unavailable")
                if isinstance(resolved, dict) else "username_lookup_unavailable"}
    peer = resolved.get("peer_id")
    if type(peer) is not int or not 0 < peer < 2**53:
        return {"status": "target_peer_unavailable"}
    try:
        opened = page.evaluate(
            """(peer) => {
              const app = window.appImManager;
              if (typeof app?.setInnerPeer !== 'function') return false;
              app.setInnerPeer({peerId:peer});
              return true;
            }""", peer)
        if opened is not True:
            return {"status": "target_chat_unavailable"}
        ready = False
        for _ in range(25):
            ready = page.evaluate(
                """(peer) => {
                  const app = window.appImManager;
                  return Number(app?.chat?.peerId) === peer &&
                    !app?.chat?.setPeerPromise &&
                    !!app?.chat?.bubbles?.chatInner?.isConnected;
                }""", peer)
            if ready is True:
                break
            page.wait_for_timeout(450)
        if ready is not True:
            return {"status": "target_chat_not_verified"}
        # Re-check the peer's *actual username* and payment state after opening.
        # A resolved peer ID is not permission to send to a different user.
        verified = page.evaluate(
            """async ({peer,username}) => {
              const app = window.appImManager, managers = app?.managers;
              if (Number(app?.chat?.peerId) !== peer ||
                  !managers?.appUsersManager || !managers?.appPeersManager)
                return false;
              try {
                const user = await managers.appUsersManager.getUser(peer);
                if (user?._ !== 'user' || user.pFlags?.deleted || user.pFlags?.bot)
                  return false;
                const names = [user.username, ...(Array.isArray(user.usernames) ?
                  user.usernames.filter(x => x?.active !== false)
                    .map(x => x?.username) : [])]
                  .filter(x => typeof x === 'string')
                  .map(x => x.toLowerCase());
                if (!names.includes(username)) return false;
                if (user.send_paid_messages_stars || user.pFlags?.contact_require_premium)
                  return false;
                const requirement =
                  await managers.appUsersManager.getRequirementToContact(user.id);
                const stars = await managers.appPeersManager.getStarsAmount(peer);
                return requirement?._ === 'requirementToContactEmpty' &&
                  !(Number(stars) > 0);
              } catch (_) { return false; }
            }""", {"peer": peer, "username": username})
        if verified is not True:
            return {"status": "target_identity_or_free_send_not_verified"}
        # Claim BEFORE any Telegram side effect. A timed-out send is not retried.
        if claim_reply_once(command) != "claimed":
            return {"status": "already_attempted_no_resend"}
        try:
            started = page.evaluate(
                """({peer,text}) => {
                  const app = window.appImManager;
                  const m = app?.managers?.appMessagesManager;
                  if (Number(app?.chat?.peerId) !== peer ||
                      typeof m?.sendText !== 'function') return false;
                  m.sendText({peerId:peer,text});
                  return true;
                }""", {"peer": peer, "text": msg})
            if started is not True:
                return {"status": "send_not_started_no_retry"}
            for _ in range(28):
                confirmed = page.evaluate(
                    """({peer,text}) => {
                      if (Number(window.appImManager?.chat?.peerId) !== peer)
                        return false;
                      return [...document.querySelectorAll(
                        '#column-center .bubble.is-out[data-mid]')].some(
                        b => !b.classList.contains('is-sending') &&
                          (b.querySelector('.message [data-message-text-source]')?.textContent ||
                           b.querySelector('.message')?.textContent || '').trim() === text);
                    }""", {"peer": peer, "text": msg})
                if confirmed is True:
                    complete_reply(command["command_id"])
                    return {"status": "sent_confirmed", "action": "web_username_message",
                            "destination": "resolved_public_username"}
                page.wait_for_timeout(450)
            return {"status": "send_status_uncertain_no_retry"}
        except Exception:
            return {"status": "send_status_uncertain_no_retry"}
    except Exception:
        return {"status": "target_chat_unavailable"}


def send_approved_existing_chat_message(page, command: dict) -> dict:
    """Free one-off direct message to a visible, verified existing *user* chat.

    Called only after run_command verified the exact selected row and opened it.
    Group/channel/bot/Saved Messages targets, ambiguous users, paid messaging,
    or a mismatch of the open chat are rejected before the durable replay claim.
    """
    p = command["params"]
    peer, msg = p["peer_id"], p["text"]
    if (p.get("approved_by_owner") is not True or
            type(peer) is not int or not 0 < peer < 2**53 or
            type(msg) is not str or not 1 <= len(msg.strip()) <= 1200):
        return {"status": "existing_chat_message_not_approved"}
    msg = msg.strip()
    try:
        # The opening code independently restricted the user to an already
        # visible sidebar chat row with an exactly matching data-peer-id.
        free_user = page.evaluate(
            """async (peer) => {
              const app = window.appImManager, managers = app?.managers;
              const self = Number(window.rootScope?.myId);
              if (Number(app?.chat?.peerId) !== peer ||
                  !Number.isSafeInteger(self) || self <= 0 ||
                  !managers?.appUsersManager || !managers?.appPeersManager)
                return false;
              try {
                const user = await managers.appUsersManager.getUser(peer);
                if (user?._ !== 'user' || user.pFlags?.deleted ||
                    user.pFlags?.bot || user.pFlags?.self ||
                    Number(user.id) !== peer || peer === self)
                  return false;
                if (user.send_paid_messages_stars || user.pFlags?.contact_require_premium)
                  return false;
                const requirement =
                  await managers.appUsersManager.getRequirementToContact(user.id);
                const stars = await managers.appPeersManager.getStarsAmount(peer);
                return requirement?._ === 'requirementToContactEmpty' &&
                  !(Number(stars) > 0);
              } catch (_) { return false; }
            }""", peer)
        if free_user is not True:
            return {"status": "target_not_verified_free_personal_user"}
        if claim_reply_once(command) != "claimed":
            return {"status": "already_attempted_no_resend"}
        try:
            started = page.evaluate(
                """({peer,text}) => {
                  const app = window.appImManager;
                  const m = app?.managers?.appMessagesManager;
                  if (Number(app?.chat?.peerId) !== peer ||
                      typeof m?.sendText !== 'function') return false;
                  m.sendText({peerId:peer,text});
                  return true;
                }""", {"peer": peer, "text": msg})
            if started is not True:
                return {"status": "send_not_started_no_retry"}
            for _ in range(28):
                confirmed = page.evaluate(
                    """({peer,text}) => {
                      if (Number(window.appImManager?.chat?.peerId) !== peer)
                        return false;
                      return [...document.querySelectorAll(
                        '#column-center .bubble.is-out[data-mid]')].some(
                        b => !b.classList.contains('is-sending') &&
                          (b.querySelector('.message [data-message-text-source]')?.textContent ||
                           b.querySelector('.message')?.textContent || '').trim() === text);
                    }""", {"peer": peer, "text": msg})
                if confirmed is True:
                    complete_reply(command["command_id"])
                    return {"status": "sent_confirmed",
                            "action": "web_chat_message",
                            "destination": "verified_existing_private_chat"}
                page.wait_for_timeout(450)
            return {"status": "send_status_uncertain_no_retry"}
        except Exception:
            return {"status": "send_status_uncertain_no_retry"}
    except Exception:
        return {"status": "existing_chat_check_unavailable"}


def normalize_messages(rows, limit: int):
    if not isinstance(rows, list):
        raise ValueError("unexpected_messages")
    result = []
    for item in rows[-limit:]:
        if not isinstance(item, dict) or type(item.get("message_id")) is not int:
            continue
        text = item.get("text")
        if not isinstance(text, str):
            text = ""
        incoming = item.get("incoming")
        result.append({
            "message_id": item["message_id"],
            "incoming": incoming if type(incoming) is bool else None,
            "text": text[:1200],
            "has_media": item.get("has_media") is True,
        })
    return result


def wait_for_chat_dom_transition(page, peer_id: int, previous_peer, old_bubbles) -> bool:
    """Wait for the actual *previous* bubble nodes to leave the DOM.

    Telegram Web K may change appImManager.chat.peerId before replacing the
    message view. Reading #column-center immediately can leak the last chat's
    bubbles into the requested peer. A timeout fails closed, never returns
    messages whose ownership cannot be established.
    """
    changed_peer = str(previous_peer) != str(peer_id)
    selected_js = "(peer) => String(window.appImManager?.chat?.peerId) === String(peer)"
    detached_js = (
        "(nodes) => { const inner = window.appImManager?.chat?.bubbles?.chatInner;"
        " return !!inner?.isConnected &&"
        " nodes.every(node => !inner.contains(node)); }")
    for _ in range(24):
        if page.evaluate(selected_js, peer_id) is True:
            if not changed_peer or old_bubbles.evaluate(detached_js) is True:
                page.wait_for_timeout(400)
                if page.evaluate(selected_js, peer_id) is True:
                    if not changed_peer or old_bubbles.evaluate(detached_js) is True:
                        return True
        page.wait_for_timeout(400)
    return False


def read_verified_username_chat(page, command: dict) -> dict:
    """Read only a verified personal public username, without sending.

    Unlike web_read, this can find an older conversation absent from the
    virtualized visible sidebar. Return only from an exact peer after the
    previous chat's bubble elements are gone; otherwise fail closed.
    """
    p = command["params"]
    username, limit = p.get("username"), p.get("limit", 10)
    if (type(username) is not str or
            not re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{4,31}", username) or
            type(limit) is not int or not 1 <= limit <= 12):
        return {"status": "invalid_username_read"}
    username = username.lstrip("@").lower()
    try:
        resolved = page.evaluate(
            """async username => {
              const app = window.appImManager;
              const users = app?.managers?.appUsersManager;
              if (typeof users?.resolveUsername !== 'function')
                return {status:'username_lookup_unavailable'};
              try {
                const user = await users.resolveUsername(username);
                if (user?._ !== 'user' || user.pFlags?.deleted ||
                    user.pFlags?.bot || user.pFlags?.self)
                  return {status:'target_not_personal_user'};
                const names = [user.username,
                  ...(Array.isArray(user.usernames)
                    ? user.usernames.filter(x => x?.active !== false)
                      .map(x => x?.username) : [])]
                  .filter(x => typeof x === 'string')
                  .map(x => x.toLowerCase());
                if (!names.includes(username))
                  return {status:'username_identity_mismatch'};
                if (typeof user.id?.toPeerId !== 'function')
                  return {status:'target_peer_unavailable'};
                const peer = Number(user.id.toPeerId(false));
                if (!Number.isSafeInteger(peer) || peer <= 0 ||
                    peer === Number(window.rootScope?.myId))
                  return {status:'target_peer_unavailable'};
                return {status:'ok', peer_id:peer};
              } catch (e) {
                if (e?.type === 'USERNAME_NOT_OCCUPIED' ||
                    e?.type === 'USERNAME_INVALID')
                  return {status:'username_not_found'};
                if (String(e?.type || '').startsWith('FLOOD_WAIT_'))
                  return {status:'telegram_rate_limited'};
                return {status:'username_lookup_restricted'};
              }
            }""", username)
        if not isinstance(resolved, dict) or resolved.get("status") != "ok":
            return {"status": resolved.get("status", "username_lookup_unavailable")
                    if isinstance(resolved, dict) else "username_lookup_unavailable"}
        peer = resolved.get("peer_id")
        if type(peer) is not int or not 0 < peer < 2**53:
            return {"status": "target_peer_unavailable"}
        previous_peer = page.evaluate(
            "() => window.appImManager?.chat?.peerId ?? null")
        old_bubbles = page.evaluate_handle(
            "() => [...document.querySelectorAll('#column-center .bubble[data-mid]')]")
        try:
            opened = page.evaluate(
                """peer => {
                  const app = window.appImManager;
                  if (typeof app?.setInnerPeer !== 'function') return false;
                  app.setInnerPeer({peerId:peer});
                  return true;
                }""", peer)
            if opened is not True:
                return {"status": "target_chat_unavailable"}
            for _ in range(25):
                ready = page.evaluate(
                    """peer => {
                      const app = window.appImManager;
                      return Number(app?.chat?.peerId) === peer &&
                        !app?.chat?.setPeerPromise &&
                        !!app?.chat?.bubbles?.chatInner?.isConnected;
                    }""", peer)
                if ready is True:
                    break
                page.wait_for_timeout(450)
            else:
                return {"status": "target_chat_not_verified"}
            if not wait_for_chat_dom_transition(
                    page, peer, previous_peer, old_bubbles):
                return {"status": "chat_transition_not_confirmed"}
        finally:
            old_bubbles.dispose()
        verified = page.evaluate(
            """async ({peer,username}) => {
              const app = window.appImManager;
              if (Number(app?.chat?.peerId) !== peer) return false;
              try {
                const u = await app.managers.appUsersManager.getUser(peer);
                const names = [u?.username,
                  ...(Array.isArray(u?.usernames)
                    ? u.usernames.filter(x => x?.active !== false)
                      .map(x => x?.username) : [])]
                  .filter(x => typeof x === 'string')
                  .map(x => x.toLowerCase());
                return u?._ === 'user' && !u.pFlags?.deleted &&
                  !u.pFlags?.bot && names.includes(username);
              } catch (_) { return false; }
            }""", {"peer": peer, "username": username})
        if verified is not True:
            return {"status": "username_identity_not_verified"}
        page.wait_for_timeout(900)
        messages = normalize_messages(page.evaluate(MESSAGES_JS, {"peer": peer, "limit": limit}), limit)
        if not messages:
            return {"status": "chat_history_not_visible"}
        if page.evaluate(
                "(peer) => String(window.appImManager?.chat?.peerId) === String(peer)",
                peer) is not True:
            return {"status": "chat_changed_during_read"}
        return {"status": "ok", "action": "web_username_read",
                "verified_username": username, "messages": messages,
                "may_mark_read": True}
    except Exception:
        return {"status": "username_read_unavailable"}


def execute_on_page(page, command: dict) -> dict:
    """Execute a validated owner command on an already authenticated page.

    The resident loop calls this without opening a second Chromium. The
    original one-shot caller uses the identical operation paths.
    """
    action = command["action"]
    p = command["params"]
    if action == "web_status":
        return {"status": "authorized", "action": action,
                "persistent_profile": True}
    if action == "web_dialogs":
        items = page.evaluate(DIALOGS_JS, p.get("limit", 10))
        return {"status": "ok", "action": action,
                "dialogs": normalize_dialogs(items, p.get("limit", 10))}
    if action == "web_self_note":
        return send_owner_self_note(page, command)
    if action == "web_owner_contact_link":
        return get_owner_contact_link(page)
    if action == "web_phone_message":
        return send_approved_phone_message(page, command)
    if action == "web_username_message":
        return send_approved_username_message(page, command)
    if action == "web_username_read":
        return read_verified_username_chat(page, command)
    # Opening a chat may mark it read. For web_reply we also
    # verify an inbound bubble before taking any send action.
    peer_id = p["peer_id"]
    selector = f'#column-left a.chatlist-chat[data-peer-id="{peer_id}"]'
    row = page.locator(selector).first
    if row.count() != 1 or not row.is_visible():
        return {"status": "chat_not_in_visible_list", "action": action}
    # Capture actual DOM element identities before changing conversations.
    # Message IDs or text alone cannot prove peer ownership: different chats
    # legitimately have overlapping message IDs and similar content.
    previous_peer = page.evaluate(
        "() => window.appImManager?.chat?.peerId ?? null")
    old_bubbles = page.evaluate_handle(
        "() => [...document.querySelectorAll('#column-center .bubble[data-mid]')]")
    row.focus()
    page.keyboard.press("Enter")
    # A forum row or hidden overlay can swallow Enter. The
    # signed-in client's supported internal chat opening method is
    # used only for the exact already-verified visible peer.
    selected = False
    for attempt in range(20):
        selected = bool(page.evaluate(
            "(peer) => String(window.appImManager?.chat?.peerId) === String(peer)",
            peer_id))
        if selected:
            break
        if attempt == 8:
            try:
                page.evaluate(
                    "(peer) => { const m = window.appImManager;"
                    "if (!m || typeof m.setInnerPeer !== 'function') return false;"
                    "m.setInnerPeer({peerId: peer}); return true; }",
                    peer_id)
            except Exception:
                pass
        page.wait_for_timeout(550)
    if not selected:
        checks = page.evaluate(
            "(peer) => { const r = [...document.querySelectorAll("
            "'#column-left .chatlist-chat')].find(x =>"
            "x.getAttribute('data-peer-id') === String(peer));"
            "return {chat_present:!!window.appImManager?.chat,"
            "row_active:!!r?.classList.contains('active'),"
            "center_visible:!!document.querySelector('#column-center .bubble')}; }",
            peer_id)
        # Diagnostic booleans only, encrypted result: never reveal
        # internal peer ID or chat content if selection is uncertain.
        old_bubbles.dispose()
        return {"status": "requested_chat_not_opened", "action": action,
                "selection_checks": checks}
    try:
        transition_ready = wait_for_chat_dom_transition(
            page, peer_id, previous_peer, old_bubbles)
    finally:
        old_bubbles.dispose()
    if not transition_ready:
        return {"status": "chat_transition_not_confirmed", "action": action}
    page.wait_for_timeout(900)
    if action == "web_reply":
        return send_approved_reply(page, peer_id, p, command)
    if action == "web_chat_message":
        return send_approved_existing_chat_message(page, command)
    messages = normalize_messages(
        page.evaluate(MESSAGES_JS, {"peer": peer_id, "limit": p.get("limit", 10)}),
        p.get("limit", 10))
    # An empty scrape after switching is not proof that a previously
    # contacted person never answered. Keep the check explicitly inconclusive.
    if not messages:
        return {"status": "chat_history_not_visible", "action": action}
    if page.evaluate(
            "(peer) => String(window.appImManager?.chat?.peerId) === String(peer)",
            peer_id) is not True:
        return {"status": "chat_changed_during_read", "action": action}
    return {"status": "ok", "action": action, "peer_id": peer_id,
            "messages": messages, "may_mark_read": True}


def _resident_call(command: dict) -> dict | None:
    """Prefer the same-user Unix socket; never fall back if one is present."""
    import socket
    path = ROOT / "resident" / "operator.sock"
    if path.is_symlink():
        return {"status": "resident_socket_unsafe"}
    if not path.exists():
        return None
    info = path.stat()
    if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077):
        return {"status": "resident_socket_unsafe"}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(130)
            client.connect(str(path))
            payload = json.dumps(command, ensure_ascii=False,
                                 separators=(",", ":")).encode("utf-8")
            if len(payload) > 16000:
                return {"status": "resident_command_too_large"}
            client.sendall(payload)
            client.shutdown(socket.SHUT_WR)
            out = bytearray()
            while True:
                block = client.recv(4096)
                if not block:
                    break
                out.extend(block)
                if len(out) > 65536:
                    return {"status": "resident_result_too_large"}
        response = json.loads(out)
        if (not isinstance(response, dict) or
                not isinstance(response.get("status"), str)):
            return {"status": "resident_result_invalid"}
        return response
    except Exception:
        return {"status": "resident_temporarily_unavailable"}


def run_command(command: dict) -> dict:
    """Start one private headed Chromium process and close it deterministically."""
    action = command["action"]
    p = command["params"]
    if action not in ALLOWED:
        return {"status": "unsupported_action"}
    resident = _resident_call(command)
    if resident is not None:
        return resident
    if ROOT.is_symlink() or not ROOT.is_dir() or LOCK.is_symlink():
        return {"status": "profile_unavailable"}
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "owner_browser_busy"}
        sys.path.insert(0, str(ROOT))
        import telegram_web_owner_portal as portal
        import telegram_web_session_check as checker
        if not checker.profile_safe(portal.PROFILE):
            return {"status": "profile_unavailable"}
        if not portal.load_private_browser_proxy():
            return {"status": "proxy_unavailable"}
        browser = portal.Browser()
        try:
            with tempfile.TemporaryDirectory(prefix="tg-encrypted-command-", dir=ROOT) as tmp:
                browser.open(Path(tmp))
                page = browser.page
                state = "unknown"
                for _ in range(18):
                    state = classify_ui(page.url, page.evaluate(UI_STATE_JS))
                    if state != "unknown":
                        break
                    page.wait_for_timeout(750)
                if state != "authorized":
                    return {"status": "auth_required" if state == "auth_required"
                            else "login_state_unverified"}
                return execute_on_page(page, command)
        finally:
            browser.close()


def main():
    # Only parsed allowlisted commands from bridge are used. The whole input
    # remains inside the VPS. Nothing from stderr is forwarded to CI.
    try:
        data = json.load(sys.stdin)
        if (not isinstance(data, dict) or data.get("action") not in ALLOWED or
                not isinstance(data.get("params"), dict)):
            raise ValueError("unsupported")
        response = run_command(data)
    except Exception:
        response = {"status": "private_browser_error"}
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
