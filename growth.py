# growth.py — привлечение подписчиков в канал.
#
# Четыре механики, и все они опираются на один факт: пользователь бота уже
# нажал «старт», то есть это тёплый контакт. Ни один внешний источник
# трафика такой конверсии не даёт, а этот у нас уже есть.
#
#   • разовое приглашение всем, кто когда-либо запускал бота;
#   • постоянная кнопка канала в главном меню;
#   • мягкий шлюз: выбранный раздел открывается после подписки;
#   • кнопка «Поделиться» под публикациями (живёт в digest.py).
#
# Ссылка на канал и состав шлюза хранятся настройками, а не константами:
# канал может смениться, а шлюз — открыться и закрыться, и ни то ни другое
# не повод трогать код.
import asyncio
import html
import logging
import time

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramBadRequest

import config
import database
import digest

router = Router()

LINK_KEY = "channel_url"        # публичная ссылка вида https://t.me/…
GATE_KEY = "channel_gate"       # какой раздел закрыт подпиской; пусто — открыто всё
INVITED_AT_KEY = "invite_sent_at"

# Разделы, которые имеет смысл закрывать. Ключ — то, что владелец пишет
# в команде, значение — префиксы кнопок и человеческое название.
GATE_TARGETS = {
    "головоломки": (("intellect_puzzle", "start_solving_puzzles", "puzzle_"), "🧩 Головоломки"),
    "курсы": (("fx_rates", "fx_calc", "fxcalc_"), "💱 Курсы валют"),
    "теннис": (("sport_tennis", "tennis_"), "🎾 Теннис"),
    "книги": (("intellect_books", "books_view_"), "📚 Книги"),
    "генетика": (("intellect_genetics",), "🧬 Генетика"),
}

# Подписку помним десять минут, чтобы не ходить в Telegram на каждый клик.
# Кэшируем только положительный ответ: тот, кто подписался только что,
# должен пройти сразу, а не досиживать чужой срок.
_subscribed: dict[int, float] = {}
CACHE_TTL = 600


# =====================================================================
# ПРОВЕРКА ПОДПИСКИ
# =====================================================================

async def is_subscribed(bot: Bot, user_id: int) -> bool:
    """Подписан ли пользователь на канал. Если канал не задан или Telegram
    не отвечает — считаем, что подписан: пускать лишних лучше, чем запирать
    своих из-за чужого сбоя."""
    if config.is_admin(user_id):
        return True

    hit = _subscribed.get(user_id)
    if hit and time.time() - hit < CACHE_TTL:
        return True

    chat = await database.get_setting(digest.TARGET_KEY)
    if not chat:
        return True

    try:
        member = await bot.get_chat_member(chat_id=int(chat), user_id=user_id)
    except (TelegramBadRequest, ValueError) as e:
        logging.warning(f"Шлюз: проверить подписку не вышло ({e}) — пропускаю")
        return True

    if member.status in ("left", "kicked"):
        return False
    _subscribed[user_id] = time.time()
    return True


async def gate_blocks(data: str) -> str | None:
    """Название закрытого раздела, если кнопка ведёт именно в него"""
    key = await database.get_setting(GATE_KEY)
    target = GATE_TARGETS.get(key or "")
    if not target:
        return None
    prefixes, title = target
    return title if data.startswith(prefixes) else None


def _gate_keyboard(url: str, lang: str) -> InlineKeyboardMarkup:
    subscribe = {"ru": "📣 Подписаться", "en": "📣 Subscribe",
                 "fr": "📣 S'abonner", "he": "📣 להירשם"}
    done = {"ru": "✅ Я подписался", "en": "✅ I subscribed",
            "fr": "✅ Je suis abonné", "he": "✅ נרשמתי"}
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=subscribe.get(lang, subscribe["en"]), url=url)],
        [InlineKeyboardButton(text=done.get(lang, done["en"]), callback_data="gate_recheck")],
    ])


GATE_TEXTS = {
    "ru": "🔒 Раздел «{section}» открыт подписчикам канала.\n\n"
          "Подпишитесь — доступ появится сразу, это бесплатно.",
    "en": "🔒 The «{section}» section is open to channel subscribers.\n\n"
          "Subscribe and access opens right away — it's free.",
    "fr": "🔒 La section «{section}» est réservée aux abonnés du canal.\n\n"
          "Abonnez-vous, l'accès s'ouvre aussitôt — c'est gratuit.",
    "he": "🔒 המדור «{section}» פתוח למנויי הערוץ.\n\n"
          "הירשמו והגישה תיפתח מיד — בחינם.",
}


async def gate_middleware(handler, event, data):
    """Внешний слой на нажатия: закрытый раздел показывает приглашение
    вместо содержимого. Всё остальное проходит насквозь."""
    if not isinstance(event, CallbackQuery) or not event.data:
        return await handler(event, data)

    section = await gate_blocks(event.data)
    if not section:
        return await handler(event, data)

    bot = data["bot"]
    if await is_subscribed(bot, event.from_user.id):
        return await handler(event, data)

    url = await database.get_setting(LINK_KEY)
    if not url:                       # ссылки нет — запирать нечем
        return await handler(event, data)

    lang = await database.get_user_language(event.from_user.id)
    await event.answer()
    await event.message.answer(
        GATE_TEXTS.get(lang, GATE_TEXTS["en"]).format(section=section),
        reply_markup=_gate_keyboard(url, lang),
    )


@router.callback_query(F.data == "gate_recheck")
async def gate_recheck(call: CallbackQuery, bot: Bot):
    lang = await database.get_user_language(call.from_user.id)
    if await is_subscribed(bot, call.from_user.id):
        opened = {"ru": "✅ Доступ открыт — откройте раздел заново.",
                  "en": "✅ Access granted — open the section again.",
                  "fr": "✅ Accès ouvert — rouvrez la section.",
                  "he": "✅ הגישה נפתחה — פתחו שוב את המדור."}
        await call.message.edit_text(opened.get(lang, opened["en"]))
        return
    still = {"ru": "Подписка пока не видна. Подпишитесь и нажмите ещё раз.",
             "en": "Subscription not visible yet. Subscribe and try again.",
             "fr": "Abonnement non détecté. Abonnez-vous et réessayez.",
             "he": "המנוי עדיין לא נראה. הירשמו ונסו שוב."}
    await call.answer(still.get(lang, still["en"]), show_alert=True)


# =====================================================================
# РАЗОВОЕ ПРИГЛАШЕНИЕ
# =====================================================================

INVITE_TEXTS = {
    "ru": "📣 У бота появился канал.\n\nТам выходят рецепты, разборы по генетике "
          "и заметки о путешествиях — то же, что внутри бота, но само приходит в ленту.",
    "en": "📣 The bot now has a channel.\n\nRecipes, genetics explainers and travel "
          "notes — the same material as inside the bot, but it comes to you.",
    "fr": "📣 Le bot a désormais un canal.\n\nRecettes, génétique et notes de voyage — "
          "le même contenu que dans le bot, mais livré dans votre fil.",
    "he": "📣 לבוט יש עכשיו ערוץ.\n\nמתכונים, גנטיקה ורשימות מסע — אותו חומר שבבוט, "
          "רק שהוא מגיע אליכם.",
}
OPEN_TEXTS = {"ru": "📣 Открыть канал", "en": "📣 Open the channel",
              "fr": "📣 Ouvrir le canal", "he": "📣 לפתוח את הערוץ"}


async def _broadcast(bot: Bot, url: str, report_to: int):
    """Шлёт приглашение всем пользователям бота.

    Идёт в фоне и медленно — 20 сообщений в секунду с запасом от лимитов
    Telegram. Заблокировавшие бота считаются отдельно: это не ошибка,
    а нормальная доля любой рассылки.
    """
    users = await database.all_user_ids()
    sent = blocked = failed = 0

    for user_id, lang in users:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=OPEN_TEXTS.get(lang, OPEN_TEXTS["en"]), url=url)]])
        try:
            await bot.send_message(user_id, INVITE_TEXTS.get(lang, INVITE_TEXTS["en"]),
                                   reply_markup=markup)
            sent += 1
        except TelegramForbiddenError:
            blocked += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            failed += 1
        except Exception as e:
            logging.warning(f"Приглашение не доставлено {user_id}: {e}")
            failed += 1
        await asyncio.sleep(0.05)

    await database.set_setting(INVITED_AT_KEY, str(int(time.time())))
    try:
        await bot.send_message(
            report_to,
            f"📣 <b>Рассылка закончена</b>\n\nДоставлено: {sent}\n"
            f"Заблокировали бота: {blocked}\nНе прошло: {failed}")
    except Exception:
        pass


@router.message(F.text.startswith("/invite"))
async def invite_command(message: Message, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return

    url = await database.get_setting(LINK_KEY)
    if not url:
        await message.answer("❌ Сначала задайте ссылку: <code>/channel https://t.me/…</code>")
        return

    users = await database.all_user_ids()
    parts = message.text.split()
    confirmed = len(parts) > 1 and parts[1] == "go"

    if not confirmed:
        sample = INVITE_TEXTS["ru"]
        await message.answer(
            f"📣 <b>Разовое приглашение</b>\n\nПолучателей: <b>{len(users)}</b>\n"
            f"Ссылка: {html.escape(url)}\n\nТекст (на языке каждого):\n\n"
            f"<i>{html.escape(sample)}</i>\n\n"
            "Отправить: <code>/invite go</code>")
        return

    was = await database.get_setting(INVITED_AT_KEY)
    if was and parts[-1] != "force":
        days = (time.time() - int(was)) / 86400
        if days < 30:
            await message.answer(
                f"⚠️ Рассылка уже была {days:.0f} дн. назад. Слишком частые "
                f"приглашения отписывают, а не подписывают.\n\n"
                f"Если всё же нужно: <code>/invite go force</code>")
            return

    await message.answer(f"📤 Отправляю {len(users)} адресатам, доложу по окончании.")
    asyncio.create_task(_broadcast(bot, url, message.from_user.id))


# =====================================================================
# НАСТРОЙКА
# =====================================================================

@router.message(F.text.startswith("/channel"))
async def channel_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if arg.startswith("http") or arg.startswith("@"):
        url = arg if arg.startswith("http") else f"https://t.me/{arg.lstrip('@')}"
        await database.set_setting(LINK_KEY, url)
        import inline_kb
        inline_kb.CHANNEL_URL = url
        await message.answer(f"✅ Ссылка на канал: {html.escape(url)}\n"
                             "Кнопка появилась в главном меню.")
        return

    if arg.startswith("шлюз"):
        target = arg[4:].strip().lower()
        if target in ("", "нет", "off"):
            await database.set_setting(GATE_KEY, "")
            await message.answer("✅ Шлюз снят, все разделы открыты.")
            return
        if target not in GATE_TARGETS:
            await message.answer("❌ Можно закрыть: " + ", ".join(GATE_TARGETS))
            return
        await database.set_setting(GATE_KEY, target)
        await message.answer(f"✅ Закрыт подпиской: {GATE_TARGETS[target][1]}")
        return

    url = await database.get_setting(LINK_KEY)
    gate = await database.get_setting(GATE_KEY)
    was = await database.get_setting(INVITED_AT_KEY)
    users = await database.all_user_ids()
    await message.answer(
        "📣 <b>Канал</b>\n\n"
        f"Ссылка: {html.escape(url) if url else 'не задана'}\n"
        f"Шлюз: {GATE_TARGETS[gate][1] if gate in GATE_TARGETS else 'нет'}\n"
        f"Пользователей бота: {len(users)}\n"
        f"Приглашение: {'было' if was else 'не отправляли'}\n\n"
        "<code>/channel @имя</code> — задать ссылку\n"
        "<code>/channel шлюз головоломки</code> — закрыть раздел подпиской\n"
        "<code>/channel шлюз нет</code> — открыть всё\n"
        "<code>/invite</code> — разовое приглашение пользователям бота")
