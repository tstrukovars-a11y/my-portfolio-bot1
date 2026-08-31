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
from aiogram.fsm.state import StatesGroup, State

import config
import database
import flags
from translator import claude_client

router = Router()

MODEL = "claude-haiku-4-5-20251001"
PER_CITY = 5          # больше пяти за раз модель начинает выдумывать
MAX_NAME = 80
MAX_TEXT = 700

GUIDE = """Ты пишешь заметки о достопримечательностях для канала о
путешествиях. Тебе называют город — ты перечисляешь до {limit} мест внутри
него.

Верни ТОЛЬКО JSON, без пояснений и markdown:
{{"spots": [{{"name": "Эйфелева башня",
             "text": "А знаете ли вы, что Гюстав Эйфель устроил на верхушке
                      башни собственный кабинет — и туда пускают посетителей.",
             "address": "Champ de Mars, 5 Av. Anatole France, 75007 Paris",
             "url": "https://www.toureiffel.paris"}}]}}

Правила:
- только реально существующие места в названном городе;
- "text" начинается с «А знаете ли вы» и содержит ОДИН неожиданный факт,
  который знают не все. Не пересказ путеводителя, а то, ради чего человек
  дочитает: 2-4 предложения;
- не выдумывайте фактов, в которых не уверены. Лучше признанно известное,
  чем красивое и неправдивое;
- "url" — только официальный сайт места. Если не знаете точно — оставьте
  пустым. Выдуманный адрес сайта хуже его отсутствия;
- "address" — почтовый адрес. Не знаете — пустая строка;
- часы работы и цены НЕ пишите: они устаревают, а ссылка на сайт нет;
- от третьего лица, без «я» и «мы» — автор сам решит, где был."""


def _clean(v, limit):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:limit]


def _url(value: str):
    """Адрес сайта либо ничего. Выдуманная ссылка ведёт читателя в никуда
    и подрывает доверие сильнее, чем её отсутствие."""
    v = _clean(value, 200)
    return v if re.fullmatch(r"https?://[\w.-]+\.[a-z]{2,}(/[^\s]*)?", v, re.I) else None


def parse(raw: dict) -> list:
    out = []
    for s in (raw.get("spots") or [])[:PER_CITY]:
        if not isinstance(s, dict):
            continue
        name = _clean(s.get("name"), MAX_NAME)
        if name:
            out.append({"name": name,
                        "text": _clean(s.get("text"), MAX_TEXT),
                        "address": _clean(s.get("address"), 200) or None,
                        "url": _url(s.get("url"))})
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
        if await database.add_spot(place_id, s["name"], s["text"], i,
                                   s["address"], s["url"]) == "added":
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
        for sid, name, _t, _p, visited, _m, _a, _u in spots]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def post_text(country: str, place: str, name: str, text: str,
              address: str = None, url: str = None, visited: bool = False) -> str:
    """Пост о достопримечательности.

    Порядок: где это → чем удивит → как дойти. Крючок идёт вторым, а не
    последним: до конца поста дочитывает меньшинство, а «а знаете ли вы»
    задерживает на первой же строке.
    """
    head = f"{flags.with_flag(country)} · {place}\n📍 {name}"
    parts = [head, (text or "").strip()]
    if visited:
        parts.append("✔️ Была здесь")
    tail = []
    if address:
        tail.append(f"🏠 {address}")
    if url:
        tail.append(f"🔗 {url}")
    if tail:
        parts.append("\n".join(tail))
    return "\n\n".join(p for p in parts if p)


# =====================================================================
# ФОТОГРАФИИ
#
# Снимки только свои. Сгенерированное изображение настоящей
# достопримечательности — правдоподобная выдумка: пропорции чужие,
# детали не тех эпох. В канале, который строит доверие к автору, такая
# картинка стоит дороже, чем отсутствие картинки вообще.
# =====================================================================

class Shooting(StatesGroup):
    waiting_photo = State()


async def _next_spot(state: FSMContext):
    data = await state.get_data()
    skipped = set(data.get("skipped", []))
    for sid, place, country, name in await database.spots_without_photo():
        if sid not in skipped:
            return sid, place, country, name
    return None


def _shoot_menu(spot_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="spotskip"),
         InlineKeyboardButton(text="⏹ Закончить", callback_data="spotstop")]])


async def _ask_spot(target, state: FSMContext, prefix: str = ""):
    nxt = await _next_spot(state)
    if not nxt:
        await state.clear()
        await target.answer(prefix + "✅ Мест без фотографии не осталось.")
        return
    sid, place, country, name = nxt
    left = len(await database.spots_without_photo())
    await state.set_state(Shooting.waiting_photo)
    await state.update_data(spot_id=sid, name=name)
    await target.answer(
        f"{prefix}📷 <b>{name}</b>\n{place} · {flags.with_flag(country)}\n\n"
        f"Пришлите свой снимок. Осталось: {left}",
        reply_markup=_shoot_menu(sid))


@router.message(F.text == "/spot_photos")
async def spot_photos(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    await state.update_data(skipped=[])
    await _ask_spot(message, state)


@router.callback_query(F.data == "spotskip")
async def skip_spot(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    skipped = list(data.get("skipped", []))
    if data.get("spot_id"):
        skipped.append(data["spot_id"])
    await state.update_data(skipped=skipped)
    await _ask_spot(call.message, state)
    await call.answer("Пропущено")


@router.callback_query(F.data == "spotstop")
async def stop_spots(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("Готово. Вернуться: <code>/spot_photos</code>")
    await call.answer()


@router.message(Shooting.waiting_photo, F.photo)
async def take_spot_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    spot_id = data.get("spot_id")
    if not spot_id:
        await state.clear()
        return
    if not await database.set_spot_photo(spot_id, message.photo[-1].file_id):
        await message.answer("⚠️ Не сохранилось. Пришлите ещё раз.")
        return
    await _ask_spot(message, state, prefix=f"✅ {data.get('name', '')}\n\n")


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
