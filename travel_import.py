# travel_import.py — список поездок превращается в наполненный раздел.
#
# Владелец пишет одним сообщением, как помнит: «Италия — Рим, Флоренция;
# Израиль — Тель-Авив». Модель раскладывает это по странам и городам и
# пишет к каждому месту короткий текст. Дальше остаётся приложить фото.
#
# Описания сочиняет модель, а значит они могут быть неточными. Поэтому
# текст — черновик, который владелец правит на месте, а не окончательный
# материал: публиковать непроверенное от своего имени нельзя.
import hashlib
import html
import json
import logging
import os
import re

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import config
import database
from translator import claude_client

router = Router()

MODEL = "claude-haiku-4-5-20251001"
MAX_LIST = 3000          # список поездок длиннее — уже мемуары
MAX_PLACES = 25          # столько модель успевает описать в одном ответе
CHUNK = 20               # список режем на части: 60 городов в один ответ
                         # не помещаются, и хвост списка молча пропадал

LIBRARIAN = """Ты редактор раздела о путешествиях. Пользователь перечисляет
города и страны, где он был, — как помнит, вперемешку и без порядка.

Верни ТОЛЬКО JSON, без пояснений и markdown:
{"places": [{"country_ru": "Италия", "country_en": "Italy",
             "place": "Рим",
             "text": "2-4 предложения о том, что там стоит увидеть"}]}

Правила:
- одно место — один город, а не страна целиком;
- если названа только страна, возьмите её главный город;
- "country_en" нужен для англоязычной версии раздела;
- в "text" — только общеизвестное: главные достопримечательности, чем город
  запоминается. Не выдумывайте подробностей, которых не знаете наверняка,
  и не пишите от первого лица: это описание места, а не рассказ о поездке;
- до {limit} мест; если названо больше, возьмите первые."""


class Importing(StatesGroup):
    waiting_list = State()
    waiting_photo = State()
    waiting_text = State()


def _source_key(country: str, place: str) -> str:
    """Устойчивый ключ места: повторный ввод того же списка не плодит копии"""
    raw = f"manual:{country.strip().lower()}:{place.strip().lower()}"
    return "travel:" + hashlib.sha1(raw.encode()).hexdigest()[:24]


def _clean(value, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def parse(raw: dict) -> list:
    """Приводит ответ модели к списку мест, отбрасывая безымянные"""
    out = []
    for p in (raw.get("places") or [])[:MAX_PLACES]:
        if not isinstance(p, dict):
            continue
        place = _clean(p.get("place"), 80)
        country = _clean(p.get("country_ru"), 80)
        if not place or not country:
            continue
        out.append({
            "country_ru": country,
            "country_en": _clean(p.get("country_en"), 80) or country,
            "place": place,
            "text": _clean(p.get("text"), 900),
        })
    return out


def _chunks(listing: str):
    """Режет список на части по строкам и запятым, сохраняя целые названия"""
    items = [x.strip() for x in re.split(r"[\n;,]+", listing) if x.strip()]
    if len(items) <= CHUNK:
        return [listing]
    return ["\n".join(items[i:i + CHUNK]) for i in range(0, len(items), CHUNK)]


async def structure(listing: str):
    """(места, ошибка). Длинный список обрабатывается частями и склеивается."""
    parts = _chunks(listing)
    if len(parts) > 1:
        merged, seen = [], set()
        for part in parts:
            got, error = await _structure_one(part)
            if error:
                return (merged, None) if merged else (None, error)
            for p in got:
                key = (p["country_ru"].lower(), p["place"].lower())
                if key not in seen:
                    seen.add(key)
                    merged.append(p)
        return merged, None
    return await _structure_one(listing)


async def _structure_one(listing: str):
    if not claude_client:
        return None, "Модель не подключена: не задан ANTHROPIC_API_KEY."
    try:
        response = await claude_client.messages.create(
            model=MODEL, max_tokens=4000,
            system=LIBRARIAN.format(limit=MAX_PLACES),
            messages=[{"role": "user", "content": listing[:MAX_LIST]}],
        )
        text = response.content[0].text.strip()
    except Exception as e:
        logging.error(f"Путешествия: модель не ответила: {type(e).__name__}: {e}")
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
        places = parse(json.loads(text))
    except json.JSONDecodeError as e:
        logging.error(f"Путешествия: список не разобрался: {e}; ответ: {text[:300]}")
        return None, "Модель прислала неразборчивый список. Попробуйте ещё раз."
    if not places:
        return None, "Ни одного места не распозналось. Напишите города через запятую."
    return places, None


# =====================================================================
# ЗАГРУЗКА СПИСКА
# =====================================================================

ASK = ("🌍 <b>Список поездок</b>\n\nНапишите одним сообщением, где вы были — "
       "как помните, через запятую или списком.\n\n"
       "<i>Например: Италия — Рим, Флоренция; Израиль — Тель-Авив, Иерусалим; "
       "Париж; Прага.</i>\n\n"
       "Я разложу по странам, напишу к каждому месту черновик описания, "
       "а дальше вы приложите фотографии и поправите текст.")


SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "data", "travel_seed.json")


@router.message(F.text == "/travel_seed")
async def load_seed(message: Message):
    """Загружает выверенный список из файла, без обращения к модели.

    Описания в нём написаны и проверены вручную. Это дешевле и точнее, чем
    просить модель, и годится для первого наполнения раздела.
    """
    if not config.is_admin(message.from_user.id):
        return
    try:
        with open(SEED_PATH, encoding="utf-8") as f:
            places = parse_seed(json.load(f))
    except Exception as e:
        logging.error(f"Путешествия: файл списка не читается: {e}")
        await message.answer("⚠️ Файл со списком мест не читается.")
        return

    note = await message.answer(f"🌍 Загружаю {len(places)} мест…")
    added = duplicate = failed = 0
    for p in places:
        result = await database.add_travel_place(
            p["country_ru"], p["country_en"], p["place"], p["text"],
            None, None, None, _source_key(p["country_ru"], p["place"]))
        if result == "added":
            added += 1
        elif result == "duplicate":
            duplicate += 1
        else:
            failed += 1

    countries = {}
    for p in places:
        countries[p["country_ru"]] = countries.get(p["country_ru"], 0) + 1
    body = "\n".join(f"{c} — {n}" for c, n in
                     sorted(countries.items(), key=lambda x: -x[1]))

    await note.edit_text(
        f"🌍 <b>Готово</b>\n\n{body}\n\n"
        f"Добавлено: {added}, уже было: {duplicate}"
        + (f", не сохранилось: {failed}" if failed else ""),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📷 Приложить фотографии",
                                  callback_data="travel_photos")]]))


def parse_seed(raw: dict) -> list:
    """То же, что parse, но без ограничения на число мест: файл выверен"""
    out = []
    for p in raw.get("places") or []:
        place = _clean(p.get("place"), 80)
        country = _clean(p.get("country_ru"), 80)
        if place and country:
            out.append({"country_ru": country,
                        "country_en": _clean(p.get("country_en"), 80) or country,
                        "place": place,
                        "text": _clean(p.get("text"), 900)})
    return out


@router.message(F.text == "/travel_import")
async def start_import(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    await state.set_state(Importing.waiting_list)
    await message.answer(ASK)


@router.message(Importing.waiting_list, F.text & ~F.text.startswith("/"))
async def take_list(message: Message, state: FSMContext):
    await state.clear()
    note = await message.answer("🌍 Разбираю список…")

    places, error = await structure(message.text)
    if error:
        await note.edit_text(f"⚠️ {error}")
        return

    added = duplicate = failed = 0
    for p in places:
        result = await database.add_travel_place(
            p["country_ru"], p["country_en"], p["place"], p["text"],
            None, None, None, _source_key(p["country_ru"], p["place"]))
        if result == "added":
            added += 1
        elif result == "duplicate":
            duplicate += 1
        else:
            failed += 1

    by_country = {}
    for p in places:
        by_country.setdefault(p["country_ru"], []).append(p["place"])
    body = "\n".join(f"<b>{html.escape(c)}</b>: {html.escape(', '.join(v))}"
                     for c, v in sorted(by_country.items()))

    tail = f"\n\nДобавлено: {added}"
    if duplicate:
        tail += f", уже было: {duplicate}"
    if failed:
        tail += f", не сохранилось: {failed}"

    await note.edit_text(
        f"🌍 <b>Разобрано</b>\n\n{body}{tail}\n\n"
        "<i>Описания написаны моделью — это черновики. Проверьте текст перед "
        "публикацией.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📷 Приложить фотографии",
                                  callback_data="travel_photos")],
        ]))


# =====================================================================
# ФОТОГРАФИИ И ПРАВКА
# =====================================================================

def _places_menu(places, title: str):
    rows = [[InlineKeyboardButton(text=f"{country} · {place}",
                                  callback_data=f"travel_pick_{pid}")]
            for pid, country, place in places[:30]]
    rows.append([InlineKeyboardButton(text="⇦ В главное меню", callback_data="go_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "travel_photos")
async def list_without_photo(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await state.clear()
    places = await database.travel_without_photo()
    if not places:
        await call.message.answer("✅ У всех мест уже есть фотографии.")
        await call.answer()
        return
    await call.message.answer(
        f"📷 <b>Без фотографии: {len(places)}</b>\n\nВыберите место — и пришлите снимок.",
        reply_markup=_places_menu(places, "без фото"))
    await call.answer()


@router.callback_query(F.data.startswith("travel_pick_"))
async def pick_place(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    try:
        place_id = int(call.data.rsplit("_", 1)[1])
    except ValueError:
        await call.answer()
        return

    row = await database.get_travel_place(place_id)
    if not row:
        await call.answer("Место не найдено", show_alert=True)
        return
    country, place, text, *_ = row

    await state.set_state(Importing.waiting_photo)
    await state.update_data(place_id=place_id, place=place)
    await call.message.answer(
        f"📷 <b>{html.escape(place)}</b> · {html.escape(country)}\n\n"
        f"{html.escape(text or '')}\n\n"
        "Пришлите фотографию — или нажмите «Изменить текст».",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить текст",
                                  callback_data=f"travel_edit_{place_id}")],
            [InlineKeyboardButton(text="⇦ К списку", callback_data="travel_photos")],
        ]))
    await call.answer()


@router.message(Importing.waiting_photo, F.photo)
async def take_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    place_id = data.get("place_id")
    if not place_id:
        await state.clear()
        return

    ok = await database.set_travel_photo(place_id, message.photo[-1].file_id)
    await state.clear()

    left = await database.travel_without_photo()
    if not ok:
        await message.answer("⚠️ Не удалось сохранить фотографию.")
        return
    await message.answer(
        f"✅ Фото для «{html.escape(data.get('place', ''))}» сохранено.\n"
        f"Осталось без фото: {len(left)}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📷 Следующее место",
                                  callback_data="travel_photos")]]))


@router.callback_query(F.data.startswith("travel_edit_"))
async def ask_text(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    try:
        place_id = int(call.data.rsplit("_", 1)[1])
    except ValueError:
        await call.answer()
        return
    await state.set_state(Importing.waiting_text)
    await state.update_data(place_id=place_id)
    await call.message.answer("✏️ Пришлите новый текст описания.")
    await call.answer()


@router.message(Importing.waiting_text, F.text & ~F.text.startswith("/"))
async def take_text(message: Message, state: FSMContext):
    data = await state.get_data()
    place_id = data.get("place_id")
    await state.clear()
    if not place_id:
        return
    ok = await database.set_travel_text(place_id, message.text.strip()[:900])
    await message.answer("✅ Текст обновлён." if ok else "⚠️ Не удалось сохранить текст.",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                             [InlineKeyboardButton(text="⇦ К списку",
                                                   callback_data="travel_photos")]]))
