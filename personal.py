# personal.py — тихий экран для того, кто пришёл за одним делом.
#
# Человек в канале нажимает «напомнить о матче». Дальше он попадал в
# бота и получал выбор языка на четырёх алфавитах, приветствие про
# ROI-кейсы, меню из восьми разделов и кнопку про удаление данных. Он
# хотел одного напоминания.
#
# По разделам никто не ходит. Меню полезно тому, кто уже решил остаться;
# тому, кто пришёл за делом, оно мешает и отпугивает.
#
# Поэтому здесь — личный угол: что ему придёт и откуда погода. Никаких
# разделов, никаких предложений. Всё остальное — одной сдержанной
# строкой внизу, для тех, кто сам захочет посмотреть.
import html

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)

import database

router = Router()

# Язык не спрашиваем, а берём у Telegram: он и так знает, на каком
# человек читает. Экран с четырьмя алфавитами на входе — это вопрос,
# ответ на который уже есть.
KNOWN = ("ru", "en", "fr", "he")


def guess_language(user) -> str:
    code = (getattr(user, "language_code", "") or "").lower()[:2]
    if code in KNOWN:
        return code
    # Иврит Telegram отдаёт как «iw» — старый код, который остался в
    # стандарте с семидесятых.
    return "he" if code == "iw" else "ru"


async def ensure_language(user) -> str:
    """Язык человека. Новому — ставим по телефону, не спрашивая."""
    saved = await database.get_user_language(user.id)
    if saved:
        return saved
    fresh = guess_language(user)
    await database.set_user_language(user.id, fresh)
    return fresh


async def card(user_id: int) -> tuple:
    """(текст, кнопки) личного экрана"""
    lines = ["🙋 <b>Ваше</b>", ""]

    try:
        import weather
        place = await weather._place(user_id)
    except Exception:
        place = None
    if place:
        lines.append(f"📍 Погода: {html.escape(place[2] or 'ваше место')}")
    else:
        lines.append("📍 Погода: место не указано")

    try:
        import subs
        chosen = await subs.chosen(user_id)
        if chosen:
            names = ", ".join(subs.BLOCKS[key] for key in sorted(chosen))
            lines.append(f"🔔 Приходит: {names}")
        else:
            lines.append("🔔 Ничего лично не присылаю")
    except Exception:
        pass

    try:
        waiting = await database.my_alerts(user_id)
    except Exception:
        waiting = 0
    if waiting:
        lines.append(f"🎾 Жду начала матчей: {waiting}")

    rows = [
        [InlineKeyboardButton(text="🌦 Погода", callback_data="wx_again")],
        [InlineKeyboardButton(text="🔔 Что присылать", callback_data="subs_open")],
        [InlineKeyboardButton(text="Посмотреть всё остальное",
                              callback_data="go_home")],
    ]

    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def quiet(message: Message, user):
    """Пришедшему по ссылке — ничего сверх того, за чем он пришёл.

    Первая версия показывала здесь личный экран: погоду, подписки,
    счётчик матчей. Это оказалось тем же меню, только короче. Человек
    нажал «напомнить о матче» и получил погоду — значит, его снова не
    услышали.

    Поэтому здесь остаётся одно невидимое действие: запомнить язык,
    чтобы следующее сообщение пришло на нужном. Личный экран никуда не
    делся — он открывается по /моё, когда человек сам захочет.
    """
    await ensure_language(user)


@router.message(F.text.regexp(r"^/(моё|мое|me)\b"))
async def mine_command(message: Message):
    text, markup = await card(message.from_user.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "mine_open")
async def open_card(call: CallbackQuery):
    await call.answer()
    text, markup = await card(call.from_user.id)
    await call.message.answer(text, reply_markup=markup)
