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

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

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
PAUSE = 1.2
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


async def _run(bot, chat: int, books, note: Message):
    new = edited = failed = 0
    for book_id, category, text, cover, msg_id in books:
        body = f"{SHELVES.get(category, '📚')}\n\n{(text or '').strip()}"
        try:
            if msg_id:
                try:
                    if cover:
                        await bot.edit_message_caption(
                            chat_id=chat, message_id=msg_id,
                            caption=body[:MAX_CAPTION], parse_mode=None)
                    else:
                        await bot.edit_message_text(
                            chat_id=chat, message_id=msg_id,
                            text=body[:MAX_MESSAGE], parse_mode=None)
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
                                                caption=body[:MAX_CAPTION], parse_mode=None)
                    await database.set_book_msg(book_id, sent.message_id)
                    edited += 1
            else:
                if cover:
                    sent = await bot.send_photo(chat, cover,
                                                caption=body[:MAX_CAPTION], parse_mode=None)
                else:
                    sent = await bot.send_message(chat, body[:MAX_MESSAGE], parse_mode=None)
                await database.set_book_msg(book_id, sent.message_id)
                new += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            failed += 1
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
