# book_find.py — читатель ищет книгу сам.
#
# В подборке «Акцента» три десятка книг, а спрашивают и то, чего в ней
# нет. Раньше такому человеку ответить было нечем: своя ссылка есть
# только у книг из подборки.
#
# Здесь он называет книгу — любую — и получает кнопки магазинов с той же
# партнёрской ссылкой, что стоит под постами. Магазинного API для этого
# не нужно: партнёрский шаблон умеет подставлять поисковый запрос, и
# кнопка ведёт на страницу поиска магазина по названию.
#
# Ссылка партнёрская, значит это реклама: пометка с erid идёт в то же
# сообщение, а не прячется внутри адреса.
import html
import logging
import time

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.dispatcher.event.bases import SkipHandler

import database
import digest
import links

router = Router()

ASK_KEY = "findbook_waiting"     # кто сейчас называет книгу
ASK_MINUTES = 20
MIN_QUERY = 3
MAX_QUERY = 80

ASK_TEXT = ("🔍 <b>Какую книгу ищете?</b>\n\n"
            "Напишите название или автора — найду, где купить.\n\n"
            "<i>Например: Атомные привычки, Канеман, метод помидора</i>")


async def _ask_on(user_id: int):
    await database.set_setting(
        ASK_KEY, f"{user_id}:{int(time.time()) + ASK_MINUTES * 60}")


async def _ask_off():
    await database.set_setting(ASK_KEY, "")


async def _ask_active(user_id: int) -> bool:
    raw = await database.get_setting(ASK_KEY) or ""
    try:
        who, until = raw.split(":")
        return int(who) == user_id and int(until) > time.time()
    except ValueError:
        return False


async def _shop_buttons(query: str, own: str = ""):
    """Кнопки магазинов для запроса. own — своя ссылка книги, если есть."""
    row = []
    if own:
        row.append(InlineKeyboardButton(text=digest._shop_label(own), url=own))
    for label, template in await digest._shop_templates("books"):
        url = digest._shop_url(template, query, "books")
        text = label or digest._shop_label(url)
        if any(text == b.text for b in row):
            continue
        row.append(InlineKeyboardButton(text=text, url=url))
    if not row:
        return None
    # Через свой счётчик — как и кнопки под постами: иначе половина
    # переходов окажется невидимой в /clicks.
    return [InlineKeyboardButton(
        text=b.text, url=links.wrap(b.url, "find", query[:60])) for b in row]


async def _marks(buttons) -> str:
    """Пометки о рекламе — по одной на магазин, без повторов"""
    found = [await digest._ad_mark(links.unwrap(b.url)) for b in buttons]
    return "\n".join(dict.fromkeys(m for m in found if m))


async def search(message: Message, query: str):
    query = " ".join((query or "").split())[:MAX_QUERY]
    if len(query) < MIN_QUERY:
        await message.answer("Слишком коротко — напишите хотя бы три буквы.")
        return

    await _ask_off()
    found = await database.search_books(query)
    lines = [f"🔍 <b>{html.escape(query)}</b>", ""]

    # Сначала своя подборка: если книга у нас есть, читателю полезнее
    # увидеть её с нашей же ссылкой, чем чужой поиск.
    own_link, own_title = "", ""
    if found:
        _, own_title, own_link = found[0]
        lines.append("Есть в подборке «Акцента»:")
        lines.append(f"<b>{html.escape(own_title)}</b>")
        for _, title, _ in found[1:]:
            lines.append(f"· {html.escape(title)}")
        lines.append("")
    else:
        lines.append("В подборке такой книги нет — посмотрим в магазинах.")
        lines.append("")

    buttons = await _shop_buttons(own_title or query, own_link)
    if not buttons:
        # Магазин не настроен: врать кнопкой «купить», которая никуда не
        # ведёт, хуже, чем сказать прямо.
        await message.answer(
            "\n".join(lines) + "Магазин пока не подключён — "
            "напишите владельцу канала.")
        return

    marks = await _marks(buttons)
    if marks:
        lines.append(marks)

    await message.answer(
        "\n".join(lines).strip(),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            buttons,
            [InlineKeyboardButton(text="🔍 Искать другую",
                                  callback_data="findbook_more")]]),
        disable_web_page_preview=True)


@router.message(F.text.regexp(r"^/start\s+findbook"))
async def start_find(message: Message):
    """Пришёл из канала по кнопке поиска.

    Роутер стоит раньше общего /start, поэтому в конце передаём ход
    дальше: человек мог оказаться здесь впервые, и приветствие с выбором
    языка ему всё равно нужно.
    """
    await _ask_on(message.from_user.id)
    await message.answer(ASK_TEXT)
    raise SkipHandler


@router.message(F.text.regexp(r"^/(книга|книгу|найти|book|find)\b"))
async def find_command(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        await search(message, parts[1])
        return
    await _ask_on(message.from_user.id)
    await message.answer(ASK_TEXT)


@router.callback_query(F.data == "findbook_more")
async def more(call: CallbackQuery):
    await call.answer()
    await _ask_on(call.from_user.id)
    await call.message.answer(ASK_TEXT)


@router.message(F.text & ~F.text.startswith("/"))
async def maybe_title(message: Message, state: FSMContext):
    """Название книги — но только когда мы сами о нём спросили.

    Иначе обработчик перехватывал бы любую фразу в боте: тут ходят и
    ответы на головоломки, и ссылки на книги от владельца.
    """
    if await state.get_state():
        raise SkipHandler
    if not await _ask_active(message.from_user.id):
        raise SkipHandler
    text = (message.text or "").strip()
    if len(text) > MAX_QUERY:
        raise SkipHandler
    try:
        await search(message, text)
    except Exception as e:
        logging.error(f"Поиск книги не удался: {e}")
        await message.answer("Не получилось поискать. Попробуйте ещё раз: "
                             "<code>/книга название</code>")
