# travel_spots.py — достопримечательности внутри города.
#
# Город перестаёт быть одним постом. В Минске проспект Независимости,
# Троицкое предместье и ратуша — три разных повода для рассказа, и из
# семидесяти четырёх городов выходит несколько сотен постов вместо
# семидесяти четырёх.
#
# Каждое место помечается: была или не была. Канал от первого лица и
# путеводитель — разные жанры, и смешивать их нельзя: «я поднималась на
# крышу Дуомо» и «на крышу Дуомо поднимаются» читаются по-разному, и
# только автор знает, какое из двух правда.
import json
import logging
import re

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.fsm.context import FSMContext

import config
import database
import flags
from translator import claude_client

router = Router()

MODEL = "claude-haiku-4-5-20251001"
PER_CITY = 5          # больше пяти за раз модель начинает выдумывать
MAX_NAME = 80
MAX_TEXT = 700

GUIDE = """Ты пишешь короткие рассказы о достопримечательностях для канала
о путешествиях. Тебе называют город — ты перечисляешь до {limit} мест
внутри него.

Верни ТОЛЬКО JSON, без пояснений и markdown:
{{"spots": [{{"name": "Проспект Независимости",
             "text": "3-5 предложений: что это, чем примечательно, что
                      увидит человек, который туда придёт"}}]}}

Правила:
- только реально существующие места в названном городе;
- не выдумывайте подробностей, в которых не уверены: лучше короче;
- пишите от третьего лица, без «я» и «мы» — автор сам решит, где был;
- живо, а не справочно: одна конкретная деталь стоит трёх общих фраз;
- никаких цен, часов работы и прочего, что устаревает."""


def _clean(v, limit):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:limit]


def parse(raw: dict) -> list:
    out = []
    for s in (raw.get("spots") or [])[:PER_CITY]:
        if not isinstance(s, dict):
            continue
        name = _clean(s.get("name"), MAX_NAME)
        if name:
            out.append({"name": name, "text": _clean(s.get("text"), MAX_TEXT)})
    return out


async def generate(country: str, place: str):
    """(места, ошибка)"""
    if not claude_client:
        return None, "Модель не подключена."
    try:
        response = await claude_client.messages.create(
            model=MODEL, max_tokens=2000, system=GUIDE.format(limit=PER_CITY),
            messages=[{"role": "user", "content": f"{place}, {country}"}])
        text = response.content[0].text.strip()
    except Exception as e:
        logging.error(f"Достопримечательности: модель не ответила: {e}")
        if "credit balance" in str(e).lower():
            return None, "Закончились средства на счёте Anthropic."
        return None, "Не удалось обратиться к модели."

    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    brace = text.find("{")
    if brace > 0:
        text = text[brace:]
    try:
        spots = parse(json.loads(text))
    except json.JSONDecodeError:
        return None, "Модель прислала неразборчивый ответ."
    return (spots, None) if spots else (None, "Ничего не нашлось.")


# =====================================================================
# КОМАНДЫ
# =====================================================================

@router.message(F.text.startswith("/spots"))
async def spots_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        total, seen, shot = await database.spot_counts()
        await message.answer(
            f"📍 <b>Достопримечательности</b>\n\n"
            f"Всего: {total}\nОтмечено «была»: {seen}\nС фотографией: {shot}\n\n"
            "<code>/spots Париж</code> — набрать места по городу\n"
            "<code>/spots все</code> — пройти по всем городам подряд")
        return

    target = parts[1].strip()
    places = await database.travel_all_ordered()

    if target.lower() in ("все", "всё", "all"):
        await message.answer(
            f"Городов {len(places)}. Это {len(places)} обращений к модели — "
            "около доллара и минут двадцать.\n\n"
            "Пока делаем по одному: <code>/spots Париж</code>. "
            "Скажете — запущу все разом.")
        return

    found = [p for p in places if p[2].lower() == target.lower()]
    if not found:
        await message.answer(f"Город «{target}» не найден среди мест.")
        return

    place_id, country, place, *_ = found[0]
    note = await message.answer(f"📍 Собираю места в городе {place}…")

    spots, error = await generate(country, place)
    if error:
        await note.edit_text(f"⚠️ {error}")
        return

    added = 0
    for i, s in enumerate(spots, 1):
        if await database.add_spot(place_id, s["name"], s["text"], i) == "added":
            added += 1

    saved = await database.spots_of(place_id)
    await note.edit_text(
        f"📍 <b>{place}</b> · {flags.with_flag(country)}\n\n"
        + "\n".join(f"• {s[1]}" for s in saved)
        + f"\n\nДобавлено: {added}\n\n"
        "<i>Отметьте, где вы действительно были — это меняет тон рассказа.</i>",
        reply_markup=_visit_menu(saved))


def _visit_menu(spots):
    rows = [[InlineKeyboardButton(
        text=("✅ " if visited else "⬜️ ") + name[:40],
        callback_data=f"spotseen_{sid}")]
        for sid, name, _t, _p, visited, _m in spots]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("spotseen_"))
async def toggle_visited(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    try:
        spot_id = int(call.data.rsplit("_", 1)[1])
    except ValueError:
        await call.answer()
        return

    # Город спрашиваем напрямую: перебор всех городов ради одного нажатия
    # означал бы семьдесят четыре запроса к базе на каждый щелчок.
    place_id = await database.spot_place(spot_id)
    if not place_id:
        await call.answer()
        return

    spots = await database.spots_of(place_id)
    hit = next((s for s in spots if s[0] == spot_id), None)
    if not hit:
        await call.answer()
        return

    await database.set_spot_visited(spot_id, not hit[4])
    await call.message.edit_reply_markup(
        reply_markup=_visit_menu(await database.spots_of(place_id)))
    await call.answer("Отмечено «была»" if not hit[4] else "Отметка снята")
