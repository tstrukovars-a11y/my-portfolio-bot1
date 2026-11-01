# tennis_highlights.py — нарезки матчей в канал.
#
# Живого матча в открытом доступе нет и не будет: права проданы. А вот
# нарезка есть — официальная, на канале самого тура, через час-другой
# после конца. Это единственное видео, которое можно давать читателю,
# ничего не нарушая, и давать его надо в тот же вечер, пока матч ещё
# помнят.
#
# Берём ленту канала YouTube по RSS: ни ключа, ни квоты, ни регистрации.
# Отдаёт пятнадцать последних видео с заголовком, ссылкой и временем —
# ровно то, что нужно.
#
# В ленте вперемешку нарезки, шортсы и ролики вроде «The Guys Play Trick
# Or Treat». Отбираем по заголовку: у нарезки он устроен одинаково и
# всегда содержит слово Highlights.
import asyncio
import html
import logging
import re

from aiogram import Router, F, Bot
from aiogram.types import Message

import config
import database
import players_ru

router = Router()

SEEN_KEY = "tennis_highlights_seen"
SEEN_MEMORY = 60
PER_RUN = 3              # больше трёх подряд — это уже лента, а не канал

# Номера каналов туров. Берутся со страницы канала: поле externalId.
# Если тур заведёт новый канал, строка меняется здесь.
CHANNELS = {
    "wta": "UCaBIVVpHjq6j3tSyxwTE-8Q",   # youtube.com/@wta
    "atp": "UCY_5h5zaSwN7Or4kIJDYNXA",   # youtube.com/@atptour
}
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={id}"
WATCH = "https://www.youtube.com/watch?v={id}"

# У WTA: «A vs. B | 2026 Tokyo Final | WTA Match Highlights»
# У ATP:  «A vs B Highlights | Basel 2026 Semi-Finals»
# Одна разметка покрывает обе.
TITLE_RE = re.compile(
    r"^(.+?)\s+vs\.?\s+(.+?)(?:\s+Highlights)?\s*\|\s*(.+?)(?:\s*\|.*)?$",
    re.I)

# Круг по-русски. Всё, чего здесь нет, остаётся как в заголовке: выдумать
# перевод «Olympic Bronze Medal Match» дороже, чем оставить английское.
ROUNDS = {
    "final": "финал",
    "finals": "финал",
    "semi-finals": "1/2 финала",
    "semi-final": "1/2 финала",
    "semifinals": "1/2 финала",
    "quarter-finals": "1/4 финала",
    "quarter-final": "1/4 финала",
    "quarterfinals": "1/4 финала",
    "round of 16": "1/8 финала",
    "fourth round": "1/8 финала",
    "third round": "третий круг",
    "second round": "второй круг",
    "first round": "первый круг",
}


def _clean(text: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", text or "")).strip()


def parse(title: str):
    """(игрок, игрок, турнир и круг) из заголовка. None — если не нарезка."""
    text = _clean(title)
    if "highlight" not in text.lower():
        return None
    found = TITLE_RE.match(text)
    if not found:
        return None
    first, second, event = (x.strip(" |") for x in found.groups())
    if not first or not second or not event:
        return None
    return first, second, event


def event_ru(event: str) -> str:
    """Турнир и круг по-русски, насколько получается.

    Год убираем: читатель смотрит сегодняшнюю нарезку, и «2026» в ней
    сообщает только то, что сейчас 2026 год.
    """
    text = re.sub(r"\b(19|20)\d{2}\b", " ", event or "")
    text = re.sub(r"\s+", " ", text).strip(" -–—|")
    low = text.lower()
    # От длинного к короткому: иначе «Semi-Finals» совпадёт с «finals»,
    # и полуфинал в Базеле станет финалом.
    for english, russian in sorted(ROUNDS.items(), key=lambda x: -len(x[0])):
        if low.endswith(english):
            place = text[:len(text) - len(english)].strip(" -–—,")
            place = players_ru.event(place) if place else ""
            return f"{place}, {russian}" if place else russian
    return players_ru.event(text)


def worth_posting(first: str, second: str) -> bool:
    """Нарезка идёт в канал, если в матче играл кто-то известный"""
    return players_ru.notable(first) or players_ru.notable(second)


async def feed(tour: str) -> list:
    """[(номер видео, заголовок)] из ленты канала тура"""
    channel = CHANNELS.get(tour)
    if not channel:
        return []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            answer = await client.get(FEED.format(id=channel),
                                      headers={"User-Agent": "Mozilla/5.0"})
            answer.raise_for_status()
            body = answer.text
    except Exception as e:
        logging.warning(f"Лента нарезок {tour} не пришла: {e}")
        return []

    out = []
    for entry in body.split("<entry>")[1:]:
        video = re.search(r"<yt:videoId>([^<]+)</yt:videoId>", entry)
        title = re.search(r"<title>([^<]*)</title>", entry)
        if video and title:
            out.append((video.group(1), title.group(1)))
    return out


async def _seen() -> set:
    raw = await database.get_setting(SEEN_KEY) or ""
    return {x for x in raw.split(",") if x}


async def _remember(ids) -> None:
    raw = await database.get_setting(SEEN_KEY) or ""
    kept = [x for x in raw.split(",") if x]
    for one in ids:
        if one not in kept:
            kept.append(one)
    await database.set_setting(SEEN_KEY, ",".join(kept[-SEEN_MEMORY:]))


def line(first: str, second: str, event: str) -> str:
    """Подпись к нарезке"""
    who = f"{players_ru.ru(first)} — {players_ru.ru(second)}"
    where = event_ru(event)
    head = f"🎬 <b>{html.escape(who)}</b>"
    return f"{head}\n{html.escape(where)}" if where else head


async def publish(bot: Bot, chat: int, thread=None) -> str:
    """Новые нарезки в канал. По одной на сообщение — ради превью."""
    seen = await _seen()
    posted, fresh = 0, []

    for tour in ("wta", "atp"):
        for video, title in await feed(tour):
            if video in seen or posted >= PER_RUN:
                continue
            parts = parse(title)
            if not parts:
                continue
            first, second, event = parts
            if not worth_posting(first, second):
                # Запоминаем и чужие: иначе каждый обход заново разбирает
                # одни и те же заголовки.
                fresh.append(video)
                continue
            try:
                await bot.send_message(
                    chat, f"{line(first, second, event)}\n\n{WATCH.format(id=video)}",
                    message_thread_id=thread)
            except Exception as e:
                logging.error(f"Нарезка {video} не вышла: {e}")
                continue
            fresh.append(video)
            posted += 1
            await asyncio.sleep(3.2)

    if fresh:
        await _remember(fresh)
    return f"нарезок: {posted}" if posted else "новых нарезок нет"


@router.message(F.text.startswith("/tennis_highlights"))
async def highlights_command(message: Message, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return
    import digest
    chat, thread = await digest._target()
    if not chat:
        await message.answer("❌ Канал не задан: <code>/digest chat -100…</code>")
        return
    await message.answer(f"🎬 {await publish(bot, chat, thread)}")
