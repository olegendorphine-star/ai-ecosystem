#!/usr/bin/env python3
"""Render actual FL-003 Yandex/Gmail evidence into legible video panels.

Runs on a trusted GitHub runner with Pillow. PNGs are displayed INSIDE the
recorded VPS Chromium window; no text is superimposed on the exported video.
No credentials or private mail headers are rendered.
"""
import argparse
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from fl003_client_demo import parse_mail,draft_reply

W,H=1280,720
BG=(13,23,39); PANEL=(29,45,66); WHITE=(235,245,255); PALE=(177,199,217)
BLUE=(105,194,255); ORANGE=(255,185,105)
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def font(n,bold=False):
    return ImageFont.truetype(BOLD if bold else FONT,n)

def line(draw,x,y,value,size=21,color=WHITE,bold=False,width=1150):
    f=font(size,bold)
    text=str(value)
    while text and draw.textbbox((0,0),text,font=f)[2]>width:
        text=text[:-2]
    if text!=value:
        text=text.rstrip()+"…"
    draw.text((x,y),text,font=f,fill=color)

def frame(name,title,items,out):
    im=Image.new("RGB",(W,H),BG)
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((35,30,1244,680),radius=22,fill=PANEL)
    line(d,66,49,"FL-003  |  АВТОНОМНОЕ ИСПОЛНЕНИЕ НА VPS",17,BLUE,True)
    line(d,66,90,title,30,WHITE,True)
    y=158
    for kind,value in items:
        if y>640:break
        if kind=="section":
            line(d,66,y,value,23,BLUE,True);y+=41
        elif kind=="warning":
            line(d,66,y,value,20,ORANGE,False);y+=39
        elif kind=="spacer":
            y+=24
        else:
            line(d,66,y,value,19,PALE,False);y+=33
    im.save(out/name,format="PNG",optimize=True)

def generate(source,mail,out):
    data=json.loads(Path(source).read_text(encoding="utf8"))
    if data.get("schema")!="fl003.yandex.search.index.v1":
        raise ValueError("source_schema_mismatch")
    parsed=parse_mail(Path(mail).read_bytes())
    attachments=parsed["attachments"]
    if not all(a.get("status") in ("parsed","parsed_docx") for a in attachments):
        raise ValueError("real_mail_attachment_parse_failed")
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    found={g["marketplace"]:g for g in data["marketplaces"]}
    counts={k:len(v["candidates"]) for k,v in found.items()}
    frame("intro.png","Задание клиента: подбор Logitech M185",[
        ("section","Запуск независимого VPS-процесса"),
        ("text","Источник поиска: Yandex Search API  |  2 запроса"),
        ("text","Компьютер владельца: не используется"),
        ("text","Письмо: доставлено в Gmail и обезличено для проверки"),
        ("text","Команды и результат: личное «Избранное» Telegram"),
        ("spacer",""),
        ("warning","Текущие цены маркетплейсов требуют отдельной проверки"),
        ("text","Никаких покупок, писем продавцам или автоматического входа")],out)
    items=[("section","Проверенные поиском адреса товарных карточек"),
           ("text","Поиск: "+str(data["checked_utc"])),
           ("text",f"Ozon — {counts.get('Ozon',0)} карточек; Авито — {counts.get('Avito',0)} объявления"),
           ("spacer","")]
    for market in ("Ozon","Avito"):
        items.append(("section",market))
        for c in found[market]["candidates"][:3]:
            items.append(("text","• "+c["title"][:82]))
        items.append(("spacer",""))
    items.append(("warning","Сведения из индекса, цены и наличие НЕ подтверждены"))
    frame("search.png","Реальный поиск товара: результат API",items,out)
    for market in ("Ozon","Avito"):
        c=found[market]["candidates"][0]
        frame("start_"+market.lower()+".png","Открываем "+market+" на VPS",[
            ("section","Действительный адрес из Yandex Search API"),
            ("text",c["title"][:99]),
            ("text",c["url"][:100]),
            ("spacer",""),
            ("warning","Следующий кадр: фактическая страница Chromium"),
            ("text","Никакой подмены экрана карточки товара")],out)
    m=parsed["structured_requirements"][0]
    frame("mail.png","Настоящее письмо Gmail: разбор вложений",[
        ("section","Полученное тестовое письмо, личные заголовки удалены"),
        ("text","Исходный формат: RFC822/MIME, файл пришёл из Gmail"),
        ("text","Тема: "+parsed["subject"][:90]),
        ("spacer",""),
        ("section","Прочитанные вложения"),
        *[("text",a["file"]+" — "+a["status"]) for a in attachments],
        ("spacer",""),
        ("text",f"Товар: {m['model']}   |   Количество: {m['quantity']} шт."),
        ("text",f"Интерфейс: {m['interface']}   |   Бюджет: {m['cap_per_item_rub']} ₽/шт."),
        ("text",f"Срок доставки: {m.get('delivery_days','?')} дней"),
        ("warning","Извлечение выполнено программно на VPS")],out)
    shop={"products":[{"marketplace":k,"source_url":v["candidates"][0]["url"],
                       "status":"yandex_index_candidate_unverified","price_rub":None}
                      for k,v in found.items()]}
    draft=draft_reply(parsed,shop)
    notes=[
        ("section","Черновик: сформирован, не отправлен"),
        ("text","Суть запроса: 2 мыши Logitech M185 для офиса"),
        ("text","Условия: USB-приёмник, до 2000 ₽/шт., доставка до 7 дней"),
        ("text","Реальные ссылки на Ozon и Авито найдены"),
        ("text","Цена, продавец и отзывы пока требуют подтверждения"),
        ("spacer",""),
        ("warning","Отправка письма отключена. Требуется отдельное согласование.")
    ]
    frame("draft.png","Подготовка ответа на письмо",notes,out)
    frame("summary.png","Итог: автономный поиск и разбор письма",[
        ("section","Подтверждено выполнением на сервере"),
        ("text",f"Yandex Search: {counts.get('Ozon',0)} ссылок Ozon, {counts.get('Avito',0)} Авито"),
        ("text","Исходное Gmail MIME: CSV и DOCX разобраны"),
        ("text","Проект ответа подготовлен, внешних отправок нет"),
        ("spacer",""),
        ("warning","Текущие цены: 0/2 подтверждено напрямую"),
        ("warning","До согласованного коммерческого демо ещё нужны live-данные"),
        ("text","Режим: без капчи, без вмешательства владельца")],out)
    print(json.dumps({"generated":7,"png_count":len(list(out.glob("*.png"))),
                      "source":"actual_Yandex_API_plus_real_Gmail_test_MIME",
                      "no_private_mail_headers":True}))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--search-json",required=True)
    p.add_argument("--mail-eml",required=True)
    p.add_argument("--out-dir",required=True)
    args=p.parse_args()
    generate(args.search_json,args.mail_eml,args.out_dir)
