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
TAIL = ("Нажмите вариант — скажу, верно ли. Ответ виден только вам, "
        "а разбор выйдет завтра вместе со следующей задачей.")

LETTERS = "АБВГДЕ"          # варианты подписываем буквами: текст не влезает
# Десять — предел Telegram для опроса, и столько же кнопок мы рисуем.
# Шесть было мало: задача с семью вариантами выходила обрезанной, и если
# верный ответ стоял седьмым, нажать его было физически нельзя — любой
# ответ считался неверным. Человек знал ответ и получал «мимо».
MAX_OPTIONS = 10


# =====================================================================
# ПУБЛИКАЦИЯ
# =====================================================================

def broken(puzzle) -> str:
    """Почему задачу нельзя выпускать. Пусто — значит можно.

    Проверяем до публикации: задача, где верный ответ не показан или
    указан за пределами списка, делает неправым каждого, кто ответит.
    """
    options = puzzle.get("options") or []
    if len(options) < 2:
        return "меньше двух вариантов"
    index = puzzle.get("correct_option_id")
    if index is None or not isinstance(index, int):
        return "не указан верный ответ"
    if not 0 <= index < len(options):
        return f"верный ответ №{index} вне списка из {len(options)}"
    if index >= MAX_OPTIONS:
        return f"верный ответ №{index + 1} не поместится в {MAX_OPTIONS} кнопок"
    return ""


async def _pick():
    """Задача, которой ещё не было в канале. Кончились — берём давнюю."""
    bank = [p for p in await database.get_all_puzzles() if not broken(p)]
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


# Пока ответов мало, доля врёт и обижает: «верно 0 из 1» читается как
# приговор одному человеку, который не угадал. Цифру показываем, когда
# она что-то значит, — а разбор вчерашней задачи выходит всегда.
MIN_ANSWERS = 3


async def yesterday_line() -> str:
    """Разбор вчерашней задачи: ответ, объяснение и — если есть смысл —
    сколько человек справилось.

    Объяснение живёт здесь, а не только во всплывающем окошке после
    ответа: окошко Telegram обрезает на двухстах знаках, оно исчезает
    через секунду, и его не перечитать. Разбор назавтра — единственное
    место, где объяснение можно спокойно дочитать, и заодно повод
    вернуться в канал.
    """
    stat = await database.last_puzzle_result()
    if not stat:
        return ""

    bank = await database.get_all_puzzles()
    puzzle = next((p for p in bank if p["id"] == stat.get("puzzle_id")), None)
    if not puzzle:
        return ""

    options = puzzle.get("options") or []
    index = puzzle.get("correct_option_id")
    if not options or index is None or index >= len(options):
        return ""

    lines = [f"📊 <b>Вчерашняя задача</b>",
             f"Верный ответ: <b>{LETTERS[index]}. "
             f"{html.escape(options[index])}</b>"]

    note = (puzzle.get("explanation") or "").strip()
    if note:
        lines.append(html.escape(note))

    if stat.get("answers", 0) >= MIN_ANSWERS:
        lines.append(f"<i>Справились {stat['correct']} из "
                     f"{stat['answers']}.</i>")
    return "\n".join(lines)


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

    # Окошко Telegram обрезает на двухстах знаках и исчезает: длинное
    # объяснение туда не помещается. Поэтому в окошке — вердикт и начало,
    # а целиком отправляем в личку тем, кто с ботом уже знаком. Разбор
    # для всех остальных выйдет завтра в канале.
    await call.answer(f"{verdict}\n\n{note}"[:200] if note else verdict,
                      show_alert=True)
    if note and len(note) > 150:
        try:
            await call.bot.send_message(
                call.from_user.id,
                f"🧩 <b>{html.escape(puzzle['question'])}</b>\n\n"
                f"{verdict}\n\n{html.escape(note)}")
        except Exception:
            # Не писал боту — ничего страшного: разбор будет завтра.
            pass

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


@router.message(F.text.regexp(r"^/задача"))
async def puzzle_command(message: Message):
    """Посмотреть задачу целиком и поправить верный ответ.

    Ошибку в банке видно только так: в канале она выглядит как «вы не
    угадали», и человек винит себя, а не задачу.
    """
    if not config.is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    bank = await database.get_all_puzzles()

    if len(parts) < 2:
        bad = [(p, broken(p)) for p in bank]
        bad = [(p, why) for p, why in bad if why]
        lines = [f"🧩 <b>Банк задач</b>: {len(bank)}"]
        if bad:
            lines += ["", f"<b>Не выпускаются ({len(bad)}):</b>"]
            lines += [f"• №{p['id']} — {why}" for p, why in bad[:10]]
        lines += ["", "Посмотреть: <code>/задача 7</code>",
                  "Поправить ответ: <code>/задача 7 = 2</code>"]
        await message.answer("\n".join(lines))
        return

    try:
        puzzle_id = int(parts[1])
    except ValueError:
        await message.answer("Нужен номер задачи: <code>/задача 7</code>")
        return

    puzzle = next((p for p in bank if p["id"] == puzzle_id), None)
    if not puzzle:
        await message.answer(f"Задачи №{puzzle_id} в банке нет.")
        return

    if "=" in (message.text or ""):
        tail = message.text.split("=", 1)[1].strip()
        if not tail.isdigit():
            await message.answer("Нужен номер варианта: <code>/задача 7 = 2</code>")
            return
        number = int(tail)
        if not 1 <= number <= len(puzzle["options"]):
            await message.answer(
                f"Вариантов всего {len(puzzle['options'])}.")
            return
        if await database.set_puzzle_answer(puzzle_id, number - 1):
            await message.answer(
                f"✅ Верный ответ задачи №{puzzle_id}: "
                f"«{html.escape(puzzle['options'][number - 1])}».")
        else:
            await message.answer("⚠️ Не записалось. Проверьте базу: /db")
        return

    lines = [f"🧩 <b>Задача №{puzzle_id}</b>", "",
             html.escape(puzzle["question"]), ""]
    for i, option in enumerate(puzzle["options"]):
        mark = " ✅" if i == puzzle["correct_option_id"] else ""
        lines.append(f"{i + 1}. {html.escape(option)}{mark}")
    note = (puzzle.get("explanation") or "").strip()
    lines += ["", f"<i>{html.escape(note)}</i>" if note else "<i>Разбора нет</i>"]
    why = broken(puzzle)
    if why:
        lines += ["", f"⚠️ Не выпускается: {why}"]
    lines += ["", "Поправить: <code>/задача "
              f"{puzzle_id} = номер</code>"]
    await message.answer("\n".join(lines))
