# repetitor.py — объяснить то место в лекции, которое не понятно.
#
# Самая маленькая из всех частей учебного модуля — и единственная, что
# успевает к экзамену. Остальное (билеты, деревья, отметки о пройденном)
# требует расшифровать весь конспект; здесь страница приходит по одной,
# ровно тогда, когда человек на ней встал.
#
# Отсюда главное устройство: источник — присланная страница, а не
# подготовленный корпус. Снял на телефон то место, где застрял, —
# получил объяснение этого места. Ничего заранее оцифровывать не надо.
#
# И отсюда же главный запрет. Государственные и муниципальные финансы —
# дисциплина нормативов, сроков и статей Бюджетного кодекса. Они меняются
# год от года, модель помнит их на момент обучения и называет уверенно.
# Студент принесёт на экзамен цифру, которой уже нет, и узнает об этом
# на экзамене. Поэтому модель объясняет написанное, а чего на странице
# нет — о том говорит, что нет. «Не знаю» здесь дороже ответа.
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
    "Ты объясняешь студентке место из её конспекта по дисциплине "
    "«Государственные и муниципальные финансы». Экзамен скоро, поэтому "
    "отвечай по существу и коротко — это читают с телефона.\n\n"
    "Главное правило. Объясняй то, что написано на присланной странице "
    "или в присланном тексте. Это дисциплина нормативов, сроков и статей "
    "Бюджетного кодекса, они меняются год от года, и названная тобой по "
    "памяти цифра может оказаться устаревшей. Поэтому:\n"
    "— если на странице есть цифра, норматив, срок или номер статьи, "
    "опирайся на них и приводи их так, как они записаны;\n"
    "— если того, о чём спрашивают, на странице нет, так и скажи: «на "
    "этой странице этого нет». Можешь добавить общее пояснение, но "
    "отдельной строкой и прямо пометив, что это не из конспекта;\n"
    "— ничего не досочиняй и не округляй.\n\n"
    "Почерк. Если слово не читается, не угадывай: скажи, какое место "
    "неразборчиво, и попроси уточнить. Неверно прочитанный термин хуже "
    "пропущенного.\n\n"
    "Как объяснять. Сначала одним предложением — о чём это место вообще. "
    "Потом разбор по сути: что за чем следует и почему именно так. "
    "Простыми словами, но термины дисциплины сохраняй — их спросят на "
    "экзамене. Без вступлений вроде «конечно» и «давайте разберём».\n\n"
    "Обычный текст или лёгкий Markdown. Без таблиц и заголовков."
)

HELLO = (
    "📘 <b>Разбор лекции</b>\n\n"
    "Пришлите фотографию страницы — или просто перепишите кусок текстом — "
    "и спросите, что непонятно. Можно сразу с вопросом в подписи к фото.\n\n"
    "Объясняю то, что на странице. Чего там нет — скажу, что нет: цифры и "
    "сроки в этой дисциплине меняются, и выдуманная цифра опаснее "
    "ненайденной.\n\n"
    "Дальше можно спрашивать подряд, я помню разговор. "
    "<code>/заново</code> — начать с чистого листа."
)

NO_KEY = "📘 Разбор пока недоступен: не настроен ключ доступа к модели."


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
