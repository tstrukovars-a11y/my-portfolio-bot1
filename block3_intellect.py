# handlers/block3_intellect.py
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

import config
import database  # Использование единой базы данных для хранения подписок и языков
import menu_texts
import inline_kb

router = Router()

# Вспомогательная функция для генерации мультиязычной кнопки возврата
def get_back_markup(lang: str, target_callback: str) -> InlineKeyboardMarkup:
    back_texts = {
        "ru": "⇦ Назад",
        "en": "⇦ Back",
        "fr": "⇦ Retour",
        "he": "חזרה ⇦"
    }
    text = back_texts.get(lang, back_texts["en"])
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=text, callback_data=target_callback)
    ]])

# ==========================================================
# 🧠 ГЛАВНЫЙ ЭКРАН: БЛОК 3 ИНТЕЛЛЕКТ И КАРЬЕРА
# ==========================================================
@router.callback_query(F.data == "menu_intellect")
async def open_intellect(call: CallbackQuery):
    await call.answer()
    try:
        user_id = call.from_user.id
        user_lang = await database.get_user_language(user_id)
        caption_text = menu_texts.INTELLECT_MENU_TEXTS.get(user_lang, menu_texts.INTELLECT_MENU_TEXTS["en"])
        
        if user_lang == "ru":
            current_markup = inline_kb.get_intellect_menu(user_lang)
        elif user_lang == "en":
            current_markup = inline_kb.get_intellect_menu(user_lang)
        elif user_lang == "fr":
            current_markup = inline_kb.get_intellect_menu(user_lang)
        else:
            current_markup = inline_kb.get_intellect_menu(user_lang)

        await call.message.edit_media(
            media=InputMediaPhoto(media=config.SCIENCE_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=current_markup
        )
    except TelegramBadRequest:
        pass


# ==========================================================
# 📖 ПОДБЛОК: ДНЕВНИК ДИРЕКТОРА (ГЛАВНЫЙ ЭКРАН)
# ==========================================================
@router.callback_query(F.data == "menu_diary")
async def open_diary_main_screen(call: CallbackQuery):
    await call.answer()
    try:
        user_id = call.from_user.id
        user_lang = await database.get_user_language(user_id)
        caption_text = menu_texts.DIARY_MENU_TEXTS.get(user_lang, menu_texts.DIARY_MENU_TEXTS["en"])
        
        if user_lang == "ru":
            current_markup = inline_kb.get_diary_menu(user_lang)
        elif user_lang == "en":
            current_markup = inline_kb.get_diary_menu(user_lang)
        elif user_lang == "fr":
            current_markup = inline_kb.get_diary_menu(user_lang)
        else:
            current_markup = inline_kb.get_diary_menu(user_lang)

        await call.message.edit_media(
            media=InputMediaPhoto(media=config.MAIN_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=current_markup
        )
    except TelegramBadRequest:
        pass


# ==========================================================
# 🏭 КЕЙСЫ ДНЕВНИКА СЕО (БЕСПЛАТНЫЙ ПРОГРЕВ)
# ==========================================================
@router.callback_query(F.data == "diary_business")
async def open_diary_business(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    user_lang = await database.get_user_language(user_id)
    back_markup = get_back_markup(user_lang, "menu_diary")

    try:
        await call.message.edit_media(
            media=InputMediaPhoto(
                media=config.MAIN_BANNER, 
                caption=menu_texts.DIARY_BUSINESS_TEXTS.get(user_lang, menu_texts.DIARY_BUSINESS_TEXTS["en"]), 
                parse_mode="Markdown"
            ),
            reply_markup=back_markup
        )
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "diary_engineering")
async def open_diary_engineering(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    user_lang = await database.get_user_language(user_id)
    back_markup = get_back_markup(user_lang, "menu_diary")

    try:
        await call.message.edit_media(
            media=InputMediaPhoto(
                media=config.MAIN_BANNER, 
                caption=menu_texts.DIARY_ENGINEERING_TEXTS.get(user_lang, menu_texts.DIARY_ENGINEERING_TEXTS["en"]), 
                parse_mode="Markdown"
            ),
            reply_markup=back_markup
        )
    except TelegramBadRequest:
        pass


# ==========================================================
# 🧬 ПОДБЛОК: ГЕНЕТИКА (ЗАКРЫТ ПЛАТНОЙ ПОДПИСКОЙ)
# ==========================================================
@router.callback_query(F.data == "intellect_genetics")
async def open_menu_intellect_genetics(call: CallbackQuery):
    """Раздел открыт для всех: платной осталась только услуга — заказ
    исследования или расшифровки, он живёт на отдельной кнопке."""
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.GENETICS_MAIN_TEXTS.get(user_lang, menu_texts.GENETICS_MAIN_TEXTS["en"])
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.GENETICS_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=inline_kb.get_genetics_hub_menu(user_lang)
        )
    except TelegramBadRequest:
        # Список глав приходит текстовым сообщением, а в текст картинку не
        # вставить. Раньше ошибка молча глоталась и «Назад» не работал.
        await call.message.answer_photo(
            photo=config.GENETICS_BANNER, caption=caption_text,
            parse_mode="Markdown", reply_markup=inline_kb.get_genetics_hub_menu(user_lang)
        )

# Экраны «Базовый контур», «Продвинутый уровень» и «Исследования & Новости»
# убраны: содержимое покрыто базой знаний канала и лентой новостей
# генетики, а сами экраны стояли пустыми.

# ==========================================================
# 📚 ПОДБЛОК: МОЯ БИБЛИОТЕКА (ГЛАВНЫЙ ЭКРАН ПОЛКИ)
# ==========================================================
@router.callback_query(F.data == "intellect_books")
async def open_menu_intellect_books(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.BOOKS_MENU_TEXTS.get(user_lang, menu_texts.BOOKS_MENU_TEXTS["en"])
        counts = await database.book_counts()
        total = sum(counts.values())
        if total:
            caption_text += f"\n\nВсего книг: {total}"

        await call.message.edit_media(
            media=InputMediaPhoto(media=config.BOOKS_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=inline_kb.get_books_shelf_menu(user_lang, counts)
        )
    except TelegramBadRequest:
        pass

# Умный движок выгрузки книг с защитой от повторных кликов и летучим переводом Claude
SHELF_TITLES = {"business": "📈 Бизнес и лидерство",
                "horizon": "🔭 Кругозор и наука",
                "tools": "🛠 Инструменты"}


async def show_shelf(call: CallbackQuery, category: str):
    """Список названий вместо трёх книг подряд.

    Раньше полка отдавала первые три книги отдельными сообщениями — из
    двенадцати. Остальные девять существовали только в базе, и добавлять
    книги не имело смысла: их всё равно никто не видел.
    """
    lang = await database.get_user_language(call.from_user.id)
    books = await database.book_titles(category)
    if not books:
        await call.message.answer("📚 На этой полке пока пусто.")
        await call.answer()
        return

    rows = [[InlineKeyboardButton(text=title, callback_data=f"bookopen_{bid}")]
            for bid, title in books]
    rows.append([InlineKeyboardButton(text=inline_kb.label(inline_kb.BACK_TEXTS, lang),
                                      callback_data="intellect_books")])
    await call.message.edit_caption(
        caption=f"{SHELF_TITLES.get(category, '📚')}\n\nКниг: {len(books)}. Выберите:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()


@router.callback_query(F.data.startswith("bookopen_"))
async def open_book(call: CallbackQuery):
    try:
        book_id = int(call.data.rsplit("_", 1)[1])
    except ValueError:
        await call.answer()
        return
    row = await database.get_book_by_id(book_id)
    if not row:
        await call.answer("Книга не найдена", show_alert=True)
        return
    text, cover = row
    lang = await database.get_user_language(call.from_user.id)
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=inline_kb.label(inline_kb.BACK_TEXTS, lang),
                             callback_data="intellect_books")]])
    # parse_mode=None: текст пришёл из канала и разметкой не является
    if cover:
        await call.message.answer_photo(cover, caption=(text or "")[:1024],
                                        parse_mode=None, reply_markup=markup)
    else:
        await call.message.answer((text or "")[:4096], parse_mode=None,
                                  reply_markup=markup)
    await call.answer()


@router.callback_query(F.data == "books_view_business")
async def view_business_books(call: CallbackQuery):
    await show_shelf(call, "business")


@router.callback_query(F.data == "books_view_horizon")
async def view_horizon_books(call: CallbackQuery):
    await show_shelf(call, "horizon")


@router.callback_query(F.data == "books_view_tools")
async def view_tools_books(call: CallbackQuery):
    await show_shelf(call, "tools")


BOOK_HASHTAGS = {"#бизнес": "business", "#кругозор": "horizon", "#инструменты": "tools"}


def _is_book_post(message: Message) -> bool:
    """Без этого фильтра хендлер матчил любой пост канала — и сам никогда не
    срабатывал, потому что сборщик рецептов в block2 перехватывал всё раньше."""
    if not config.channel_allowed(config.BOOKS_CHANNEL, message.chat.id):
        return False
    text = (message.text or message.caption or "").lower()
    return any(tag in text for tag in BOOK_HASHTAGS)


@router.channel_post(_is_book_post)
async def auto_listen_books_channel(message: Message):
    text_to_check = message.text or message.caption or ""
    hashtag_map = BOOK_HASHTAGS
    
    detected_category = None
    for hashtag, cat_name in hashtag_map.items():
        if hashtag in text_to_check.lower():
            detected_category = cat_name
            break
            
    if detected_category:
        cover_id = message.photo[-1].file_id if message.photo else None
        await database.add_book(detected_category, text_to_check, cover_id)
        print(f"📚 АВТО-БИБЛИОТЕКА: Добавлен новый лот книги в категорию {detected_category}!")


# Старый движок головоломок (пересылка опросов из канала по одному, без
# подсчёта баллов) удалён — его заменил puzzles.py.
