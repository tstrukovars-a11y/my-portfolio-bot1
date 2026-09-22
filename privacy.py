# privacy.py — что бот знает о человеке и как это стереть.
#
# Экран нужен не для галочки. Бот видит, кто им пользуется, и хранит
# место, если человек прислал его ради погоды. Пока это не сказано вслух,
# человек узнаёт об этом сам и в худший момент — например, увидев, что
# бот помнит его город.
#
# Поэтому три правила:
#
#   1. Перечисляем то, что храним на самом деле, а не общими словами.
#      «Некоторые технические данные» — это признание, что считать лень.
#   2. Каждому пункту — зачем. Данные без назначения не собирают.
#   3. Удаление работает по-настоящему и доступно самому человеку, а не
#      по письму владельцу. Обещание стереть, которое исполняется вручную
#      и когда-нибудь, — не обещание.
#
# Это не юридическая политика обработки персональных данных: такую пишет
# юрист, и она нужна отдельно. Здесь — честный человеческий текст.
from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)

import database

router = Router()

TEXT = {
    "ru": (
        "🔒 <b>Данные</b>\n\n"
        "<b>Что бот видит и хранит</b>\n"
        "• ваш номер в Telegram, имя и @имя — их Telegram сообщает любому "
        "боту, которому вы написали;\n"
        "• выбранный язык — чтобы не спрашивать каждый раз;\n"
        "• какие разделы вы открывали и когда — чтобы понимать, что здесь "
        "нужно, а что нет;\n"
        "• место, <b>если вы сами его прислали</b> ради погоды, — "
        "округлённое примерно до километра. Точку на карте бот не хранит: "
        "для погоды хватает города;\n"
        "• ваш прогресс в уроках и играх, ответы в опросах, оплаченный "
        "доступ и напоминания, на которые вы подписались.\n\n"
        "<b>Кому это уходит</b>\n"
        "• погода считается по координатам во внешнем сервисе прогнозов — "
        "туда уходит только место, без вашего имени;\n"
        "• если вы пишете в раздел «Чат AI», текст запроса уходит в "
        "Anthropic — иначе ответить нечем;\n"
        "• оплата целиком проходит внутри Telegram: карту и её номер бот "
        "не видит и не хранит.\n\n"
        "Больше никуда и никому. Списки не продаются и не передаются — "
        "это бот одного человека, а не рекламная сеть.\n\n"
        "<b>Как стереть</b>\n"
        "Кнопкой ниже, сразу и без переписки. Удалится всё: имя, история, "
        "место, прогресс и оплаченный доступ — восстановить будет нечем. "
        "Останутся только записи об оплатах: этого требует учёт.\n\n"
        "Открыть этот экран снова — команда /данные."
    ),
    "en": (
        "🔒 <b>Your data</b>\n\n"
        "<b>What the bot sees and keeps</b>\n"
        "• your Telegram id, name and @username — Telegram gives these to "
        "any bot you write to;\n"
        "• your chosen language, so it needn't ask again;\n"
        "• which sections you opened and when, to see what is useful here;\n"
        "• your location <b>if you sent it yourself</b> for the weather — "
        "rounded to about a kilometre. The exact point is not stored: a "
        "town is enough for a forecast;\n"
        "• your progress in lessons and games, poll answers, paid access "
        "and the reminders you subscribed to.\n\n"
        "<b>Where it goes</b>\n"
        "• the forecast is fetched from an external weather service — only "
        "the place is sent, never your name;\n"
        "• if you write in the AI section, your text goes to Anthropic — "
        "there is no other way to answer;\n"
        "• payment happens inside Telegram: the bot never sees your card.\n\n"
        "Nowhere else. Nothing is sold or shared — this is one person's "
        "bot, not an ad network.\n\n"
        "<b>How to erase it</b>\n"
        "The button below, at once and with no correspondence. Everything "
        "goes: name, history, location, progress and paid access. Only "
        "payment records stay — bookkeeping requires them.\n\n"
        "To open this screen again: /data"
    ),
}

ASK = {
    "ru": ("Удалить всё, что бот о вас знает?\n\n"
           "Вместе с историей пропадёт прогресс в уроках и оплаченный "
           "доступ, если он есть. Вернуть будет нечем."),
    "en": ("Erase everything the bot knows about you?\n\n"
           "Your lesson progress and any paid access go with it. "
           "There is no way back."),
}

DONE = {
    "ru": "🗑 Готово. Бот вас не помнит.\n\nМожно начать заново: /start",
    "en": "🗑 Done. The bot does not remember you.\n\nStart over: /start",
}

FAILED = {
    "ru": "Не вышло — база не отвечает. Попробуйте позже.",
    "en": "It did not work — the database is unavailable. Try later.",
}

BTN_OPEN = {"ru": "🔒 Что бот знает обо мне", "en": "🔒 What the bot knows",
            "fr": "🔒 Mes données", "he": "🔒 המידע שלי"}
BTN_ERASE = {"ru": "🗑 Удалить мои данные", "en": "🗑 Erase my data"}
BTN_YES = {"ru": "🗑 Да, удалить", "en": "🗑 Yes, erase"}
BTN_NO = {"ru": "⇦ Отмена", "en": "⇦ Cancel"}


def _t(table: dict, lang: str) -> str:
    return table.get(lang) or table.get("en") or ""


def _screen_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_t(BTN_ERASE, lang),
                              callback_data="privacy_erase")],
        [InlineKeyboardButton(text="⇦", callback_data="go_home")]])


@router.message(F.text.regexp(r"^/(данные|data|privacy)\b"))
async def privacy_command(message: Message):
    lang = await database.get_user_language(message.from_user.id)
    await message.answer(_t(TEXT, lang), reply_markup=_screen_kb(lang),
                         disable_web_page_preview=True)


@router.callback_query(F.data == "privacy_open")
async def open_screen(call: CallbackQuery):
    lang = await database.get_user_language(call.from_user.id)
    await call.answer()
    await call.message.answer(_t(TEXT, lang), reply_markup=_screen_kb(lang),
                              disable_web_page_preview=True)


@router.callback_query(F.data == "privacy_erase")
async def confirm(call: CallbackQuery):
    """Спрашиваем один раз: удаление необратимо, а кнопка рядом с текстом."""
    lang = await database.get_user_language(call.from_user.id)
    await call.answer()
    await call.message.answer(
        _t(ASK, lang),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=_t(BTN_YES, lang),
                                  callback_data="privacy_erase_yes")],
            [InlineKeyboardButton(text=_t(BTN_NO, lang),
                                  callback_data="privacy_open")]]))


@router.callback_query(F.data == "privacy_erase_yes")
async def erase(call: CallbackQuery):
    lang = await database.get_user_language(call.from_user.id)
    ok = await database.forget_everything(call.from_user.id)
    await call.answer()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(_t(DONE if ok else FAILED, lang))
