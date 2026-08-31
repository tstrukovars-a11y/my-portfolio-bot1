# travel_channel.py — канал путешествий как рабочая витрина.
#
# Бот выкладывает туда все места и запоминает номер каждого поста. Дальше
# связь двусторонняя:
#
#   правка в боте  → бот переписывает пост в канале;
#   правка в канале → бот обновляет текст у себя.
#
# Номер поста — то, на чём всё держится. Без него повторная выкладка
# создаёт копии вместо правок, и канал за неделю превращается в свалку
# из трёх версий каждого места.
import asyncio
import html
import logging

from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

import config
import database
import flags

router = Router()

CHANNEL_KEY = "travel_channel"
PAUSE = 1.2               # между постами: Telegram не любит очередь без пауз
MAX_CAPTION = 1024
MAX_MESSAGE = 4096


async def _channel():
    raw = await database.get_setting(CHANNEL_KEY)
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _post_text(country: str, place: str, text: str) -> str:
    """Один и тот же вид у нового поста и у правки — иначе правка меняет
    не только текст, но и оформление, и это видно как мигание."""
    body = (text or "").strip()
    return f"📍 {place} · {flags.with_flag(country)}\n\n{body}".strip()


@router.message(F.text.startswith("/travel_channel"))
async def set_channel(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        await database.set_setting(CHANNEL_KEY, parts[1].strip())
        await message.answer(f"✅ Канал путешествий: <code>{html.escape(parts[1].strip())}</code>\n\n"
                             "Выложить всё: <code>/travel_publish</code>")
        return

    chat = await _channel()
    places = await database.travel_all_ordered()
    posted = sum(1 for p in places if p[5])
    await message.answer(
        f"🌍 <b>Канал путешествий</b>\n\n"
        f"Канал: <code>{chat or 'не задан'}</code>\n"
        f"Мест: {len(places)}, выложено: {posted}\n\n"
        "<code>/travel_channel -100…</code> — задать канал\n"
        "<code>/travel_publish</code> — выложить или обновить всё")


@router.message(F.text == "/travel_publish")
async def publish_all(message: Message, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return
    chat = await _channel()
    if not chat:
        await message.answer("❌ Сначала задайте канал: <code>/travel_channel -100…</code>")
        return

    places = await database.travel_all_ordered()
    if not places:
        await message.answer("Мест пока нет. Загрузите список: <code>/travel_seed</code>")
        return

    note = await message.answer(f"🌍 Выкладываю {len(places)} мест…")
    asyncio.create_task(_run(bot, chat, places, note))


async def _run(bot: Bot, chat: int, places, note: Message):
    """Выкладка идёт фоном: восемьдесят постов с паузами — это две минуты,
    и держать всё это время сообщение «выкладываю» бессмысленно."""
    new = edited = failed = 0

    for place_id, country, place, text, photo, msg_id in places:
        body = _post_text(country, place, text)
        try:
            if msg_id:
                # Пост уже был — правим его, а не публикуем второй раз.
                if photo:
                    await bot.edit_message_caption(
                        chat_id=chat, message_id=msg_id,
                        caption=body[:MAX_CAPTION], parse_mode=None)
                else:
                    await bot.edit_message_text(
                        chat_id=chat, message_id=msg_id,
                        text=body[:MAX_MESSAGE], parse_mode=None)
                edited += 1
            else:
                if photo:
                    sent = await bot.send_photo(chat, photo,
                                                caption=body[:MAX_CAPTION], parse_mode=None)
                else:
                    sent = await bot.send_message(chat, body[:MAX_MESSAGE], parse_mode=None)
                await database.set_travel_msg(place_id, sent.message_id)
                new += 1
        except TelegramBadRequest as e:
            # «message is not modified» — не ошибка: текст просто не менялся.
            if "not modified" in str(e).lower():
                continue
            logging.error(f"Канал путешествий: {place} — {e}")
            failed += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            failed += 1
        except Exception as e:
            logging.error(f"Канал путешествий: {place} — {type(e).__name__}: {e}")
            failed += 1
        await asyncio.sleep(PAUSE)

    tail = f"Новых: {new}, обновлено: {edited}"
    if failed:
        tail += f", не прошло: {failed}"
    try:
        await note.edit_text(f"🌍 <b>Готово</b>\n\n{tail}")
    except Exception:
        pass


@router.message(F.text.startswith("/travel_drop"))
async def drop_country(message: Message, bot: Bot):
    """Убирает страну и из канала, и из базы.

    Только из канала мало: следующая выкладка вернула бы её обратно.
    Только из базы мало: посты остались бы висеть. Поэтому оба разом.
    """
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Укажите страну: <code>/travel_drop Крым</code>")
        return

    country = parts[1].strip()
    places = await database.travel_country_places(country)
    if not places:
        await message.answer(f"Мест страны «{html.escape(country)}» не найдено.")
        return

    chat = await _channel()
    removed = 0
    for _, place, msg_id in places:
        if not (chat and msg_id):
            continue
        try:
            await bot.delete_message(chat_id=chat, message_id=msg_id)
            removed += 1
        except Exception as e:
            # Телеграм не даёт удалять посты старше двух суток — это не
            # повод оставлять запись в базе, но сказать об этом надо.
            logging.warning(f"Канал путешествий: пост «{place}» не удалён: {e}")
        await asyncio.sleep(0.4)

    gone = await database.delete_travel_country(country)
    tail = f"Удалено мест: {gone}"
    if chat:
        tail += f", постов в канале: {removed} из {sum(1 for p in places if p[2])}"
    await message.answer(f"🗑 <b>{html.escape(country)}</b>\n\n{tail}")


# =====================================================================
# ПРАВКА В КАНАЛЕ ВОЗВРАЩАЕТСЯ В БОТ
# =====================================================================

async def _is_travel_post(message: Message) -> bool:
    chat = await _channel()
    return chat is not None and message.chat.id == chat


@router.edited_channel_post(_is_travel_post)
async def pick_up_edit(message: Message):
    """Текст, поправленный прямо в канале, забираем обратно в базу.

    Иначе бот при следующей выкладке перезапишет чужую правку своим старым
    текстом — то есть аккуратно затрёт сделанную вручную работу.
    """
    found = await database.travel_by_msg(message.message_id)
    if not found:
        return
    place_id, place = found

    raw = (message.text or message.caption or "").strip()
    # Снимаем заголовок «📍 Место · Страна», который бот сам и поставил
    lines = raw.split("\n")
    if lines and lines[0].startswith("📍"):
        raw = "\n".join(lines[1:]).strip()
    if not raw:
        return

    if await database.set_travel_text(place_id, raw[:900]):
        logging.info(f"Канал путешествий: текст «{place}» обновлён правкой в канале")
