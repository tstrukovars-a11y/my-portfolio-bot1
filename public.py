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
BLOCKED_POPUP = "Здесь это не открывается. Напишите боту — отвечу лично."

# Служебное в общем чате не показывается никому, включая владелицу:
# её команда, набранная в группе, печатает списки там же, где стоят
# читатели. Чтобы подключить чат, нужен его номер — его и присылаем
# в личку, а сама команда выполняется оттуда.
OWNER_HINT = ("Служебное в общий чат не выходит — его видно всем, кто "
              "туда зашёл.\n\nНомер этого чата: <code>{chat_id}</code>\n"
              "Команду наберите здесь, в личке.")


def allowed(data: str) -> bool:
    """Можно ли этой кнопке работать под постом"""
    return bool(data) and data.startswith(PUBLIC_OK)


# ---------------------------------------------------------------------
# ПРАВИЛО, КОТОРОЕ НЕЛЬЗЯ ОБОЙТИ ПО ЗАБЫВЧИВОСТИ
# ---------------------------------------------------------------------
#
# Список разрешённых кнопок — всё ещё договорённость: тот, кто завтра
# добавит в задачу дня строчку message.answer(...), напишет в канал, и
# список ему не помешает. Договорённость держится на памяти, а память
# и подвела в прошлый раз.
#
# Поэтому обработчику в общем чате пост выдаётся не целиком. Всё, чем
# можно написать, ответить, переслать или стереть, закрыто на уровне
# самого объекта. Открыта ровно одна вещь — перерисовать свою же
# разметку: на ней держатся счётчик отклика и счётчик ответов.
#
# Попытка написать в канал не проходит молча: она падает с ошибкой и
# уходит в лог с именем кнопки. Это сигнал, что появился обработчик,
# который считает канал своим чатом.

WRITES = ("answer", "reply", "send", "edit", "delete", "forward", "copy",
          "pin", "unpin")
KEEP = ("edit_reply_markup",)   # счётчик на кнопке — часть самого поста


class PublicWrite(RuntimeError):
    """Обработчик попытался написать в общий чат"""


class Guarded:
    """Пост, выданный обработчику в руки, но не целиком.

    Не «обработчик не должен писать в канал», а «обработчик не может
    писать в канал». Разница видна ровно тогда, когда кто-то забудет
    правило — то есть однажды обязательно.
    """

    def __init__(self, real, why: str = ""):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_why", why)

    def __getattr__(self, name):
        real = object.__getattribute__(self, "_real")
        value = getattr(real, name)
        if name in KEEP or not callable(value) or not name.startswith(WRITES):
            return value

        why = object.__getattribute__(self, "_why")

        async def refuse(*args, **kwargs):
            logging.error(
                f"Публичный чат: обработчик «{why}» попытался вызвать "
                f"{name}() под постом. Личный ответ в общий чат не уходит.")
            raise PublicWrite(name)

        return refuse


class GuardedBot(Guarded):
    """Бот, которому закрыт путь в один конкретный чат.

    Обработчик пишет человеку в личку сколько угодно — это и есть то,
    чего от него ждут. Закрыт только адрес общего чата, откуда пришло
    нажатие.
    """

    def __init__(self, real, chat_id, why: str = ""):
        super().__init__(real, why)
        object.__setattr__(self, "_chat_id", chat_id)

    def __getattr__(self, name):
        real = object.__getattribute__(self, "_real")
        value = getattr(real, name)
        if not callable(value) or not name.startswith(WRITES):
            return value

        chat_id = object.__getattribute__(self, "_chat_id")
        why = object.__getattribute__(self, "_why")

        async def checked(*args, **kwargs):
            target = kwargs.get("chat_id", args[0] if args else None)
            if target == chat_id:
                logging.error(
                    f"Публичный чат: обработчик «{why}» попытался вызвать "
                    f"{name}() прямо в общий чат.")
                raise PublicWrite(name)
            return await value(*args, **kwargs)

        return checked


def narrowed(event):
    """Нажатие в общем чате, урезанное до того, что ему можно.

    Сам объект нажатия не трогаем: call.answer — это окошко у того, кто
    нажал, его никто другой не видит.
    """
    chat_id = getattr(getattr(event.message, "chat", None), "id", None)
    return _Call(event,
                 Guarded(event.message, event.data),
                 GuardedBot(event.bot, chat_id, event.data))


class _Call:
    """Нажатие, у которого пост и бот уже урезаны"""

    def __init__(self, real, message, bot):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_why", getattr(real, "data", ""))
        object.__setattr__(self, "_message", message)
        object.__setattr__(self, "_bot", bot)

    def __getattr__(self, name):
        if name == "message":
            return object.__getattribute__(self, "_message")
        if name == "bot":
            return object.__getattribute__(self, "_bot")
        real = object.__getattribute__(self, "_real")
        # answer — окошко у нажавшего, а не сообщение в чат.
        return getattr(real, name)


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
    if is_private(event):
        return await handler(event, data)

    if allowed(event.data):
        # Разрешённой кнопке пост выдаётся урезанным: написать в канал
        # она не может, даже если однажды попробует.
        try:
            return await handler(narrowed(event), data)
        except PublicWrite:
            await event.answer(BLOCKED_POPUP, show_alert=True)
            return None

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
    """Команды в общем чате не выполняются ни для кого.

    Сначала здесь было исключение для владелицы: ей случается
    подключать чат оттуда, где она стоит. Исключение неверное. Ответ на
    её команду печатается в том же чате — то есть служебные списки
    выходят на глаза всем, кто туда зашёл. Право набрать команду и
    право показать ответ при всех — разные вещи.

    Поэтому чат ей нужен не для команды, а для номера. Номер уходит в
    личку, команда набирается там же.
    """
    import config

    text = getattr(event, "text", "") or ""
    chat = getattr(event, "chat", None)
    if getattr(chat, "type", "private") == "private" or not text.startswith("/"):
        return await handler(event, data)

    user = getattr(event, "from_user", None)
    if user and config.is_admin(user.id):
        try:
            await event.bot.send_message(
                user.id, OWNER_HINT.format(chat_id=getattr(chat, "id", "?")))
        except Exception as e:
            logging.info(f"Команда в общем чате: личка недоступна ({e})")
    return None
