# courses.py — подготовка к отбору и программа по ИИ.
#
# Два курса, устроенных одинаково: вопрос, четыре варианта и разбор.
# Разбор здесь главное. Тест, который говорит «неверно» и молчит,
# запоминается как обида; тест, который объясняет, почему неверный ответ
# выглядел правильным, запоминается как знание. Поэтому «почему»
# показывается всегда — и после ошибки, и после попадания.
#
# Содержание лежит в data/courses.json и правится без кода. Добавить тему
# или вопрос — дописать словарь.
#
# Доступ делится по курсам (access.py): первая тема открыта всем, дальше
# нужен доступ к этому курсу — не к боту целиком.
import html
import json
import logging
import os

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)

import access
import database

router = Router()

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "courses.json")
STATE_KEY = "course_state_"      # + id: прохождение целиком, переживает деплой
FREE_TOPICS = 1                  # первая тема каждого курса — всем

_content = None


def content() -> dict:
    global _content
    if _content is None:
        try:
            with open(DATA, encoding="utf-8") as f:
                _content = json.load(f).get("courses") or {}
        except Exception as e:
            logging.error(f"Курсы не читаются: {e}")
            _content = {}
    return _content


def topics_of(course: str) -> dict:
    return (content().get(course) or {}).get("topics") or {}


def items_of(course: str, topic: str) -> list:
    return (topics_of(course).get(topic) or {}).get("items") or []


def skill_of(course: str) -> str:
    return f"course_{course}"


def free_topics(course: str) -> list:
    return list(topics_of(course))[:FREE_TOPICS]


# ---------------------------------------------------------------------
# ЭКРАНЫ
# ---------------------------------------------------------------------

def _courses_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=data["title"], callback_data=f"crs_c_{key}")]
            for key, data in content().items()]
    rows.append([InlineKeyboardButton(text="⇦", callback_data="menu_intellect")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _topics_kb(course: str, paid: bool) -> InlineKeyboardMarkup:
    free = free_topics(course)
    rows = []
    for key, topic in topics_of(course).items():
        # Замок рисуем, но кнопку оставляем: закрытое должно быть видно,
        # иначе человек не знает, за что ему предлагают заплатить.
        shut = not paid and key not in free
        rows.append([InlineKeyboardButton(
            text=("🔒 " if shut else "") + topic["title"],
            callback_data=f"crs_t_{course}_{key}")])
    rows.append([InlineKeyboardButton(text="⇦", callback_data="crs_open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text.regexp(r"^/(курсы|courses)"))
async def courses_command(message: Message):
    await message.answer(
        "🎓 <b>Курсы</b>\n\nВопрос, четыре варианта и разбор. Разбор — "
        "главное: важно не то, что вы ошиблись, а почему неверный ответ "
        "выглядел правильным.",
        reply_markup=_courses_kb())


@router.callback_query(F.data == "crs_open")
async def open_courses(call: CallbackQuery):
    await call.answer()
    await call.message.answer("🎓 <b>Курсы</b>", reply_markup=_courses_kb())


@router.callback_query(F.data.startswith("crs_c_"))
async def pick_course(call: CallbackQuery):
    course = call.data[len("crs_c_"):]
    data = content().get(course)
    await call.answer()
    if not data:
        return
    paid = await access.has(call.from_user.id, skill_of(course))
    await call.message.answer(f"<b>{html.escape(data['title'])}</b>\n\n"
                              f"{html.escape(data['about'])}",
                              reply_markup=_topics_kb(course, paid))


@router.callback_query(F.data.startswith("crs_t_"))
async def pick_topic(call: CallbackQuery):
    course, _, topic = call.data[len("crs_t_"):].partition("_")
    await call.answer()

    items = items_of(course, topic)
    if not items:
        await call.message.answer("Здесь пока пусто.")
        return

    if topic not in free_topics(course) \
            and not await access.has(call.from_user.id, skill_of(course)):
        await _wall(call.message, course)
        return

    await _save(call.from_user.id,
                {"course": course, "topic": topic, "i": 0, "right": 0})
    await _ask(call.message, call.from_user.id)


# ---------------------------------------------------------------------
# ПРОХОЖДЕНИЕ
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


def _answers_kb(item: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text[:64],
                              callback_data=f"crs_a_{1 if i == item['right'] else 0}")]
        for i, text in enumerate(item["options"])])


async def _ask(message: Message, user_id: int):
    state = await _state(user_id)
    if not state:
        return
    items = items_of(state["course"], state["topic"])
    if state["i"] >= len(items):
        await _finish(message, user_id, state)
        return

    item = items[state["i"]]
    await message.answer(
        f"<b>{html.escape(item['q'])}</b>\n\n"
        f"<i>{state['i'] + 1} / {len(items)}</i>",
        reply_markup=_answers_kb(item))


@router.callback_query(F.data.startswith("crs_a_"))
async def answer(call: CallbackQuery):
    user_id = call.from_user.id
    state = await _state(user_id)
    if not state:
        await call.answer("Этот вопрос уже закрыт. Начать заново: /курсы",
                          show_alert=True)
        return

    items = items_of(state["course"], state["topic"])
    if state["i"] >= len(items):
        await call.answer()
        return

    item = items[state["i"]]
    right = call.data.endswith("1")
    await call.answer("Верно" if right else "Не так")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Разбор после каждого ответа, включая верный: угадать из четырёх
    # вариантов можно и не поняв, а понять — только из объяснения.
    head = "✅" if right else f"❌ Верно: <b>{html.escape(item['options'][item['right']])}</b>"
    await call.message.answer(f"{head}\n\n{html.escape(item['why'])}")

    if right:
        state["right"] += 1
    state["i"] += 1
    await _save(user_id, state)
    await _ask(call.message, user_id)


async def _finish(message: Message, user_id: int, state: dict):
    course, topic = state["course"], state["topic"]
    items = items_of(course, topic)
    total = len(items)
    got = state["right"]
    await _save(user_id, None)

    # Итог словами, а не только цифрой: «3 из 5» ничего не говорит о том,
    # что делать дальше.
    if got == total:
        verdict = "Всё верно. Эту тему можно считать закрытой."
    elif got * 2 >= total:
        verdict = "Больше половины. Разборы к ошибкам стоит перечитать — там и лежит разница."
    else:
        verdict = "Тема пока не ваша. Это нормально: пройдите её ещё раз, разборы уже прочитаны."

    await message.answer(
        f"<b>{got} / {total}</b>\n\n{verdict}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔁", callback_data=f"crs_t_{course}_{topic}")],
            [InlineKeyboardButton(text=content().get(course, {}).get("title", "⇦"),
                                  callback_data=f"crs_c_{course}")]]))

    if not await access.has(user_id, skill_of(course)):
        await _wall(message, course, "🎓 Это была пробная тема целиком.")


async def _wall(message: Message, course: str, done: str = ""):
    skill = skill_of(course)
    await message.answer(
        access.wall_text(skill, done, card=bool(await access.pay_url(skill))),
        reply_markup=await access.buy_kb(skill),
        disable_web_page_preview=True)
