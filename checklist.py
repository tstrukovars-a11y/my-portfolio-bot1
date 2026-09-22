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
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)

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


# --- записанное руками ------------------------------------------------
#
# Всё остальное на этом экране считается из данных: чего нет у книги, у
# места, у картины. Но часть дел живёт вне бота — завести кассу, снять
# картины, — и помнить их негде. Поэтому короткий список, который ведётся
# руками и лежит там же, где смотрят «что не готово».

OWED_KEY = "owed_by_owner"

# То, что уже проговорено и ждёт своей очереди. Список показывается,
# пока его не тронули: как только первый пункт вычеркнут, дальше живёт
# сохранённый — включая пустой.
OWED_DEFAULT = [
    "завести кассу Т-Банка и прислать ссылку (/касса)",
    "зарегистрироваться в Travelpayouts (ИНН, счёт, самозанятость)",
    "израильский тик — после развода, не раньше",
    "снять и загрузить фото картин (/art_list)",
]


async def _owed() -> list:
    raw = await database.get_setting(OWED_KEY)
    if not raw:
        return list(OWED_DEFAULT)
    try:
        items = json.loads(raw)
        return [str(x) for x in items] if isinstance(items, list) else []
    except (ValueError, TypeError):
        return []


async def _save_owed(items: list):
    await database.set_setting(OWED_KEY, json.dumps(items, ensure_ascii=False))


@router.message(F.text.regexp(r"^/долг"))
async def owed_command(message: Message):
    """/долг — показать, /долг текст — добавить, /долг -2 — вычеркнуть"""
    if not config.is_admin(message.from_user.id):
        return

    tail = (message.text or "").split(maxsplit=1)
    items = await _owed()

    if len(tail) < 2:
        if not items:
            await message.answer(
                "За вами ничего не записано.\n\n"
                "<code>/долг завести ЮKassa</code> — записать\n"
                "<code>/долг -1</code> — вычеркнуть первое")
            return
        lines = ["<b>За вами:</b>"]
        lines += [f"{i}. {html.escape(x)}" for i, x in enumerate(items, 1)]
        lines += ["", "<code>/долг -1</code> — вычеркнуть первое"]
        await message.answer("\n".join(lines))
        return

    text = tail[1].strip()
    if text.startswith("-") and text[1:].strip().isdigit():
        number = int(text[1:].strip())
        if not 1 <= number <= len(items):
            await message.answer(f"Столько пунктов нет: их {len(items)}.")
            return
        done = items.pop(number - 1)
        await _save_owed(items)
        await message.answer(f"✅ Вычеркнула: {html.escape(done)}")
        return

    items.append(text[:200])
    await _save_owed(items)
    await message.answer(f"Записала. Всего за вами: {len(items)}.")


@router.message(F.text.startswith(("/todo", "/чего")))
async def todo(message: Message):
    """Что мешает публиковать: по разделам, с командой для починки"""
    if not config.is_admin(message.from_user.id):
        return

    lines = ["🧾 <b>Чего не хватает</b>", ""]

    # Руками записанное идёт первым: остальное считается из данных и
    # само себя покажет, а это помнить больше негде.
    owed = await _owed()
    if owed:
        lines.append("<b>За вами:</b>")
        lines += [f"{i}. {html.escape(item)}" for i, item in enumerate(owed, 1)]
        lines.append("    <code>/долг</code>")
        lines.append("")

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

    # --- что устарело ------------------------------------------------
    #
    # Цены и правила меняются молча. Пока цифра на экране старая,
    # ошибается читатель, а отвечает владелица — поэтому напоминание
    # стоит рядом с остальным «чего не хватает», а не отдельной командой,
    # о которой надо помнить.
    try:
        import esim
        import exchange
        import freshness
        import hotels

        stale = freshness.stale_report({
            "Связь": await esim.plans(),
            "Бронирование": await hotels.places(),
            "Переводы": await exchange.services(),
        })
        if stale:
            lines += [stale, ""]
    except Exception as e:
        logging.warning(f"Проверка свежести справочников не прошла: {e}")

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
# ДОХОД С КНИГ
# =====================================================================
#
# Считать его автоматически пока нечем: выгрузка заказов AdvCake на все
# варианты параметра отвечает «Invalid offer», и пока их поддержка не
# назовёт верный, цифру приходится брать глазами из кабинета.
#
# Поэтому экран устроен так: что бот знает сам — переходы по вашим
# кнопкам — он показывает сразу; что знает только кабинет, вы вписываете
# раз в месяц одной строкой. Смешивать их в общую сумму нельзя, это
# разные вещи, и подписаны они порознь.
#
# Когда выгрузка заработает, заказы встанут в тот же экран третьим
# блоком, а вписанное руками останется историей.

INCOME_KEY = "book_income"        # список выплат в JSON

# Ключевые слова магазинов: человек пишет «литрес», а не «litres.ru».
SHOPS = {
    "литрес": "Литрес",
    "litres": "Литрес",
    "читай": "Читай-город",
    "chitai": "Читай-город",
    "озон": "Ozon",
    "ozon": "Ozon",
    "лабиринт": "Лабиринт",
    "wb": "Wildberries",
}


def _shop_name(word: str) -> str:
    low = (word or "").strip().lower()
    for key, name in SHOPS.items():
        if low.startswith(key):
            return name
    return (word or "").strip()[:20].capitalize()


async def _income() -> list:
    raw = await database.get_setting(INCOME_KEY)
    if not raw:
        return []
    try:
        saved = json.loads(raw)
        return saved if isinstance(saved, list) else []
    except (ValueError, TypeError):
        return []


async def _save_income(items: list):
    await database.set_setting(INCOME_KEY, json.dumps(items, ensure_ascii=False))


def _money(value) -> str:
    """1250.0 → «1 250 ₽»: разряды пробелом, копейки не нужны"""
    try:
        return f"{round(float(value)):,}".replace(",", " ") + " ₽"
    except (TypeError, ValueError):
        return "— ₽"


def _income_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗄 Кабинеты", callback_data="admin_cabinets")],
        [InlineKeyboardButton(text="👆 Переходы подробно", callback_data="admin_clicks")],
    ])


async def income_text() -> str:
    """Доход одним экраном: переходы бот считает сам, выплаты — из кабинета"""
    lines = ["💰 <b>Доход с партнёрских ссылок</b>", ""]

    # 1. То, что видно и без кабинетов, с первого дня.
    total, _, by_host, _ = await database.clicks_stats(30)
    shops = [(host, n) for host, n in by_host if host]
    lines.append("<b>Переходы за 30 дней</b>")
    if shops:
        lines += [f"{html.escape(host)} — {n}" for host, n in shops[:6]]
    else:
        lines.append("Пока ни одного.")
    lines.append("")

    # 2. То, что знает только кабинет.
    paid = await _income()
    lines.append("<b>Начислено по кабинетам</b>")
    if paid:
        by_month = {}
        for item in paid:
            by_month.setdefault(item.get("month") or "—", []).append(item)
        for month in sorted(by_month, reverse=True)[:6]:
            shops_line = ", ".join(
                f"{html.escape(str(i.get('shop') or '—'))} {_money(i.get('amount'))}"
                for i in by_month[month])
            month_sum = sum(float(i.get("amount") or 0) for i in by_month[month])
            lines.append(f"<b>{month}</b> · {_money(month_sum)}")
            lines.append(f"    {shops_line}")
        lines.append("")
        every = sum(float(i.get("amount") or 0) for i in paid)
        lines.append(f"Всего за всё время: <b>{_money(every)}</b>")
    else:
        lines.append("Пока ничего не вписано.")

    lines.append("")
    lines.append("Вписать: <code>/доход литрес 1250</code>")
    lines.append("За другой месяц: <code>/доход литрес 1250 2026-08</code>")
    lines.append("Убрать: <code>/доход удалить литрес 2026-08</code>")
    return "\n".join(lines)


@router.message(F.text.regexp(r"^/(доход|income)\b"))
async def income_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()

    if len(parts) >= 3 and parts[1].lower() in ("удалить", "del", "-"):
        shop = _shop_name(parts[2])
        month = parts[3] if len(parts) > 3 else datetime.now().strftime("%Y-%m")
        items = await _income()
        left = [i for i in items
                if not (i.get("shop") == shop and i.get("month") == month)]
        if len(left) == len(items):
            await message.answer(f"Записи «{html.escape(shop)} {month}» нет.")
            return
        await _save_income(left)
        await message.answer(f"✅ Убрала: {html.escape(shop)}, {month}")
        return

    if len(parts) >= 3:
        shop = _shop_name(parts[1])
        try:
            amount = float(parts[2].replace(",", ".").replace(" ", ""))
        except ValueError:
            await message.answer(
                "Сумма должна быть числом: <code>/доход литрес 1250</code>")
            return
        month = parts[3] if len(parts) > 3 else datetime.now().strftime("%Y-%m")
        # Запись за тот же магазин и месяц заменяется, а не копится: в
        # кабинете сумма за месяц растёт, и вписывать её будут не раз.
        items = [i for i in await _income()
                 if not (i.get("shop") == shop and i.get("month") == month)]
        items.append({"shop": shop, "month": month, "amount": amount})
        await _save_income(items)
        await message.answer(
            f"✅ {html.escape(shop)}, {month}: {_money(amount)}\n\n"
            f"Весь доход: <code>/доход</code>")
        return

    await message.answer(await income_text(), reply_markup=_income_menu())


@router.callback_query(F.data == "admin_income")
async def income_screen(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await call.message.answer(await income_text(), reply_markup=_income_menu())


@router.callback_query(F.data == "admin_clicks")
async def clicks_screen(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await call.message.answer(await clicks_text(30))


@router.callback_query(F.data == "admin_cabinets")
async def cabinets_screen(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    items = await _cabinets()
    if not items:
        await call.message.answer("Кабинетов пока нет.\n\n"
                                  "Добавить: <code>/kab + Литрес https://…</code>")
        return
    await call.message.answer(
        "🗄 <b>Кабинеты партнёрских программ</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=i["name"][:40], url=i["url"])]
            for i in items]))


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
            "\n\nУвидели сумму — впишите, чтобы она осталась в истории: "
            "<code>/доход литрес 1250</code>\n"
            "Весь доход: <code>/доход</code>\n\n"
            "Отключить: <code>/kab напоминание нет</code>",
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


# =====================================================================
# ПЕРЕХОДЫ ПО КНОПКАМ
# =====================================================================

async def clicks_text(days: int = 30) -> str:
    """Своя статистика переходов — она есть с первого дня, без сетей"""
    total, by_section, by_host, top = await database.clicks_stats(days)
    if not total:
        return (f"👆 За {days} дн. переходов не было.\n\n"
                "Считаются нажатия на кнопки магазинов под публикациями.")

    lines = [f"👆 <b>Переходы за {days} дн.</b>", "", f"Всего: <b>{total}</b>"]
    if by_section:
        lines += ["", "<b>Разделы</b>"]
        lines += [f"{s or '—'} — {n}" for s, n in by_section]
    if by_host:
        lines += ["", "<b>Магазины</b>"]
        lines += [f"{h or '—'} — {n}" for h, n in by_host]
    if top:
        lines += ["", "<b>Что нажимали</b>"]
        lines += [f"{html.escape(t[:40])} — {n}" for t, n in top]
    return "\n".join(lines)


@router.message(F.text.startswith("/clicks"))
async def clicks(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 30
    await message.answer(await clicks_text(days))
