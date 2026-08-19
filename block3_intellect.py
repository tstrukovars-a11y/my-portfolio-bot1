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

# 🧬 3.1 Экран: База
@router.callback_query(F.data == "genetics_view_base")
async def open_genetics_base(call: CallbackQuery):
    await call.answer()
    try:
        user_id = call.from_user.id
        user_lang = await database.get_user_language(user_id)
        caption_text = menu_texts.GENETICS_BASE_TEXTS.get(user_lang, menu_texts.GENETICS_BASE_TEXTS["en"])
        back_markup = get_back_markup(user_lang, "intellect_genetics")
        
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.GENETICS_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=back_markup
        )
    except TelegramBadRequest:
        pass

# 🧬 3.2 Экран: Продвинутый
@router.callback_query(F.data == "genetics_view_advanced")
async def open_genetics_advanced(call: CallbackQuery):
    await call.answer()
    try:
        user_id = call.from_user.id
        user_lang = await database.get_user_language(user_id)
        caption_text = menu_texts.GENETICS_ADVANCED_TEXTS.get(user_lang, menu_texts.GENETICS_ADVANCED_TEXTS["en"])
        back_markup = get_back_markup(user_lang, "intellect_genetics")
        
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.GENETICS_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=back_markup
        )
    except TelegramBadRequest:
        pass

# 🧬 3.3 Экран: Научные исследования и новости
@router.callback_query(F.data == "genetics_view_research")
async def open_genetics_research(call: CallbackQuery):
    await call.answer()
    try:
        user_id = call.from_user.id
        user_lang = await database.get_user_language(user_id)
        caption_text = menu_texts.GENETICS_RESEARCH_TEXTS.get(user_lang, menu_texts.GENETICS_RESEARCH_TEXTS["en"])
        back_markup = get_back_markup(user_lang, "intellect_genetics")
        
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.GENETICS_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=back_markup
        )
    except TelegramBadRequest:
        pass



# Раздел «Головоломка» целиком переехал в puzzles.py: там банк задач из канала,
# случайный порядок, итоговый балл, повторные прохождения и статистика.


# ==========================================================
# 📚 ПОДБЛОК: МОЯ БИБЛИОТЕКА (ГЛАВНЫЙ ЭКРАН ПОЛКИ)
# ==========================================================
@router.callback_query(F.data == "intellect_books")
async def open_menu_intellect_books(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.BOOKS_MENU_TEXTS.get(user_lang, menu_texts.BOOKS_MENU_TEXTS["en"])
        
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.BOOKS_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=inline_kb.get_books_shelf_menu(user_lang)
        )
    except TelegramBadRequest:
        pass

# Умный движок выгрузки книг с защитой от повторных кликов и летучим переводом Claude
async def fetch_and_send_books(call: CallbackQuery, category_key: str):
    user_id = call.from_user.id
    user_lang = await database.get_user_language(user_id)
    
    # ЗАЩИТА: Если пользователь уже нажал кнопку и Claude переводит — игнорируем повторный клик
    if user_id in processing_users:
        return
        
    rows = await database.get_books(category_key, limit=3)
            
    if not rows:
        empty_texts = {
            "ru": "📚 На этой полке пока пусто. Скоро я опубликую новый обзор в канале!",
            "en": "📚 This shelf is empty for now. I will post a new review in the channel soon!",
            "fr": "📚 Cette étagère est vide. Un nouvel examen sera publié bientôt !",
            "he": "📚 המדף הזה ריק בינתיים. בקרוב אפרסם סקירה חדשה בערוץ!"
        }
        await call.message.answer(empty_texts.get(user_lang, empty_texts["en"]))
        return

    # Включаем лок пользователя
    processing_users.add(user_id)
    need_translation = user_lang != "ru"

    # Выводим красивый статус загрузки перевода
    if need_translation:
        load_msgs = {
            "en": "⏳ Translating review via Claude AI...",
            "fr": "⏳ Traduction de l'examen via Claude AI...",
            "he": "⏳ מתרגם סקירה באמצעות Claude AI..."
        }
        await call.message.answer(load_msgs.get(user_lang, load_msgs["en"]))

    from handlers.block2_creative import claude_client

    try:
        for row in rows:
            text, cover_id = row
            final_text = text
            
            if need_translation:
                try:
                    lang_names = {"en": "English", "fr": "French", "he": "Hebrew"}
                    response = await claude_client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=1000,
                        system=f"You are an expert executive editor. Translate this book review precisely into {lang_names.get(user_lang, 'English')}. Keep all headers, book structure, emojis, and specific business terminology. Do not add any intros, output only the translation.",
                        messages=[{"role": "user", "content": text}]
                    )
                    final_text = response.content[0].text
                except Exception as e:
                    print(f"⚠️ Ошибка Claude: {e}")

            if cover_id:
                await call.message.answer_photo(photo=cover_id, caption=final_text, parse_mode="Markdown")
            else:
                await call.message.answer(final_text, parse_mode="Markdown")
    finally:
        # ОБЯЗАТЕЛЬНО СНИМАЕМ БЛОКИРОВКУ ПОСЛЕ ЗАВЕРШЕНИЯ ЦИКЛА
        processing_users.discard(user_id)

@router.callback_query(F.data == "books_view_business")
async def view_business_books(call: CallbackQuery):
    await call.answer()
    await fetch_and_send_books(call, "business")

@router.callback_query(F.data == "books_view_horizon")
async def view_horizon_books(call: CallbackQuery):
    await call.answer()
    await fetch_and_send_books(call, "horizon")

@router.callback_query(F.data == "books_view_tools")
async def view_tools_books(call: CallbackQuery):
    await call.answer()
    await fetch_and_send_books(call, "tools")


# =====================================================================
# 🤖 СЛУШАТЕЛЬ КАНАЛА ОБЗОРОВ КНИГ (АВТОМАТИЧЕСКАЯ СБОРКА)
# =====================================================================
# ВАЖНО: #полезное здесь быть не должно — он закреплён за кулинарией. Хэштеги
# книг и рецептов обязаны не пересекаться: сборщик рецептов отрабатывает раньше
# и забрал бы такой пост себе, а до библиотеки он бы просто не дошёл.
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
