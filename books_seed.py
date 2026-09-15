# books_seed.py — книжная полка из готового списка.
#
# Список написан и выверен вручную, а не сгенерирован: у моделей книги
# путаются авторами, и одна такая ошибка в канале для предпринимателей
# стоит дороже, чем весь выигрыш во времени.
#
# Обложки — только настоящие, их подгружает владелец. Сгенерированная
# обложка существующей книги вводит в заблуждение так же, как выдуманная
# фотография настоящего места.
import asyncio
import html
import json
import logging
import os
import time

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.dispatcher.event.bases import SkipHandler

import config
import database

router = Router()

SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "data", "books_seed.json")

SHELVES = {"business": "📈 Бизнес и лидерство",
           "horizon": "🔭 Кругозор и наука",
           "tools": "🛠 Инструменты"}


class Covers(StatesGroup):
    waiting = State()


def _post(book: dict) -> str:
    """Как книга выглядит и в разделе, и в канале.

    Автор и название первой строкой: по ней же ищется дубль при повторной
    загрузке, поэтому строка должна быть устойчивой.
    """
    return (f"{book['author']} — {book['title']}\n\n"
            f"Чему научит: {book['learn']}")


def load_seed():
    with open(SEED_PATH, encoding="utf-8") as f:
        return json.load(f).get("books") or []


@router.message(F.text == "/books_seed")
async def seed(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    try:
        books = load_seed()
    except Exception as e:
        logging.error(f"Список книг не читается: {e}")
        await message.answer("⚠️ Файл со списком книг не читается.")
        return

    note = await message.answer(f"📚 Загружаю {len(books)} книг…")
    added = updated = failed = 0
    for b in books:
        result = await database.add_book_unique(
            b.get("category", "business"), _post(b))
        if result == "added":
            added += 1
        elif result == "updated":
            updated += 1
        else:
            failed += 1

    by_shelf = {}
    for b in books:
        key = b.get("category", "business")
        by_shelf[key] = by_shelf.get(key, 0) + 1
    body = "\n".join(f"{SHELVES.get(k, k)}: {v}" for k, v in by_shelf.items())

    await note.edit_text(
        f"📚 <b>Книжная полка</b>\n\n{body}\n\n"
        f"Добавлено: {added}, обновлено: {updated}"
        + (f", не прошло: {failed}" if failed else "")
        + "\n\nОбложки: <code>/book_covers</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🖼 Загрузить обложки",
                                  callback_data="bookcovers")]]))


@router.message(F.text == "/books_check")
async def check(message: Message):
    """Сверяет список из файла с тем, что лежит на полке.

    Счётчик «добавлено 29» не говорит, какая книга не дошла, а искать её
    глазами среди тридцати — работа на ровном месте.
    """
    if not config.is_admin(message.from_user.id):
        return
    try:
        books = load_seed()
    except Exception as e:
        await message.answer(f"⚠️ Файл не читается: {e}")
        return

    in_db = await database.books_all()
    heads = {(t or "").split("\n")[0].strip() for _, _, t, _, _ in in_db}

    missing = [b for b in books if _post(b).split("\n")[0].strip() not in heads]
    extra = len(in_db) - (len(books) - len(missing))

    lines = [f"📚 <b>Сверка</b>\n",
             f"В файле: {len(books)}",
             f"На полке: {len(in_db)}"]
    if missing:
        lines.append(f"\n<b>Не дошли ({len(missing)}):</b>")
        lines += [f"• {html.escape(b['author'])} — {html.escape(b['title'])}"
                  for b in missing]
        lines.append("\nПовторите <code>/books_seed</code> — добавятся только они.")
    else:
        lines.append("\n✅ Все книги из файла на месте.")
    if extra > 0:
        lines.append(f"\nСверх файла на полке: {extra} "
                     f"(пришли из канала по хештегу — это нормально)")
    await message.answer("\n".join(lines))


# =====================================================================
# КАНАЛ-СПРАВОЧНИК
#
# Полка живёт отдельным каналом, а «Акцент» на неё ссылается. Выкладка
# помнит номер каждого поста, поэтому повторный запуск правит вышедшее,
# а не выкладывает второй раз — как это уже сделано у путешествий.
# =====================================================================

CHANNEL_KEY = "books_channel"
# Telegram пропускает в канал около двадцати сообщений в минуту. Пауза
# в 1,2 секунды давала пятьдесят — часть постов отбивалась по частоте.
PAUSE = 3.2
MAX_CAPTION = 1024
MAX_MESSAGE = 4096


async def _channel():
    raw = await database.get_setting(CHANNEL_KEY)
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


@router.message(F.text.startswith("/books_channel"))
async def set_channel(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        await database.set_setting(CHANNEL_KEY, parts[1].strip())
        await message.answer(
            f"✅ Канал книг: <code>{html.escape(parts[1].strip())}</code>\n\n"
            "Выложить полку: <code>/books_publish</code>")
        return
    chat = await _channel()
    books = await database.books_all()
    posted = sum(1 for b in books if b[4])
    await message.answer(
        f"📚 <b>Канал книг</b>\n\nКанал: <code>{chat or 'не задан'}</code>\n"
        f"Книг: {len(books)}, выложено: {posted}\n\n"
        "<code>/books_channel -100…</code> — задать канал\n"
        "<code>/books_publish</code> — выложить или обновить")


@router.message(F.text == "/books_publish")
async def publish_all(message: Message, bot):
    if not config.is_admin(message.from_user.id):
        return
    chat = await _channel()
    if not chat:
        await message.answer("❌ Сначала задайте канал: <code>/books_channel -100…</code>")
        return
    books = await database.books_all()
    if not books:
        await message.answer("Книг нет. Загрузите: <code>/books_seed</code>")
        return
    note = await message.answer(f"📚 Выкладываю {len(books)} книг…")
    asyncio.create_task(_run(bot, chat, books, note))


async def _buy_markup(text: str):
    """Кнопка покупки под книгой в справочнике. Шаблон общий с «Акцентом»:
    менять партнёра в двух местах — верный способ забыть одно из них."""
    import digest
    title = (text or "").split("\n")[0]
    row = await digest._buy_row("books", title)
    # Раскладку берём оттуда же: четыре кнопки в одну строку не помещаются.
    return (InlineKeyboardMarkup(inline_keyboard=digest._pairs(row))
            if row else None)


async def _run(bot, chat: int, books, note: Message):
    """Очередь, а не простой обход: отбитое по частоте возвращается в
    конец и выходит позже. Раньше такая книга молча выпадала из полки —
    из тридцати в канал попадало двадцать девять."""
    new = edited = failed = 0
    queue = list(books)
    tries = {}

    while queue:
        book_id, category, text, cover, msg_id = queue.pop(0)
        body = f"{SHELVES.get(category, '📚')}\n\n{(text or '').strip()}"
        buy = await _buy_markup(text)
        try:
            if msg_id:
                try:
                    if cover:
                        await bot.edit_message_caption(
                            chat_id=chat, message_id=msg_id,
                            caption=body[:MAX_CAPTION], parse_mode=None,
                            reply_markup=buy)
                    else:
                        await bot.edit_message_text(
                            chat_id=chat, message_id=msg_id,
                            text=body[:MAX_MESSAGE], parse_mode=None,
                            reply_markup=buy)
                    edited += 1
                except TelegramBadRequest as e:
                    if "not modified" in str(e).lower():
                        continue
                    # Обложку приложили после выкладки: текстовый пост
                    # картинкой не станет, его надо переиздать.
                    if not cover:
                        raise
                    try:
                        await bot.delete_message(chat_id=chat, message_id=msg_id)
                    except Exception as drop:
                        logging.warning(f"Старый пост книги не снялся: {drop}")
                    sent = await bot.send_photo(chat, cover,
                                                caption=body[:MAX_CAPTION], parse_mode=None,
                                                reply_markup=buy)
                    await database.set_book_msg(book_id, sent.message_id)
                    edited += 1
            else:
                if cover:
                    sent = await bot.send_photo(chat, cover,
                                                caption=body[:MAX_CAPTION], parse_mode=None,
                                                reply_markup=buy)
                else:
                    sent = await bot.send_message(chat, body[:MAX_MESSAGE], parse_mode=None,
                                                  reply_markup=buy)
                await database.set_book_msg(book_id, sent.message_id)
                new += 1
        except TelegramRetryAfter as e:
            tries[book_id] = tries.get(book_id, 0) + 1
            if tries[book_id] <= 3:
                logging.info(f"Канал книг: пауза {e.retry_after} с, книга {book_id} в конец очереди")
                queue.append((book_id, category, text, cover, msg_id))
            else:
                logging.error(f"Канал книг: книга {book_id} отбита по частоте трижды")
                failed += 1
            await asyncio.sleep(e.retry_after + 1)
            continue
        except Exception as e:
            logging.error(f"Канал книг: {book_id} — {type(e).__name__}: {e}")
            failed += 1
        await asyncio.sleep(PAUSE)

    tail = f"Новых: {new}, обновлено: {edited}"
    if failed:
        tail += f", не прошло: {failed}"
    try:
        await note.edit_text(f"📚 <b>Готово</b>\n\n{tail}")
    except Exception:
        pass


# =====================================================================
# ОБЛОЖКИ
# =====================================================================

async def _next_book(state: FSMContext):
    data = await state.get_data()
    skipped = set(data.get("skipped", []))
    for bid, title in await database.books_without_cover():
        if bid not in skipped:
            return bid, title
    return None


async def _ask_cover(target, state: FSMContext, prefix: str = ""):
    nxt = await _next_book(state)
    if not nxt:
        await state.clear()
        await target.answer(prefix + "✅ Все книги с обложками.")
        return
    bid, title = nxt
    left = len(await database.books_without_cover())
    await state.set_state(Covers.waiting)
    await state.update_data(book_id=bid, title=title)
    await target.answer(
        f"{prefix}🖼 <b>{html.escape(title)}</b>\n\n"
        f"Пришлите обложку. Осталось: {left}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="bookskip"),
             InlineKeyboardButton(text="⏹ Закончить", callback_data="bookstop")]]))


@router.message(F.text == "/book_covers")
async def covers_command(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    await state.update_data(skipped=[])
    await _ask_cover(message, state)


@router.callback_query(F.data == "bookcovers")
async def covers_button(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await state.update_data(skipped=[])
    await _ask_cover(call.message, state)
    await call.answer()


@router.callback_query(F.data == "bookskip")
async def skip_book(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    skipped = list(data.get("skipped", []))
    if data.get("book_id"):
        skipped.append(data["book_id"])
    await state.update_data(skipped=skipped)
    await _ask_cover(call.message, state)
    await call.answer("Пропущено")


@router.callback_query(F.data == "bookstop")
async def stop_books(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("Готово. Вернуться: <code>/book_covers</code>")
    await call.answer()


@router.message(Covers.waiting, F.photo)
async def take_cover(message: Message, state: FSMContext):
    data = await state.get_data()
    book_id = data.get("book_id")
    if not book_id:
        await state.clear()
        return
    if not await database.set_book_cover(book_id, message.photo[-1].file_id):
        await message.answer("⚠️ Не сохранилось. Пришлите ещё раз.")
        return
    await _ask_cover(message, state, prefix=f"✅ {html.escape(data.get('title', ''))}\n\n")


# =====================================================================
# ПАРТНЁРСКИЕ ССЫЛКИ
# =====================================================================
#
# Магазин отдаёт ссылку на конкретную страницу товара, а не шаблон, —
# значит, у каждой книги ссылка своя, и её надо ввести руками.
#
# Состояние ввода живёт в базе, а не в памяти процесса. Первая версия
# держала «на какой книге остановились» в FSM, и деплой посреди работы
# стирал его: следующая присланная ссылка не подходила ни одному
# обработчику, и бот молчал.

# Ходить в кабинет магазина за каждой из тридцати книг — работа, которой
# быть не должно. Партнёрская ссылка почти всегда устроена одинаково:
# адрес сети, а внутри, отдельным параметром, адрес страницы товара. Если
# такой параметр в шаблоне раздела есть, мы просто подставляем в него
# обычный адрес книги — и получаем то же, что выдал бы генератор ссылок.
#
# Заворачиваем только то, что похоже на адрес самого магазина: чужую
# ссылку подставлять в свою партнёрскую нельзя.
SHOP_HOSTS = ("litres.ru", "chitai-gorod.ru", "book24.ru", "labirint.ru",
              "ozon.ru", "wildberries.ru")


def _host(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url or "").netloc.lower().removeprefix("www.")


def _fill(url: str) -> str:
    """Подставить метку раздела вместо {sub}.

    После сборки адреса фигурные скобки оказываются в процентной
    кодировке, поэтому меняем оба написания — иначе в ссылку уходит
    буквальное «%7Bsub%7D», и статистика сети считает его именем метки.
    """
    for mark in ("{sub}", "%7Bsub%7D", "%7bsub%7d"):
        url = url.replace(mark, "books")
    return url


async def affiliate(plain: str):
    """(партнёрская ссылка, имя магазина) из обычного адреса книги.

    Пусто — значит завернуть не во что: у раздела нет шаблона с адресом
    этого магазина внутри.
    """
    from urllib.parse import urlparse, urlunparse, parse_qs, urlencode, unquote
    import digest

    host = _host(plain)
    if not host or not any(shop in host for shop in SHOP_HOSTS):
        return "", ""

    for label, template in await digest._shop_templates("books"):
        parts = urlparse(template)

        # Второй вид партнёрской ссылки: она ведёт прямо в магазин, а
        # партнёра выдаёт параметр — у Литреса это lfrom. Тогда страницу
        # книги не подставляют внутрь, а наоборот: метку переносят на
        # адрес книги.
        if _host(template) == host:
            marks = {k: v[0] for k, v in
                     parse_qs(parts.query, keep_blank_values=True).items()
                     if "{q}" not in (v[0] or "") and "{sub}" not in (v[0] or "")}
            if not marks:
                continue
            book = urlparse(plain)
            merged = {k: v[0] for k, v in
                      parse_qs(book.query, keep_blank_values=True).items()}
            merged.update(marks)
            ready = urlunparse(book._replace(query=urlencode(merged)))
            return _fill(ready), (label or host)

        params = parse_qs(parts.query, keep_blank_values=True)
        for name, values in params.items():
            inside = unquote(values[0] or "")
            # Параметр, в котором лежит адрес того же магазина, — и есть
            # место для страницы книги.
            if inside.startswith("http") and host in _host(inside):
                params[name] = [plain]
                query = urlencode({k: v[0] for k, v in params.items()})
                ready = urlunparse(parts._replace(query=query))
                return _fill(ready), (label or host)
    return "", ""


MODE_KEY = "book_links_user"      # кто сейчас вводит
CURSOR_KEY = "book_links_cursor"  # какую книгу назвали последней
SKIP_KEY = "book_links_skipped"   # что пропустили за эту сессию
ALL_KEY = "book_links_all"        # идём по всем книгам, а не только пустым
FILTER_KEY = "book_links_shop"    # какой магазин правим, если не все
DONE_KEY = "book_links_done"      # что уже заменили за эту сессию

# Человек пишет «литрес», а в ссылке стоит домен. Список тот же, что у
# заворачивания: чинить можно только то, что умеем заворачивать.
SHOP_WORDS = {
    "литрес": "litres.ru", "litres": "litres.ru",
    "читай": "chitai-gorod.ru", "читай-город": "chitai-gorod.ru",
    "chitai": "chitai-gorod.ru",
    "озон": "ozon.ru", "ozon": "ozon.ru",
    "лабиринт": "labirint.ru", "labirint": "labirint.ru",
    "book24": "book24.ru",
}


# Метки, по которым видно, что ссылка уже партнёрская. Их ставят сами
# магазины и сети: lfrom у Литреса, erid по закону о рекламе, остальное —
# обычные пометки источника.
PARTNER_MARKS = ("lfrom", "erid", "advcake", "partner", "affiliate", "aff_id",
                 "utm_source", "utm_medium", "pp", "ref", "sub1")


def is_affiliate(url: str) -> bool:
    """Ссылка уже партнёрская — трогать её нельзя.

    Сделанную руками в кабинете ссылку переделывать не просто незачем, а
    вредно: в ней могут быть метки, которых нет в шаблоне, и подмена их
    шаблонными потеряет часть учёта.
    """
    from urllib.parse import urlparse, parse_qs
    if not url:
        return False
    host = _host(url)
    if host and not any(shop in host for shop in SHOP_HOSTS):
        return True              # ведёт не в магазин, а в сеть — значит, готова
    keys = {k.lower() for k in parse_qs(urlparse(url).query,
                                        keep_blank_values=True)}
    return any(mark in key for key in keys for mark in PARTNER_MARKS)


def _mentions(link: str, host: str) -> bool:
    """Ссылка ведёт в этот магазин — прямо или внутри партнёрской.

    После заворачивания домен магазина уходит внутрь параметра, и по
    одному только хосту такую ссылку уже не найти: «обновить литрес»
    переставало видеть как раз то, что само и завернуло.
    """
    from urllib.parse import unquote
    return host in unquote(link or "").lower()


def _shop_of(link: str) -> str:
    """Какой магазин за ссылкой — даже если он спрятан внутри партнёрской.

    Показывать «ad.advcake.ru» бессмысленно: это адрес сети, а человеку
    надо знать, чья это книга — Литреса или Читай-города.
    """
    for host in SHOP_HOSTS:
        if _mentions(link, host):
            return host
    return _host(link)


def _shop_host(word: str) -> str:
    """Домен магазина по слову человека. Пусто — слово не про магазин."""
    low = (word or "").strip().lower()
    for key, host in SHOP_WORDS.items():
        if low.startswith(key):
            return host
    return ""
# Сессия на полдня. Полтора часа было мало: ссылку на каждую книгу надо
# сначала сделать в кабинете магазина, а это ходьба туда-сюда с перерывами.
# Сессия истекала посреди работы, и присланная ссылка уходила в никуда.
MODE_MINUTES = 720


def _link_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⏭ Пропустить", callback_data="booklink_skip"),
        InlineKeyboardButton(text="✅ Закончить", callback_data="booklink_stop")]])


async def _mode_on(user_id: int):
    await database.set_setting(
        MODE_KEY, f"{user_id}:{int(time.time()) + MODE_MINUTES * 60}")


async def _mode_off():
    await database.set_setting(MODE_KEY, "")
    await database.set_setting(CURSOR_KEY, "")
    await database.set_setting(SKIP_KEY, "")
    await database.set_setting(ALL_KEY, "")
    await database.set_setting(FILTER_KEY, "")
    await database.set_setting(DONE_KEY, "")


async def _skipped() -> set:
    raw = await database.get_setting(SKIP_KEY) or ""
    return {int(x) for x in raw.split(",") if x.strip().isdigit()}


async def _done() -> set:
    """Что уже заменили за эту сессию.

    В режиме «все» книга остаётся в списке и после замены — ссылка у неё
    просто становится другой. Без этой отметки бот показывал бы первую
    книгу по кругу, сколько её ни правь.
    """
    raw = await database.get_setting(DONE_KEY) or ""
    return {int(x) for x in raw.split(",") if x.strip().isdigit()}


async def _done_add(book_id: int):
    ids = await _done()
    ids.add(book_id)
    await database.set_setting(DONE_KEY, ",".join(str(i) for i in sorted(ids)))


async def _skip_add(book_id: int):
    """Пропуски копятся за сессию.

    Раньше исключалась только текущая книга, и на двух оставшихся бот
    ходил по кругу: пропустил первую — показал вторую, пропустил вторую —
    снова первую.
    """
    ids = await _skipped()
    ids.add(book_id)
    await database.set_setting(SKIP_KEY, ",".join(str(i) for i in sorted(ids)))


async def _mode_active(user_id: int) -> bool:
    raw = await database.get_setting(MODE_KEY) or ""
    try:
        who, until = raw.split(":")
        return int(who) == user_id and int(until) > time.time()
    except ValueError:
        return False


async def _books_for_session():
    """Какие книги показывать: только пустые или все подряд.

    «Все» нужны, когда ссылки уже заведены, но их надо заменить: магазин
    сменил адреса, или прежние ссылки были не партнёрскими.
    """
    if (await database.get_setting(ALL_KEY) or "") != "1":
        return [(i, t, "", "") for i, t in await database.books_without_link()]

    every = await database.books_links_all()
    only = await database.get_setting(FILTER_KEY) or ""
    if only:
        # Правим один магазин — книги без его ссылки сюда не относятся.
        return [row for row in every
                if _mentions(row[2], only) or _mentions(row[3], only)]
    return every


async def _ask_next(message: Message):
    """Назвать следующую книгу либо завершить"""
    all_left = await _books_for_session()
    skipped, done = await _skipped(), await _done()
    left = [b for b in all_left if b[0] not in skipped and b[0] not in done]
    stats = await database.books_link_stats()

    if not left:
        await _mode_off()
        tail = ""
        if skipped:
            tail = (f"\n\nПропущено книг: {len(skipped)} — у них осталась "
                    f"прежняя ссылка. Вернуться к ним — "
                    f"<code>/book_links</code>, посмотреть номера — "
                    f"<code>/book_links_show</code>.")
        await message.answer(
            f"✅ Готово: ссылки есть у {stats['done']} книг из {stats['total']}.{tail}")
        return

    book_id, title, first, second = left[0]
    await database.set_setting(CURSOR_KEY, str(book_id))
    # Показываем магазины, а не адреса: адрес длинный и в сообщении только
    # мешает, а решение принимается по магазину.
    shops = [_shop_of(u) for u in (first, second) if u]
    now_line = f"Сейчас: {html.escape(' и '.join(shops))}\n" if shops else ""
    await message.answer(
        f"📚 <b>{html.escape(title)}</b>\n\n"
        f"{now_line}"
        f"Пришлите ссылку на эту книгу — годится и готовая партнёрская "
        f"из кабинета, и обычный адрес страницы.\n"
        f"«Пропустить» — оставить прежнюю.\n"
        f"<i>Осталось {len(left)}, готово {stats['done']} из {stats['total']}</i>",
        reply_markup=_link_kb())


@router.message(F.text.regexp(r"^/book_links\s+(шаблон|проверка|check)"))
async def check_templates(message: Message):
    """Почему заворачивание не работает — по самим шаблонам раздела.

    Спрашивать у владельца «покажите вашу ссылку» плохо: она длинная, в
    ней партнёрский номер, и переписывать её в переписку незачем. Бот
    видит её сам и может сказать, годится она для подстановки или нет.
    """
    if not config.is_admin(message.from_user.id):
        return

    from urllib.parse import urlparse, parse_qs, unquote
    import digest

    templates = await digest._shop_templates("books")
    lines = ["🔧 <b>Шаблоны магазинов для книг</b>", ""]
    if not templates:
        await message.answer(
            "У раздела книг нет ни одного шаблона — заворачивать не во что.\n\n"
            "Задать: <code>/digest shop books 📱 Литрес | ссылка</code>")
        return

    for label, template in templates:
        lines.append(f"<b>{html.escape(label or _host(template))}</b>")
        lines.append(f"Сеть: <code>{html.escape(_host(template))}</code>")

        found = []
        for name, values in parse_qs(urlparse(template).query,
                                     keep_blank_values=True).items():
            inside = unquote(values[0] or "")
            if inside.startswith("http"):
                found.append(f"{name} → {_host(inside)}")
        marks = [k for k, v in parse_qs(urlparse(template).query,
                                        keep_blank_values=True).items()
                 if "{q}" not in (v[0] or "") and "{sub}" not in (v[0] or "")]
        if found:
            lines.append("Адрес магазина внутри: <code>"
                         + html.escape(", ".join(found)) + "</code>")
            lines.append("✅ Подставлю страницу книги внутрь ссылки.")
        elif _host(template) in SHOP_HOSTS and marks:
            lines.append("Метка партнёра: <code>"
                         + html.escape(", ".join(marks)) + "</code>")
            lines.append("✅ Перенесу метку на адрес книги.")
        else:
            lines.append("❌ Ни адреса магазина внутри, ни партнёрской метки — "
                         "подставить книгу некуда. Такая ссылка ведёт только "
                         "на поиск и денег не принесёт.")
        lines.append("")

    # Живая проверка на настоящем адресе: словами можно ошибиться, делом нет.
    sample = "https://www.litres.ru/book/proverka-123/"
    ready, shop = await affiliate(sample)
    lines.append("<b>Проба на адресе книги с Литреса</b>")
    lines.append(f"→ {html.escape(shop)}: <code>{html.escape(ready[:90])}…</code>"
                 if ready else "→ завернуть не вышло")
    await message.answer("\n".join(lines))


@router.message(F.text.regexp(r"^/book_links\s+(обновить|перезавернуть|rewrap)"))
async def rewrap_links(message: Message):
    """Перезавернуть уже введённые ссылки в партнёрские.

    Ссылки заводились до того, как бот научился заворачивать их сам:
    часть из них — обычные адреса магазина, и покупка по ним не
    засчитывается. Проходим по всем и чиним молча — руками это тридцать
    походов в кабинет.
    """
    if not config.is_admin(message.from_user.id):
        return

    parts = message.text.split()
    only = _shop_host(parts[2]) if len(parts) > 2 else ""
    if len(parts) > 2 and not only:
        await message.answer(
            f"Не знаю магазин «{html.escape(parts[2])}». "
            f"Можно: {', '.join(sorted(set(SHOP_WORDS.values())))}")
        return

    books = await database.books_with_link()
    if only:
        # Правим ссылки одного магазина: остальные не трогаем совсем,
        # чтобы «обновить литрес» не переписало заодно Читай-город.
        books = [b for b in books if _mentions(b[2], only)]
    if not books:
        await message.answer("Таких ссылок нет — править нечего.")
        return

    changed, already, skipped = 0, 0, []
    for book_id, title, link in books:
        if is_affiliate(link):
            already += 1
            continue
        ready, shop = await affiliate(link)
        if not ready:
            # Либо уже партнёрская, либо магазин без шаблона.
            if any(host in _host(link) for host in SHOP_HOSTS):
                skipped.append(title)
            else:
                already += 1
            continue
        if ready == link:
            already += 1
            continue
        if await save_link(book_id, ready) is not None:
            changed += 1

    lines = [f"🔗 <b>Перезавернула ссылки</b>"
             + (f" · {only}" if only else ""), "",
             f"Обновлено: <b>{changed}</b>",
             f"Уже были партнёрскими: {already}"]
    if skipped:
        lines += ["", f"⚠️ Остались обычными: {len(skipped)} — для их магазина "
                      f"нет шаблона в <code>/digest shop</code>:"]
        lines += [f"· {html.escape(t)}" for t in skipped[:6]]
    await message.answer("\n".join(lines))


@router.message(F.text.startswith("/book_links"))
async def book_links(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    every = len(parts) > 1 and parts[1].lower() in ("все", "всё", "all", "заново")
    # «/book_links литрес» — тоже проход по готовым, только одного магазина.
    only = _shop_host(parts[1]) if len(parts) > 1 else ""
    if not only and len(parts) > 2:
        only = _shop_host(parts[2])
    if only:
        every = True

    await _mode_on(message.from_user.id)
    await database.set_setting(SKIP_KEY, "")
    await database.set_setting(DONE_KEY, "")
    await database.set_setting(ALL_KEY, "1" if every else "")
    await database.set_setting(FILTER_KEY, only)
    stats = await database.books_link_stats()
    if only:
        where = (f"Иду по книгам со ссылками на {only} — присланная заменит "
                 f"прежнюю.")
    elif every:
        where = "Иду по всем книгам подряд — присланная ссылка заменит прежнюю."
    else:
        where = ("Иду по книгам без ссылок. Пройти все подряд и заменить "
                 "готовые — <code>/book_links все</code>")
    await message.answer(
        "🔗 <b>Партнёрские ссылки на книги</b>\n\n"
        f"Сейчас со ссылками: {stats['done']} из {stats['total']}.\n"
        f"{where}\n\n"
        "Буду называть книгу — присылайте ссылку. Годится обычный адрес "
        "страницы книги из Литреса или Читай-города: в партнёрскую заверну "
        "сама. "
        "Можно и списком: строки вида <code>номер ссылка</code>.\n"
        "Отдельная книга: <code>/book_link 12 https://…</code>")
    await _ask_next(message)


async def save_link(book_id: int, url: str) -> str:
    """Положить ссылку в ячейку того же магазина. Возвращает приписку.

    Ячеек две — под бумагу и под файл. Если прислали ссылку магазина,
    который уже записан, она заменяет его же; если нового — занимает
    свободную ячейку. Так проход по книгам не требует помнить, какая
    ссылка в какой ячейке лежит.
    """
    first, second = await database.book_links_by_id(book_id)
    shop = _shop_of(url)

    if first and _shop_of(first) == shop:
        place = False
    elif second and _shop_of(second) == shop:
        place = True
    elif not first:
        place = False
    elif not second:
        place = True
    else:
        # Обе заняты чужими магазинами: меняем вторую, первую бережём —
        # она заводилась раньше и, скорее всего, основная.
        place = True

    if not await database.set_book_link_slot(book_id, url, place):
        return None          # не сохранилось — врать «готово» нельзя
    other = second if not place else first
    if other and _shop_of(other) != shop:
        return f" · теперь две кнопки: {_shop_of(other)} и {shop}"
    return ""


async def _ready_link(raw: str):
    """(ссылка для кнопки, приписка для ответа).

    Обычный адрес книги заворачиваем в партнёрский сами. Партнёрскую
    ссылку, сделанную в кабинете, оставляем как есть — она уже готова.
    """
    if is_affiliate(raw):
        return raw, ""
    ready, shop = await affiliate(raw)
    if ready:
        return ready, f" и завернула в партнёрскую ссылку {shop}"
    if any(host in _host(raw) for host in SHOP_HOSTS):
        # Прямой адрес магазина, а завернуть не во что: денег такая
        # ссылка не принесёт, и молчать об этом нельзя.
        return raw, ("\n\n⚠️ Это обычная ссылка магазина, не партнёрская — "
                     "покупка по ней не засчитается. Задайте шаблон: "
                     "<code>/digest shop books</code>")
    return raw, ""


@router.message(F.text.regexp(r"^/book_link\s"))
async def book_link_one(message: Message):
    """Ссылка конкретной книге, без всякой сессии"""
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer(
            "Нужно так: <code>/book_link 12 https://…</code>\n"
            "Снять ссылку: <code>/book_link 12 нет</code>")
        return

    value = parts[2].strip()
    # Книга кончилась — ссылку снимаем, кнопка «Купить» просто исчезает.
    # Это лучше, чем вести читателя на «нет в наличии».
    if value.lower() in ("нет", "-", "off", "убрать"):
        ok = await database.set_book_link(int(parts[1]), "")
        await message.answer("✅ Ссылка снята — кнопки «Купить» у этой книги "
                             "больше нет" if ok else "❌ Книга не найдена")
        return

    if not value.startswith("http"):
        await message.answer("Это не похоже на ссылку.")
        return
    value, note = await _ready_link(value)
    placed = await save_link(int(parts[1]), value)
    await message.answer(("✅ Сохранила" + note + placed) if placed is not None
                         else "❌ Книга с таким номером не найдена")


@router.callback_query(F.data == "booklink_skip")
async def link_skip(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    # Кнопки под старыми сообщениями остаются нажимаемыми и после конца
    # сессии — без этой проверки нажатие начинало новый круг.
    if not await _mode_active(call.from_user.id):
        await call.answer("Сессия закончена. Начать заново: /book_links",
                          show_alert=True)
        return

    current = await database.get_setting(CURSOR_KEY)
    if (current or "").isdigit():
        await _skip_add(int(current))
    await call.answer("Пропустила")
    await _ask_next(call.message)


@router.callback_query(F.data == "booklink_stop")
async def link_stop(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await _mode_off()
    stats = await database.books_link_stats()
    await call.answer()
    await call.message.answer(
        f"Остановила. Со ссылками: {stats['done']} из {stats['total']}.\n"
        "Продолжить: <code>/book_links</code>")


@router.message(F.text.startswith("http"))
async def link_got(message: Message, state: FSMContext):
    """Голая ссылка от админа во время сессии ввода.

    Фильтр без состояния: сессия хранится в базе и переживает деплой.
    Вне сессии обработчик пропускает сообщение дальше, чтобы не мешать
    остальным разделам.
    """
    if not config.is_admin(message.from_user.id):
        raise SkipHandler
    # Идёт другой разговор — картина, место, обложка: там ссылку ждёт свой
    # обработчик, и перехватывать её нельзя.
    if await state.get_state():
        raise SkipHandler
    if not await _mode_active(message.from_user.id):
        # Молчать нельзя: человек присылает ссылку за ссылкой и не знает,
        # что сессия кончилась, — со стороны это выглядит как «бот больше
        # не просит книги».
        if await database.books_without_link():
            await message.answer(
                "Ссылку вижу, но сессия ввода закончилась — не знаю, какой "
                "книге её приписать.\n\n"
                "Продолжить с того же места: <code>/book_links</code>\n"
                "Конкретной книге: <code>/book_link 12 ссылка</code> "
                "(номера — <code>/book_links_show</code>)")
            return
        raise SkipHandler

    current = await database.get_setting(CURSOR_KEY)
    if not (current or "").isdigit():
        await _ask_next(message)
        return

    link, note = await _ready_link(message.text.strip())
    placed = await save_link(int(current), link)
    if placed is None:
        await message.answer("❌ Не сохранилась — книга не найдена")
    else:
        await _done_add(int(current))
        await message.answer("✅ Сохранила" + note + placed)
    await _ask_next(message)


@router.message(F.text.regexp(r"^\s*\d+\s+https?://"))
async def links_bulk(message: Message):
    """Списком: «12 https://…» построчно"""
    if not config.is_admin(message.from_user.id):
        raise SkipHandler
    saved, wrapped = 0, 0
    for line in message.text.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            link, note = await _ready_link(parts[1].strip())
            if note.startswith(" и завернула"):
                wrapped += 1
            if await save_link(int(parts[0]), link) is not None:
                saved += 1
    stats = await database.books_link_stats()
    await message.answer(
        f"Сохранила ссылок: {saved}"
        + (f", из них завернула в партнёрские: {wrapped}." if wrapped else ".")
        + f"\nВсего со ссылками: {stats['done']} из {stats['total']}.")


@router.message(F.text.startswith("/book_links_show"))
async def links_show(message: Message):
    """Что уже введено, а что нет — с номерами для /book_link"""
    if not config.is_admin(message.from_user.id):
        return
    every = await database.books_links_all()
    stats = await database.books_link_stats()

    lines = [f"🔗 Со ссылками: {stats['done']} из {stats['total']}", ""]
    if not every:
        lines.append("Книг пока нет.")
    for book_id, title, first, second in every[:60]:
        shops = [_shop_of(u) for u in (first, second) if u]
        mark = ", ".join(shops) if shops else "—"
        lines.append(f"<code>{book_id}</code> — {html.escape(title)}\n"
                     f"      {html.escape(mark)}")
    if every:
        lines += ["", "Заменить: <code>/book_link 12 https://…</code>",
                  "Снять: <code>/book_link 12 нет</code>",
                  "Пройти все подряд: <code>/book_links все</code>"]
    await message.answer("\n".join(lines))
