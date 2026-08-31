# books_seed.py — книжная полка из готового списка.
#
# Список написан и выверен вручную, а не сгенерирован: у моделей книги
# путаются авторами, и одна такая ошибка в канале для предпринимателей
# стоит дороже, чем весь выигрыш во времени.
#
# Обложки — только настоящие, их подгружает владелец. Сгенерированная
# обложка существующей книги вводит в заблуждение так же, как выдуманная
# фотография настоящего места.
import html
import json
import logging
import os

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

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
