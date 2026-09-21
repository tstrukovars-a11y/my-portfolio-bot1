# lang.py — язык учится без языка-прокладки.
#
# Так учат в стране языка: значение показывают, а не переводят. Поэтому в
# уроке нет ни одного русского слова — только картинка, фраза и выбор.
# Перевод дал бы понимание быстрее, но чужое: человек запоминал бы пару
# «ножницы = ciseaux» и каждый раз ходил бы через русский.
#
# Отсюда три правила, на которых держится модуль:
#
#   1. Вопрос и ответ — на изучаемом языке. Значение несёт эмодзи.
#   2. Слова возвращаются: то, что встретилось в теме «школа», всплывает
#      в диалоге и в следующей теме. Повторение делает понимание своим.
#   3. Проверка — выбором, а не набором текста: иврит с русской
#      клавиатуры не наберёшь, и урок сломался бы на первом же слове.
#
# Содержание лежит в data/lang.json и правится без кода: добавить тему —
# это дописать словарь, а не трогать модуль.
import json
import logging
import os
import random

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)

import config
import database

router = Router()

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "lang.json")
STATE_KEY = "lang_state_"        # + id: урок целиком, чтобы пережить деплой
LESSON = 8                       # карточек в уроке: больше не досиживают

_content = None


def content() -> dict:
    global _content
    if _content is None:
        try:
            with open(DATA, encoding="utf-8") as f:
                _content = json.load(f).get("languages") or {}
        except Exception as e:
            logging.error(f"Уроки языка не читаются: {e}")
            _content = {}
    return _content


def cards_of(code: str, topic: str) -> list:
    return ((content().get(code) or {}).get("topics") or {}).get(topic, {}).get("cards", [])


def all_cards(code: str) -> list:
    """Все карточки языка — из них берутся неверные варианты.

    Брать их только из текущей темы было бы проще, но тогда выбор всегда
    идёт между пятью знакомыми словами и превращается в угадайку.
    """
    out = []
    for topic in ((content().get(code) or {}).get("topics") or {}).values():
        out.extend(topic.get("cards", []))
    return out


# ---------------------------------------------------------------------
# УРОК
# ---------------------------------------------------------------------

def build(code: str, topic: str, known: set) -> list:
    """Задания урока.

    Сначала идут новые карточки, потом те, что человек уже видел, — иначе
    повторение вытесняет новое и урок стоит на месте.
    """
    cards = cards_of(code, topic)
    if not cards:
        return []
    fresh = [c for c in cards if c["id"] not in known]
    seen = [c for c in cards if c["id"] in known]
    random.shuffle(fresh)
    random.shuffle(seen)
    picked = (fresh + seen)[:LESSON]

    tasks = []
    for i, card in enumerate(picked):
        # Чередуем: «что это» (выбрать фразу) и «покажи» (выбрать картинку).
        tasks.append({"card": card, "kind": "say" if i % 2 == 0 else "show"})
    return tasks


def options(code: str, card: dict, kind: str) -> list:
    """Четыре варианта: верный и три чужих из того же языка"""
    pool = [c for c in all_cards(code) if c["id"] != card["id"]]
    random.shuffle(pool)
    others = pool[:3]
    if kind == "say":
        items = [(card["lines"][0]["a"], card["id"])] + \
                [(c["lines"][0]["a"], c["id"]) for c in others]
    else:
        items = [(card["emoji"], card["id"])] + \
                [(c["emoji"], c["id"]) for c in others]
    random.shuffle(items)
    return items


def question(code: str, task: dict) -> str:
    card = task["card"]
    line = card["lines"][0]
    if task["kind"] == "say":
        return f"{card['emoji']}\n\n<b>{line['q']}</b>"
    return f"<b>{card['word']}</b>"


def _kb(items: list, right_id: str) -> InlineKeyboardMarkup:
    rows = []
    for text, cid in items:
        mark = "1" if cid == right_id else "0"
        rows.append([InlineKeyboardButton(text=text[:64],
                                          callback_data=f"lang_a_{mark}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------
# СОСТОЯНИЕ
# ---------------------------------------------------------------------

async def _state(user_id: int):
    raw = await database.get_setting(STATE_KEY + str(user_id))
    try:
        return json.loads(raw) if raw else None
    except (ValueError, TypeError):
        return None


async def _save(user_id: int, state):
    await database.set_setting(STATE_KEY + str(user_id),
                               json.dumps(state, ensure_ascii=False) if state else "")


# ---------------------------------------------------------------------
# ЭКРАНЫ
# ---------------------------------------------------------------------

def _langs_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=data["title"], callback_data=f"lang_l_{code}")]
        for code, data in content().items()])


def _topics_kb(code: str) -> InlineKeyboardMarkup:
    topics = (content().get(code) or {}).get("topics") or {}
    rows = [[InlineKeyboardButton(text=t["title"], callback_data=f"lang_t_{code}_{key}")]
            for key, t in topics.items()]
    rows.append([InlineKeyboardButton(text="⇦", callback_data="lang_open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text.regexp(r"^/(язык|lang)"))
async def lang_command(message: Message):
    await message.answer(
        "🗣 <b>Язык без перевода</b>\n\nВыберите язык. Дальше русского не "
        "будет: значение показывает картинка, а слова возвращаются в других "
        "фразах — так понимание становится своим.",
        reply_markup=_langs_kb())


@router.callback_query(F.data == "lang_open")
async def open_menu(call: CallbackQuery):
    await call.answer()
    await call.message.answer("🗣 <b>Язык без перевода</b>\n\nВыберите язык.",
                              reply_markup=_langs_kb())


@router.callback_query(F.data.startswith("lang_l_"))
async def pick_language(call: CallbackQuery):
    code = call.data.split("_")[-1]
    data = content().get(code)
    await call.answer()
    if not data:
        return
    await call.message.answer(f"{data['hello']}\n\n{data['title']}",
                              reply_markup=_topics_kb(code))


@router.callback_query(F.data.startswith("lang_t_"))
async def pick_topic(call: CallbackQuery):
    _, _, code, topic = call.data.split("_", 3)
    await call.answer()

    known = await database.lang_known(call.from_user.id)
    tasks = build(code, topic, known)
    if not tasks:
        await call.message.answer("Здесь пока пусто.")
        return

    await _save(call.from_user.id,
                {"code": code, "topic": topic, "i": 0, "right": 0,
                 "ids": [t["card"]["id"] for t in tasks],
                 "kinds": [t["kind"] for t in tasks]})
    await _ask(call.message, call.from_user.id)


async def _ask(message: Message, user_id: int):
    state = await _state(user_id)
    if not state:
        return
    if state["i"] >= len(state["ids"]):
        await _finish(message, user_id, state)
        return

    code = state["code"]
    card_id = state["ids"][state["i"]]
    card = next((c for c in all_cards(code) if c["id"] == card_id), None)
    if not card:
        state["i"] += 1
        await _save(user_id, state)
        await _ask(message, user_id)
        return

    task = {"card": card, "kind": state["kinds"][state["i"]]}
    items = options(code, card, task["kind"])
    await message.answer(
        f"{question(code, task)}\n\n<i>{state['i'] + 1} / {len(state['ids'])}</i>",
        reply_markup=_kb(items, card["id"]))


@router.callback_query(F.data.startswith("lang_a_"))
async def answer(call: CallbackQuery):
    user_id = call.from_user.id
    state = await _state(user_id)
    if not state:
        await call.answer("Урок закончен. Начать заново: /язык", show_alert=True)
        return

    right = call.data.endswith("1")
    data = content().get(state["code"]) or {}
    await call.answer(random.choice(data.get("right" if right else "wrong", ["…"])))

    card_id = state["ids"][state["i"]]
    await database.lang_seen(user_id, card_id, right)
    if right:
        state["right"] += 1
    state["i"] += 1
    await _save(user_id, state)
    await _ask(call.message, user_id)


async def _finish(message: Message, user_id: int, state: dict):
    code, topic = state["code"], state["topic"]
    data = content().get(code) or {}
    total = len(state["ids"])
    await _save(user_id, None)

    # Диалог в конце — то, ради чего всё: слова урока встречаются снова,
    # уже в живой речи, и понимаются без разбора по словам.
    dialog = ((data.get("topics") or {}).get(topic) or {}).get("dialog")
    lines = [f"<b>{state['right']} / {total}</b>"]
    if dialog:
        lines += ["", f"<b>{dialog['title']}</b>", ""]
        lines += [f"{turn['who']}  {turn['text']}" for turn in dialog["turns"]]

    await message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔁", callback_data=f"lang_t_{code}_{topic}")],
            [InlineKeyboardButton(text=data.get("title", "⇦"),
                                  callback_data=f"lang_l_{code}")]]))
