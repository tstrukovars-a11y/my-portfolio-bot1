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
              "кто ведёт своё дело."),
    "путешествия": ("travel_channel", "Вокруг света",
                    "Эти места приходят сюда из «Акцента» — журнала для тех, "
                    "кто ведёт своё дело."),
    "еда": ("recipes_channel", "Кухня",
            "Эти рецепты — часть «Акцента», журнала для тех, "
            "кто ведёт своё дело."),
    "теннис": ("tennis_channel", "Теннис",
               "Расписание матчей ведёт «Акцент» — журнал для тех, "
               "кто ведёт своё дело."),
    "клуб": ("club_chat", "Клуб",
             "Обсуждение живёт вокруг «Акцента» — журнала для тех, "
             "кто ведёт своё дело."),
}

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

CLOSING = ("Без рассылок и без «доброго времени суток». "
           "Семь коротких сообщений в день — и можно отписаться в любой момент.")


async def _card(where: str) -> str:
    lead = TARGETS[where][2]
    return f"{lead}\n\n{DAY}\n\n{CLOSING}"


async def _markup() -> InlineKeyboardMarkup:
    url = await database.get_setting(LINK_KEY)
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📣 Читать «Акцент»", url=url)]])


def _menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=title, callback_data=f"invcard_{name}")]
        for name, (_, title, _) in TARGETS.items()])


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

    parts = message.text.split()
    where = parts[1].lower() if len(parts) > 1 else ""
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
    if where not in TARGETS:
        await call.answer()
        return
    await call.answer()
    await _preview(call.message, where)
