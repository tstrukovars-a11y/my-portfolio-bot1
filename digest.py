# digest.py — публикация материалов бота в канал.
#
# Канал наполняется из того, что уже собрано разделами: генетика, рецепты,
# путешествия. Разделы чередуются, чтобы не выходило три рецепта подряд, а
# опубликованное запоминается — источники о канале ничего не знают и сами
# повторов не отследят.
#
# Цель публикации задаётся настройкой, а не константой: канал может смениться,
# и это не повод трогать код. Пока она пуста, публикация просто не идёт.
import asyncio
import html
import logging
from datetime import datetime, timezone

from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

import config
import database

router = Router()

TARGET_KEY = "digest_chat"       # id канала
THREAD_KEY = "digest_thread"     # тема, если целью выбрана группа с разделами
INTERVAL_HOURS = 12              # два поста в сутки: канал живой, но не назойливый

# Дубль в группу. Нужен потому, что Telegram не даёт привязать группу с темами
# как обсуждение канала, а ломать её разделы ради привязки — плохой размен.
# Пока настройка пуста, дубль не идёт и поведение прежнее.
MIRROR_KEY = "digest_mirror"
MIRROR_THREAD_KEY = "digest_mirror_thread"

# Тема задаётся отдельно для каждого раздела: в группе с разделами рецепт
# в теме про генетику выглядит ошибкой, а не публикацией. Раздел без своей
# темы падает на общую, а нет и её — уходит в общий поток группы.
SECTION_ALIASES = {
    "генетика": "genetics", "genetics": "genetics",
    "рецепты": "recipes", "кулинария": "recipes", "recipes": "recipes",
    "путешествия": "travel", "travel": "travel",
}

# Время последней публикации. Хранится в базе, а не в памяти процесса:
# сервис перезапускается при каждом деплое, и интервал, отсчитанный от
# старта, превратил бы пять деплоев за вечер в пять постов подряд.
LAST_AT_KEY = "digest_last_at"

MAX_CAPTION = 1024
MAX_MESSAGE = 4096

# Порядок обхода. Меняется здесь же — раздел добавляется одной строкой,
# если он есть в database.DIGEST_SOURCES.
ROTATION = ["genetics", "recipes", "travel"]

SECTION_TITLES = {
    "genetics": "🧬 Генетика",
    "recipes": "🍳 Кулинария",
    "travel": "🌍 Путешествия",
}


async def _target():
    """(чат, тема) либо (None, None), если канал ещё не задан"""
    chat = await database.get_setting(TARGET_KEY)
    if not chat:
        return None, None
    thread = await database.get_setting(THREAD_KEY)
    try:
        return int(chat), int(thread) if thread else None
    except (TypeError, ValueError):
        return None, None


async def _build(section: str, item_id: int):
    """(заголовок, текст, фото, видео, ссылка) материала конкретного раздела"""
    if section == "genetics":
        row = await database.get_article(item_id)
        if not row:
            return None
        title, text, photo, video, link = row
        return title, text, photo, video, link

    if section == "recipes":
        row = await database.get_recipe_by_id(item_id)
        if not row:
            return None
        text, video, link, photo = row
        title = (text or "").strip().split("\n")[0][:80]
        return title, text, photo, video, link

    if section == "travel":
        row = await database.get_travel_place(item_id)
        if not row:
            return None
        country, place, text, photo, video, link = row
        return f"{place} · {country}", text, photo, video, link

    return None


async def _mirror_thread(section: str) -> str:
    """Тема для раздела: своя, иначе общая, иначе общий поток группы"""
    return (await database.get_setting(f"{MIRROR_THREAD_KEY}_{section}")
            or await database.get_setting(MIRROR_THREAD_KEY))


async def _mirror(bot: Bot, from_chat: int, message_id: int, section: str):
    """Дублирует свежий пост в группу, если она задана.

    Именно пересылка, а не копия: у пересланного поста остаётся подпись
    канала, и по ней участники группы попадают в сам канал. Ради этого
    перехода дубль и нужен — копия без подписи роста не даёт.

    Ошибка дубля не отменяет публикацию: пост в канале уже вышел, и
    сбрасывать его из-за недоступной группы было бы хуже.
    """
    target = await database.get_setting(MIRROR_KEY)
    if not target:
        return
    thread = await _mirror_thread(section)
    try:
        await bot.forward_message(
            chat_id=int(target), from_chat_id=from_chat, message_id=message_id,
            message_thread_id=int(thread) if thread else None,
        )
    except Exception as e:
        logging.error(f"Дайджест: пост вышел, но дубль в группу не прошёл: {e}")


async def _ad_block() -> str:
    """Рекламная вставка, если она задана и срок не вышел"""
    text = await database.get_setting("digest_ad")
    if not text:
        return ""
    until = await database.get_setting("digest_ad_until")
    if until:
        try:
            if datetime.fromisoformat(until) < datetime.now():
                return ""
        except ValueError:
            pass
    return f"\n\n———\n{text}"


async def publish_next(bot: Bot) -> str:
    """Публикует следующий материал по ротации. Возвращает строку для лога."""
    chat, thread = await _target()
    if not chat:
        return "канал не задан — публикация пропущена"

    # Идём по кругу, начиная с раздела, следующего за прошлым: так разделы
    # чередуются, а исчерпанные не блокируют остальные.
    last = await database.get_setting("digest_last_section")
    order = ROTATION[ROTATION.index(last) + 1:] + ROTATION[:ROTATION.index(last) + 1] \
        if last in ROTATION else ROTATION

    for section in order:
        item_id = await database.next_for_digest(section)
        if not item_id:
            continue

        built = await _build(section, item_id)
        if not built:
            await database.mark_published(section, item_id)   # битую запись пропускаем
            continue

        title, text, photo, video, link = built
        head = SECTION_TITLES.get(section, section)
        body = (text or title or "").strip()
        caption = f"{head}\n\n{body}" + await _ad_block()

        rows = []
        if link:
            rows.append([InlineKeyboardButton(text="🔗 Подробнее", url=link)])
        markup = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

        try:
            # parse_mode=None: текст пришёл из чужого поста и разметкой не является
            if video and len(caption) <= MAX_CAPTION:
                sent = await bot.send_video(chat, video, caption=caption, parse_mode=None,
                                            message_thread_id=thread, reply_markup=markup)
            elif photo and len(caption) <= MAX_CAPTION:
                sent = await bot.send_photo(chat, photo, caption=caption, parse_mode=None,
                                            message_thread_id=thread, reply_markup=markup)
            else:
                if photo or video:
                    media = bot.send_video if video else bot.send_photo
                    await media(chat, video or photo, caption=head, parse_mode=None,
                                message_thread_id=thread)
                sent = await bot.send_message(chat, caption[:MAX_MESSAGE], parse_mode=None,
                                              message_thread_id=thread, reply_markup=markup)
        except Exception as e:
            logging.error(f"Дайджест: не удалось опубликовать {section}/{item_id}: {e}")
            return f"ошибка публикации: {e}"

        await database.mark_published(section, item_id, sent.message_id)
        await database.set_setting("digest_last_section", section)
        await database.set_setting(LAST_AT_KEY, datetime.now().isoformat())
        await _mirror(bot, chat, sent.message_id, section)
        return f"опубликовано: {section}/{item_id} — {title[:50]}"

    return "публиковать нечего: все материалы уже вышли"


async def _seconds_until_due() -> float:
    """Сколько ещё ждать — считая от прошлой публикации, а не от запуска"""
    raw = await database.get_setting(LAST_AT_KEY)
    if not raw:
        return 0.0
    try:
        last = datetime.fromisoformat(raw)
    except ValueError:
        return 0.0
    return max(0.0, INTERVAL_HOURS * 3600 - (datetime.now() - last).total_seconds())


async def scheduler(bot: Bot):
    """Фоновая публикация. Минута задержки на старте — чтобы бот успел
    подняться; дальше срок берётся из базы и перезапуск его не сбивает."""
    await asyncio.sleep(60)
    while True:
        wait = await _seconds_until_due()
        if wait > 0:
            await asyncio.sleep(min(wait, 3600))   # просыпаемся сверить время
            continue
        try:
            logging.info(f"Дайджест: {await publish_next(bot)}")
        except Exception as e:
            logging.error(f"Ошибка планировщика дайджеста: {e}")
        await asyncio.sleep(INTERVAL_HOURS * 3600)


# =====================================================================
# УПРАВЛЕНИЕ (только владелец)
# =====================================================================

@router.message(F.text == "/id")
async def show_chat_id(message: Message):
    """Показывает id чата и тему, откуда команду отправили.

    Нужно потому, что @userinfobot по пересланному сообщению показывает
    автора, а не чат: id группы через него не узнать в принципе.
    """
    if not config.is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    thread = message.message_thread_id
    lines = [f"Чат: <code>{chat_id}</code>"]
    if thread:
        lines.append(f"Тема: <code>{thread}</code>")
    lines.append("\nГотовая команда — допишите раздел:")
    lines.append(f"<code>/digest mirror {chat_id}{f' {thread}' if thread else ''} генетика</code>")
    lines.append("\nРазделы: генетика, рецепты, путешествия")
    await message.answer("\n".join(lines))


@router.message(F.text.startswith("/digest"))
async def digest_command(message: Message, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=2)
    command = parts[1] if len(parts) > 1 else "status"

    if command == "now":
        await message.answer(f"📤 {await publish_next(bot)}")
        return

    if command == "chat" and len(parts) > 2:
        await database.set_setting(TARGET_KEY, parts[2].strip())
        await message.answer(f"✅ Канал публикации: <code>{html.escape(parts[2].strip())}</code>")
        return

    if command == "mirror" and len(parts) > 2:
        # «id_группы [номер_темы] [раздел]». Без раздела тема считается общей,
        # без темы — дубль идёт в общий поток группы.
        bits = parts[2].split()
        await database.set_setting(MIRROR_KEY, bits[0])
        thread = bits[1] if len(bits) > 1 else ""

        if len(bits) > 2:
            section = SECTION_ALIASES.get(bits[2].lower())
            if not section:
                await message.answer(
                    "❌ Неизвестный раздел. Возможные: "
                    + ", ".join(sorted(set(SECTION_ALIASES) - set(SECTION_ALIASES.values())))
                )
                return
            await database.set_setting(f"{MIRROR_THREAD_KEY}_{section}", thread)
            await message.answer(
                f"✅ {SECTION_TITLES[section]} → группа "
                f"<code>{html.escape(bits[0])}</code>, тема {html.escape(thread) or 'общая'}"
            )
            return

        await database.set_setting(MIRROR_THREAD_KEY, thread)
        await message.answer(
            f"✅ Дубль в группу: <code>{html.escape(bits[0])}</code>"
            + (f" · тема {html.escape(thread)} для всех разделов без своей"
               if thread else " · общий поток")
        )
        return

    if command == "nomirror":
        await database.set_setting(MIRROR_KEY, "")
        for section in ROTATION:
            await database.set_setting(f"{MIRROR_THREAD_KEY}_{section}", "")
        await database.set_setting(MIRROR_THREAD_KEY, "")
        await message.answer("✅ Дубль в группу отключён, темы забыты.")
        return

    if command == "ad" and len(parts) > 2:
        await database.set_setting("digest_ad", parts[2])
        await message.answer("✅ Рекламный блок сохранён — пойдёт в следующие посты.")
        return

    if command == "noad":
        await database.set_setting("digest_ad", "")
        await message.answer("✅ Рекламный блок снят.")
        return

    chat, thread = await _target()
    stats = await database.digest_stats()
    lines = [
        "📤 <b>Дайджест-канал</b>",
        f"Цель: <code>{chat or 'не задана'}</code>"
        + (f" · тема {thread}" if thread else ""),
        f"Публикация раз в {INTERVAL_HOURS} ч",
    ]
    left = await _seconds_until_due()
    lines.append("Следующая: " + ("в ближайшую минуту" if left <= 0
                                  else f"через {int(left // 3600)} ч {int(left % 3600 // 60)} мин"))
    lines.append("")
    for section, data in stats.items():
        left = data["total"] - data["published"]
        lines.append(f"{SECTION_TITLES.get(section, section)}: "
                     f"{data['published']} из {data['total']}, осталось {left}")

    mirror = await database.get_setting(MIRROR_KEY)
    lines.append(f"\nДубль в группу: <code>{mirror or 'нет'}</code>")
    if mirror:
        for section in ROTATION:
            thread = await _mirror_thread(section)
            lines.append(f"  {SECTION_TITLES.get(section, section)} → "
                         + (f"тема {thread}" if thread else "общий поток"))

    ad = await database.get_setting("digest_ad")
    lines.append(f"Реклама: {'есть' if ad else 'нет'}")
    lines.append("\n<code>/digest now</code> — опубликовать сейчас\n"
                 "<code>/digest chat -100…</code> — задать канал\n"
                 "<code>/digest mirror -100… тема раздел</code> — дубль в группу\n"
                 "<code>/digest nomirror</code> — не дублировать\n"
                 "<code>/digest ad текст</code> — рекламный блок\n"
                 "<code>/digest noad</code> — снять рекламу")
    await message.answer("\n".join(lines))
