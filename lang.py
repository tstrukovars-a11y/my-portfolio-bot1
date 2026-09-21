# lang.py — язык на слух, без языка-прокладки.
#
# Учится тот язык, на котором живёшь. С текстом переводчик справляется:
# даже кривой перевод вывески понятен. А в кафе и по телефону текста нет —
# автоответчик говорит быстро и не ждёт. Поэтому урок начинается со звука,
# а написанное показывается уже после ответа.
#
# И без русского: перевод дал бы понимание быстрее, но чужое — человек
# запоминал бы пару «ножницы = ciseaux» и каждый раз ходил бы через него.
#
# Отсюда четыре правила, на которых держится модуль:
#
#   1. Сначала слышно, потом видно. Фраза звучит, значение несёт эмодзи,
#      текст появляется после ответа — как закрепление, а не подсказка.
#   2. Половина заданий — ответы: расслышать мало, надо дать понять, что
#      понял, или переспросить. Для этого есть отдельная тема.
#   3. Слова возвращаются: то, что встретилось в теме «школа», всплывает
#      в диалоге и в следующей теме. Повторение делает понимание своим.
#   4. Проверка — выбором, а не набором текста: иврит с русской
#      клавиатуры не наберёшь, и урок сломался бы на первом же слове.
#
# Содержание лежит в data/lang.json и правится без кода: добавить тему —
# это дописать словарь, а не трогать модуль.
import hashlib
import json
import logging
import os
import random

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, FSInputFile)

import config
import database

router = Router()

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "lang.json")
AUDIO = os.path.join(HERE, "data", "audio")
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
# ЗВУК
# ---------------------------------------------------------------------
#
# В стране текста нет: автоответчик не ждёт, а в кафе никто не пишет.
# Кривой перевод на бумаге понятен, речь на слух — нет. Поэтому главное
# упражнение здесь — слушать, и только потом читать.
#
# Файлы озвучены заранее (tools/make_audio.py) и лежат рядом с кодом:
# синтезировать на сервере нечем, да и ходить в чужой сервис на каждое
# задание незачем. Имя файла — отпечаток текста, чтобы фраза, которую
# нужно узнать на слух, не читалась глазами в проигрывателе.

def digest(text: str) -> str:
    """Имя файла для фразы. Общее с tools/make_audio.py — иначе бот будет
    искать один файл, а генератор класть другой, и звук молча пропадёт."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def spoken(code: str, text: str) -> str:
    """Как фразу произносить, если написание обманывает синтезатор.

    Иврит пишут без огласовок, и одно и то же слово читается по-разному:
    синтезатор угадывает и иногда ошибается. Тогда в lang.json в раздел
    "voice" кладётся тот же текст с огласовками — на экране он остаётся
    прежним, меняется только произношение.
    """
    return ((content().get(code) or {}).get("voice") or {}).get(text, text)


def audio_path(code: str, text: str):
    path = os.path.join(AUDIO, code, digest(text) + ".m4a")
    return path if os.path.exists(path) else None


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
        # Слух первым: «услышал — покажи» и «услышал — ответь». Чтение
        # остаётся запасным вариантом, когда звука для фразы нет.
        if audio_path(code, card["word"]):
            kind = "hear"
        elif audio_path(code, card["lines"][0]["q"]):
            kind = "reply"
        else:
            kind = "say" if i % 2 == 0 else "show"
        if kind == "hear" and i % 2 and audio_path(code, card["lines"][0]["q"]):
            kind = "reply"          # чередуем узнавание и ответ
        tasks.append({"card": card, "kind": kind})
    return tasks


def options(code: str, card: dict, kind: str) -> list:
    """Четыре варианта: верный и три чужих из того же языка"""
    pool = [c for c in all_cards(code) if c["id"] != card["id"]]
    random.shuffle(pool)
    others = pool[:3]
    if kind in ("say", "reply"):
        items = [(card["lines"][0]["a"], card["id"])] + \
                [(c["lines"][0]["a"], c["id"]) for c in others]
    else:
        items = [(card["emoji"], card["id"])] + \
                [(c["emoji"], c["id"]) for c in others]
    random.shuffle(items)
    return items


# Подпись под звуком — без текста фразы: в ней весь смысл задания.
LISTEN = {"hear": "🎧", "reply": "🎧 …?"}


def question(code: str, task: dict) -> str:
    card = task["card"]
    line = card["lines"][0]
    kind = task["kind"]
    if kind in LISTEN:
        return LISTEN[kind]
    if kind == "say":
        return f"{card['emoji']}\n\n<b>{line['q']}</b>"
    return f"<b>{card['word']}</b>"


def sound(code: str, task: dict):
    """Файл, который надо услышать, либо None"""
    card = task["card"]
    if task["kind"] == "hear":
        return audio_path(code, card["word"])
    if task["kind"] == "reply":
        return audio_path(code, card["lines"][0]["q"])
    return None


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
        "🎧 <b>Язык на слух</b>\n\nВыберите язык. Дальше русского не будет: "
        "фраза звучит, а значение показывает картинка.\n\nГлавное здесь — "
        "расслышать и ответить хоть как-то: в кафе и по телефону текста "
        "нет, а переводчик не поможет.",
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
    caption = (f"{question(code, task)}\n\n"
               f"<i>{state['i'] + 1} / {len(state['ids'])}</i>")
    markup = _kb(items, card["id"])

    voice = sound(code, task)
    if voice:
        # Заголовок нейтральный: имя файла и подпись видны в проигрывателе,
        # а фразу нужно узнать ухом.
        await message.answer_audio(FSInputFile(voice), title="🎧",
                                   performer=" ", caption=caption,
                                   reply_markup=markup)
        return
    await message.answer(caption, reply_markup=markup)


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
    kind = state["kinds"][state["i"]]
    await database.lang_seen(user_id, card_id, right)

    # После звука показываем фразу письменно — тогда услышанное
    # закрепляется написанием, а не наоборот.
    if kind in LISTEN:
        card = next((c for c in all_cards(state["code"]) if c["id"] == card_id), None)
        if card:
            said = card["word"] if kind == "hear" else card["lines"][0]["q"]
            try:
                await call.message.answer(f"🎧 <b>{said}</b>")
            except Exception:
                pass
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
