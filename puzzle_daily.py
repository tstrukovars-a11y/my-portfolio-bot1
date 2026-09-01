# puzzle_daily.py — задача дня в канале и статистика по решениям.
#
# Почему кнопки, а не встроенный опрос-викторина. В канале опрос всегда
# анонимный, и бот получает только суммарные цифры: кто ответил — неизвестно.
# С кнопками приходит callback, а в нём user_id, поэтому видно и общую
# точность, и участие конкретного читателя, и то, вернулся ли он завтра.
#
# Читателю при этом ничего чужого не видно: на кнопке только число, а верно
# или нет — всплывающим окном ему одному.
import asyncio
import html
import json
import logging
import random

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)

import config
import database

router = Router()

LEAD = "🧩 <b>Задача дня</b>"
TAIL = ("Нажмите вариант — скажу, верно ли, и почему. "
        "Ответ виден только вам.")

LETTERS = "АБВГДЕ"          # варианты подписываем буквами: текст не влезает
MAX_OPTIONS = 6


# =====================================================================
# ПУБЛИКАЦИЯ
# =====================================================================

async def _pick():
    """Задача, которой ещё не было в канале. Кончились — берём давнюю."""
    bank = await database.get_all_puzzles()
    if not bank:
        return None
    used = await database.published_puzzle_ids()
    fresh = [p for p in bank if p["id"] not in used]
    if fresh:
        return random.choice(fresh)
    # Повтор — не баг: через месяц задача читается заново, а старые
    # ответы остаются в статистике отдельной публикацией.
    oldest = await database.oldest_published_puzzle()
    return next((p for p in bank if p["id"] == oldest), random.choice(bank))


def _markup(puzzle, counts=None) -> InlineKeyboardMarkup:
    """Кнопки вариантов. Счётчик появляется, когда кто-то уже ответил."""
    rows = []
    for i, option in enumerate(puzzle["options"][:MAX_OPTIONS]):
        n = (counts or {}).get(i, 0)
        label = f"{LETTERS[i]}. {option[:28]}"
        if n:
            label += f" · {n}"
        rows.append([InlineKeyboardButton(
            text=label, callback_data=f"pz_{puzzle['id']}_{i}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _text(puzzle) -> str:
    lines = [LEAD, "", html.escape(puzzle["question"]), ""]
    for i, option in enumerate(puzzle["options"][:MAX_OPTIONS]):
        lines.append(f"<b>{LETTERS[i]}.</b> {html.escape(option)}")
    lines += ["", TAIL]
    return "\n".join(lines)


async def publish(bot: Bot, chat: int, thread=None) -> str:
    """Выпустить задачу дня. Строка — для лога и для /digest."""
    puzzle = await _pick()
    if not puzzle:
        return "банк задач пуст"
    if not puzzle.get("options"):
        return "у задачи нет вариантов"

    # Вчерашний итог ставим перед новой задачей: цифра появляется тогда,
    # когда её ещё помнят, и сама подталкивает ответить сегодня.
    head = await yesterday_line()
    text = _text(puzzle)
    if head:
        text = f"{head}\n\n{text}"

    try:
        sent = await bot.send_message(chat, text, message_thread_id=thread,
                                      reply_markup=_markup(puzzle))
    except Exception as e:
        logging.error(f"Задача дня не вышла: {e}")
        return f"ошибка: {e}"

    await database.mark_puzzle_published(puzzle["id"], chat, sent.message_id)
    return f"задача дня №{puzzle['id']}"


async def yesterday_line() -> str:
    """«Вчера верно ответили 7 из 11» — либо пусто, если вчера тишина."""
    stat = await database.last_puzzle_result()
    if not stat or not stat["answers"]:
        return ""
    return (f"📊 Вчерашнюю задачу решили верно "
            f"<b>{stat['correct']}</b> из <b>{stat['answers']}</b>.")


# =====================================================================
# ОТВЕТ ЧИТАТЕЛЯ
# =====================================================================

@router.callback_query(F.data.startswith("pz_"))
async def answer(call: CallbackQuery):
    try:
        _, raw_id, raw_choice = call.data.split("_", 2)
        puzzle_id, choice = int(raw_id), int(raw_choice)
    except ValueError:
        await call.answer()
        return

    bank = await database.get_all_puzzles()
    puzzle = next((p for p in bank if p["id"] == puzzle_id), None)
    if not puzzle:
        await call.answer("Задача больше недоступна", show_alert=True)
        return

    # Второй ответ не считаем: иначе точность накручивается перебором.
    already = await database.puzzle_answer_of(call.from_user.id, puzzle_id)
    if already is not None:
        await call.answer(
            "Вы уже отвечали на эту задачу — засчитан первый ответ.",
            show_alert=True)
        return

    correct = choice == puzzle["correct_option_id"]
    await database.save_puzzle_answer(call.from_user.id, puzzle_id, correct, choice)

    right = puzzle["options"][puzzle["correct_option_id"]]
    verdict = "✅ Верно!" if correct else f"❌ Мимо. Правильный ответ: {right}"
    note = (puzzle.get("explanation") or "").strip()
    await call.answer(f"{verdict}\n\n{note}"[:200] if note else verdict,
                      show_alert=True)

    counts = await database.puzzle_choice_counts(puzzle_id)
    try:
        await call.message.edit_reply_markup(reply_markup=_markup(puzzle, counts))
    except Exception:
        pass


# =====================================================================
# СТАТИСТИКА
# =====================================================================

@router.message(F.text.startswith("/puzzlestats"))
async def stats_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    rows = await database.puzzle_channel_stats(limit=12)
    if not rows:
        await message.answer(
            "🧩 Задач в канале ещё не было.\n"
            "Выпустить сейчас: <code>/digest slot puzzle</code>")
        return

    lines = ["🧩 <b>Задача дня — как решают</b>", ""]
    total_a = total_c = 0
    for r in rows:
        total_a += r["answers"]
        total_c += r["correct"]
        pct = round(r["correct"] / r["answers"] * 100) if r["answers"] else 0
        day = r["published_at"].strftime("%d.%m") if r["published_at"] else "—"
        lines.append(
            f"{day} · {html.escape((r['question'] or '')[:40])}\n"
            f"    ответили {r['answers']}, верно {r['correct']} ({pct}%)")

    if total_a:
        lines += ["", f"<b>Всего:</b> ответов {total_a}, "
                      f"верных {total_c} ({round(total_c / total_a * 100)}%)"]
        people = await database.puzzle_people()
        lines.append(f"<b>Участников:</b> {people['people']}, "
                     f"из них вернулись больше раза: {people['repeat']}")
    await message.answer("\n".join(lines))
