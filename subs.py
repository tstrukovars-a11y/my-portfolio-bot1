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
    "tennis": "расписание на день",
    "tennis_loud": "громкие события",
    "tennis_results": "итоги дня",
    "tennis_champion": "чемпионы турниров",
    "books": "📚 Книги",
    "travel": "🌍 Путешествия",
}

# Тема — это ещё не то, на что человек хочет подписаться.
#
# В теннисе мы выпускаем пять разных вещей, и нужны они разным людям:
# одному важно, что сняли Медведева, другому — только итоги вечером,
# третьему расписание, чтобы успеть сесть к экрану. Подписка «теннис»
# присылала всем всё, и отписывались не от темы, а от количества.
#
# Поэтому внутри темы — типы постов. Кнопка «всё о теннисе» остаётся
# для тех, кому правда нужно всё: выбор из пяти пунктов там, где
# человек хотел один раз нажать, тоже отпугивает.
GROUPS = {
    "tennis": {
        "title": "🎾 Теннис",
        "parts": ("tennis", "tennis_loud", "tennis_results",
                  "tennis_champion"),
    },
}

# Ключи, которые показываются сами по себе, — всё, что не внутри группы.
GROUPED = {key for group in GROUPS.values() for key in group["parts"]}


async def chosen(user_id: int) -> set:
    raw = await database.get_setting(KEY + str(user_id)) or ""
    return {x for x in raw.split(",") if x in BLOCKS}


async def save(user_id: int, blocks: set):
    await database.set_setting(KEY + str(user_id), ",".join(sorted(blocks)))


def _mark(on: bool) -> str:
    return "✅ " if on else "○ "


def _kb(picked: set) -> InlineKeyboardMarkup:
    """Кнопки выбора. Группа — заголовком, её типы — под ним.

    Отступ у вложенных не для красоты: без него пять теннисных строк
    читаются как пять отдельных тем, и человек выбирает одну вместо
    того, чтобы понять, что это одна тема в разных видах.
    """
    rows, done = [], set()
    for key, name in BLOCKS.items():
        if key in done:
            continue
        group = next((g for g in GROUPS.values() if key in g["parts"]), None)
        if group:
            parts = group["parts"]
            whole = all(p in picked for p in parts)
            some = any(p in picked for p in parts)
            head = "✅ " if whole else ("◍ " if some else "○ ")
            rows.append([InlineKeyboardButton(
                text=f"{head}{group['title']} — всё",
                callback_data=f"sub_g_{parts[0]}")])
            for part in parts:
                rows.append([InlineKeyboardButton(
                    text=f"     {_mark(part in picked)}{BLOCKS[part]}",
                    callback_data=f"sub_t_{part}")])
            done.update(parts)
            continue
        rows.append([InlineKeyboardButton(
            text=_mark(key in picked) + name, callback_data=f"sub_t_{key}")])

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


@router.callback_query(F.data.startswith("sub_g_"))
async def toggle_group(call: CallbackQuery):
    """«Всё о теме» — одним нажатием.

    Полвыбора считаем «не всё»: если отмечены два типа из четырёх,
    нажатие добирает остальные, а не снимает выбранное. Снять всё можно
    вторым нажатием — но потерять уже сделанный выбор случайно нельзя.
    """
    first = call.data[len("sub_g_"):]
    group = next((g for g in GROUPS.values() if first in g["parts"]), None)
    if not group:
        await call.answer()
        return

    parts = set(group["parts"])
    picked = await chosen(call.from_user.id)
    if parts <= picked:
        picked -= parts
        await call.answer(f"{group['title']} — больше не присылаю")
    else:
        picked |= parts
        await call.answer(f"{group['title']} — буду присылать целиком")
    await save(call.from_user.id, picked)
    try:
        await call.message.edit_reply_markup(reply_markup=_kb(picked))
    except Exception:
        pass


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

    # Теннисные посты собраны на HTML, утренние — на Markdown. Отправить
    # одно разметкой другого значит получить отказ Telegram и молчание
    # вместо рассылки.
    mode = "HTML" if slot.startswith("tennis") else "Markdown"

    sent = 0
    for user_id in await database.subscribers_of(KEY, slot):
        try:
            await bot.send_message(user_id, text[:4000],
                                   parse_mode=mode,
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
    # Ради этого экрана теннис и делился: видно, что выбирают — тему
    # целиком или один её вид. Если узкое берут чаще широкого, значит
    # догадка про типы постов верна, и это проверяется цифрами, а не
    # ощущением.
    for key, name in BLOCKS.items():
        people = await database.subscribers_of(KEY, key)
        total += len(people)
        group = next((g for g in GROUPS.values() if key in g["parts"]), None)
        label = f"    └ {name}" if group else name
        lines.append(f"{html.escape(label)} — {len(people)}")
    if not total:
        lines.append("\n<i>Пока никто не подписался. Кнопка — в главном "
                     "меню и по команде /подписки.</i>")
    return "\n".join(lines)
