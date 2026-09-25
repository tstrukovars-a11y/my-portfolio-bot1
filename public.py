# public.py — граница между каналом и личкой.
#
# Кнопка, нажатая под постом в канале, приходит в бота вместе с самим
# постом: call.message — это опубликованное сообщение, а не переписка с
# человеком. Дальше обработчик делает привычное message.answer(...) — и
# ответ уходит туда же, в канал, на глазах у всех подписчиков.
#
# Так утекло меню: кнопка «Как это касается меня» под утренним выпуском
# вызывала список разборов, и он печатался прямо в «Акценте».
#
# Хуже другое. Шаг разбора идёт через edit_text, а если правка не
# вышла — через delete. И то и другое применяется к call.message, то
# есть к опубликованному посту: любой читатель мог переписать или
# стереть выпуск в канале.
#
# Поэтому правило обратное привычному: в публичном чате запрещено всё,
# кроме названного здесь поимённо. Обработчик, написанный завтра, по
# умолчанию окажется закрытым — а не открытым, как вышло с деревом.
#
# Разрешены только те кнопки, которые задуманы под постом и ничего в
# чужой чат не пишут: они отвечают окошком и перерисовывают свою же
# разметку.
#
#   vote_ — отклик под новостью: счётчик на самой кнопке.
#   pz_   — задача дня: вердикт в окошке, разбор приходит в личку.
#   xo_   — крестики-нолики: игра в чате и есть смысл затеи.
#
# Всё остальное открывается у человека в личке — там же, где он и
# ожидал это увидеть.
import logging

PUBLIC_OK = ("vote_", "pz_", "xo_", "xoi_")

# Текст окошка, когда в личку написать не удалось: человек не начинал
# с ботом разговор, и Telegram не даёт написать первым.
CLOSED = ("Это открывается в личке с ботом.\n\n"
          "Напишите ему — и нажмите снова.")
MOVED = "Открыла у вас в личке — чтобы не мешать остальным в канале."

LEAD = ("Вы нажали кнопку в канале. Отвечаю здесь: в канале это увидели "
        "бы все подписчики.")


def allowed(data: str) -> bool:
    """Можно ли этой кнопке работать под постом"""
    return bool(data) and data.startswith(PUBLIC_OK)


def is_private(event) -> bool:
    """Нажатие пришло из переписки с человеком, а не из канала.

    Сообщения нет вовсе — это инлайн-режим: поле живёт в чужом чате,
    своего чата у него нет и утечь ответу некуда.
    """
    message = getattr(event, "message", None)
    if message is None:
        return True
    chat = getattr(message, "chat", None)
    return getattr(chat, "type", "private") == "private"


def button_of(markup, data: str):
    """Надпись на кнопке, которую нажали.

    Нужна, чтобы в личке предложить ровно ту же кнопку: человек узнаёт
    её и понимает, что попал куда хотел, а не в случайное меню.
    """
    for row in getattr(markup, "inline_keyboard", None) or []:
        for button in row:
            if getattr(button, "callback_data", None) == data:
                return getattr(button, "text", "") or "Открыть"
    return "Открыть"


async def keep_private(handler, event, data):
    """Не пускать личный ответ в общий чат.

    Обработчик в публичном чате не запускается вовсе — иначе он успеет
    написать в канал раньше, чем мы поймём, что он это сделал.

    Вместо этого человеку в личку уходит та же кнопка. Нажатие в личке
    приходит обычным путём, и обработчик отрабатывает там, где и должен
    был: ничего не зная про эту подмену.
    """
    if is_private(event) or allowed(event.data):
        return await handler(event, data)

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    label = button_of(getattr(event.message, "reply_markup", None), event.data)
    try:
        await event.bot.send_message(
            event.from_user.id, LEAD,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=label,
                                     callback_data=event.data)]]))
    except Exception as e:
        # Не писал боту — Telegram не даёт написать первым.
        logging.info(f"Кнопка из канала: личка закрыта ({e})")
        await event.answer(CLOSED, show_alert=True)
        return None

    await event.answer(MOVED, show_alert=True)
    return None


async def commands_stay_private(handler, event, data):
    """Команды в общем чате — только от владелицы.

    В группе-дубле команда печатается всем, кто туда заходит: человек
    пишет /меню, и разделы бота разворачиваются у всех на виду. Своим
    же командам владелицы мешать незачем — ей случается подключать
    канал прямо оттуда, где она стоит.
    """
    import config

    text = getattr(event, "text", "") or ""
    chat = getattr(event, "chat", None)
    if getattr(chat, "type", "private") == "private" or not text.startswith("/"):
        return await handler(event, data)

    user = getattr(event, "from_user", None)
    if user and config.is_admin(user.id):
        return await handler(event, data)
    return None
