# avatars.py — аватарки каналов ставит сам бот.
#
# Аватарку бота поставить нельзя ни отсюда, ни откуда-либо ещё через API:
# в Bot API просто нет такого метода, она живёт только в @BotFather. А вот
# фото канала бот меняет через setChatPhoto — при условии, что он там
# администратор с правом менять информацию.
#
# Знаки лежат в data/marks рядом с кодом, а не в базе: это часть проекта,
# они должны приезжать вместе с деплоем.
import logging
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton,
                           CallbackQuery, FSInputFile)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import config
import database

router = Router()

MARKS = Path(__file__).parent / "data" / "marks"

# раздел -> (файл знака, ключ настройки с id канала, человеческое имя)
TARGETS = {
    "акцент":       ("znak-aktsent-512.png",       "digest_chat",     "Акцент"),
    "книги":        ("znak-knigi-512.png",         "books_channel",   "Бизнес-литература"),
    "путешествия":  ("znak-puteshestviya-512.png", "travel_channel",  "Вокруг света"),
    "еда":          ("znak-eda-512.png",           "recipes_channel", "Кухня"),
    "теннис":       ("znak-tennis-512.png",        "tennis_channel",  "Теннис"),
}


def _menu() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"{name} → {title}",
                                  callback_data=f"avatar_{name}")]
            for name, (_, _, title) in TARGETS.items()]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _apply(bot: Bot, name: str) -> str:
    """Поставить знак на канал раздела. Возвращает строку для ответа."""
    file_name, key, title = TARGETS[name]
    path = MARKS / file_name
    if not path.exists():
        return f"❌ {title}: файла {file_name} нет в data/marks"

    raw = await database.get_setting(key)
    if not raw:
        return (f"⚪️ {title}: канал не задан (настройка <code>{key}</code>). "
                f"Задайте его, и команда сработает.")
    try:
        chat_id = int(raw)
    except (TypeError, ValueError):
        return f"❌ {title}: в настройке <code>{key}</code> не число, а «{raw}»"

    try:
        await bot.set_chat_photo(chat_id, FSInputFile(path))
    except TelegramForbiddenError:
        return f"❌ {title}: бот не в канале"
    except TelegramBadRequest as e:
        # Самая частая причина — нет права «Изменение профиля канала».
        return (f"❌ {title}: {e.message}\n"
                f"Обычно это значит, что боту не выдано право менять "
                f"информацию канала.")
    except Exception as e:
        logging.error(f"Аватарка {title} не встала: {e}")
        return f"❌ {title}: {e}"
    return f"✅ {title}: знак поставлен"


@router.message(F.text.startswith("/avatar"))
async def avatar_command(message: Message, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    arg = parts[1].lower() if len(parts) > 1 else ""

    if arg in ("все", "всё", "all"):
        lines = [await _apply(bot, name) for name in TARGETS]
        await message.answer("\n".join(lines))
        return

    if arg in TARGETS:
        # /avatar еда -1001234567890 — заодно запомнить канал. Каналы кухни
        # и тенниса ещё не заведены, и без этого команда была бы бесполезна
        # до тех пор, пока их id не появится где-то ещё.
        if len(parts) > 2:
            try:
                chat_id = int(parts[2])
            except ValueError:
                await message.answer("id канала — число вида <code>-100…</code>")
                return
            await database.set_setting(TARGETS[arg][1], str(chat_id))
        await message.answer(await _apply(bot, arg))
        return

    await message.answer(
        "🖼 <b>Аватарки каналов</b>\n\n"
        "Бот ставит их сам — если он администратор канала с правом менять "
        "информацию. Выберите канал или пришлите <code>/avatar все</code>.\n\n"
        "Аватарку самого бота так поменять нельзя: в Telegram она "
        "ставится только через @BotFather → <code>/setuserpic</code>.",
        reply_markup=_menu())


@router.callback_query(F.data.startswith("avatar_"))
async def avatar_button(call: CallbackQuery, bot: Bot):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    name = call.data.split("_", 1)[1]
    if name not in TARGETS:
        await call.answer()
        return
    await call.answer("Ставлю…")
    await call.message.answer(await _apply(bot, name))
