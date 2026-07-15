# handlers/block3_intellect.py
import aiosqlite
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
    await call.answer()
    user_id = call.from_user.id
    user_lang = await database.get_user_language(user_id)
    
    # 🔒 Проверка Premium-подписки в базе данных перед выдачей контента
    has_premium = await database.check_subscription(user_id)
    if not has_premium:
        # Тексты-уведомления об ограничении доступа на 4 языках
        limit_warnings = {
            "ru": "⚠️ **Раздел Premium-доступ**\n\nЭтот подблок содержит научные исследования, чек-листы и защищенные материалы. Пожалуйста, оформите подписку для продолжения.",
            "en": "⚠️ **Premium Access Only**\n\nThis subsection contains research data, check-lists, and locked assets. Please buy a subscription to proceed.",
            "fr": "⚠️ **Accès Premium Uniquement**\n\nCette sous-section contient des données de recherche et des fiches pratiques. Veuillez vous abonner pour continuer.",
            "he": "⚠️ **גישת פריмиיום בלבד**\n\nתת-סעיף זה מכיל נתוני מחקר, צ'ק-ליסטים וחומרים מוגנים. אנא רכוש מנוי כדי להמשיך."
        }
        caption_limit = limit_warnings.get(user_lang, limit_warnings["en"])
        
        # Подгружаем правильные 4-язычные тарифные сетки (Все на месте)
        if user_lang == "ru": current_pay_markup = inline_kb.get_claude_pay_menu(user_lang)
        elif user_lang == "fr": current_pay_markup = inline_kb.get_claude_pay_menu(user_lang)
        elif user_lang == "he": current_pay_markup = inline_kb.get_claude_pay_menu(user_lang)
        else: current_pay_markup = inline_kb.get_claude_pay_menu(user_lang)
            
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.CLOD_BANNER, caption=caption_limit, parse_mode="Markdown"),
            reply_markup=current_pay_markup
        )
        return

    try:
        caption_text = menu_texts.GENETICS_MAIN_TEXTS.get(user_lang, menu_texts.GENETICS_MAIN_TEXTS["en"])
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.GENETICS_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=inline_kb.get_genetics_hub_menu(user_lang)
        )
    except TelegramBadRequest:
        pass

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



# ==========================================================
# 🧩 ПОДБЛОК: ГОЛОВОЛОМКА
# ==========================================================
@router.callback_query(F.data == "intellect_puzzle")
async def open_menu_intellect_puzzle(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.PUZZLE_MENU_TEXTS.get(user_lang, menu_texts.PUZZLE_MENU_TEXTS["en"])
        
        puzzle_actions_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧩 Решать задачи" if user_lang == "ru" else "🧩 Solve Puzzles", callback_data="start_solving_puzzles")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_diary")]
        ])
        
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.PUZZLE_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=puzzle_actions_menu
        )
    except TelegramBadRequest:
        pass


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
        
    async with aiosqlite.connect(database.DB_PATH) as db:
        async with db.execute(
            "SELECT text_content, cover_file_id FROM books WHERE category = ? ORDER BY id DESC LIMIT 3", 
            (category_key,)
        ) as cursor:
            rows = await cursor.fetchall()
            
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
                        model="claude-3-5-sonnet-20241022",
                        max_tokens=1000,
                        system=f"You are an expert executive editor. Translate this book review precisely into {lang_names.get(user_lang, 'English')}. Keep all headers, book structure, emojis, and specific business terminology. Do not add any intros, output only the translation.",
                        messages=[{"role": "user", "content": text}]
                    )
                    final_text = response.content.text
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
@router.channel_post()
async def auto_listen_books_channel(message: Message):
    text_to_check = message.text or message.caption or ""
    hashtag_map = {"#бизнес": "business", "#кругозор": "horizon", "#полезное": "tools"}
    
    detected_category = None
    for hashtag, cat_name in hashtag_map.items():
        if hashtag in text_to_check.lower():
            detected_category = cat_name
            break
            
    if detected_category:
        cover_id = message.photo[-1].file_id if message.photo else None
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "INSERT INTO books (category, text_content, cover_file_id) VALUES (?, ?, ?)",
                (detected_category, text_to_check, cover_id)
            )
            await db.commit()
        print(f"📚 АВТО-БИБЛИОТЕКА: Добавлен новый лот книги в категорию {detected_category}!")


# =====================================================================
# 🧩 СИМУЛЯТОР КВИЗОВ-ГОЛОВОЛОМОК (ОСТАВЛЕН БЕЗ ИЗМЕНЕНИЙ)
# =====================================================================
async def channel_puzzles(message: Message, user_id: int):
    async with aiosqlite.connect(database.DB_PATH) as db:
        async with db.execute("""
            SELECT poll_id, message_id FROM quizzes 
            WHERE poll_id NOT IN (SELECT poll_id FROM user_answers WHERE user_id = ?)
            ORDER BY message_id ASC LIMIT 1
        """, (user_id,)) as cursor:
            row = await cursor.fetchone()
            
    if not row:
        no_puzzles_texts = {
            "ru": "🎉 **Все доступные задачи решены!** Загляните позже за новыми головоломками.",
            "en": "🎉 **All available puzzles are solved!** Check back later for new challenges.",
            "fr": "🎉 **Tous les puzzles disponibles sont résolus !** Revenez plus tard.",
            "he": "🎉 **כל החידות הזמינות נפתרו!** בדוק שוב מאוחר יותר."
        }
        btn_stop_texts = {"ru": "🛑 Вернуться в Дневник", "en": "🛑 Back to Diary", "fr": "🛑 Retour au Journal", "he": "🛑 חזרה ליומן"}
        lang = await database.get_user_language(user_id)
        exit_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn_stop_texts.get(lang, btn_stop_texts["en"]), callback_data="menu_diary")]])
        await message.answer(text=no_puzzles_texts.get(lang, no_puzzles_texts["en"]), reply_markup=exit_markup, parse_mode="Markdown")
        return

    poll_id, message_id = row
    try:
        await message.bot.forward_message(chat_id=message.chat.id, from_chat_id=config.QUIZ_CHANNEL, message_id=message_id)
        lang = await database.get_user_language(user_id)
        btn_next = {"ru": "➡ Следующая задача", "en": "➡ Next Puzzle", "fr": "➡ Puzzle Suivant", "he": "➡ החידה הבאה"}
        btn_stop = {"ru": "🛑 Вернуться в Дневник", "en": "🛑 Back to Diary", "fr": "🛑 Retour au Journal", "he": "🛑 חזרה ליומן"}
        
        control_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_next.get(lang, btn_next["en"]), callback_data="puzzle_next")],
            [InlineKeyboardButton(text=btn_stop.get(lang, btn_stop["en"]), callback_data="puzzle_stop")]
        ])
        instruction = {
            "ru": "▲ **Новая задача.** Ответьте на встроенный опрос выше и нажмите кнопку управления:",
            "en": "▲ **New puzzle.** Answer the built-in poll above and use the control button:",
            "fr": "▲ **Nouveau puzzle.** Répondez au sondage ci-dessus et utilisez le bouton :",
            "he": "▲ **חידה חדשה.** ענה על הסקר למעלה והשתמש בכפתור השליטה:"
        }
        await message.answer(instruction.get(lang, instruction["en"]), reply_markup=control_menu, parse_mode="Markdown")
    except Exception as e:
        print(f"Ошибка пересылки опроса из канала: {e}")

@router.callback_query(F.data == "start_solving_puzzles")
async def inbound_puzzle_click(call: CallbackQuery):
    user_id = call.from_user.id
    user_lang = await database.get_user_language(user_id)
    alert_texts = {"ru": "Загружаю тренажер... 🧩", "en": "Loading trainer... 🧩", "fr": "Chargement...", "he": "טוען... 🧩"}
    await call.answer(alert_texts.get(user_lang, alert_texts["en"]))
    try:
        await call.message.delete()
    except Exception:
        pass
    await channel_puzzles(message=call.message, user_id=user_id)

@router.callback_query(F.data == "puzzle_next")
async def process_puzzle_next(call: CallbackQuery):
    user_id = call.from_user.id
    try:
        await call.message.delete()
    except Exception:
        pass
    await channel_puzzles(message=call.message, user_id=user_id)

@router.callback_query(F.data == "puzzle_stop")
async def process_puzzle_stop(call: CallbackQuery):
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass
    user_lang = await database.get_user_language(call.from_user.id)
    caption_text = menu_texts.DIARY_MENU_TEXTS.get(user_lang, menu_texts.DIARY_MENU_TEXTS["en"])
    current_markup = inline_kb.get_diary_menu(user_lang) if user_lang == "ru" else (inline_kb.get_diary_menu(user_lang) if user_lang == "fr" else (inline_kb.get_diary_menu(user_lang) if user_lang == "he" else inline_kb.get_diary_menu(user_lang)))
    await call.message.answer_photo(photo=config.MAIN_BANNER, caption=caption_text, reply_markup=current_markup, parse_mode="Markdown")
