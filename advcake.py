# advcake.py — партнёрская статистика AdvCake прямо в боте.
#
# Раньше единственным способом узнать про заказы был поход в кабинет, и
# напоминание раз в месяц только подталкивало сходить. С ключом можно не
# ходить: цифры приезжают сами.
#
# Ключ живёт в переменной окружения, а не в базе и не в коде: это доступ к
# деньгам, и ему не место там, куда я или кто-то ещё может заглянуть.
#
# Отвечают они JSON, хотя документация обещала XML, — поэтому разбираем
# оба вида. И главное: при неполном кабинете приходит не пустой список, а
# {"success": false, "error": "…"} — эту причину надо показывать дословно,
# иначе владелец видит «не разобралось» и не понимает, что дело в анкете.
import json
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

ORDER_TAGS = {"order", "action", "row", "item", "conversion"}
# Обёртки списка: сами по себе заказами не являются, даже когда пустые
CONTAINER_TAGS = {"orders", "actions", "rows", "items", "conversions", "data"}
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


def _from_json(text: str):
    """(заказы, ошибка) из JSON-ответа. None — значит это не JSON."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None, None
    if isinstance(data, list):
        return data, None
    if not isinstance(data, dict):
        return None, None

    if data.get("error"):
        return None, str(data["error"])
    if data.get("success") is False:
        return None, "AdvCake отказал, но причину не назвал."

    for key in ("data", "orders", "result", "items", "rows"):
        rows = data.get(key)
        if isinstance(rows, list):
            return rows, None
    return [], None


def _pick(row: dict, names):
    """Поле из словаря по любому из подходящих имён"""
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value)
    return ""


def _from_xml(text: str):
    """(заказы, ошибка) из XML. Ошибка у них лежит тегом <error>, и раньше
    я принимала служебные теги ответа за три заказа."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        logging.warning(f"AdvCake: ответ не разобрался как XML: {e}")
        return None, None

    error = root.find("error")
    if error is not None and (error.text or "").strip():
        return None, error.text.strip()
    success = root.find("success")
    if success is not None and (success.text or "").strip().lower() == "false":
        return None, "AdvCake отказал, но причину не назвал."

    found = [n for n in root.iter()
             if n is not root
             and n.tag.lower() not in CONTAINER_TAGS
             and n.tag.lower().rstrip("s") in ORDER_TAGS]
    return found, None


async def _get(client, url, params):
    """Текст ответа либо (None, причина)"""
    try:
        response = await client.get(url, params=params)
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


ID_FIELDS = ("id", "offer_id")
ALIAS_FIELDS = ("alias", "offer_alias", "code", "name")

# Как именно называть оффер в выгрузке, документация не говорит, а «offer=957»
# им не подошло. Поэтому перебираем разумные пары «имя параметра — значение»
# и запоминаем сработавшую: гадать один раз лучше, чем каждый запрос.
PARAM_NAMES = ("offer", "offer_id", "offer_alias", "id")
_working = {"url": None, "param": None, "index": None}


async def offers_raw():
    key = _key()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        return await _get(client, OFFERS_URL, {"pass": key, "type": "json"})


async def offers():
    """[(id, алиас, название)] подключённых офферов либо (None, ошибка)"""
    text, error = await offers_raw()
    if error:
        return None, error
    rows, error = parse(text)
    if error:
        return None, error
    out = []
    for row in rows or []:
        get = _pick if isinstance(row, dict) else _field
        ident = get(row, ID_FIELDS)
        alias = get(row, ALIAS_FIELDS)
        if ident or alias:
            out.append((ident, alias, get(row, ("name", "title")) or alias or ident))
    return out, None


async def fetch(days: int = MAX_DAYS, values=()):
    """(текст ответа, ошибка). values — чем можно назвать оффер."""
    key = _key()
    if not key:
        return None, ("Ключ не задан. Впишите его в Render → Environment, "
                      "переменная <code>ADVCAKE_KEY</code>, и перезапустите сервис.")
    base = {"pass": key, "days": max(1, min(MAX_DAYS, days))}
    values = [v for v in values if v]

    # Запоминаем и имя параметра, и каким значением он сработал, и адрес:
    # иначе перебор начинался заново на каждом запросе.
    tries = []
    if _working["param"] is not None and _working["index"] is not None:
        tries.append((_working["url"], _working["param"], _working["index"]))
    for index in range(len(values)):
        # Номер оффера может стоять и прямо в адресе: /partner/offer/957
        tries.append((f"{ORDERS_URL}/{values[index]}", None, None))
    for name in PARAM_NAMES:
        for index in range(len(values)):
            tries.append((ORDERS_URL, name, index))
    tries.append((ORDERS_URL, None, None))

    seen, errors = set(), {}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for url, name, index in tries:
            if (url, name, index) in seen:
                continue
            seen.add((url, name, index))
            params = dict(base)
            if name is not None:
                params[name] = values[index]
            text, error = await _get(client, url, params)
            if not error:
                _, error = parse(text)
            if not error:
                _working.update(url=url, param=name, index=index)
                return text, None
            tag = (f"{name}={values[index]}" if name is not None
                   else (f"в адресе {url.rsplit('/', 1)[-1]}"
                         if url != ORDERS_URL else "без оффера"))
            # Группируем по тексту ответа, а не по попытке: одинаковых
            # «Invalid offer» может быть десяток, а важно, что ответов разных
            # всего два — по ним и видно, куда копать.
            errors.setdefault(error, tag)

    if not errors:
        return None, "AdvCake не ответил"
    return None, "; ".join(f"«{text}» ({tag})"
                           for text, tag in list(errors.items())[:4])


async def report(days: int = MAX_DAYS) -> str:
    """Сводка по всем подключённым офферам разом"""
    found, error = await offers()
    if error:
        return f"AdvCake отвечает: «{error}»"
    if not found:
        return ("В кабинете нет подключённых офферов. Подайте заявку на "
                "нужную программу — до одобрения статистики не будет.")

    rows, failed = [], []
    for ident, alias, name in found[:10]:
        text, error = await fetch(days, (ident, alias, name))
        if error:
            failed.append(f"{name}: {error}")
            continue
        part, _ = parse(text)
        rows.extend(part or [])

    if not rows and failed:
        return "AdvCake отвечает:\n" + "\n".join(f"• {f}" for f in failed[:5])
    summary_text = _summary_rows(rows, days, json_mode=bool(rows) and isinstance(rows[0], dict))
    if failed:
        summary_text += "\n\n<i>Не ответили: " + "; ".join(failed[:3]) + "</i>"
    return summary_text


def _money(value: str) -> float:
    try:
        return float(str(value).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return 0.0


def summary(xml_text: str, days: int) -> str:
    """Человеческая сводка по выгрузке"""
    rows, error = parse(xml_text)
    if error:
        return f"AdvCake отвечает: «{error}»"
    if rows is None:
        return ("Ответ пришёл, но разобрать его не вышло — покажите мне "
                "<code>/advcake сырое</code>, и я поправлю разбор.")
    return _summary_rows(rows, days, json_mode=not rows or isinstance(rows[0], dict))


def parse(text: str):
    """(заказы, ошибка) — из чего бы ни пришёл ответ"""
    rows, error = _from_json(text)
    if rows is not None or error:
        return rows, error
    return _from_xml(text)


def _summary_rows(orders, days: int, json_mode: bool) -> str:
    if not orders:
        return f"За {days} дн. заказов нет."

    get = (lambda row, names: _pick(row, names)) if json_mode else _field
    total = 0.0
    statuses, shops, subs = Counter(), Counter(), Counter()
    known = 0          # у скольких строк нашлось хоть одно поле заказа
    for node in orders:
        money, status = get(node, SUM_FIELDS), get(node, STATUS_FIELDS)
        shop, sub = get(node, OFFER_FIELDS), get(node, SUB_FIELDS)
        if money or status or shop:
            known += 1
        total += _money(money)
        statuses[status or "без статуса"] += 1
        shops[shop or "—"] += 1
        if sub:
            subs[sub] += 1

    # Строки есть, а полей заказа в них нет — значит это не заказы, и
    # рапортовать «заказов 3» нельзя: цифра выглядит правдой, ею не будучи.
    if not known:
        return (f"Пришло {len(orders)} записей, но полей заказа в них нет — "
                f"похоже, это не заказы.\n\nПокажите <code>/advcake сырое</code>, "
                f"поправлю разбор под их формат.")

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

    if arg in ("сырое", "raw"):
        found, _ = await offers()
        first = found[0] if found else ()
        raw, error = await fetch(MAX_DAYS, first)
        if error:
            await message.answer(f"❌ {error}")
            return
        await message.answer(
            f"Параметр: <code>{_working['param'] or 'не подобран'}</code>\n\n"
            f"Ответ:\n\n<code>"
            + raw[:900].replace("<", "&lt;").replace(">", "&gt;") + "</code>")
        return

    if arg in ("офферы", "offers") and len(parts) > 2 and parts[2].lower() in ("сырое", "raw"):
        text, error = await offers_raw()
        if error:
            await message.answer(f"❌ {error}")
            return
        await message.answer("Список офферов как есть:\n\n<code>"
                             + text[:900].replace("<", "&lt;").replace(">", "&gt;")
                             + "</code>")
        return

    if arg in ("офферы", "offers"):
        found, error = await offers()
        if error:
            await message.answer(f"❌ AdvCake отвечает: «{error}»")
            return
        if not found:
            await message.answer("Подключённых офферов нет.")
            return
        await message.answer("<b>Офферы</b>\n" + "\n".join(
            f"<code>{i or '—'}</code> · <code>{a or '—'}</code> — {n}"
            for i, a, n in found[:20]))
        return

    days = int(arg) if arg.isdigit() else MAX_DAYS
    await message.answer(await report(days))
