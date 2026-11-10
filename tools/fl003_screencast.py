#!/usr/bin/env python3
"""Real, timestamped VPS Chromium screencast for FL-003.

Records actual navigation to the two allowlisted marketplace cards, plus real
MIME CSV+DOCX parsing of an explicitly synthetic email. No external writes.
Never substitutes indexed prices or fixtures for verified product facts.
"""
import argparse
import html
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
from fl003_client_demo import (
    CARD_SOURCES, create_synthetic_mail, parse_mail, inspect_card, draft_reply
)
from fl003_yandex_marketplace_search import is_product_card

def render(title, content, accent="#74b6ff"):
    return ("""<!doctype html><html lang="ru"><meta charset="utf-8">
    <style>
      body{background:#101b2a;color:#eff5ff;font:23px/1.6 Arial, sans-serif;
      padding:48px;margin:0} h1{color:%s;font-size:35px;margin:0 0 18px}
      h2{font-size:25px;margin:20px 0 8px}
      .panel{background:#1d3047;padding:22px;border-radius:16px}
      .small{font-size:17px;color:#bacbdd} .bad{color:#ffd28b}
      code{color:#99dafa} pre{white-space:pre-wrap;font:17px/1.55 monospace}
      .tag{display:inline-block;padding:4px 14px;border:1px solid #7590a6;border-radius:20px;font-size:16px}
    </style><h1>%s</h1><div class="panel">%s</div></html>"""
    % (accent,html.escape(title),content))

def text(s):
    return html.escape(str(s))

def load_search_evidence(path):
    """Read pre-fetched Yandex Search API evidence; never treat index data as live."""
    if not path:
        return None, CARD_SOURCES
    raw=json.loads(Path(path).read_text(encoding="utf8"))
    if raw.get("schema") != "fl003.yandex.search.index.v1":
        raise ValueError("unsupported_yandex_evidence")
    chosen=[]
    counts={}
    for marketplace in ("Ozon","Avito"):
        match=next((m for m in raw.get("marketplaces",[])
                    if m.get("marketplace")==marketplace),None)
        if not match or match.get("status")!="found":
            raise ValueError("yandex_search_missing_marketplace_"+marketplace.lower())
        safe=[c for c in match.get("candidates",[])
              if c.get("source_type")=="yandex_search_index"
              and c.get("live_price_verified") is False
              and is_product_card(c.get("url",""),marketplace,c.get("title",""))]
        if not safe:
            raise ValueError("yandex_candidates_not_verified_as_links_"+marketplace.lower())
        counts[marketplace]=len(safe)
        chosen.append({"marketplace":marketplace,"url":safe[0]["url"],"expected":"m185"})
    evidence={"source":"Yandex Search API v2","checked_utc":raw.get("checked_utc"),
              "filtered_candidate_counts":counts,
              "search_index_only":True,"prices_verified_by_search":False,
              "chosen_urls":[x["url"] for x in chosen]}
    return evidence, tuple(chosen)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",required=True)
    p.add_argument("--search-json",default="")
    args=p.parse_args()
    out=Path(args.output_dir).expanduser()
    if out.is_symlink():raise SystemExit("unsafe_output_symlink")
    out.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chmod(out,0o700)
    search_evidence,sources=load_search_evidence(args.search_json)
    when=datetime.now(timezone.utc).isoformat(timespec="seconds")
    report={"schema":"fl003.real.vps.screencast.v1",
            "checked_utc":when,"runtime":"isolated VPS Chromium / Playwright",
            "browser_on_vps":True,"recording_is_real_browser_session":True,
            "mail_source":"SYNTHETIC .eml with actual CSV + DOCX file bytes",
            "mailbox_connected":False,"kimi_api_called":False,
            "external_messages_sent":0,"purchases":0,"products":[],
            "search_evidence":search_evidence}
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=["--no-sandbox"])
        ctx=browser.new_context(locale="ru-RU",timezone_id="Europe/Moscow",
            viewport={"width":1280,"height":720},
            record_video_dir=str(out),record_video_size={"width":1280,"height":720})
        page=ctx.new_page()
        video=page.video
        page.set_content(render("FL-003 · Протокол живого браузера VPS",
            "<span class='tag'>Действительная сессия Playwright</span>"
            "<p>Поручение: выбрать Logitech M185 на Ozon и Авито.</p>"
            "<p class='small'>Каждый сайт открывается непосредственно из браузера сервера. "
            "Цены не подставляются из примеров. Если сайт ограничит доступ — это будет видно на записи.</p>"))
        page.wait_for_timeout(3000)
        if search_evidence:
            names=search_evidence["filtered_candidate_counts"]
            summary=("<p>Yandex Search API: Ozon — "+str(names["Ozon"])+
                     " карточек; Авито — "+str(names["Avito"])+" объявлений.</p>")
            summary+=("<p class='small'>Время индексного поиска: "+
                      text(search_evidence["checked_utc"])+"</p>")
            summary+="<p class='bad'>Ссылки найдены в поиске. Текущие цены и наличие НЕ подтверждены.</p>"
            summary+=("<p class='small'>Первый Ozon: "+text(sources[0]["url"])+
                      "</p><p class='small'>Первый Авито: "+text(sources[1]["url"])+"</p>")
            page.set_content(render("Поиск Яндекса · действительные результаты API",summary))
            page.wait_for_timeout(4500)
        for src in sources:
            page.set_content(render("Переход на "+text(src["marketplace"]),
                "<p>Открываем реальную страницу по адресу:</p><p class='small'>"+text(src["url"])+"</p>"))
            page.wait_for_timeout(1300)
            result=inspect_card(page,src)
            report["products"].append(result)
            page.wait_for_timeout(3500)
            # Show the actual extraction result AFTER showing the real site/gate.
            status=text(result.get("status"))
            price=result.get("price_rub")
            label=("%s ₽" % price) if price is not None else "НЕ ПОДТВЕРЖДЕНА"
            page.set_content(render("Проверка "+text(src["marketplace"]),
                "<p>Статус проверки: <code>"+status+"</code></p>"
                "<p>Цена: <strong class='bad'>"+text(label)+"</strong></p>"
                "<p class='small'>Источник: "+text(src["url"])+"</p>"
                "<p class='small'>Записано: "+text(result.get("checked_at_utc"))+"</p>"))
            page.wait_for_timeout(2200)
        mail=parse_mail(create_synthetic_mail())
        shop={"products":report["products"]}
        draft=draft_reply(mail,shop)
        report["mail"]={"subject":mail["subject"],"attachment_files":
            [a["file"] for a in mail["attachments"]],
            "attachment_statuses":[a["status"] for a in mail["attachments"]],
            "structured_requirements":mail["structured_requirements"],
            "draft_created":True,"draft_sent":False}
        report["draft"] = draft
        page.set_content(render("Письмо с вложениями · тестовые данные",
            "<span class='tag'>Синтетическое письмо, настоящий MIME разбор на VPS</span>"
            "<p>Тема: "+text(mail["subject"])+"</p>"
            "<p>Вложения:</p><pre>"+text("\n".join(
            a["file"]+" — "+a["status"] for a in mail["attachments"]))+"</pre>"
            "<p class='small'>Требования извлечены непосредственно из CSV и DOCX.</p>"))
        page.wait_for_timeout(3500)
        body=draft.get("text") or draft.get("body") or str(draft)
        page.set_content(render("Проект ответа · не отправлен",
            "<pre>"+text(body)[:2500]+"</pre>"
            "<p class='small'>Рабочая почта НЕ подключалась. Это обезличенный тест исходного письма.</p>"))
        page.wait_for_timeout(5000)
        verified=sum(p.get("status")=="verified_price_and_card" for p in report["products"])
        report["verified_marketplace_cards"]=verified
        report["full_client_demo_ready"]=verified==2 and False # no real mailbox or Kimi API
        page.set_content(render("Итог серверного испытания",
            "<p>Реальный VPS-браузер: <strong>запущен</strong></p>"
            "<p>Проверенные живые цены: <strong>"+str(verified)+"/2</strong></p>"
            "<p>CSV / DOCX: <strong>разобраны</strong></p>"
            "<p>Черновик: <strong>сформирован, не отправлен</strong></p>"
            "<p class='small'>Полная клиентская приёмка: НЕ ПРОЙДЕНА. "
            "Обход CAPTCHA не выполнялся. ПК владельца не использовался.</p>"))
        page.wait_for_timeout(4300)
        page.close()
        # Save while the Playwright driver/context is still alive.
        video.save_as(str(out/"fl003-actual-vps-browser.webm"))
        ctx.close()
        browser.close()
    report_path=out/"report.json"
    with report_path.open("w",encoding="utf8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({"schema":report["schema"],"video":str(out/"fl003-actual-vps-browser.webm"),
       "verified":report["verified_marketplace_cards"],
       "mail_attachments":report["mail"]["attachment_statuses"],
       "yandex_search_included":bool(search_evidence),
       "yandex_candidates":search_evidence["filtered_candidate_counts"] if search_evidence else None,
       "full_client_demo_ready":report["full_client_demo_ready"],
       "external_messages_sent":0},ensure_ascii=False))
if __name__=="__main__":main()
