#!/usr/bin/env python3
"""FL-003 bounded evidence demo: public product pages and a synthetic .eml fixture.

Never opens a personal mailbox, sends mail, purchases, writes on marketplaces,
uses user cookies, or calls paid model APIs. Live product checks are explicitly
fail-closed when anti-bot rules prevent a verifiable read.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlparse

SCHEMA = "fl003.client.demo.v1"
TASK = "Подобрать беспроводную мышь Logitech M185, сравнить предложения и подготовить ответ на письмо о покупке"
CARD_SOURCES = (
    {"marketplace": "Ozon", "url": "https://www.ozon.ru/product/logitech-m185-m186-besprovodnaya-mysh-sinyaya-7231897/", "expected": "m185"},
    {"marketplace": "Avito", "url": "https://www.avito.ru/sankt-peterburg/tovary_dlya_kompyutera/besprovodnaya_mysh_logitech_m185_8049018171", "expected": "m185"},
)
ALLOWED_HOSTS = {"www.ozon.ru", "ozon.ru", "www.avito.ru", "avito.ru", "m.avito.ru"}
GATE_WORDS = ("нужна небольшая проверка браузера", "пройти проверку", "страница не загрузилась из-за проблем с ip", "проверьте, что вы человек", "доступ ограничен", "подозрительная активность", "капча", "captcha", "access denied", "access blocked", "attention required", "доступ запрещён")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_synthetic_mail() -> bytes:
    """Create a non-personal .eml with a real CSV attachment in memory."""
    msg = EmailMessage()
    msg["From"] = "buyer@example.invalid"
    msg["To"] = "assistant@example.invalid"
    msg["Subject"] = "Запрос на подбор Logitech M185"
    msg.set_content(
        "Здравствуйте! Подберите Logitech M185 с USB-приёмником для офиса. "
        "Бюджет не более 2 000 рублей за штуку. Сравните Ozon и Авито, "
        "учтите состояние и доставку. Подготовьте ответ, но ничего не отправляйте. "
        "Требования приложены в CSV."
    )
    spec = "модель;интерфейс;количество;лимит_за_шт_руб\nLogitech M185;USB-приёмник;2;2000\n"
    msg.add_attachment(spec.encode("utf-8"), maintype="text", subtype="csv", filename="requirements.csv")
    return msg.as_bytes(policy=policy.default)


def parse_mail(raw: bytes) -> dict:
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    subject = str(msg.get("subject") or "")
    content = msg.get_body(preferencelist=("plain",))
    body = content.get_content() if content else ""
    attachments = []
    for part in msg.iter_attachments():
        fname = part.get_filename() or "unnamed"
        if not fname.lower().endswith(".csv"):
            attachments.append({"file": fname, "status": "unsupported_file_type"})
            continue
        payload = part.get_payload(decode=True) or b""
        if len(payload) > 100_000:
            attachments.append({"file": fname, "status": "too_large"})
            continue
        decoded = payload.decode("utf-8-sig", errors="strict")
        reader = csv.DictReader(io.StringIO(decoded), delimiter=";")
        rows = list(reader)
        expected = {"модель", "интерфейс", "количество", "лимит_за_шт_руб"}
        if not rows or not expected.issubset(set(rows[0])):
            attachments.append({"file": fname, "status": "invalid_format"})
            continue
        entries = []
        for row in rows[:10]:
            try:
                quantity = int(row["количество"])
                cap = int(row["лимит_за_шт_руб"])
                if quantity < 1 or cap < 1:
                    raise ValueError()
            except ValueError:
                attachments.append({"file": fname, "status": "invalid_numeric_data"})
                break
            entries.append({"model": row["модель"], "interface": row["интерфейс"],
                            "quantity": quantity, "cap_per_item_rub": cap})
        else:
            attachments.append({"file": fname, "status": "parsed", "rows": entries})
    good = next((a for a in attachments if a.get("status") == "parsed"), None)
    return {"kind": "synthetic_email_fixture", "subject": subject, "body": body,
            "attachments": attachments,
            "structured_requirements": good["rows"] if good else [],
            "mail_sent": False, "mailbox_accessed": False}


def product_jsonld(page) -> list[dict]:
    out = []
    for node in page.locator('script[type="application/ld+json"]').all()[:12]:
        try:
            parsed = json.loads(node.inner_text(timeout=1000))
        except Exception:
            continue
        todo = parsed if isinstance(parsed, list) else [parsed]
        while todo:
            item = todo.pop()
            if isinstance(item, list):
                todo.extend(item)
            elif isinstance(item, dict):
                if "@graph" in item:
                    todo.append(item["@graph"])
                k = item.get("@type")
                if k == "Product" or isinstance(k, list) and "Product" in k:
                    out.append(item)
    return out[:3]


def best_price(product: dict) -> tuple[int | float | None, str]:
    offers = product.get("offers") or []
    if isinstance(offers, dict):
        offers = [offers]
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        currency = offer.get("priceCurrency")
        price = offer.get("price") or offer.get("lowPrice")
        if currency in ("RUB", "RUR") and price is not None:
            try:
                value = float(str(price).replace(" ", "").replace(",", "."))
                if 1 <= value <= 10_000_000:
                    return value, "product_jsonld_rub"
            except ValueError:
                pass
    return None, "unverified"


def inspect_card(page, source: dict) -> dict:
    result = {"marketplace": source["marketplace"], "source_url": source["url"],
              "checked_at_utc": now_utc(), "status": "unverified", "price_rub": None,
              "price_evidence": "unverified", "seller": None, "title": None, "read_only": True}
    try:
        target = urlparse(source["url"])
        if target.scheme != "https" or target.hostname not in ALLOWED_HOSTS:
            return {**result, "status": "invalid_source_url"}
        response = page.goto(source["url"], wait_until="domcontentloaded", timeout=16000)
        page.wait_for_timeout(1600)
        result["http_status"] = response.status if response else None
        result["final_url"] = page.url
        if urlparse(page.url).hostname not in ALLOWED_HOSTS:
            return {**result, "status": "unexpected_redirect"}
        title = page.title()[:180]
        result["title"] = title
        text = page.locator("body").inner_text(timeout=4000)[:7000]
        if result["http_status"] in (401, 403, 429, 439) or any(word in text.lower() for word in GATE_WORDS):
            result["status"] = "site_access_or_human_login_required"
            return result
        if result["http_status"] is None or result["http_status"] >= 400:
            result["status"] = "http_error_not_a_verified_product_page"
            return result
        expected = source["expected"].lower()
        products = product_jsonld(page)
        product = next((p for p in products if expected in str(p.get("name", "")).lower()), None)
        if product is None and expected not in (title + " " + text[:1200]).lower():
            result["status"] = "product_identity_not_verified"
            return result
        result["title"] = str(product.get("name") or title)[:180] if product else title
        if product:
            price, evidence = best_price(product)
            result["price_rub"] = price
            result["price_evidence"] = evidence
            offers = product.get("offers") or {}
            offer = offers[0] if isinstance(offers, list) and offers else offers
            if isinstance(offer, dict):
                seller = offer.get("seller")
                if isinstance(seller, dict):
                    result["seller"] = str(seller.get("name") or "")[:80] or None
        result["status"] = "verified_price_and_card" if result["price_rub"] is not None else "verified_identity_price_unknown"
        return result
    except Exception as exc:
        # No local paths, cookies, or stack traces in public CI logs.
        result["status"] = "browser_error_or_timeout"
        result["error_class"] = type(exc).__name__
        return result


def shop_live(sources=CARD_SOURCES) -> dict:
    from playwright.sync_api import sync_playwright
    output = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            context = browser.new_context(locale="ru-RU", timezone_id="Europe/Moscow", viewport={"width": 1280, "height": 860})
            for source in sources:
                page = context.new_page()
                try:
                    output.append(inspect_card(page, source))
                finally:
                    page.close()
            context.close()
        finally:
            browser.close()
    return {"source": "live_public_pages", "browser_on_server": True,
            "products": output,
            "full_comparison_verified": len(output) >= 2 and all(x["status"] == "verified_price_and_card" for x in output),
            "login_or_antibot_bypass_attempted": False, "purchase_performed": False}


def draft_reply(mail: dict, shop: dict) -> dict:
    reqs = mail["structured_requirements"]
    lines = ["Здравствуйте!", "", "Получил запрос на подбор Logitech M185 и требования из вложения."]
    if reqs:
        r = reqs[0]
        lines.append(f"Требуется: {r['quantity']} шт., {r['interface']}, бюджет до {r['cap_per_item_rub']} ₽ за штуку.")
    verified = [p for p in shop["products"] if p.get("status") == "verified_price_and_card"]
    if len(verified) >= 2:
        lines.append("Проверенные на момент просмотра предложения:")
        for p in verified:
            lines.append(f"— {p['marketplace']}: {p['title']} — {int(p['price_rub'])} ₽; {p['source_url']}")
        lines.append("Перед покупкой следует отдельно проверить доставку, состояние и продавца.")
    else:
        lines.append("Пока не могу достоверно сравнить цены с двух площадок: актуальные карточки/цены доступны не полностью.")
        for p in shop["products"]:
            lines.append(f"— {p['marketplace']}: {p['source_url']} (статус: {p['status']}; цена НЕ подтверждена)")
        lines.append("Для завершения нужна разрешённая проверка карточек в браузере; при запросе сайта — ручное участие владельца.")
    lines.extend(["", "Это черновик. Отправка и покупка не выполнялись."])
    text = "\n".join(lines)
    return {"status": "draft_only_approval_required", "text": text,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "approval_required": True, "sent": False, "llm_generated": False,
            "model_used": "none_rule_based_extract_and_template"}


def run(offline=False) -> dict:
    mail = parse_mail(create_synthetic_mail())
    if offline:
        shop = {"source": "offline_fixture_no_live_product_check", "browser_on_server": False,
                "products": [{"marketplace": s["marketplace"], "source_url": s["url"],
                              "status": "not_checked_offline", "price_rub": None} for s in CARD_SOURCES],
                "full_comparison_verified": False, "purchase_performed": False}
    else:
        try:
            shop = shop_live()
        except Exception as exc:
            shop = {"source": "live_probe_failed", "browser_on_server": False,
                    "error_class": type(exc).__name__,
                    "products": [{"marketplace": s["marketplace"], "source_url": s["url"],
                                  "status": "browser_unavailable", "price_rub": None} for s in CARD_SOURCES],
                    "full_comparison_verified": False, "purchase_performed": False}
    reply = draft_reply(mail, shop)
    return {"schema": SCHEMA, "checked_at_utc": now_utc(), "task": TASK,
            "workstation_needed": False,
            "mode": "offline_fixture" if offline else "vps_live_page_checks",
            "mail": mail, "shopping": shop, "reply": reply,
            "telegram_connected": False, "private_mailbox_connected": False,
            "kimi_api_called": False,
            "external_write_actions": 0, "external_messages_sent": 0,
            "client_facing_full_demo_ready": bool(shop["full_comparison_verified"] and not offline)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--out", type=Path, help="Optional restricted report path")
    parser.add_argument("--print-full", action="store_true", help="Print full synthetic-only result for evidence artifact")
    args = parser.parse_args()
    report = run(args.offline)
    if args.out:
        target = args.out.expanduser()
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.is_symlink():
            raise SystemExit("symlink_output_blocked")
        fd = os.open(target, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    if args.print_full:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if report["mail"]["structured_requirements"] and report["external_write_actions"] == 0 else 1
    print(json.dumps({"schema": SCHEMA, "checked_at_utc": report["checked_at_utc"],
                      "mode": report["mode"], "workstation_needed": False,
                      "attachment_parsed": bool(report["mail"]["structured_requirements"]),
                      "product_statuses": [{"marketplace": p["marketplace"], "status": p["status"],
                                            "price_rub": p.get("price_rub")}
                                           for p in report["shopping"]["products"]],
                      "full_comparison_verified": report["shopping"]["full_comparison_verified"],
                      "draft_awaits_approval": report["reply"]["approval_required"],
                      "external_messages_sent": 0, "private_mailbox_connected": False,
                      "telegram_connected": False, "kimi_api_called": False},
                     ensure_ascii=False, sort_keys=True))
    return 0 if report["mail"]["structured_requirements"] and report["external_write_actions"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
