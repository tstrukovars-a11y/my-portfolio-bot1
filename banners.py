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

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

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
    "музыка": "MUSIC_BANNER",
    "новости": "NEWS_BANNER",
    "головоломки": "PUZZLE_BANNER",
    "ии": "CLOD_BANNER",
}

# Заводские значения запоминаем до первой подмены — иначе «сбросить»
# будет не к чему.
_FACTORY = {attr: getattr(config, attr, None) for attr in SECTIONS.values()}

_KEY = "banner_"


class Waiting(StatesGroup):
    photo = State()


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


def _menu() -> InlineKeyboardMarkup:
    rows, row = [], []
    for name in SECTIONS:
        row.append(InlineKeyboardButton(text=name, callback_data=f"banner_{name}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text.startswith("/banner"))
async def banner_command(message: Message, state: FSMContext):
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
        await message.answer(f"↩️ «{name}» — вернула прежнюю картинку.")
        return

    await state.clear()
    await message.answer(
        "🖼 <b>Картинка раздела</b>\n\n"
        "Выберите раздел — и пришлите фото. Оно заменит картинку сразу, "
        "без передеплоя.\n\n"
        "Вернуть прежнюю: <code>/banner сброс библиотека</code>",
        reply_markup=_menu())


@router.callback_query(F.data.startswith("banner_"))
async def pick_section(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    name = call.data.split("_", 1)[1]
    if name not in SECTIONS:
        await call.answer()
        return
    await state.set_state(Waiting.photo)
    await state.update_data(section=name)
    await call.message.answer(
        f"Жду фото для раздела «{name}».\n\n"
        "Горизонтальное подходит лучше: под картинкой идёт текст, и "
        "вертикальная занимает весь экран. Отменить — /cancel")
    await call.answer()


@router.message(Waiting.photo, F.text == "/cancel")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменила, картинка прежняя.")


@router.message(Waiting.photo, F.photo)
async def save_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("section")
    attr = SECTIONS.get(name)
    if not attr:
        await state.clear()
        return

    # Берём самый крупный размер: Telegram отдаёт лесенку превью, а в
    # разделе картинка показывается во всю ширину.
    file_id = message.photo[-1].file_id
    await database.set_setting(_KEY + attr, file_id)
    setattr(config, attr, file_id)
    await state.clear()
    await message.answer_photo(
        file_id,
        caption=f"✅ Готово: «{name}». Откройте раздел — картинка уже новая.")


@router.message(Waiting.photo)
async def not_a_photo(message: Message):
    await message.answer(
        "Нужна именно фотография. Если отправляете файлом, Telegram "
        "не даёт file_id картинки — пришлите как фото. Отменить — /cancel")
