# banners.py — замена картинок разделов прямо из бота.
#
# Картинки лежали в config.py как file_id: чтобы поменять фото в «Моей
# библиотеке», надо было править код и передеплоивать сервис. Это не та
# работа, которую делают ради одной фотографии.
#
# Теперь file_id хранится в базе, а при старте подменяет константу в
# config. Все полсотни мест, где написано config.BOOKS_BANNER, остаются
# нетронутыми — они читают уже подменённое значение.
import logging
import time

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.dispatcher.event.bases import SkipHandler

import config
import database

router = Router()

# Ключ — то, что пишет человек; значение — имя константы в config.
SECTIONS = {
    "главная": "MAIN_BANNER",
    "библиотека": "BOOKS_BANNER",
    "генетика": "GENETICS_BANNER",
    "наука": "SCIENCE_BANNER",
    "спорт": "SPORT_BANNER",
    "теннис": "TENNIS_BANNER",
    "гольф": "GOLF_BANNER",
    "лошади": "HORSE_BANNER",
    "падел": "PADEL_BANNER",
    "настольный": "TABLE_TENNIS_BANNER",
    "путешествия": "TRAVEL_BANNER",
    "творчество": "ART_BANNER",
    "картины": "PAINTINGS_BANNER",
    "ателье": "ATELIER_BANNER",
    "интерактив": "GAME_BANNER",
    "кухня": "FOOD_BANNER",
    "музыка": "MUSIC_BANNER",
    "новости": "NEWS_BANNER",
    "головоломки": "PUZZLE_BANNER",
    "ии": "CLOD_BANNER",
}

# Заводские значения запоминаем до первой подмены — иначе «сбросить»
# будет не к чему.
_FACTORY = {attr: getattr(config, attr, None) for attr in SECTIONS.values()}

# Подписи с иконками. Держим отдельно от ключей: ключ — то, что человек
# пишет в команде («/banner сброс библиотека»), и эмодзи там только мешал бы.
LABELS = {
    "главная": "🏠 Главная",
    "библиотека": "📚 Библиотека",
    "генетика": "🧬 Генетика",
    "наука": "🔬 Наука",
    "спорт": "🏆 Спорт",
    "теннис": "🎾 Теннис",
    "гольф": "🏌 Гольф",
    "лошади": "🏇 Лошади",
    "падел": "🥎 Падел",
    "настольный": "🏓 Настольный",
    "путешествия": "🌍 Путешествия",
    "творчество": "🎨 Творчество",
    "картины": "🖼 Картины",
    "ателье": "👗 Ателье",
    "интерактив": "🎮 Интерактив",
    "кухня": "🍳 Кухня",
    "музыка": "🎵 Музыка",
    "новости": "📰 Новости",
    "головоломки": "🧩 Головоломки",
    "ии": "🤖 ИИ",
}

_KEY = "banner_"

# Какой раздел ждёт фото — в базе, а не в памяти процесса. С FSM выбор
# терялся при каждом деплое: человек жал раздел, присылал фото, и оно
# уходило в никуда без единого слова.
PENDING_KEY = "banner_pending"
PENDING_MINUTES = 30


async def _pending_set(user_id: int, section: str):
    await database.set_setting(
        PENDING_KEY, f"{user_id}:{section}:{int(time.time()) + PENDING_MINUTES * 60}")


async def _pending_get(user_id: int):
    raw = await database.get_setting(PENDING_KEY) or ""
    try:
        who, section, until = raw.split(":")
        if int(who) == user_id and int(until) > time.time() and section in SECTIONS:
            return section
    except ValueError:
        pass
    return None


async def _pending_clear():
    await database.set_setting(PENDING_KEY, "")


async def load():
    """Поднять сохранённые картинки в config. Вызывается при старте."""
    changed = 0
    for name, attr in SECTIONS.items():
        try:
            saved = await database.get_setting(_KEY + attr)
        except Exception as e:
            logging.warning(f"Картинки разделов не прочитались: {e}")
            return
        if saved:
            setattr(config, attr, saved)
            changed += 1
    if changed:
        logging.info(f"Свои картинки разделов: {changed}")


async def _own() -> set:
    """Разделы, где уже стоит своя картинка — чтобы было видно, что загружено"""
    out = set()
    for name, attr in SECTIONS.items():
        try:
            if await database.get_setting(_KEY + attr):
                out.add(name)
        except Exception:
            return out
    return out


def _menu(own=()) -> InlineKeyboardMarkup:
    rows, row = [], []
    for name in SECTIONS:
        mark = "✅ " if name in own else ""
        row.append(InlineKeyboardButton(text=mark + LABELS.get(name, name),
                                        callback_data=f"banner_{name}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text.startswith("/banner"))
async def banner_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()

    # /banner сброс библиотека — вернуть заводскую картинку
    if len(parts) >= 3 and parts[1].lower() in ("сброс", "reset"):
        name = parts[2].lower()
        attr = SECTIONS.get(name)
        if not attr:
            await message.answer(f"Не знаю раздел «{name}». Список: /banner")
            return
        await database.set_setting(_KEY + attr, "")
        if _FACTORY.get(attr) is not None:
            setattr(config, attr, _FACTORY[attr])
        await message.answer(f"↩️ {LABELS.get(name, name)} — вернула прежнюю картинку.")
        return

    await _pending_clear()
    await message.answer(
        "🖼 <b>Картинка раздела</b>\n\n"
        "Выберите раздел — и пришлите фото. Оно заменит картинку сразу, "
        "без передеплоя.\n\n"
        "Вернуть прежнюю: <code>/banner сброс библиотека</code>\n"
        "Галочка — там уже стоит ваше фото.",
        reply_markup=_menu(await _own()))


@router.callback_query(F.data.startswith("banner_"))
async def pick_section(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    name = call.data.split("_", 1)[1]
    if name not in SECTIONS:
        await call.answer()
        return
    await _pending_set(call.from_user.id, name)
    await call.message.answer(
        f"Жду фото для раздела {LABELS.get(name, name)}.\n\n"
        "Горизонтальное подходит лучше: под картинкой идёт текст, и "
        "вертикальная занимает весь экран. Отменить — /cancel")
    await call.answer()


@router.message(F.text == "/cancel")
async def cancel(message: Message):
    if not config.is_admin(message.from_user.id):
        raise SkipHandler
    if not await _pending_get(message.from_user.id):
        raise SkipHandler
    await _pending_clear()
    await message.answer("Отменила, картинка прежняя.")


@router.message(F.photo)
async def save_photo(message: Message, state: FSMContext):
    """Фото от владельца, когда раздел выбран. Иначе пропускаем дальше."""
    if not config.is_admin(message.from_user.id):
        raise SkipHandler
    # Идёт другой разговор с фотографиями — обложки книг, картины, места:
    # перехватывать его нельзя.
    if await state.get_state():
        raise SkipHandler
    name = await _pending_get(message.from_user.id)
    if not name:
        raise SkipHandler
    attr = SECTIONS.get(name)
    if not attr:
        await _pending_clear()
        return

    # Берём самый крупный размер: Telegram отдаёт лесенку превью, а в
    # разделе картинка показывается во всю ширину.
    file_id = message.photo[-1].file_id
    await database.set_setting(_KEY + attr, file_id)
    setattr(config, attr, file_id)
    await _pending_clear()
    await message.answer_photo(
        file_id,
        caption=f"✅ Готово: {LABELS.get(name, name)}. "
                f"Откройте раздел — картинка уже новая.")


@router.message(F.document)
async def not_a_photo(message: Message):
    """Файлом вместо фото — частая ошибка, о ней надо сказать"""
    if not config.is_admin(message.from_user.id):
        raise SkipHandler
    if not await _pending_get(message.from_user.id):
        raise SkipHandler
    await message.answer(
        "Нужна именно фотография. Отправленное файлом Telegram не отдаёт "
        "как картинку — пришлите как фото. Отменить — /cancel")
