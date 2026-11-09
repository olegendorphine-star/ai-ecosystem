#!/usr/bin/env python3
"""Read-only FL.ru owner service moderation check. No account or message writes.

Runs only through the owner's existing isolated VPS Chromium. Only booleans
and counts are printed. Never print cookies, page text, email or browser state.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path.home() / ".fl-agent"
OWNER_SETTINGS = "https://www.fl.ru/users/olegendorphine/setup/main/"
OWNER_SERVICES = "https://www.fl.ru/users/olegendorphine/uslugi-freelancera/"
OWNER_PORTFOLIO = "https://www.fl.ru/users/olegendorphine/portfolio/"

def main() -> None:
    result = {
        "schema": "fl.owner.services.moderation.readonly.v1",
        "account": "olegendorphine",
        "status": "unavailable",
        "verified_owner": False,
        "write_actions": False,
        "customer_messages_opened": False,
        "payment_actions": False,
        "service_page_http": None,
        "service_audit_present": False,
        "service_tz_present": False,
        "review_label_count": 0,
        "approved_label_count": 0,
        "rejected_label_count": 0,
        "buyer_price_6500_visible": False,
        "buyer_price_15600_visible": False,
        "portfolio_page_http": None,
        "portfolio_work_count": 0,
    }
    browser = None
    try:
        if not ROOT.is_dir():
            result["status"] = "browser_state_missing"
            return
        sys.path.insert(0, str(ROOT))
        from fl_rootless_owner_desktop import Browser, is_fl_url
        browser = Browser()
        with tempfile.TemporaryDirectory(prefix="fl-moderation-readonly-", dir=ROOT) as tmp:
            browser.open(Path(tmp))
            page = browser.page
            response = page.goto(OWNER_SETTINGS, wait_until="domcontentloaded", timeout=25000)
            signs = page.evaluate("""() => ({
                owner: Array.from(document.querySelectorAll('input')).some(
                  el => (el.value || '').trim().toLowerCase() === 'olegendorphine@gmail.com'),
                settings: (document.body?.innerText || '').includes('Основные настройки')
            })""")
            if not (response and response.status == 200 and is_fl_url(page.url)
                    and signs.get("owner") and signs.get("settings")):
                result["status"] = "owner_verification_failed"
                return
            result["verified_owner"] = True
            response = page.goto(OWNER_SERVICES, wait_until="domcontentloaded", timeout=25000)
            if not (response and response.status == 200 and is_fl_url(page.url)):
                result["status"] = "service_page_unavailable"
                return
            result["service_page_http"] = response.status
            page.wait_for_timeout(600)
            service = page.evaluate("""() => {
                const t = document.body?.innerText || '';
                const count = re => (t.match(re) || []).length;
                return {
                  audit: t.includes('Аудит одного процесса') || t.includes('Аудит процесса и карта'),
                  tz: t.includes('ТЗ на персонального ИИ-ассистента') || t.includes('техническое задание на персонального ИИ'),
                  review: count(/На проверке|На модерации|Ожидает модерации/gi),
                  approved: count(/Одобрено|Опубликовано/gi),
                  rejected: count(/Отклонено|Не прошло модерацию/gi),
                  p6500: t.includes('6 500') || t.includes('6500'),
                  p15600: t.includes('15 600') || t.includes('15600')
                };
            }""")
            result.update({
                "service_audit_present": bool(service.get("audit")),
                "service_tz_present": bool(service.get("tz")),
                "review_label_count": min(int(service.get("review") or 0), 20),
                "approved_label_count": min(int(service.get("approved") or 0), 20),
                "rejected_label_count": min(int(service.get("rejected") or 0), 20),
                "buyer_price_6500_visible": bool(service.get("p6500")),
                "buyer_price_15600_visible": bool(service.get("p15600"))
            })
            response = page.goto(OWNER_PORTFOLIO, wait_until="domcontentloaded", timeout=25000)
            if response and response.status == 200 and is_fl_url(page.url):
                result["portfolio_page_http"] = response.status
                labels = page.evaluate("""() => {
                    const t = document.body?.innerText || '';
                    return [
                        t.includes('Персональный ИИ-Штаб: память, документы и контроль'),
                        t.includes('Автономный браузер на VPS и контроль сессий'),
                        t.includes('ИИ-документооборот: связи, анализ и полезные сигналы')
                    ];
                }""")
                result["portfolio_work_count"] = sum(bool(x) for x in labels)
            result["status"] = "ok"
    except Exception:
        result["status"] = "technical_error"
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                result["status"] = "technical_error"
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    main()
