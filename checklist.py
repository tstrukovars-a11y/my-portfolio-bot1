# checklist.py — один экран «чего не хватает».
#
# Данные для этого были и раньше, но по разным командам: книги без обложек в
# одной, места без фото в другой, ссылки в третьей. Держать в голове семь
# команд, чтобы понять, что мешает публикации, — работа, которой быть не
# должно.
#
# Считаем на лету, ничего не храня: любая сохранённая сводка врёт на
# следующий день после первой же загруженной фотографии.
import asyncio
import html
import json
import logging

from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

import config
import database

router = Router()

MAX_NAMES = 6      # длиннее список не читается, дальше — по своей команде

# Кабинеты партнёрских программ. Ссылки живут в базе, а не в коде: программ
# со временем станет больше, а деплой ради закладки — глупость.
CABINETS_KEY = "admin_cabinets"
REMIND_DAY_KEY = "cabinets_remind_day"    # число месяца, 0 — не напоминать
REMIND_SENT_KEY = "cabinets_reminded"     # какой месяц уже напомнили
REMIND_DAY_DEFAULT = 5                    # к пятому числу выплаты обычно видны
REMIND_HOUR = 11
CABINETS_DEFAULT = [
    {"name": "📚 Читай-город", "url": "https://partners.chitai-gorod.ru/"},
]


async def _cabinets() -> list:
    raw = await database.get_setting(CABINETS_KEY)
    if not raw:
        return list(CABINETS_DEFAULT)
    try:
        saved = json.loads(raw)
        return saved if isinstance(saved, list) else list(CABINETS_DEFAULT)
    except (ValueError, TypeError):
        return list(CABINETS_DEFAULT)


async def _save_cabinets(items: list):
    await database.set_setting(CABINETS_KEY, json.dumps(items, ensure_ascii=False))


def _line(title: str, missing: int, total: int, command: str) -> str:
    if not missing:
        return f"✅ {title} — всё на месте ({total})"
    return (f"⚠️ <b>{title}</b> — не хватает у {missing} из {total}\n"
            f"    {command}")


def _names(rows) -> str:
    """Первые несколько названий — чтобы было видно, о чём речь.

    У книг название во втором столбце, у мест — в третьем, у
    достопримечательностей — в четвёртом. Берём последний: он везде
    оказывается тем, что человек читает.
    """
    shown = [html.escape(str(r[-1])[:38]) for r in rows[:MAX_NAMES]]
    tail = f" и ещё {len(rows) - MAX_NAMES}" if len(rows) > MAX_NAMES else ""
    return "    " + "; ".join(shown) + tail


@router.message(F.text.startswith(("/todo", "/чего")))
async def todo(message: Message):
    """Что мешает публиковать: по разделам, с командой для починки"""
    if not config.is_admin(message.from_user.id):
        return

    lines = ["🧾 <b>Чего не хватает</b>", ""]

    # --- книги -------------------------------------------------------
    stats = await database.books_link_stats()
    no_link = await database.books_without_link()
    no_cover = await database.books_without_cover(100)
    lines.append(_line("Книги: партнёрские ссылки", len(no_link),
                       stats.get("total", 0), "<code>/book_links</code>"))
    if no_link:
        lines.append(_names(no_link))
    lines.append(_line("Книги: обложки", len(no_cover), stats.get("total", 0),
                       "<code>/book_covers</code>"))
    if no_cover:
        lines.append(_names(no_cover))
    lines.append("")

    # --- путешествия -------------------------------------------------
    places = await database.travel_without_photo(200)
    lines.append(_line("Города и места: фото", len(places),
                       await database.count_travel_places(),
                       "<code>/travel_photos</code>"))
    if places:
        lines.append(_names(places))

    spots = await database.spots_without_photo(200)
    lines.append(_line("Достопримечательности: фото", len(spots),
                       await database.count_spots(),
                       "<code>/spot_photos</code>"))
    if spots:
        lines.append(_names(spots))
    lines.append("")

    # --- картины -----------------------------------------------------
    works = await database.art_list()
    no_photo = [w for w in works if not w.get("photo_file_id")]
    if works:
        lines.append(_line("Картины: фото", len(no_photo), len(works),
                           "<code>/art_list</code>"))
        in_channel = sum(1 for w in works if w.get("channel_msg_id"))
        if in_channel < len(works):
            lines.append(f"⚠️ <b>Картины: не в канале</b> — "
                         f"{len(works) - in_channel} из {len(works)}\n"
                         f"    <code>/art_publish</code>")
        lines.append("")

    # --- очередь публикаций ------------------------------------------
    # Буфер считает то же самое с другой стороны: не «чего нет у материала»,
    # а «что из-за этого не выйдет».
    lines += ["<i>Что именно не выйдет в канал и почему — "
              "<code>/buffer</code></i>"]

    await message.answer("\n".join(lines))


# =====================================================================
# КАБИНЕТЫ ПАРТНЁРСКИХ ПРОГРАММ
# =====================================================================

@router.message(F.text.startswith("/kab"))
async def cabinets(message: Message):
    """Ссылки на личные кабинеты партнёрок — одним экраном"""
    if not config.is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=2)
    action = parts[1].lower() if len(parts) > 1 else ""
    items = await _cabinets()

    # /kab + Литрес https://… — добавить или заменить по названию
    if action in ("+", "добавить", "add") and len(parts) > 2:
        body = parts[2].strip()
        if " " not in body or "http" not in body:
            await message.answer(
                "Нужно название и ссылка: "
                "<code>/kab + Литрес https://litres.ru/...</code>")
            return
        name, url = body.rsplit(" ", 1)
        if not url.startswith("http"):
            await message.answer("Ссылка должна начинаться с https://")
            return
        items = [i for i in items if i["name"].lower() != name.strip().lower()]
        items.append({"name": name.strip()[:40], "url": url.strip()})
        await _save_cabinets(items)
        await message.answer(f"✅ Добавила: {html.escape(name.strip())}")
        return

    if action in ("напоминание", "напоминания", "remind"):
        value = parts[2].strip().lower() if len(parts) > 2 else ""
        if value in ("нет", "off", "0"):
            await database.set_setting(REMIND_DAY_KEY, "0")
            await message.answer("✅ Напоминать не буду.")
            return
        if value.isdigit():
            day = max(1, min(28, int(value)))
            await database.set_setting(REMIND_DAY_KEY, str(day))
            await message.answer(f"✅ Буду напоминать {day}-го числа, в "
                                 f"{REMIND_HOUR}:00 по часам канала.")
            return
        day = await _remind_day()
        await message.answer(
            (f"Напоминаю {day}-го числа каждого месяца." if day
             else "Сейчас не напоминаю.")
            + "\n\nИзменить: <code>/kab напоминание 10</code>\n"
              "Выключить: <code>/kab напоминание нет</code>\n"
              "Прислать сейчас: <code>/kab проверка</code>")
        return

    if action in ("проверка", "test") :
        await message.answer(f"✅ {await remind(message.bot)}")
        return

    if action in ("-", "удалить", "del") and len(parts) > 2:
        name = parts[2].strip().lower()
        left = [i for i in items if name not in i["name"].lower()]
        if len(left) == len(items):
            await message.answer("Такого кабинета в списке нет.")
            return
        await _save_cabinets(left)
        await message.answer("✅ Убрала.")
        return

    if not items:
        await message.answer(
            "Кабинетов пока нет.\n\n"
            "Добавить: <code>/kab + Литрес https://…</code>")
        return

    rows = [[InlineKeyboardButton(text=i["name"][:40], url=i["url"])]
            for i in items]
    await message.answer(
        "🗄 <b>Кабинеты партнёрских программ</b>\n\n"
        "Добавить: <code>/kab + Литрес https://…</code>\n"
        "Убрать: <code>/kab - Литрес</code>\n"
        f"Напоминание: <code>/kab напоминание</code> — "
        f"{'выключено' if not await _remind_day() else str(await _remind_day()) + '-го'}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


# =====================================================================
# НАПОМИНАНИЕ О ВЫПЛАТАХ
# =====================================================================
#
# Партнёрские программы считают вознаграждение своими циклами и никого не
# оповещают: деньги начислены, а вы об этом не знаете. Раз в месяц бот
# толкает заглянуть — с теми же кнопками, чтобы не искать адреса.
#
# Отметка о том, что за этот месяц уже напомнили, лежит в базе: иначе
# перезапуск сервиса в тот же день слал бы напоминание второй раз.

async def _remind_day() -> int:
    try:
        return max(0, min(28, int(await database.get_setting(REMIND_DAY_KEY)
                                  or REMIND_DAY_DEFAULT)))
    except (TypeError, ValueError):
        return REMIND_DAY_DEFAULT


async def remind(bot: Bot) -> str:
    """Отправить напоминание владельцу. Строка — для лога."""
    items = await _cabinets()
    if not items:
        return "кабинетов нет"
    rows = [[InlineKeyboardButton(text=i["name"][:40], url=i["url"])]
            for i in items]

    # Если ключ AdvCake задан, вместо «сходи посмотри» сразу цифры.
    numbers = ""
    try:
        import advcake
        if advcake._key():
            numbers = "\n\n" + await advcake.report(advcake.MAX_DAYS)
    except Exception as e:
        logging.warning(f"Цифры AdvCake к напоминанию не подъехали: {e}")

    try:
        await bot.send_message(
            config.ADMIN_ID,
            "🗄 <b>Пора заглянуть в кабинеты</b>\n\n"
            "Проверьте начисления за прошлый месяц: партнёрские программы "
            "считают вознаграждение сами и о нём не сообщают."
            + numbers +
            "\n\nОтключить: <code>/kab напоминание нет</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except Exception as e:
        logging.error(f"Напоминание о кабинетах не ушло: {e}")
        return f"ошибка: {e}"
    return "напомнила о кабинетах"


async def scheduler(bot: Bot):
    """Раз в час смотрит, не пора ли напомнить"""
    await asyncio.sleep(180)
    while True:
        try:
            day = await _remind_day()
            if day:
                import digest
                now = await digest._local_now()
                stamp = now.strftime("%Y-%m")
                already = await database.get_setting(REMIND_SENT_KEY)
                if now.day == day and now.hour >= REMIND_HOUR and already != stamp:
                    logging.info(f"Кабинеты: {await remind(bot)}")
                    await database.set_setting(REMIND_SENT_KEY, stamp)
        except Exception as e:
            logging.error(f"Проверка напоминания о кабинетах сорвалась: {e}")
        await asyncio.sleep(3600)
