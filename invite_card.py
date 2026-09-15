# invite_card.py — приглашение в «Акцент» для читателей других каналов.
#
# У справочных каналов своя публика: в книжный приходят за книгами, в
# кухню за рецептами. Звать их общим «подпишитесь на наш канал» — значит
# получить отказ: человек не знает, что он там найдёт.
#
# Поэтому приглашение начинается с того, зачем человек уже здесь, и
# только потом показывает остальное. Одно и то же предложение, четыре
# разных первых фразы.
import html
import logging
import os

from aiogram import Router, F, Bot
from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton,
                           FSInputFile)

import config
import database

router = Router()

MARKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "marks")
MARK = os.path.join(MARKS, "kontur", "znak-aktsent-512.png")

LINK_KEY = "channel_url"        # та же настройка, что у growth

# Куда звать: слово человека -> (настройка с id канала, имя, первая фраза).
TARGETS = {
    "книги": ("books_channel", "Бизнес-литература",
              "Эту книжную полку собирает «Акцент» — журнал для тех, "
              "кто хочет начать своё дело."),
    "путешествия": ("travel_channel", "Вокруг света",
                    "Эти места приходят сюда из «Акцента» — журнала для тех, "
                    "кто хочет начать своё дело."),
    "еда": ("recipes_channel", "Кухня",
            "Эти рецепты — часть «Акцента», журнала для тех, "
            "кто хочет начать своё дело."),
    "теннис": ("tennis_channel", "Теннис",
               "Расписание матчей ведёт «Акцент» — журнал для тех, "
               "кто хочет начать своё дело."),
    "клуб": ("club_chat", "Клуб",
             "Обсуждение живёт вокруг «Акцента» — журнала для тех, "
             "кто хочет начать своё дело."),
}

# Общее приглашение — то, что пересылают в чужие чаты и каналы. Здесь
# первой фразой не за что зацепиться темой, поэтому цепляемся за
# состояние: человек и так листает ленту, вопрос лишь в том, остаётся ли
# после этого что-нибудь в голове.
#
# Текст можно переписать из бота: чужие слова в своём канале всегда
# звучат чужими, а лезть за этим в код — глупость.
GENERAL_KEY = "invite_card_text"

GENERAL = (
    "🧭 <b>«Акцент» — журнал для тех, кто хочет начать своё дело</b>\n\n"
    "Быть в курсе — не листать ленту до полуночи.\n\n"
    "Здесь за семь минут в день вы узнаёте, что случилось в мире, сколько "
    "стоит доллар, какую книгу стоит прочитать и почему, куда съездить и "
    "что приготовить на ужин. Только факты и никаких рассылок в три часа "
    "ночи.\n\n"
    "Подписывайтесь — и завтра утром вы уже будете знать, что происходит."
)


# Что человек получает, подписавшись. Список по времени суток, а не по
# темам: так видно, что канал живой каждый день, а не «иногда пишем».
DAY = (
    "🕗 <b>Утро</b> — курсы валют и что случилось вчера, коротко\n"
    "📚 <b>11:00</b> — книга и чему она учит\n"
    "🧬 <b>13:00</b> — генетика человеческим языком\n"
    "🧩 <b>14:30</b> — задача дня\n"
    "🌍 <b>16:00</b> — место, куда стоит съездить\n"
    "🏆 <b>19:00</b> — спорт\n"
    "🍳 <b>20:30</b> — что приготовить на ужин"
)

# Пост для чужого канала. Его публикует другой человек, поэтому он
# написан от третьего лица: «мы» и «наш» в чужом канале выдают чужой
# текст. Кнопок здесь нет и быть не может — инлайн-кнопку в чужом канале
# ставит только бот-администратор этого канала, а у нас его там нет.
# Поэтому ссылка идёт строкой, её видно и по ней нажимают.
PARTNER = (
    "<b>«Акцент» — журнал для тех, кто хочет начать своё дело</b>\n\n"
    "Каждый день коротко: что случилось в мире и сколько стоит доллар, "
    "какую книгу прочитать и почему, куда съездить и что приготовить "
    "вечером.\n\n"
    "Без воды, без рассылок, семь коротких сообщений в день.\n\n"
    "👉 {url}"
)

CLOSING = ("Без рассылок и без «доброго времени суток». "
           "Семь коротких сообщений в день — и можно отписаться в любой момент.")


async def _card(where: str) -> str:
    if where == "общее":
        return await database.get_setting(GENERAL_KEY) or GENERAL
    lead = TARGETS[where][2]
    return f"{lead}\n\n{DAY}\n\n{CLOSING}"


async def _markup(share: bool = False) -> InlineKeyboardMarkup:
    url = await database.get_setting(LINK_KEY)
    rows = [[InlineKeyboardButton(text="📣 Читать «Акцент»", url=url)]]
    if share:
        # Кнопка «Поделиться» открывает у нажавшего выбор чата с уже
        # готовым текстом. Для приглашения, которое пересылают, это
        # важнее всего: приглашать должны читатели, а не только автор.
        from urllib.parse import quote
        rows.append([InlineKeyboardButton(
            text="↗️ Поделиться",
            url=f"https://t.me/share/url?url={quote(url, safe='')}"
                f"&text={quote('Журнал «Акцент» — коротко о том, что стоит знать', safe='')}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _menu() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🧭 Общее приглашение",
                                  callback_data="invcard_общее")],
            [InlineKeyboardButton(text="🤝 Пост для чужого канала",
                                  callback_data="invcard_обмен")]]
    rows += [[InlineKeyboardButton(text=title, callback_data=f"invcard_{name}")]
             for name, (_, title, _) in TARGETS.items()]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text.startswith("/zvat"))
async def invite_card(message: Message, bot: Bot):
    """Приглашение в «Акцент» для соседнего канала"""
    if not config.is_admin(message.from_user.id):
        return

    url = await database.get_setting(LINK_KEY)
    if not url:
        await message.answer(
            "❌ Сначала задайте ссылку на «Акцент»: "
            "<code>/channel https://t.me/accent_hub</code>")
        return

    parts = message.text.split(maxsplit=2)
    where = parts[1].lower() if len(parts) > 1 else ""

    # /zvat текст … — переписать общее приглашение своими словами.
    if where in ("текст", "text"):
        value = parts[2].strip() if len(parts) > 2 else ""
        if value.lower() in ("сброс", "reset", "по умолчанию"):
            await database.set_setting(GENERAL_KEY, "")
            await message.answer("✅ Вернула мой текст. Посмотреть: "
                                 "<code>/zvat общее</code>")
            return
        if not value:
            await message.answer(
                "Своими словами:\n<code>/zvat текст Ваш текст…</code>\n"
                "Вернуть мой: <code>/zvat текст сброс</code>\n\n"
                "Можно с разметкой: <code>&lt;b&gt;жирный&lt;/b&gt;</code>, "
                "<code>&lt;i&gt;курсив&lt;/i&gt;</code>. Предел — 1024 знака.")
            return
        if len(value) > 1024:
            await message.answer(f"Слишком длинно: {len(value)} знаков из 1024. "
                                 f"Это подпись под картинкой, Telegram обрежет.")
            return
        await database.set_setting(GENERAL_KEY, value)
        await message.answer("✅ Запомнила. Посмотреть: <code>/zvat общее</code>")
        return

    if where in ("общее", "общая", "всем", "general"):
        await _general(message)
        return

    if where in ("обмен", "партнёр", "партнер", "чужой"):
        await _partner(message)
        return

    if where not in TARGETS:
        await message.answer(
            "📣 <b>Приглашение в «Акцент»</b>\n\n"
            "Куда позвать? Выберите канал — покажу, как это будет выглядеть, "
            "и только потом отправлю.",
            reply_markup=_menu())
        return

    send = len(parts) > 2 and parts[2].lower() in ("go", "отправить", "да")
    if send:
        await _publish(message, bot, where)
        return

    await _preview(message, where)


async def _partner(message: Message):
    """Готовый пост для чужого канала — по договорённости.

    Отдаём три вещи сразу: сам текст, которым можно поделиться, картинку
    файлом (её партнёр приложит к посту) и короткую записку о том, что
    ему сказать. Иначе договорённость упирается в «а пришлите материалы».
    """
    url = await database.get_setting(LINK_KEY)
    text = PARTNER.format(url=url)

    await message.answer(text, disable_web_page_preview=False)
    await message.answer_document(
        FSInputFile(MARK), caption="Картинка к посту — приложить к тексту выше.")
    await message.answer(
        "☝️ <b>Готовый пост для чужого канала.</b>\n\n"
        "Перешлите партнёру оба сообщения: текст он вставит к себе как "
        "свой, картинку приложит. Кнопок в нём намеренно нет — в чужом "
        "канале их может поставить только бот-администратор этого канала.\n\n"
        "⚖️ Если размещение по обмену или за деньги, это реклама: "
        "маркировку и токен получает рекламодатель, то есть вы. "
        "Взаимный пост друг у друга — тот же случай, уточните у своего ОРД.\n\n"
        "Своими словами: <code>/zvat текст …</code> меняет общее "
        "приглашение; этот пост правится в коде — скажите, и перепишу.")


async def _general(message: Message):
    """Приглашение без привязки к каналу — его пересылают.

    Отправлять его самим некуда: адресат у него не задан. Поэтому просто
    отдаём готовое сообщение владельцу, а дальше оно живёт пересылкой —
    кнопки при этом сохраняются.
    """
    await message.answer_photo(
        FSInputFile(MARK), caption=await _card("общее"),
        reply_markup=await _markup(share=True))
    await message.answer(
        "☝️ Это общее приглашение. Перешлите его куда угодно — в чат, "
        "канал, личную переписку: кнопки сохраняются при пересылке.\n\n"
        "Переписать своими словами: <code>/zvat текст …</code>\n"
        "В конкретный канал, с своей первой фразой: <code>/zvat</code>")


async def _preview(message: Message, where: str):
    """Показать карточку владельцу — до того, как её увидит канал"""
    chat = await database.get_setting(TARGETS[where][0])
    where_name = TARGETS[where][1]
    await message.answer_photo(
        FSInputFile(MARK), caption=await _card(where),
        reply_markup=await _markup())
    await message.answer(
        f"☝️ Так это увидят читатели канала «{html.escape(where_name)}».\n\n"
        + (f"Отправить: <code>/zvat {where} go</code>" if chat else
           f"⚠️ Канал не задан — сначала <code>/avatar {where} -100…</code> "
           f"или задайте настройку <code>{TARGETS[where][0]}</code>."))


async def _publish(message: Message, bot: Bot, where: str):
    key, title, _ = TARGETS[where]
    raw = await database.get_setting(key)
    try:
        chat = int(raw)
    except (TypeError, ValueError):
        await message.answer(f"❌ Канал «{html.escape(title)}» не задан.")
        return

    try:
        sent = await bot.send_photo(chat, FSInputFile(MARK),
                                    caption=await _card(where),
                                    reply_markup=await _markup())
    except Exception as e:
        logging.error(f"Приглашение в {title} не вышло: {e}")
        await message.answer(f"❌ Не отправилось: {html.escape(str(e))}")
        return

    # Закрепление делает приглашение постоянным: новый читатель канала
    # увидит его первым, а не потеряет в ленте через день.
    pinned = ""
    try:
        await bot.pin_chat_message(chat, sent.message_id,
                                   disable_notification=True)
        pinned = " и закрепила"
    except Exception as e:
        logging.info(f"Закрепить приглашение не вышло: {e}")

    await message.answer(f"✅ Отправила в «{html.escape(title)}»{pinned}.")


@router.callback_query(F.data.startswith("invcard_"))
async def pick_target(call, bot: Bot):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    where = call.data.split("_", 1)[1]
    await call.answer()
    if where == "общее":
        await _general(call.message)
        return
    if where == "обмен":
        await _partner(call.message)
        return
    if where not in TARGETS:
        return
    await _preview(call.message, where)
