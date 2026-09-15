# content_plan.py — план публикаций о себе и о том, что строится.
#
# Канал «Акцент» выходит сам, по расписанию. А вот рассказ о том, как он
# устроен и что в нём изменилось, никакой автомат не напишет: это личная
# история, и писать её нужно руками. План нужен, чтобы она писалась
# регулярно, а не когда вспомнилось.
#
# Чужая схема «сторис про жизнь, посты про результаты клиентов» здесь не
# подходит: клиентов нет, зато есть работающая вещь, которую видно.
# Поэтому план крутится вокруг неё — что сделано, что сломалось, как
# устроено, сколько принесло.
#
# Отметки в плане не выдуманы: галочка ставится по факту публикации,
# значок правки — по настоящим дырам в содержимом, тем же, что считает
# /todo. План, который врёт о состоянии дел, хуже отсутствующего.
import html
import logging
import os
import re
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)

import config
import database

router = Router()

# Латинское /plan занято календарём другой части бота, поэтому здесь
# только русское /план — иначе две команды спорили бы за одно имя, и
# побеждала бы та, чей роутер подключён раньше.
DONE_KEY = "content_plan_done_"   # + номер недели: что уже вышло

# День недели -> (площадка, тема, шаблон). Три поста в неделю — столько
# можно выдержать годами; пять «обязательных» бросают на третьей неделе.
WEEK = (
    (0, "Канал", "Что изменилось за неделю", "изменения"),
    (2, "Канал", "Польза по теме", ""),
    (4, "Канал", "Как это устроено", "закулисье"),
)

DAYS = ("понедельник", "вторник", "среда", "четверг",
        "пятница", "суббота", "воскресенье")
SHORT = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6}

# Раз в месяц — открытые цифры. Их читают охотнее всего и почти никто
# не публикует.
MONTHLY = (1, "Канал", "Цифры месяца", "цифры")

EVERY_DAY = "Сторис: одно «что делаю прямо сейчас». Хватает снимка экрана."


def _week_id(when: datetime = None) -> str:
    when = when or datetime.now()
    year, week, _ = when.isocalendar()
    return f"{year}-{week:02d}"


async def _done(week: str) -> set:
    raw = await database.get_setting(DONE_KEY + week) or ""
    return {int(x) for x in raw.split(",") if x.strip().isdigit()}


async def _mark(week: str, day: int, done: bool):
    days = await _done(week)
    days.add(day) if done else days.discard(day)
    await database.set_setting(DONE_KEY + week,
                               ",".join(str(d) for d in sorted(days)))


# ---------------------------------------------------------------------
# ЧТО В СОДЕРЖИМОМ ТРЕБУЕТ РУК
# ---------------------------------------------------------------------

async def gaps() -> list:
    """[(значок, строка, команда)] — настоящие дыры, а не напоминания."""
    out = []
    try:
        stats = await database.books_link_stats()
        no_link = await database.books_without_link()
        no_cover = await database.books_without_cover(100)
        if no_link:
            out.append(("✏️", f"книг без ссылок: {len(no_link)} "
                              f"из {stats.get('total', 0)}", "/book_links"))
        if no_cover:
            out.append(("✏️", f"книг без обложек: {len(no_cover)}", "/book_covers"))

        places = await database.travel_without_photo(200)
        if places:
            out.append(("✏️", f"мест без фото: {len(places)}", "/travel_photos"))
        spots = await database.spots_without_photo(200)
        if spots:
            out.append(("✏️", f"достопримечательностей без фото: {len(spots)}",
                        "/spot_photos"))

        works = await database.art_list()
        blind = [w for w in works if not w.get("photo_file_id")]
        if blind:
            out.append(("✏️", f"картин без фото: {len(blind)}", "/art_list"))
    except Exception as e:
        logging.warning(f"План: дыры не посчитались: {e}")
    return out


# ---------------------------------------------------------------------
# ЗАПАСЫ: НА СКОЛЬКО ДНЕЙ ХВАТИТ
# ---------------------------------------------------------------------
#
# Каждый раздел канала выходит раз в день и берёт следующий
# неопубликованный материал. Значит, число невыпущенных — это прямо
# число дней, которые раздел проживёт. Когда материал кончается, канал
# начинает повторяться, и заметно это становится позже, чем хотелось бы.

STOCK = (
    ("books", "📚 Книги", "/books_seed"),
    ("genetics", "🧬 Генетика", "/genetics"),
    ("travel", "🌍 Путешествия", "/spots"),
    ("recipes", "🍳 Рецепты", "/recipes"),
)

LOW = 7        # неделя — время успеть пополнить
CRITICAL = 3   # три дня — уже горит


def _stock_mark(left: int) -> str:
    if left <= CRITICAL:
        return "🔴"
    if left <= LOW:
        return "⚠️"
    return "✅"


async def stock() -> list:
    """[(значок, раздел, осталось, всего, команда)] по всем разделам"""
    out = []
    for section, title, command in STOCK:
        total, _, left = await database.section_stock(section)
        if not total:
            continue
        out.append((_stock_mark(left), title, left, total, command))

    try:
        bank = await database.count_puzzles()
        used = len(await database.published_puzzle_ids())
        left = max(0, bank - used)
        if bank:
            out.append((_stock_mark(left), "🧩 Задачи дня", left, bank,
                        "/puzzles"))
    except Exception as e:
        logging.warning(f"Запас задач не посчитался: {e}")
    return out


async def stock_text() -> str:
    rows = await stock()
    if not rows:
        lines = ["📦 <b>Запасы контента</b>", "", "Материалов пока нет вовсе."]
        return "\n".join(lines)

    lines = ["📦 <b>Запасы контента</b>", "",
             "<i>Раздел выходит раз в день, поэтому «осталось» — это "
             "и есть число дней.</i>", ""]
    for mark, title, left, total, command in rows:
        lines.append(f"{mark} <b>{title}</b> — {left} из {total}, "
                     f"это {_days_word(left)}")
        if left <= LOW:
            lines.append(f"    пополнить: <code>{command}</code>")

    soon = [t for m, t, *_ in rows if m != "✅"]
    if soon:
        lines += ["", f"⚠️ Скоро закончится: {', '.join(soon)}. "
                      f"Когда материал кончается, канал начинает повторяться."]
    else:
        lines += ["", "✅ Всем разделам хватает больше чем на неделю."]
    return "\n".join(lines)


def _days_word(n: int) -> str:
    if 11 <= n % 100 <= 14:
        return f"{n} дней"
    return {1: f"{n} день", 2: f"{n} дня", 3: f"{n} дня",
            4: f"{n} дня"}.get(n % 10, f"{n} дней")


# ---------------------------------------------------------------------
# ФАКТЫ ДЛЯ ПУБЛИКАЦИЙ
# ---------------------------------------------------------------------

async def facts() -> dict:
    """Живые цифры проекта — их и вставляем в шаблоны.

    Выдуманная цифра в посте о собственной работе дороже любой другой
    ошибки: её проверяют.
    """
    out = {}
    here = os.path.dirname(os.path.abspath(__file__))

    tests = 0
    folder = os.path.join(here, "tests")
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if name.startswith("test_") and name.endswith(".py"):
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    tests += len(re.findall(r"^def test_", f.read(), re.M))
    out["тестов в коде"] = tests

    try:
        import commands
        out["команды"] = sum(len(group) for _, group in commands.collect())
    except Exception:
        out["команды"] = 0

    try:
        stats = await database.books_link_stats()
        out["книг"] = stats.get("total", 0)
        out["книг со ссылками"] = stats.get("done", 0)
    except Exception:
        pass

    try:
        total, _, by_host, _ = await database.clicks_stats(30)
        out["переходов за месяц"] = total
        out["магазинов"] = len(by_host)
    except Exception:
        pass

    try:
        out["мест"] = await database.count_travel_places()
    except Exception:
        pass
    return out


def _facts_block(data: dict) -> str:
    if not data:
        return ""
    return "\n".join(f"· {name}: <b>{value}</b>" for name, value in data.items())


TEMPLATES = {
    "изменения": (
        "Что изменилось за неделю",
        "На этой неделе {что сделали}.\n\n"
        "{Что сломалось и как нашли — эта часть интереснее всего, "
        "не выкидывайте её.}\n\n"
        "{Что это даёт читателю.}\n\n"
        "Сейчас в проекте:\n{факты}"),
    "закулисье": (
        "Как это устроено",
        "{Что читатель видит каждый день — одна фраза.}\n\n"
        "Под этим: {как оно работает, без терминов}.\n\n"
        "{Почему сделано именно так, а не проще.}\n\n"
        "Проверить можно прямо сейчас: {ссылка или команда}."),
    "цифры": (
        "Цифры месяца",
        "Открытые цифры за месяц — их почти никто не публикует, "
        "а читать интересно.\n\n{факты}\n\n"
        "{Что из этого вышло неожиданным.}\n\n"
        "{Что планируете в следующем месяце.}"),
    "польза": (
        "Польза по теме",
        "{Ситуация, знакомая читателю.}\n\n"
        "{Что с этим делать — по шагам, коротко.}\n\n"
        "{Чем это кончится, если не делать.}"),
}


# ---------------------------------------------------------------------
# ЭКРАНЫ
# ---------------------------------------------------------------------

def _menu(week: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"✍️ {name}",
                                  callback_data=f"plantpl_{key}")]
            for key, (name, _) in TEMPLATES.items()]
    rows.append([InlineKeyboardButton(text="📦 Запасы контента",
                                      callback_data="planstock")])
    rows.append([InlineKeyboardButton(text="🧾 Что править",
                                      callback_data="plangaps")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def screen() -> str:
    now = datetime.now()
    week = _week_id(now)
    done = await _done(week)
    monday = now - timedelta(days=now.weekday())

    lines = [f"🗓 <b>План публикаций</b> · неделя {week}", ""]
    for day, where, theme, template in WEEK:
        date = (monday + timedelta(days=day)).strftime("%d.%m")
        mark = "✅" if day in done else ("🔸" if day < now.weekday() else "⬜️")
        hint = f" · <code>/шаблон {template}</code>" if template else ""
        lines.append(f"{mark} <b>{DAYS[day].capitalize()} {date}</b> — "
                     f"{theme}{hint}")
    lines.append("")

    if now.day <= 5:
        lines.append(f"📊 <b>Начало месяца</b> — {MONTHLY[2]}: "
                     f"<code>/шаблон цифры</code>")
        lines.append("")

    lines.append(f"<i>{EVERY_DAY}</i>")
    lines.append("")

    holes = await gaps()
    if holes:
        lines.append("✏️ <b>Содержимое, которое просит рук</b>")
        lines += [f"{mark} {text} — <code>{cmd}</code>"
                  for mark, text, cmd in holes]
    else:
        lines.append("✅ Дыр в содержимом нет.")

    # Строка о запасах — в самом плане, а не только по кнопке: раздел,
    # которому осталось три дня, должен попасться на глаза сам.
    low = [f"{title} — {_days_word(left)}"
           for mark, title, left, _, _ in await stock() if mark != "✅"]
    if low:
        lines += ["", "📦 <b>Заканчивается</b>", *[f"{m}" for m in low],
                  "Подробно: <code>/запасы</code>"]

    lines += ["", "Отметить вышедшее: <code>/план готово пн</code>",
              "Снять отметку: <code>/план не пн</code>"]
    return "\n".join(lines)


@router.message(F.text.regexp(r"^/(план|контент)$"))
async def plan_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    await message.answer(await screen(), reply_markup=_menu(_week_id()))


@router.message(F.text.regexp(r"^/(план|контент)\s"))
async def plan_mark(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    action = parts[1].lower() if len(parts) > 1 else ""
    day_word = parts[2].lower()[:2] if len(parts) > 2 else ""

    if action in ("готово", "done", "не", "нет") and day_word in SHORT:
        await _mark(_week_id(), SHORT[day_word], action in ("готово", "done"))
        await message.answer(await screen(), reply_markup=_menu(_week_id()))
        return
    await message.answer(
        "Отметить: <code>/план готово пн</code>\n"
        "Снять: <code>/план не пн</code>\n"
        "Шаблон: <code>/шаблон изменения</code>")


@router.message(F.text.regexp(r"^/шаблон"))
async def template_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    key = parts[1].strip().lower() if len(parts) > 1 else ""
    if key not in TEMPLATES:
        await message.answer(
            "✍️ <b>Шаблоны</b>\n\n" + "\n".join(
                f"<code>/шаблон {k}</code> — {name}"
                for k, (name, _) in TEMPLATES.items()),
            reply_markup=_menu(_week_id()))
        return
    await message.answer(await filled(key))


async def filled(key: str) -> str:
    """Шаблон с подставленными цифрами — остаётся дописать своё"""
    name, body = TEMPLATES[key]
    data = await facts()
    text = body.replace("{факты}", _facts_block(data) or "· (цифры не собрались)")
    return (f"✍️ <b>{name}</b>\n\n{text}\n\n"
            f"<i>В фигурных скобках — то, что пишете вы. Цифры уже "
            f"настоящие, из бота.</i>")


@router.callback_query(F.data == "admin_plan")
async def plan_screen(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await call.message.answer(await screen(), reply_markup=_menu(_week_id()))


@router.callback_query(F.data.startswith("plantpl_"))
async def template_button(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    key = call.data.split("_", 1)[1]
    await call.answer()
    if key in TEMPLATES:
        await call.message.answer(await filled(key))


@router.message(F.text.regexp(r"^/(запасы|stock)"))
async def stock_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    await message.answer(await stock_text())


@router.callback_query(F.data == "planstock")
async def stock_button(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await call.message.answer(await stock_text())


@router.callback_query(F.data == "plangaps")
async def gaps_button(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    holes = await gaps()
    if not holes:
        await call.message.answer("✅ Дыр в содержимом нет — можно писать.")
        return
    await call.message.answer(
        "✏️ <b>Что править</b>\n\n" + "\n".join(
            f"{mark} {text}\n    <code>{cmd}</code>" for mark, text, cmd in holes))
