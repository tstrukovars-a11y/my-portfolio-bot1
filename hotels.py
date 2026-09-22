# hotels.py — где и как бронировать, чтобы не переплатить.
#
# Сравнивать цены на агрегаторах умеют все. Теряют деньги на другом:
#
#   • у отеля напрямую нередко дешевле или с завтраком — агрегатор берёт
#     свою долю, и отель охотно её экономит;
#   • «бесплатная отмена» важнее цены, когда планы ещё не твёрдые: это
#     право передумать, и стоит оно обычно пары процентов;
#   • на месте доплачивают городской налог и депозит — их нет в цене
#     ночи, и счёт на выезде оказывается неожиданностью.
#
# Поэтому здесь сначала правила, а потом список сервисов. Правила
# работают всегда, список устаревает — и у каждой записи есть дата
# проверки (freshness.py).
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

PLACES_KEY = "hotel_services"

RULES = (
    "🏨 <b>Бронирование</b>\n\n"
    "<b>1. Нашли на агрегаторе — проверьте у отеля.</b> Напрямую часто "
    "дешевле или с завтраком: отелю выгоднее отдать вам то, что он "
    "отдал бы агрегатору.\n\n"
    "<b>2. Бесплатная отмена дороже скидки.</b> Пока планы не твёрдые, "
    "это право передумать, и стоит оно обычно пары процентов. "
    "Невозвратный тариф берут, когда билеты уже куплены.\n\n"
    "<b>3. Цена ночи — не вся цена.</b> Городской налог и депозит платят "
    "на месте; в одних странах это пара евро, в других — заметная сумма "
    "за каждую ночь.\n\n"
    "<b>4. Отзывы читайте свежие и на своём языке.</b> Отель меняет "
    "хозяев и ремонтируется; отзыв трёхлетней давности описывает другое "
    "место.\n\n"
    "<b>5. Платёжная карта — та, что примут.</b> Депозит блокируют на "
    "карте, и карта другой страны может не подойти."
)


async def places() -> list:
    raw = await database.get_setting(PLACES_KEY)
    if not raw:
        return []
    try:
        items = json.loads(raw)
        return items if isinstance(items, list) else []
    except (ValueError, TypeError):
        logging.error("Список сервисов бронирования не читается")
        return []


async def save_places(items: list):
    await database.set_setting(PLACES_KEY, json.dumps(items, ensure_ascii=False))


def parse_place(text: str):
    """«Название | https://… | где работает | чем хорош»"""
    parts = [p.strip() for p in text.split("|")]
    if not parts or not parts[0]:
        return None

    item = {"name": parts[0][:40], "url": "", "where": "", "note": ""}
    for part in parts[1:]:
        if part.startswith("http"):
            item["url"] = part[:200]
        elif not item["where"]:
            item["where"] = part[:40]
        else:
            item["note"] = part[:100]
    return freshness.stamp(item)


async def report() -> str:
    items = await places()
    if not items:
        return RULES + "\n\n<i>Сервисы пока не заведены.</i>"

    lines = [RULES, "", "<b>Чем пользуемся:</b>"]
    for item in items:
        name = html.escape(item.get("name", "—"))
        title = (f'<a href="{html.escape(item["url"])}">{name}</a>'
                 if item.get("url") else name)
        where = html.escape(item.get("where") or "")
        lines.append(f"• {title}{' — ' + where if where else ''}")
        tail = f"    <i>{freshness.label(item)}"
        if item.get("note"):
            tail += f" · {html.escape(item['note'])}"
        lines.append(tail + "</i>")

    lines.append(freshness.warning(items))
    lines.append("\n<i>Бот не бронирует и не берёт оплату. Это справочник.</i>")
    return "\n".join(line for line in lines if line)


def _kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⇦", callback_data="sport_travel")]])


@router.message(F.text.regexp(r"^/(отели|hotels)\b"))
async def hotels_command(message: Message):
    await message.answer(await report(), reply_markup=_kb(),
                         disable_web_page_preview=True)


@router.callback_query(F.data == "hotel_open")
async def open_screen(call: CallbackQuery):
    await call.answer()
    await call.message.answer(await report(), reply_markup=_kb(),
                              disable_web_page_preview=True)


HELP = (
    "🏨 <b>Сервисы бронирования</b>\n\n"
    "Добавить:\n"
    "<code>/бронь + Название | https://ссылка | где работает | чем хорош</code>"
    "\n\nУдалить: <code>/бронь -2</code>\n"
    "Отметить проверенным: <code>/бронь ✓2</code>")


@router.message(F.text.regexp(r"^/бронь"))
async def places_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=1)
    items = await places()

    if len(parts) < 2:
        if not items:
            await message.answer(HELP)
            return
        lines = ["🏨 <b>Сервисы бронирования</b>", ""]
        for i, item in enumerate(items, 1):
            lines.append(f"{i}. <b>{html.escape(item['name'])}</b> — "
                         f"{freshness.label(item)}")
        lines += ["", HELP]
        await message.answer("\n".join(lines), disable_web_page_preview=True)
        return

    body = parts[1].strip()

    if body[:1] in ("✓", "+") and body[1:].strip().isdigit():
        number = int(body[1:].strip())
        if not 1 <= number <= len(items):
            await message.answer(f"Столько сервисов нет: их {len(items)}.")
            return
        freshness.stamp(items[number - 1])
        await save_places(items)
        await message.answer(
            f"✅ {html.escape(items[number - 1]['name'])} — проверено сегодня.")
        return

    if body.startswith("-") and body[1:].strip().isdigit():
        number = int(body[1:].strip())
        if not 1 <= number <= len(items):
            await message.answer(f"Столько сервисов нет: их {len(items)}.")
            return
        gone = items.pop(number - 1)
        await save_places(items)
        await message.answer(f"Убрала: {html.escape(gone['name'])}")
        return

    if body.startswith("+"):
        item = parse_place(body[1:].strip())
        if not item:
            await message.answer("Нужно хотя бы название.")
            return
        items.append(item)
        await save_places(items)
        await message.answer(f"✅ <b>{html.escape(item['name'])}</b>. "
                             f"Всего сервисов: {len(items)}.")
        return

    await message.answer(HELP)
