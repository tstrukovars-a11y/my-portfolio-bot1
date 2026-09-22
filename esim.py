# esim.py — связь в поездке, без роуминга и без потери своего номера.
#
# Вопрос звучит как «где дешевле интернет», а ломается на другом.
#
# Первое: звонки давно бесплатны — через интернет. Платить нужно только
# за трафик, и весь выбор сводится к цене гигабайта.
#
# Второе, о чём не пишут в сравнениях: коды от банков приходят на
# домашний номер. Вставили местную симку вместо своей — и потеряли
# доступ к деньгам в чужой стране. eSIM это и решает: свой номер живёт
# рядом и принимает SMS, а интернет идёт по местному тарифу.
#
# Третье: eSIM поддерживает не каждый телефон, и узнавать об этом в
# аэропорту поздно.
#
# Поэтому модуль — не витрина тарифов, а ответ на эти три вопроса, и
# только потом цены. Цены живут с датой проверки (freshness.py): тариф
# меняется молча, а отвечает за старое число тот, кто его показал.
import html
import json
import logging

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)

import config
import database
import freshness

router = Router()

PLANS_KEY = "esim_plans"

# То, ради чего экран и открывают. Написано один раз наверху: человек,
# который это уже знает, пролистает, а тот, кто не знает, — спасётся.
BEFORE = (
    "📶 <b>Связь в поездке</b>\n\n"
    "Три вещи, которые решаются <b>до</b> вылета:\n\n"
    "1. <b>Звонить можно бесплатно</b> — через интернет: Telegram, "
    "WhatsApp, FaceTime. Платить нужно только за трафик, поэтому весь "
    "выбор сводится к цене гигабайта.\n\n"
    "2. <b>Не выбрасывайте свой номер.</b> Коды от банков приходят на "
    "него, и без него вы останетесь без денег в чужой стране. eSIM "
    "ставится второй линией: номер на месте, интернет — местный.\n\n"
    "3. <b>Проверьте, что телефон умеет eSIM.</b> Наберите "
    "<code>*#06#</code>: если среди номеров есть EID — умеет. Узнавать "
    "это в аэропорту поздно."
)


# ---------------------------------------------------------------------
# СПРАВОЧНИК
# ---------------------------------------------------------------------

async def plans() -> list:
    raw = await database.get_setting(PLANS_KEY)
    if not raw:
        return []
    try:
        items = json.loads(raw)
        return items if isinstance(items, list) else []
    except (ValueError, TypeError):
        logging.error("Список тарифов связи не читается")
        return []


async def save_plans(items: list):
    await database.set_setting(PLANS_KEY, json.dumps(items, ensure_ascii=False))


def parse_plan(text: str):
    """«Airalo | Израиль | https://… | 4.5 | номер нет» → запись.

    Цена — за гигабайт, в долларах: сравнивать тарифы на 1, 3 и 10 ГБ
    иначе невозможно, а именно так их и продают.
    """
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None

    item = {"name": parts[0][:40], "country": parts[1][:40], "url": "",
            "price": 0.0, "number": False, "note": ""}
    for part in parts[2:]:
        low = part.lower()
        if part.startswith("http"):
            item["url"] = part[:200]
            continue
        if "номер" in low:
            # «номер есть» и «номер нет» отличаются одним словом, а
            # значат разное: с номером приходят местные SMS.
            item["number"] = "нет" not in low and "без" not in low
            continue
        value = part.replace(",", ".").replace("$", "").replace(" ", "")
        try:
            item["price"] = float(value)
            continue
        except ValueError:
            pass
        item["note"] = part[:80]
    return freshness.stamp(item)


def countries(items: list) -> list:
    """Страны, по которым есть тарифы, — в порядке появления"""
    out = []
    for item in items:
        name = item.get("country", "")
        if name and name not in out:
            out.append(name)
    return out


def for_country(items: list, country: str) -> list:
    """Тарифы страны, от дешёвого гигабайта к дорогому"""
    picked = [item for item in items
              if item.get("country", "").lower() == country.lower()]
    return sorted(picked, key=lambda item: float(item.get("price") or 0) or 1e9)


# ---------------------------------------------------------------------
# ЭКРАНЫ
# ---------------------------------------------------------------------

def _countries_kb(names: list) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=name, callback_data=f"sim_c_{i}")]
            for i, name in enumerate(names)]
    rows.append([InlineKeyboardButton(text="⇦", callback_data="sport_travel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def report(country: str) -> str:
    items = for_country(await plans(), country)
    if not items:
        return f"📶 <b>{html.escape(country)}</b>\n\nТарифов пока нет."

    lines = [f"📶 <b>{html.escape(country)}</b>", ""]
    for item in items:
        name = html.escape(item.get("name", "—"))
        title = (f'<a href="{html.escape(item["url"])}">{name}</a>'
                 if item.get("url") else name)
        price = item.get("price") or 0
        money = f"{price:.2f} $ за ГБ" if price else "цена не записана"
        number = "местный номер есть" if item.get("number") else "без номера"
        lines.append(f"{title} — <b>{money}</b>")
        tail = f"    <i>{number} · {freshness.label(item)}"
        if item.get("note"):
            tail += f" · {html.escape(item['note'])}"
        lines.append(tail + "</i>")

    lines.append(freshness.warning(items))
    lines.append("\n<i>Бот не продаёт связь. Это справочник: условия "
                 "уточняйте у оператора.</i>")
    return "\n".join(line for line in lines if line)


@router.message(F.text.regexp(r"^/(связь|esim)\b"))
async def sim_command(message: Message):
    names = countries(await plans())
    if not names:
        await message.answer(BEFORE + "\n\n<i>Тарифы пока не заведены.</i>")
        return
    await message.answer(BEFORE, reply_markup=_countries_kb(names),
                         disable_web_page_preview=True)


@router.callback_query(F.data == "sim_open")
async def open_screen(call: CallbackQuery):
    await call.answer()
    await sim_command(call.message)


@router.callback_query(F.data.regexp(r"^sim_c_\d+$"))
async def pick_country(call: CallbackQuery):
    names = countries(await plans())
    index = int(call.data.split("_")[-1])
    await call.answer()
    if not 0 <= index < len(names):
        return
    await call.message.answer(
        await report(names[index]),
        reply_markup=_countries_kb(names), disable_web_page_preview=True)


# ---------------------------------------------------------------------
# ВЕДЕНИЕ СПИСКА
# ---------------------------------------------------------------------

HELP = (
    "📶 <b>Тарифы связи</b>\n\n"
    "Добавить:\n"
    "<code>/тарифы + Airalo | Израиль | https://ссылка | 4.5 | номер нет</code>"
    "\n\nПо порядку: название, страна, ссылка, цена за гигабайт в "
    "долларах, есть ли местный номер. Всё после страны можно опустить.\n\n"
    "Удалить: <code>/тарифы -2</code>\n"
    "Отметить проверенным сегодня: <code>/тарифы ✓2</code>\n\n"
    "<i>Цена за гигабайт, а не за пакет: иначе тарифы на 1 и 10 ГБ не "
    "сравнить, а продают их именно так.</i>")


@router.message(F.text.regexp(r"^/тарифы"))
async def plans_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=1)
    items = await plans()

    if len(parts) < 2:
        if not items:
            await message.answer(HELP)
            return
        lines = ["📶 <b>Тарифы связи</b>", ""]
        for i, item in enumerate(items, 1):
            lines.append(
                f"{i}. <b>{html.escape(item['name'])}</b> · "
                f"{html.escape(item['country'])} — "
                f"{item.get('price', 0):.2f} $/ГБ · {freshness.label(item)}")
        lines += ["", HELP]
        await message.answer("\n".join(lines), disable_web_page_preview=True)
        return

    body = parts[1].strip()

    if body[:1] in ("✓", "+") and body[1:].strip().isdigit():
        number = int(body[1:].strip())
        if not 1 <= number <= len(items):
            await message.answer(f"Столько тарифов нет: их {len(items)}.")
            return
        freshness.stamp(items[number - 1])
        await save_plans(items)
        await message.answer(
            f"✅ {html.escape(items[number - 1]['name'])} — проверено сегодня.")
        return

    if body.startswith("-") and body[1:].strip().isdigit():
        number = int(body[1:].strip())
        if not 1 <= number <= len(items):
            await message.answer(f"Столько тарифов нет: их {len(items)}.")
            return
        gone = items.pop(number - 1)
        await save_plans(items)
        await message.answer(f"Убрала: {html.escape(gone['name'])}")
        return

    if body.startswith("+"):
        item = parse_plan(body[1:].strip())
        if not item:
            await message.answer("Нужны хотя бы название и страна.")
            return
        items.append(item)
        await save_plans(items)
        await message.answer(
            f"✅ <b>{html.escape(item['name'])}</b> · "
            f"{html.escape(item['country'])}: {item['price']:.2f} $/ГБ, "
            f"{'номер есть' if item['number'] else 'без номера'}.\n\n"
            f"Всего тарифов: {len(items)}.")
        return

    await message.answer(HELP)
