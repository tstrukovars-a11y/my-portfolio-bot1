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

import access
import config
import database

router = Router()

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "lang.json")
AUDIO = os.path.join(HERE, "data", "audio")
STATE_KEY = "lang_state_"        # + id: урок целиком, чтобы пережить деплой
LESSON = 8                       # карточек в уроке: больше не досиживают

# Первая тема каждого языка бесплатна целиком, вместе с входным тестом.
# Огрызок вместо урока показывал бы, что продукт плохой: человек должен
# успеть понять на себе, что слух без перевода работает.
FREE_TOPICS = 1


def skill_of(code: str) -> str:
    return f"lang_{code}"


def free_topics(code: str) -> list:
    return list(((content().get(code) or {}).get("topics") or {}))[:FREE_TOPICS]

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


def phrases(code: str) -> list:
    """Всё, что в языке звучит: слова, реплики, диалоги.

    Один перечень на всех: по нему озвучивают (tools/make_audio.py),
    по нему же проверяют на слух. Разойдись они — проверять начали бы
    одно, а отправлять людям другое.
    """
    out, said = [], set()
    for topic in ((content().get(code) or {}).get("topics") or {}).values():
        for card in topic.get("cards", []):
            for text in [card["word"]] + [l["q"] for l in card["lines"]] \
                    + [l["a"] for l in card["lines"]]:
                if text not in said:
                    said.add(text)
                    out.append(text)
        for turn in topic.get("dialog", {}).get("turns", []):
            if turn["text"] not in said:
                said.add(turn["text"])
                out.append(turn["text"])
    return out


# ---------------------------------------------------------------------
# УРОВЕНЬ
# ---------------------------------------------------------------------
#
# Уровень здесь — не словарный запас, а то, сколько нужно удержать в
# голове на слух:
#
#   1. Услышал слово — показал, что это. Значение несёт картинка.
#   2. Услышал вопрос — выбрал ответ. Слово надо не только узнать, но и
#      понять, о чём спрашивают.
#   3. Услышал чужую реплику в разговоре — понял, что сказать дальше.
#      Картинки нет, опоры нет, есть только речь.
#
# Считать сложность по длине фразы не вышло: «un crayon» и «a pencil» —
# два слова из-за артикля, а трудности в них нет. Зато разница между
# «узнать слово» и «ответить в разговоре» настоящая и слышна сразу.

MAX_LEVEL = 3


def turns_of(code: str) -> list:
    """Пары реплик из диалогов: (что слышно, что отвечают).

    Диалог — единственный материал, где речь идёт своим ходом и не ждёт,
    пока вы вспомните слово. Поэтому третья ступень измеряется им.
    """
    out = []
    for topic in ((content().get(code) or {}).get("topics") or {}).values():
        turns = (topic.get("dialog") or {}).get("turns") or []
        for first, second in zip(turns, turns[1:]):
            if audio_path(code, first["text"]):
                out.append((first["text"], second["text"]))
    return out


# ---------------------------------------------------------------------
# УРОК
# ---------------------------------------------------------------------

def build(code: str, topic: str, known: set, level: int = 1) -> list:
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
        #
        # Чем выше ступень, тем реже картинка: узнавать слово по ней
        # начинающему нужно, а тому, кто держит вопрос, — уже нет.
        answers = audio_path(code, card["lines"][0]["q"])
        if answers and (level >= 3 or (level == 2 and i % 2)):
            kind = "reply"
        elif audio_path(code, card["word"]):
            kind = "hear"
        elif answers:
            kind = "reply"
        else:
            kind = "say" if i % 2 == 0 else "show"
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


def _kb(items: list, right_id: str, prefix: str = "lang_a_") -> InlineKeyboardMarkup:
    rows = []
    for text, cid in items:
        mark = "1" if cid == right_id else "0"
        rows.append([InlineKeyboardButton(text=text[:64],
                                          callback_data=prefix + mark)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------
# ВХОДНОЙ ТЕСТ
# ---------------------------------------------------------------------
#
# Спрашивать «какой у вас уровень» бессмысленно: человек либо скромничает,
# либо называет школьный английский двадцатилетней давности. Поэтому
# уровень не спрашивается, а слышится — шесть записей от слова к реплике.
#
# Тест короткий и обрывается сам: если обе фразы ступени не узнаны, дальше
# слушать нечего, и лучше начать заниматься, чем добивать человека тем,
# чего он ещё не понимает.

EXAM = 2                         # заданий на ступень
EXAM_KEY = "lang_exam_"          # + id: незаконченный тест
LEVEL_KEY = "lang_level_"        # + id + _ + код языка


def exam(code: str) -> list:
    """Задания входного теста: слово → вопрос → реплика в разговоре"""
    out = []

    words = [c for c in all_cards(code) if audio_path(code, c["word"])]
    random.shuffle(words)
    out += [{"tier": 1, "kind": "hear", "id": c["id"]} for c in words[:EXAM]]

    asks = [c for c in all_cards(code) if audio_path(code, c["lines"][0]["q"])]
    random.shuffle(asks)
    out += [{"tier": 2, "kind": "reply", "id": c["id"]} for c in asks[:EXAM]]

    pairs = turns_of(code)
    random.shuffle(pairs)
    out += [{"tier": 3, "kind": "turn", "phrase": heard, "answer": reply}
            for heard, reply in pairs[:EXAM]]
    return out


def turn_options(code: str, answer: str) -> list:
    """Что ответить: верная реплика и три чужих

    Чужие берём из ответов карточек — они того же вида и той же длины,
    поэтому выбрать наугад по форме не выйдет, придётся расслышать.
    """
    pool = [c["lines"][0]["a"] for c in all_cards(code)
            if c["lines"][0]["a"] != answer]
    random.shuffle(pool)
    items = [(answer, "1")] + [(text, "0") for text in pool[:3]]
    random.shuffle(items)
    return items


def level_of(answers: list) -> int:
    """Уровень по ответам: [(ступень, верно ли), …]

    Достаточно одного попадания на ступени: на слух угадать чужую фразу
    из четырёх вариантов — это уже понимание, а не везение. Требовать
    оба ответа значило бы ронять человека на ступень вниз за одну помарку.
    """
    level = 1
    for tier, right in answers:
        if right:
            level = max(level, tier)
    return min(level, MAX_LEVEL)


def exam_over(answers: list, tier: int) -> bool:
    """Ступень провалена целиком — дальше будет только хуже"""
    tried = [right for t, right in answers if t == tier]
    return len(tried) >= EXAM and not any(tried)


LEVEL_NAMES = {
    1: "Слышу отдельные слова",
    2: "Понимаю короткий вопрос",
    3: "Держу реплику целиком",
}

LEVEL_NEXT = {
    1: "Начнём со слов: их надо узнавать мгновенно, иначе фраза "
       "рассыпается, пока вы вспоминаете первое слово.",
    2: "Уроки будут из вопросов и ответов — тех, что звучат в кафе и по "
       "телефону. Картинка останется через раз.",
    3: "Дальше — вопрос и ответ без картинок: опора вам уже не нужна.",
}


async def level(user_id: int, code: str) -> int:
    raw = await database.get_setting(f"{LEVEL_KEY}{user_id}_{code}")
    try:
        return max(1, min(MAX_LEVEL, int(raw)))
    except (TypeError, ValueError):
        return 1


async def set_level(user_id: int, code: str, value: int):
    await database.set_setting(f"{LEVEL_KEY}{user_id}_{code}", str(value))


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
    rows = [[InlineKeyboardButton(text=data["title"], callback_data=f"lang_l_{code}")]
            for code, data in content().items()]
    # Сюда приходят и по команде /язык, и из «Путешествий»: выход должен
    # быть в обоих случаях, иначе экран становится тупиком.
    rows.append([InlineKeyboardButton(text="⇦", callback_data="go_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _topics_kb(code: str, at_level: int = 0, paid: bool = True) -> InlineKeyboardMarkup:
    topics = (content().get(code) or {}).get("topics") or {}
    free = free_topics(code)
    rows = []
    for key, t in topics.items():
        # Замок рисуем, но кнопку не убираем: спрятанное не купят, а
        # человек должен видеть, что там дальше.
        shut = not paid and key not in free
        rows.append([InlineKeyboardButton(
            text=("🔒 " if shut else "") + t["title"],
            callback_data=f"lang_t_{code}_{key}")])
    if at_level:
        rows.append([InlineKeyboardButton(
            text=f"🎚 {LEVEL_NAMES[at_level]} · проверить заново",
            callback_data=f"lang_x_{code}")])
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

    user_id = call.from_user.id
    if not await database.get_setting(f"{LEVEL_KEY}{user_id}_{code}"):
        # Уровень ещё не известен. Предлагаем проверить, но не запираем:
        # тест — помощь, а не турникет, и начать с нуля можно сразу.
        await call.message.answer(
            f"{data['hello']}\n\n"
            "Прежде чем начать — шесть записей, чтобы понять, что вы уже "
            "слышите. Спрашивать «какой у вас уровень» бесполезно: это "
            "видно только на слух.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎧 Проверить слух",
                                      callback_data=f"lang_x_{code}")],
                [InlineKeyboardButton(text="Начать с простого",
                                      callback_data=f"lang_s_{code}")],
                [InlineKeyboardButton(text="⇦", callback_data="lang_open")]]))
        return

    await _topics(call.message, user_id, code)


async def _topics(message: Message, user_id: int, code: str):
    data = content().get(code) or {}
    at = await level(user_id, code)
    paid = await access.has(user_id, skill_of(code))
    await message.answer(f"{data.get('hello', '')}\n\n{data.get('title', '')}",
                         reply_markup=_topics_kb(code, at, paid))


@router.callback_query(F.data.startswith("lang_s_"))
async def start_simple(call: CallbackQuery):
    """Без теста — значит с первой ступени"""
    code = call.data.split("_")[-1]
    await call.answer()
    await set_level(call.from_user.id, code, 1)
    await _topics(call.message, call.from_user.id, code)


# --- входной тест -----------------------------------------------------

async def _exam_state(user_id: int):
    raw = await database.get_setting(EXAM_KEY + str(user_id))
    try:
        return json.loads(raw) if raw else None
    except (ValueError, TypeError):
        return None


@router.callback_query(F.data.startswith("lang_x_"))
async def start_exam(call: CallbackQuery):
    code = call.data.split("_")[-1]
    await call.answer()
    items = exam(code)
    if not items:
        await set_level(call.from_user.id, code, 1)
        await _topics(call.message, call.from_user.id, code)
        return

    await database.set_setting(EXAM_KEY + str(call.from_user.id), json.dumps(
        {"code": code, "i": 0, "answers": [], "items": items},
        ensure_ascii=False))
    await _exam_ask(call.message, call.from_user.id)


async def _exam_ask(message: Message, user_id: int):
    state = await _exam_state(user_id)
    if not state:
        return
    items = state["items"]
    if state["i"] >= len(items):
        await _exam_finish(message, user_id, state)
        return

    code = state["code"]
    item = items[state["i"]]
    counter = f"\n\n<i>{state['i'] + 1} / {len(items)}</i>"

    if item["kind"] == "turn":
        voice = audio_path(code, item["phrase"])
        markup = _kb(turn_options(code, item["answer"]), "1", "lang_xa_")
        caption = LISTEN["reply"] + counter
    else:
        card = next((c for c in all_cards(code) if c["id"] == item["id"]), None)
        if not card:
            state["i"] += 1
            await database.set_setting(EXAM_KEY + str(user_id),
                                       json.dumps(state, ensure_ascii=False))
            await _exam_ask(message, user_id)
            return
        task = {"card": card, "kind": item["kind"]}
        voice = sound(code, task)
        markup = _kb(options(code, card, item["kind"]), card["id"], "lang_xa_")
        caption = question(code, task) + counter

    if voice:
        await message.answer_audio(FSInputFile(voice), title="🎧",
                                   performer=" ", caption=caption,
                                   reply_markup=markup)
        return
    await message.answer(caption, reply_markup=markup)


@router.callback_query(F.data.startswith("lang_xa_"))
async def exam_answer(call: CallbackQuery):
    user_id = call.from_user.id
    state = await _exam_state(user_id)
    if not state:
        await call.answer()
        return

    right = call.data.endswith("1")
    data = content().get(state["code"]) or {}
    await call.answer(random.choice(data.get("right" if right else "wrong", ["…"])))

    tier = state["items"][state["i"]]["tier"]
    state["answers"].append([tier, right])
    state["i"] += 1
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Ступень не взята ни разу — дальше только сложнее. Останавливаемся:
    # добивать человека тем, чего он не понимает, незачем.
    if exam_over([tuple(a) for a in state["answers"]], tier):
        await _exam_finish(call.message, user_id, state)
        return

    await database.set_setting(EXAM_KEY + str(user_id),
                               json.dumps(state, ensure_ascii=False))
    await _exam_ask(call.message, user_id)


async def _exam_finish(message: Message, user_id: int, state: dict):
    code = state["code"]
    at = level_of([tuple(a) for a in state["answers"]])
    await database.set_setting(EXAM_KEY + str(user_id), "")
    await set_level(user_id, code, at)

    await message.answer(
        f"🎚 <b>{LEVEL_NAMES[at]}</b>\n\n{LEVEL_NEXT[at]}")
    await _topics(message, user_id, code)


@router.callback_query(F.data.startswith("lang_t_"))
async def pick_topic(call: CallbackQuery):
    _, _, code, topic = call.data.split("_", 3)
    await call.answer()

    if topic not in free_topics(code) \
            and not await access.has(call.from_user.id, skill_of(code)):
        await _wall(call.message, code)
        return

    known = await database.lang_known(call.from_user.id)
    tasks = build(code, topic, known, await level(call.from_user.id, code))
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

    # Разговор дослушан — вот теперь и только теперь уместно про деньги:
    # человек уже знает на себе, работает это у него или нет.
    if not await access.has(user_id, skill_of(code)):
        await _wall(message, code, "🎧 Это был пробный урок целиком.")


async def _wall(message: Message, code: str, done: str = ""):
    skill = skill_of(code)
    await message.answer(access.wall_text(skill, done),
                         reply_markup=await access.buy_kb(skill),
                         disable_web_page_preview=True)
