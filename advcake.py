# advcake.py — партнёрская статистика AdvCake прямо в боте.
#
# Раньше единственным способом узнать про заказы был поход в кабинет, и
# напоминание раз в месяц только подталкивало сходить. С ключом можно не
# ходить: цифры приезжают сами.
#
# Ключ живёт в переменной окружения, а не в базе и не в коде: это доступ к
# деньгам, и ему не место там, куда я или кто-то ещё может заглянуть.
#
# Схему выгрузки я не видела — она у каждой сети своя и в открытой
# документации не описана. Поэтому разбор терпимый: ищем заказы по любым
# похожим тегам и читаем поля и из атрибутов, и из вложенных узлов. Если
# формат окажется другим, «/advcake сырое» покажет ответ как есть, и я
# поправлю разбор по факту, а не по догадке.
import logging
import os
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta

import httpx
from aiogram import Router, F
from aiogram.types import Message

import config

router = Router()

ORDERS_URL = "https://export.advcake.ru/partner/offer"
OFFERS_URL = "https://api.advcake.ru/offers"
MAX_DAYS = 7            # столько отдаёт выгрузка за один запрос
TIMEOUT = 30

ORDER_TAGS = {"order", "orders", "action", "row", "item", "conversion"}
SUM_FIELDS = ("payment", "commission", "reward", "sum", "amount", "price", "cart")
STATUS_FIELDS = ("status", "state", "action_status")
OFFER_FIELDS = ("offer", "offer_name", "advertiser", "shop")
SUB_FIELDS = ("sub1", "sub_1", "subid", "sub_id")


def _key() -> str:
    return (os.getenv("ADVCAKE_KEY") or "").strip()


def _field(node, names):
    """Поле берём и из атрибутов, и из вложенных тегов — сети пишут по-разному"""
    for name in names:
        value = node.get(name)
        if value:
            return value
        child = node.find(name)
        if child is not None and (child.text or "").strip():
            return child.text.strip()
    return ""


def _orders(xml_text: str):
    """Список заказов из ответа. Пусто — значит формат другой."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logging.warning(f"AdvCake: ответ не разобрался как XML: {e}")
        return None

    found = [node for node in root.iter()
             if node.tag.lower().rstrip("s") in {t.rstrip("s") for t in ORDER_TAGS}
             and node is not root]
    # Иногда заказы лежат прямо детьми корня без узнаваемого имени
    return found or list(root)


async def fetch(days: int = MAX_DAYS):
    """(текст ответа, ошибка). Ошибка — строкой для показа владельцу."""
    key = _key()
    if not key:
        return None, ("Ключ не задан. Впишите его в Render → Environment, "
                      "переменная <code>ADVCAKE_KEY</code>, и перезапустите сервис.")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                ORDERS_URL, params={"pass": key, "days": max(1, min(MAX_DAYS, days))})
            response.raise_for_status()
            return response.text, None
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code in (401, 403):
            return None, "Ключ не подошёл — проверьте его в кабинете AdvCake."
        return None, f"AdvCake ответил {code}."
    except Exception as e:
        logging.error(f"AdvCake недоступен: {e}")
        return None, f"Не дозвонилась до AdvCake: {type(e).__name__}"


def _money(value: str) -> float:
    try:
        return float(str(value).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return 0.0


def summary(xml_text: str, days: int) -> str:
    """Человеческая сводка по выгрузке"""
    orders = _orders(xml_text)
    if orders is None:
        return ("Ответ пришёл, но разобрать его не вышло — покажите мне "
                "<code>/advcake сырое</code>, и я поправлю разбор.")
    if not orders:
        return f"За {days} дн. заказов нет."

    total = 0.0
    statuses, shops, subs = Counter(), Counter(), Counter()
    for node in orders:
        total += _money(_field(node, SUM_FIELDS))
        statuses[_field(node, STATUS_FIELDS) or "без статуса"] += 1
        shops[_field(node, OFFER_FIELDS) or "—"] += 1
        sub = _field(node, SUB_FIELDS)
        if sub:
            subs[sub] += 1

    lines = [f"💰 <b>AdvCake за {days} дн.</b>", "",
             f"Заказов: <b>{len(orders)}</b>"]
    if total:
        lines.append(f"Вознаграждение: <b>{total:,.0f} ₽</b>".replace(",", " "))
    if len(shops) > 1 or (shops and "—" not in shops):
        lines += ["", "<b>Магазины</b>"]
        lines += [f"{name} — {count}" for name, count in shops.most_common(6)]
    if statuses:
        lines += ["", "<b>Статусы</b>"]
        lines += [f"{name} — {count}" for name, count in statuses.most_common(6)]
    if subs:
        # Метка Sub1 — это площадка: по ней видно, что именно продаёт
        lines += ["", "<b>Откуда пришли</b>"]
        lines += [f"{name} — {count}" for name, count in subs.most_common(6)]
    return "\n".join(lines)


@router.message(F.text.startswith("/advcake"))
async def advcake_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    arg = parts[1].lower() if len(parts) > 1 else ""

    if arg in ("ключ", "key"):
        key = _key()
        await message.answer(
            f"Ключ задан, длина {len(key)} знаков." if key else
            "Ключ не задан.\n\nRender → Environment → <code>ADVCAKE_KEY</code>. "
            "Сюда его не присылайте.")
        return

    days = int(arg) if arg.isdigit() else MAX_DAYS
    raw, error = await fetch(days)
    if error:
        await message.answer(f"❌ {error}")
        return

    if arg in ("сырое", "raw"):
        await message.answer(
            "Первые строки ответа:\n\n<code>"
            + raw[:900].replace("<", "&lt;").replace(">", "&gt;") + "</code>")
        return
    await message.answer(summary(raw, days))
