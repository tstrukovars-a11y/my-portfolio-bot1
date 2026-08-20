# travel.py — раздел «Путешествия»: посты из канала, разложенные по странам.
# Навигация в три шага: страна → локация → публикация.
#
# Страну определяет Claude по тексту поста: «Сан-Мало» он опознаёт как Францию,
# а вручную это пришлось бы указывать для каждой публикации. Если ключа нет или
# модель не ответила, бот спрашивает страну у владельца — раскладка не зависит
# от доступности внешнего сервиса.
import hashlib
import html
import json
import logging
import re

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest

import config
import database
from block2_creative import claude_client

router = Router()

MAX_CAPTION = 1024
MAX_MESSAGE = 4096

EMPTY = {
    "ru": "🌍 Пока ни одной поездки. Материалы появятся здесь совсем скоро.",
    "en": "🌍 No trips yet. Material will appear here soon.",
    "fr": "🌍 Aucun voyage pour l'instant.",
    "he": "🌍 אין עדיין טיולים."
}

PICK_COUNTRY = {
    "ru": "🌍 <b>Страны</b>\n\nВыберите страну — внутри локации:",
    "en": "🌍 <b>Countries</b>\n\nPick a country — locations inside:",
    "fr": "🌍 <b>Pays</b>\n\nChoisissez un pays :",
    "he": "🌍 <b>מדינות</b>\n\nבחרו מדינה:"
}

PICK_PLACE = {
    "ru": "📍 <b>{country}</b>\n\nВыберите локацию:",
    "en": "📍 <b>{country}</b>\n\nPick a location:",
    "fr": "📍 <b>{country}</b>\n\nChoisissez un lieu :",
    "he": "📍 <b>{country}</b>\n\nבחרו מקום:"
}

BACK = {"ru": "🔙 Назад", "en": "🔙 Back", "fr": "🔙 Retour", "he": "🔙 חזרה"}
TO_COUNTRIES = {"ru": "🌍 К странам", "en": "🌍 All countries",
                "fr": "🌍 Tous les pays", "he": "🌍 כל המדינות"}
SOURCE = {"ru": "🔗 Читать в канале", "en": "🔗 Read in the channel",
          "fr": "🔗 Lire dans le canal", "he": "🔗 קראו בערוץ"}
NO_TEXT = {
    "ru": "📷 В этой публикации пока только изображение.",
    "en": "📷 This entry has only an image so far.",
    "fr": "📷 Seulement une image pour l'instant.",
    "he": "📷 יש כאן בינתיים רק תמונה."
}


def _t(mapping: dict, lang: str) -> str:
    return mapping.get(lang, mapping["en"])


def _token(country: str) -> str:
    """Короткий стабильный ключ страны для callback.

    Название целиком туда класть нельзя: Telegram ограничивает callback_data
    64 байтами, а кириллица занимает по два — «Объединённые Арабские Эмираты»
    в лимит не влезает, и клавиатура не отрисуется вовсе.
    """
    return hashlib.md5((country or "").encode("utf-8")).hexdigest()[:10]


async def _country_by_token(token: str):
    """Обратное преобразование: хэш детерминирован, состояние хранить не нужно"""
    for country_ru, _, _ in await database.get_travel_countries():
        if _token(country_ru) == token:
            return country_ru
    return None


# =====================================================================
# ПРОСМОТР: СТРАНА → ЛОКАЦИЯ → ПУБЛИКАЦИЯ
# =====================================================================

@router.callback_query(F.data == "travel_places")
async def show_countries(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    countries = await database.get_travel_countries()

    if not countries:
        await call.message.answer(_t(EMPTY, lang))
        return

    rows = []
    for country_ru, country_en, count in countries:
        # Страна подписана на языке читателя: англоязычному «Франция» ни о чём
        label = country_ru if lang == "ru" else (country_en or country_ru)
        rows.append([InlineKeyboardButton(
            text=f"{label} ({count})", callback_data=f"trcountry_{_token(country_ru)}")])
    rows.append([InlineKeyboardButton(text=_t(BACK, lang), callback_data="sport_travel")])

    await call.message.answer(_t(PICK_COUNTRY, lang), parse_mode="HTML",
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("trcountry_"))
async def show_places(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    country = await _country_by_token(call.data.removeprefix("trcountry_"))
    places = await database.get_travel_places(country) if country else []
    if not places:
        await call.answer("Локаций пока нет", show_alert=True)
        return

    rows = [[InlineKeyboardButton(text=place or "—", callback_data=f"trplace_{place_id}")]
            for place_id, place in places]
    rows.append([InlineKeyboardButton(text=_t(TO_COUNTRIES, lang),
                                      callback_data="travel_places")])

    text = _t(PICK_PLACE, lang).format(country=html.escape(country))
    try:
        await call.message.edit_text(text, parse_mode="HTML",
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        await call.message.answer(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("trplace_"))
async def show_place(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    try:
        place_id = int(call.data.removeprefix("trplace_"))
    except ValueError:
        return

    entry = await database.get_travel_place(place_id)
    if not entry:
        await call.answer("Публикация не найдена", show_alert=True)
        return

    country, place, text, photo_id, video_id, link = entry
    body = (text or "").strip() or (place or "").strip() or _t(NO_TEXT, lang)

    rows = []
    if link and link.startswith(("http://", "https://", "tg://")):
        rows.append([InlineKeyboardButton(text=_t(SOURCE, lang), url=link)])
    if config.is_admin(call.from_user.id):
        rows.append([InlineKeyboardButton(text="🌍 Сменить страну",
                                          callback_data=f"trmove_{place_id}")])
    rows.append([InlineKeyboardButton(text=_t(BACK, lang),
                                      callback_data=f"trcountry_{_token(country)}")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)

    # Текст целиком: по границе подписи не режем, иначе публикация рвётся надвое
    media = video_id or photo_id
    try:
        if media and len(body) <= MAX_CAPTION:
            sender = call.message.answer_video if video_id else call.message.answer_photo
            await sender(media, caption=body, parse_mode=None, reply_markup=markup)
            return
        if media:
            sender = call.message.answer_video if video_id else call.message.answer_photo
            await sender(media, caption=(place or "")[:MAX_CAPTION] or None,
                         parse_mode=None, reply_markup=markup)
        for index, chunk in enumerate(_split(body, MAX_MESSAGE)):
            is_last = index == len(_split(body, MAX_MESSAGE)) - 1
            await call.message.answer(chunk, parse_mode=None,
                                      reply_markup=markup if is_last else None)
    except TelegramBadRequest as e:
        logging.error(f"Локация {place_id} не отправилась: {e}")
        await call.message.answer(f"⚠️ Не удалось показать: {e.message}", reply_markup=markup)


def _split(text: str, limit: int):
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(paragraph) > limit:
            cut = paragraph.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            chunks.append(paragraph[:cut])
            paragraph = paragraph[cut:].lstrip()
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


# =====================================================================
# ИМПОРТ
# =====================================================================

class TravelImport(StatesGroup):
    collecting = State()
    waiting_country = State()


_pending: dict[int, dict] = {}

GEO_PROMPT = (
    "You get a travel post. Identify the country and the specific place it is about. "
    "Reply with raw JSON only, no explanation:\n"
    '{"country_ru": "Франция", "country_en": "France", "place": "Сен-Мало"}\n'
    "Use the place name as written in the post. If the country is unclear, "
    'return {"country_ru": "", "country_en": "", "place": ""}.'
)


async def detect_geo(text: str):
    """(страна_ru, страна_en, локация) или None, если определить не удалось"""
    if claude_client is None or not text.strip():
        return None
    try:
        response = await claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=GEO_PROMPT,
            messages=[{"role": "user", "content": text[:2000]}]
        )
        raw = response.content[0].text.strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1:
            return None
        data = json.loads(raw[start:end + 1])
        country_ru = (data.get("country_ru") or "").strip()
        if not country_ru:
            return None
        return (country_ru, (data.get("country_en") or country_ru).strip(),
                (data.get("place") or "").strip())
    except Exception as e:
        logging.warning(f"Не удалось определить страну: {e}")
        return None


def _first_line(text: str) -> str:
    for raw in (text or "").split("\n"):
        line = re.sub(r"[*_`~]", "", re.sub(r"#\S+", "", raw)).strip(" -—–·•|")
        if len(re.sub(r"[^\w]", "", line, flags=re.UNICODE)) >= 3:
            return line[:80]
    return "Локация"


def extract(message: Message) -> dict:
    text = (message.text or message.caption or "").strip()
    link = None
    for entity in list(message.entities or []) + list(message.caption_entities or []):
        if entity.type == "text_link" and entity.url:
            link = entity.url
            break
        if entity.type == "url":
            link = entity.extract_from(text)
            break
    return {
        "text": text,
        "place": _first_line(text),
        "photo_id": message.photo[-1].file_id if message.photo else None,
        "video_id": message.video.file_id if message.video else None,
        "link": link,
    }


def source_key(message: Message) -> str:
    origin = getattr(message, "forward_origin", None)
    chat = getattr(origin, "chat", None) if origin is not None else None
    message_id = getattr(origin, "message_id", None) if origin is not None else None
    if chat is None:
        chat = getattr(message, "forward_from_chat", None)
        message_id = getattr(message, "forward_from_message_id", None)
    if chat is None or message_id is None:
        return f"{message.chat.id}:{message.message_id}"
    return f"{chat.id}:{message_id}"


@router.message(F.text == "/travel")
async def import_start(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    await state.set_state(TravelImport.collecting)
    await message.answer(
        "🌍 <b>Режим импорта путешествий включён.</b>\n\n"
        f"Сейчас локаций в базе: <b>{await database.count_travel_places()}</b>\n\n"
        "Пересылайте посты из канала. Страну определю по тексту сама — "
        "«Сан-Мало» положу во Францию. Если не пойму, спрошу.\n\n"
        "Локацией станет первая строка поста.\n\n"
        "Когда закончите — отправьте /travel_done"
    )


@router.message(F.text == "/travel_done", TravelImport.collecting)
@router.message(F.text == "/travel_done", TravelImport.waiting_country)
async def import_stop(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(
        f"✅ Импорт завершён. Локаций в базе: <b>{await database.count_travel_places()}</b>")


async def _save(data: dict, country_ru: str, country_en: str) -> str:
    result = await database.add_travel_place(
        country_ru, country_en, data["place"], data["text"],
        data["photo_id"], data["video_id"], data["link"], data["key"]
    )
    total = await database.count_travel_places()
    if result == "added":
        return (f"✅ <b>{html.escape(country_ru)}</b> → «{html.escape(data['place'])}»\n\n"
                f"Локаций в базе: <b>{total}</b>")
    if result == "duplicate":
        return f"↩️ Этот пост уже импортирован. Всего: <b>{total}</b>"
    detail = result.split(":", 1)[1] if result.startswith("error:") else "причина неизвестна"
    return f"⚠️ Не сохранено.\n\n<code>{detail[:400]}</code>"


@router.message(TravelImport.collecting, F.text | F.caption, ~F.text.startswith("/"))
async def import_post(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return

    data = extract(message)
    data["key"] = source_key(message)

    geo = await detect_geo(data["text"])
    if geo:
        country_ru, country_en, place = geo
        if place:
            data["place"] = place
        await message.answer(await _save(data, country_ru, country_en))
        return

    _pending[message.from_user.id] = data
    await state.set_state(TravelImport.waiting_country)
    await message.answer(
        f"❓ Не смогла определить страну для «{html.escape(data['place'])}».\n\n"
        f"Напишите её одним словом, например: Франция"
    )


@router.message(TravelImport.waiting_country, F.text, ~F.text.startswith("/"))
async def take_country(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return

    data = _pending.pop(message.from_user.id, None)
    await state.set_state(TravelImport.collecting)
    if not data:
        await message.answer("Пост потерялся — перешлите его заново.")
        return

    country = message.text.strip()[:60]

    # Тот же ввод обслуживает две задачи: страну для новой публикации и
    # исправление страны у сохранённой.
    if "move_id" in data:
        ok = await database.update_travel_country(data["move_id"], country, country)
        await message.answer(f"✅ Перенесено в «{html.escape(country)}»" if ok
                             else "⚠️ Не удалось перенести — ошибка базы.")
        return

    await message.answer(await _save(data, country, country))


@router.callback_query(F.data.startswith("trmove_"))
async def ask_move_country(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        return
    await call.answer()
    await state.set_state(TravelImport.waiting_country)
    _pending[call.from_user.id] = {"move_id": int(call.data.removeprefix("trmove_"))}
    await call.message.answer("Напишите правильную страну одним словом:")


@router.message(TravelImport.collecting)
async def import_hint(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    if (message.text or "").startswith("/"):
        return
    await message.answer(
        "В посте нет ни текста, ни подписи — по нему не понять страну. "
        "Перешлите пост с описанием или отправьте /travel_done."
    )
