# subs.py — подписка на отдельные блоки, а не на всё сразу.
#
# Канал выпускает девять разных вещей в день. Человеку из них интересны
# одна-две: кто-то пришёл за теннисом, кто-то за генетикой, и заставлять
# его листать остальное — верный способ получить отписку.
#
# Поэтому подписка поштучно и приходит в личные сообщения: там она не
# конкурирует с лентой каналов и не теряется. Канал при этом остаётся
# как был — подписка не вместо него, а для тех, кому нужно наверняка.
#
# Присылаем копию, а не ссылку. Ссылка требует ещё одного нажатия, и на
# нём теряется половина: человек уже в переписке с ботом, и текст должен
# быть перед глазами.
import asyncio
import html
import logging

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.exceptions import TelegramForbiddenError

import database

router = Router()

KEY = "news_sub_"                # + id: какие блоки выбраны
PAUSE = 0.05                     # между отправками: Telegram не любит залпы

# Что можно выбрать. Ключ — слот дайджеста, чтобы рассылка цеплялась к
# уже существующему расписанию, а не заводила своё.
BLOCKS = {
    "morning": "📰 Новости и курсы",
    "genetics": "🧬 Генетика",
    "tennis": "🎾 Теннис",
    "books": "📚 Книги",
    "travel": "🌍 Путешествия",
}


async def chosen(user_id: int) -> set:
    raw = await database.get_setting(KEY + str(user_id)) or ""
    return {x for x in raw.split(",") if x in BLOCKS}


async def save(user_id: int, blocks: set):
    await database.set_setting(KEY + str(user_id), ",".join(sorted(blocks)))


def _kb(picked: set) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=("✅ " if key in picked else "○ ") + name,
        callback_data=f"sub_t_{key}")] for key, name in BLOCKS.items()]
    rows.append([InlineKeyboardButton(text="⇦", callback_data="go_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


INTRO = (
    "🔔 <b>Что присылать лично</b>\n\n"
    "Канал выпускает несколько разных вещей в день. Отметьте то, что "
    "интересно вам, — это будет приходить сюда, в переписку, чтобы не "
    "теряться в ленте.\n\n"
    "Остальное останется в канале. Отписаться — снять галочку."
)


@router.message(F.text.regexp(r"^/(подписки|subscribe)\b"))
async def subs_command(message: Message):
    await message.answer(INTRO, reply_markup=_kb(await chosen(message.from_user.id)))


@router.callback_query(F.data == "subs_open")
async def open_screen(call: CallbackQuery):
    await call.answer()
    await call.message.answer(INTRO, reply_markup=_kb(await chosen(call.from_user.id)))


@router.callback_query(F.data.startswith("sub_t_"))
async def toggle(call: CallbackQuery):
    key = call.data[len("sub_t_"):]
    if key not in BLOCKS:
        await call.answer()
        return

    picked = await chosen(call.from_user.id)
    if key in picked:
        picked.discard(key)
        await call.answer(f"{BLOCKS[key]} — больше не присылаю")
    else:
        picked.add(key)
        await call.answer(f"{BLOCKS[key]} — буду присылать")
    await save(call.from_user.id, picked)

    try:
        await call.message.edit_reply_markup(reply_markup=_kb(picked))
    except Exception:
        pass


# ---------------------------------------------------------------------
# РАССЫЛКА
# ---------------------------------------------------------------------

async def deliver(bot: Bot, slot: str, text: str) -> int:
    """Разослать вышедший блок тем, кто его выбрал.

    Заблокировавшего бота отписываем молча: повторять некому, а очередь
    он засоряет каждый день. Остальные ошибки пропускаем — один
    недоставленный не должен останавливать рассылку.
    """
    if slot not in BLOCKS or not text.strip():
        return 0

    sent = 0
    for user_id in await database.subscribers_of(KEY, slot):
        try:
            await bot.send_message(user_id, text[:4000],
                                   parse_mode="Markdown",
                                   disable_web_page_preview=True)
            sent += 1
        except TelegramForbiddenError:
            await database.set_setting(KEY + str(user_id), "")
            logging.info(f"Подписка: {user_id} заблокировал бота, отписала")
        except Exception as e:
            logging.warning(f"Подписка: {user_id} не получил {slot}: {e}")
        await asyncio.sleep(PAUSE)
    return sent


async def stats() -> str:
    """Сколько людей на каждом блоке — для служебного экрана"""
    lines = ["🔔 <b>Подписки на блоки</b>", ""]
    total = 0
    for key, name in BLOCKS.items():
        people = await database.subscribers_of(KEY, key)
        total += len(people)
        lines.append(f"{html.escape(name)} — {len(people)}")
    if not total:
        lines.append("\n<i>Пока никто не подписался. Кнопка — в главном "
                     "меню и по команде /подписки.</i>")
    return "\n".join(lines)
