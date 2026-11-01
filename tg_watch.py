# tg_watch.py — слежение за чужими публичными каналами.
#
# Организаторы турниров объявляют составы когда захотят, и узнать об
# этом надо первой, а не через сутки из чужого пересказа.
#
# Ботом вступить в чужой канал нельзя: добавить его туда может только
# администратор канала. Зато у любого публичного канала есть веб-превью
# по адресу t.me/s/<имя> — обычная страница, которую сервер отдаёт кому
# угодно. Оттуда и читаем: ни ключа, ни токена, ни членства.
#
# Найденное уходит владелице в личку, а не в канал. Решение, делать ли
# из чужой новости пост, принимает человек: перепечатка чужого поста —
# это не «Акцент».
import asyncio
import html
import logging
import re

from aiogram import Router, F, Bot
from aiogram.types import Message

import config
import database

router = Router()

LIST_KEY = "tg_watch_list"        # за кем следим, через запятую
SEEN_KEY = "tg_watch_seen"        # что уже показали
SEEN_MEMORY = 300
PER_RUN = 5                       # больше пяти за обход — это уже лента
PREVIEW = "https://t.me/s/{name}"
POST = "https://t.me/{name}/{num}"

# Канал организаторов «Трофеев Северной Пальмиры». Отсюда приходят
# составы, расписание и билеты.
DEFAULT = ["formulatx"]

# Слова, ради которых всё и затевалось. Пост с ними помечается в личке
# отдельно, чтобы не потерялся среди расписаний и опросов.
IMPORTANT = ("состав", "заявл", "объявл", "сыграет", "сыграют",
             "примет участие", "примут участие", "игрок", "участник",
             "приедет", "приедут", "выступит", "выступят")

# Разметка превью: номер поста в data-post, текст в своём блоке.
POST_RE = re.compile(r'data-post="([^"/]+)/(\d+)"')
TEXT_RE = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)


def _plain(raw: str) -> str:
    """Текст поста без разметки"""
    text = re.sub(r"<br\s*/?>", "\n", raw or "")
    text = re.sub(r"</?[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def parse(page: str, name: str) -> list:
    """[(номер, текст)] постов со страницы превью, от старых к новым"""
    out = []
    for block in page.split('class="tgme_widget_message ')[1:]:
        found = POST_RE.search(block)
        if not found or found.group(1).lower() != name.lower():
            continue
        body = TEXT_RE.search(block)
        out.append((int(found.group(2)), _plain(body.group(1)) if body else ""))
    out.sort()
    return out


def is_important(text: str) -> bool:
    low = (text or "").lower()
    return any(word in low for word in IMPORTANT)


async def watched() -> list:
    raw = await database.get_setting(LIST_KEY)
    if raw is None:
        return list(DEFAULT)
    names = [x.strip().lstrip("@") for x in raw.split(",") if x.strip()]
    return names


async def _set_watched(names) -> None:
    await database.set_setting(LIST_KEY, ",".join(names))


async def _seen() -> set:
    raw = await database.get_setting(SEEN_KEY) or ""
    return {x for x in raw.split(",") if x}


async def _remember(keys) -> None:
    raw = await database.get_setting(SEEN_KEY) or ""
    kept = [x for x in raw.split(",") if x]
    for one in keys:
        if one not in kept:
            kept.append(one)
    await database.set_setting(SEEN_KEY, ",".join(kept[-SEEN_MEMORY:]))


async def fetch(name: str) -> list:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            answer = await client.get(
                PREVIEW.format(name=name),
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X "
                                       "10_15_7) AppleWebKit/537.36 (KHTML, "
                                       "like Gecko) Chrome/140.0.0.0 Safari/537.36"})
            answer.raise_for_status()
            page = answer.text
    except Exception as e:
        logging.warning(f"Канал @{name} не прочитался: {e}")
        return []
    return parse(page, name)


def card(name: str, num: int, text: str) -> str:
    """Карточка поста для личного сообщения"""
    head = "🔔 <b>Новое у @{0}</b>".format(html.escape(name))
    if is_important(text):
        head = "⚡️ <b>Похоже на состав — @{0}</b>".format(html.escape(name))
    body = html.escape(text[:600]) if text else "<i>без текста</i>"
    return f"{head}\n\n{body}\n\n{POST.format(name=name, num=num)}"


async def check(bot: Bot) -> str:
    """Обойти каналы и прислать владелице новое. Возвращает сводку."""
    if not config.ADMIN_ID:
        return "владелец не задан"
    seen = await _seen()
    sent, fresh = 0, []
    first_run = not seen

    for name in await watched():
        posts = await fetch(name)
        for num, text in posts:
            key = f"{name}/{num}"
            if key in seen:
                continue
            fresh.append(key)
            # Первый обход запоминает ленту молча: иначе при включении
            # прилетит сразу двадцать старых постов.
            if first_run or sent >= PER_RUN:
                continue
            try:
                await bot.send_message(config.ADMIN_ID, card(name, num, text),
                                       disable_web_page_preview=True)
                sent += 1
                await asyncio.sleep(0.6)
            except Exception as e:
                logging.warning(f"Карточка {key} не ушла: {e}")

    if fresh:
        await _remember(fresh)
    if first_run:
        return f"лента запомнена: {len(fresh)} постов, слежу дальше"
    return f"новых постов: {sent}" if sent else "нового нет"


async def scheduler(bot: Bot):
    """Раз в десять минут. Составы объявляют один раз, и лучше узнать сразу."""
    await asyncio.sleep(120)
    while True:
        try:
            await check(bot)
        except Exception as e:
            logging.error(f"Слежение за каналами: {e}")
        await asyncio.sleep(600)


@router.message(F.text.startswith("/watch"))
async def watch_command(message: Message, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    names = await watched()

    if len(parts) == 1:
        rows = "\n".join(f"• @{x}" for x in names) or "никого"
        await message.answer(
            f"👀 <b>Слежу за каналами</b>\n\n{rows}\n\n"
            "<code>/watch add имя</code> — добавить\n"
            "<code>/watch del имя</code> — убрать\n"
            "<code>/watch now</code> — проверить сейчас")
        return

    action = parts[1].lower()
    if action == "now":
        await message.answer(f"👀 {await check(bot)}")
        return

    if len(parts) < 3:
        await message.answer("❌ Нужно имя канала: <code>/watch add formulatx</code>")
        return
    who = parts[2].strip().lstrip("@")

    if action == "add":
        if who in names:
            await message.answer(f"@{who} уже в списке")
            return
        names.append(who)
        await _set_watched(names)
        await message.answer(f"✅ Слежу за @{who}")
    elif action == "del":
        if who not in names:
            await message.answer(f"@{who} в списке не было")
            return
        names.remove(who)
        await _set_watched(names)
        await message.answer(f"✅ Больше не слежу за @{who}")
    else:
        await message.answer("❌ Только add, del или now")
