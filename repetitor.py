# repetitor.py — объяснить то, что в конспекте написано, а понятнее не
# стало.
#
# Самая маленькая из частей учебного модуля — и единственная, что
# успевает к экзамену. Остальное (билеты, деревья, отметки о пройденном)
# требует сначала расшифровать весь конспект; здесь ничего заранее
# оцифровывать не надо: спрашивают про то место, где встали.
#
# Задача не в том, чтобы прочитать почерк. Тетрадь свою человек читает
# прекрасно — он читает и не понимает. Поэтому первая версия этого
# модуля была ошибкой: в ней стояло правило «объясняй только то, что на
# странице», и оно запрещало ровно то, ради чего сюда приходят. В
# лекции записано сжато, непонятное место на той же странице не
# объясняется никогда, и ответ «этого тут нет» оставляет человека ровно
# там, где он был.
#
# Но и свободы не может быть полной. Государственные и муниципальные
# финансы — дисциплина нормативов, сроков и статей Бюджетного кодекса,
# они меняются год от года, модель помнит их на момент обучения и
# называет уверенно. Устаревший норматив, принесённый на экзамен как
# знание, хуже невыученного: его не перепроверяют.
#
# Отсюда граница, на которой держится весь раздел. Смысл — свободно:
# чем дотация отличается от субвенции, от года не зависит. Величины —
# только из конспекта: норматив, по которому налог делится между
# бюджетами, зависит. Объяснять шире страницы, цифры брать со страницы.
import base64
import html
import io
import logging

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import config
import database

router = Router()

MODEL = "claude-opus-5-5"
MAX_TOKENS = 1400

# Сколько реплик помним. Разговор учебный: «а почему тогда…» без истории
# не к чему отнести. Но страницы — это картинки, и они тяжёлые, поэтому
# хвост короче, чем в общем разделе ИИ.
HISTORY_TURNS = 8

ALLOWED_KEY = "repetitor_users"     # кому открыт, через запятую

PROMPT = (
    "Ты репетитор по дисциплине «Государственные и муниципальные "
    "финансы». Студентка читает свой конспект, не понимает место и "
    "спрашивает. Экзамен скоро — отвечай по существу и коротко, это "
    "читают с телефона.\n\n"
    "Объясняй шире конспекта. В лекции записано сжато, и непонятное "
    "место почти никогда не объясняется на той же странице: держись ты "
    "одного написанного — непонятное таким и останется. Приводи примеры, "
    "говори, зачем эта вещь существует и чем отличается от соседней; "
    "именно различие соседних понятий обычно и есть пробел.\n\n"
    "Но величины — только из конспекта. Нормативы отчислений, сроки, "
    "предельные доли, номера и редакции статей Бюджетного кодекса "
    "меняются год от года, а ты помнишь их на момент обучения. Поэтому "
    "цифру, срок или номер статьи называй, только если они есть в "
    "присланном тексте, и ровно так, как там записаны. Если нужной "
    "величины в присланном нет — скажи, что её тут нет, и отправь "
    "смотреть в конспект или в кодекс. По памяти не называй и не "
    "округляй.\n\n"
    "Граница простая: чем дотация отличается от субвенции, от года не "
    "зависит — это объясняй свободно. Норматив, по которому налог "
    "делится между бюджетами, зависит — его бери только из конспекта.\n\n"
    "Ищи пробел. Если из вопроса видно, что не хватает более раннего "
    "понятия, назови его и объясни сначала его: непонятно обычно не то "
    "место, о котором спрашивают, а то, на которое оно опирается.\n\n"
    "Термины дисциплины сохраняй — их спросят на экзамене. Объясняй "
    "простыми словами, но не подменяй термин бытовым словом.\n\n"
    "Без вступлений вроде «конечно» и «давайте разберём». Обычный текст "
    "или лёгкий Markdown, без таблиц и заголовков.\n\n"
    "Если прислали фотографию и слово не читается — скажи какое и "
    "попроси уточнить, не угадывай."
)

HELLO = (
    "📘 <b>Репетитор</b>\n\n"
    "Спросите, что непонятно, своими словами. Кусок конспекта можно "
    "переписать текстом — или сфотографировать страницу, чтобы не "
    "перепечатывать.\n\n"
    "Объясняю шире конспекта: примеры, зачем это нужно, чем отличается "
    "от соседнего. А вот цифры — нормативы, сроки, статьи — беру только "
    "из вашего конспекта: они меняются год от года, и названная по "
    "памяти может оказаться прошлогодней.\n\n"
    "Спрашивайте подряд, я помню разговор. "
    "<code>/заново</code> — начать с чистого листа."
)

NO_KEY = "📘 Репетитор пока недоступен: не настроен ключ доступа к модели."


class Razbor(StatesGroup):
    asking = State()


# ─────────────────────────── доступ ───────────────────────────
#
# Белый список, а не общий лимит. Раздел ходит в модель с картинками, и
# открытый вход — это чужой счёт за чужую учёбу. Список короткий и
# пополняется одной кнопкой: владелице приходит запрос, она разрешает.

async def allowed_ids() -> set:
    raw = await database.get_setting(ALLOWED_KEY) or ""
    out = set()
    for piece in raw.replace(" ", "").split(","):
        if piece.lstrip("-").isdigit():
            out.add(int(piece))
    return out


async def allow(user_id: int) -> bool:
    ids = await allowed_ids()
    if user_id in ids:
        return False
    ids.add(user_id)
    await database.set_setting(ALLOWED_KEY, ",".join(str(x) for x in sorted(ids)))
    return True


async def may_use(user_id: int) -> bool:
    return config.is_admin(user_id) or user_id in await allowed_ids()


def _request_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Разрешить",
                             callback_data=f"rep_ok_{user_id}")]])


async def _ask_owner(bot: Bot, message: Message):
    """Показать владелице, кто просится, и дать кнопку.

    Без этого доступ выдаётся так: человек узнаёт свой telegram id,
    диктует его, владелица вводит команду. Три шага, на каждом ошибка в
    цифре, и всё это ради одного разрешения.
    """
    who = message.from_user
    name = html.escape(who.full_name or "без имени")
    tag = f" @{html.escape(who.username)}" if who.username else ""
    try:
        await bot.send_message(
            config.ADMIN_ID,
            f"📘 Просит доступ к разбору лекций:\n<b>{name}</b>{tag} "
            f"· <code>{who.id}</code>",
            reply_markup=_request_kb(who.id))
    except Exception as e:
        logging.warning(f"Запрос доступа к разбору не дошёл: {e}")


@router.callback_query(F.data.startswith("rep_ok_"))
async def grant(call: CallbackQuery, bot: Bot):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    try:
        who = int(call.data[len("rep_ok_"):])
    except ValueError:
        await call.answer()
        return
    added = await allow(who)
    await call.answer("Открыла" if added else "Уже был открыт")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if added:
        try:
            await bot.send_message(who, HELLO)
        except Exception as e:
            logging.warning(f"Приглашение в разбор не дошло: {e}")


# ─────────────────────────── вход ───────────────────────────

@router.message(F.text.regexp(r"^/(разбор|лекция|repetitor)"))
async def open_razbor(message: Message, state: FSMContext, bot: Bot):
    if not await may_use(message.from_user.id):
        await message.answer(
            "📘 Разбор лекций открывается по запросу. Я передала вашу "
            "просьбу — ответ придёт сюда же.")
        await _ask_owner(bot, message)
        return
    await state.set_state(Razbor.asking)
    await state.update_data(history=[])
    await message.answer(HELLO)


@router.message(F.text.regexp(r"^/(заново|reset_razbor)"))
async def restart(message: Message, state: FSMContext):
    if await state.get_state() != Razbor.asking:
        return
    await state.update_data(history=[])
    await message.answer("📘 Начали заново. Присылайте страницу.")


@router.message(F.text.regexp(r"^/(стоп|выход)"))
async def leave(message: Message, state: FSMContext):
    if await state.get_state() != Razbor.asking:
        return
    await state.clear()
    await message.answer("📘 Вышла из разбора. Вернуться: /разбор")


# ─────────────────────────── разговор ───────────────────────────

async def _image_block(bot: Bot, file_id: str) -> dict:
    """Страница в том виде, в каком её понимает модель."""
    buffer = io.BytesIO()
    await bot.download(file_id, destination=buffer)
    data = base64.standard_b64encode(buffer.getvalue()).decode("ascii")
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg",
                       "data": data}}


def _photo_id(message: Message) -> str:
    """Самый крупный размер: мелкий почерк на превью не прочитать."""
    if message.photo:
        return message.photo[-1].file_id
    doc = message.document
    if doc and (doc.mime_type or "").startswith("image/"):
        return doc.file_id
    return ""


@router.message(Razbor.asking, F.photo | F.document | F.text)
async def answer(message: Message, state: FSMContext, bot: Bot):
    if not await may_use(message.from_user.id):
        await state.clear()
        return

    from anthropic import AsyncAnthropic
    if not config.ANTHROPIC_API_KEY:
        await message.answer(NO_KEY)
        return

    file_id = _photo_id(message)
    said = (message.caption if file_id else message.text) or ""

    if not file_id and not said.strip():
        await message.answer("Пришлите фотографию страницы или напишите "
                             "вопрос текстом.")
        return

    content = []
    if file_id:
        try:
            content.append(await _image_block(bot, file_id))
        except Exception as e:
            logging.error(f"Разбор: страница не скачалась — {e}")
            await message.answer("Не смогла открыть фотографию. "
                                 "Пришлите ещё раз.")
            return
    content.append({"type": "text", "text": said.strip()
                    or "Объясните, что написано на этой странице."})

    data = await state.get_data()
    history = list(data.get("history", []))
    history.append({"role": "user", "content": content})

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    try:
        response = await client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=PROMPT,
            messages=history)
        reply = "".join(b.text for b in response.content
                        if getattr(b, "type", "") == "text")
    except Exception as e:
        logging.error(f"Разбор: модель не ответила — {type(e).__name__}: {e}")
        note = "Модель сейчас не отвечает. Попробуйте ещё раз через минуту."
        if "credit balance" in str(e).lower() or "billing" in str(e).lower():
            note = "Закончились средства на счёте модели."
        if config.is_admin(message.from_user.id):
            note += f"\n\n<code>{html.escape(str(e)[:300])}</code>"
        await message.answer(note)
        return

    if not reply.strip():
        await message.answer("Модель промолчала. Пришлите страницу ещё раз.")
        return

    history.append({"role": "assistant", "content": reply})
    # Храним хвост: страницы тяжёлые, а старые к новому вопросу уже не
    # относятся.
    await state.update_data(history=history[-HISTORY_TURNS:])

    # Разметку модель иногда возвращает такую, что Telegram её не
    # разбирает и отклоняет сообщение целиком. Тогда — обычным текстом:
    # объяснение без курсива лучше, чем отсутствие объяснения.
    try:
        await message.answer(reply)
    except Exception:
        await message.answer(reply, parse_mode=None)
