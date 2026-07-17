# handlers/block2_creative.py
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest
from anthropic import AsyncAnthropic

import config
import database
import menu_texts
import inline_kb

router = Router()
try:
    if config.ANTHROPIC_API_KEY and config.ANTHROPIC_API_KEY != "dummy_key":
        claude_client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    else:
        claude_client = None
except Exception as e:
    import logging
    logging.error(f"Ошибка инициализации Claude: {e}")
    claude_client = None

# =====================================================================
# 📑 СОСТОЯНИЯ МАШИНЫ СТАТУСОВ (FSM)
# =====================================================================
class ArtworkFormStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_year = State()
    waiting_for_substrate = State()
    waiting_for_paint = State()
    waiting_for_size = State()
    waiting_for_photo = State()
    waiting_for_format = State()
    waiting_for_price = State()

class AtelierB2BStates(StatesGroup):
    waiting_for_brand_name = State()
    waiting_for_link = State()
    waiting_for_audience = State()
    waiting_for_description = State()

# =====================================================================
# 🎨 НАВИГАЦИЯ: ГЛАВНЫЕ ЭКРАНЫ ТВОРЧЕСТВА И КАРТИН
# =====================================================================

@router.callback_query(F.data == "menu_creative")
async def open_creative(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption = menu_texts.CREATIVE_MENU_TEXTS.get(user_lang, menu_texts.CREATIVE_MENU_TEXTS["en"])
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.ART_BANNER, caption=caption, parse_mode="Markdown"),
            reply_markup=inline_kb.get_creative_menu(user_lang)
        )
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "creative_paintings")
async def open_creative_paintings(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.ART_MAIN_TEXTS.get(user_lang, menu_texts.ART_MAIN_TEXTS["en"])
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.ART_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=inline_kb.get_art_hub_main_menu(user_lang)
        )
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "art_my_portfolio")
async def open_art_portfolio(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.ART_MY_GALLERY_TEXTS.get(user_lang, menu_texts.ART_MY_GALLERY_TEXTS["en"])
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.ART_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=inline_kb.get_music_back_button(user_lang, "creative_paintings")
        )
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "art_subscriptions_prices")
async def open_art_subs(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.ART_MARKET_INFO_TEXTS.get(user_lang, menu_texts.ART_MARKET_INFO_TEXTS["en"])
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.ART_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=inline_kb.get_art_subs_markup(user_lang)
        )
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "art_exhibitions_calendar")
async def open_art_calendar(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.ART_EXHIBITIONS_TEXTS.get(user_lang, menu_texts.ART_EXHIBITIONS_TEXTS["en"])
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.ART_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=inline_kb.get_music_back_button(user_lang, "creative_paintings")
        )
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "art_start_application_form")
async def open_art_form_intro(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.ART_FORM_START_TEXTS.get(user_lang, menu_texts.ART_FORM_START_TEXTS["en"])
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.ART_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=inline_kb.get_art_form_trigger_markup(user_lang)
        )
    except TelegramBadRequest:
        pass

# =====================================================================
# 👗 НАВИГАЦИЯ БЛОКА АТЕЛЬЕ И FASHION DESIGN
# =====================================================================

@router.callback_query(F.data == "creative_atelier")
async def open_creative_atelier_main(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.ATELIER_MAIN_TEXTS.get(user_lang, menu_texts.ATELIER_MAIN_TEXTS["en"])
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.ART_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=inline_kb.get_creative_atelier_menu(user_lang)
        )
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "atelier_my_collection")
async def open_atelier_capsule(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.ATELIER_MY_CAPSULE_TEXTS.get(user_lang, menu_texts.ATELIER_MY_CAPSULE_TEXTS["en"])
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.ART_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=inline_kb.get_music_back_button(user_lang, "creative_atelier")
        )
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "atelier_fashion_history")
async def open_atelier_history(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.ATELIER_HISTORY_TEXTS.get(user_lang, menu_texts.ATELIER_HISTORY_TEXTS["en"])
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.ART_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=inline_kb.get_music_back_button(user_lang, "creative_atelier")
        )
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "atelier_b2b_integration_form")
async def open_atelier_b2b_intro(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.ATELIER_B2B_TEXTS.get(user_lang, menu_texts.ATELIER_B2B_TEXTS["en"])
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.ART_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=inline_kb.get_atelier_b2b_action_menu(user_lang)
        )
    except TelegramBadRequest:
        pass

# =====================================================================
# 🤝 FSM-СБОРЩИК: ЗАЯВКИ НА B2B ИНТЕГРАЦИЮ МОДНЫХ БРЕНДОВ
# =====================================================================

@router.callback_query(F.data == "atelier_fsm_b2b_initiate")
async def start_b2b_wizard(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_lang = await database.get_user_language(call.from_user.id)
    msg = "🤝 ШАГ 1: Введите НАЗВАНИЕ вашего fashion-бренда:" if user_lang == "ru" else "🤝 STEP 1: Enter the NAME of your fashion brand:"
    await call.message.answer(msg)
    await state.set_state(AtelierB2BStates.waiting_for_brand_name)

@router.message(AtelierB2BStates.waiting_for_brand_name, F.text)
async def process_brand_name(message: Message, state: FSMContext):
    await state.update_data(brand_name=message.text)
    user_lang = await database.get_user_language(message.from_user.id)
    msg = "🔗 ШАГ 2: Укажите ССЫЛКУ на ваш сайт или профиль магазина:" if user_lang == "ru" else "🔗 STEP 2: Provide a LINK to your website or profile:"
    await message.answer(msg)
    await state.set_state(AtelierB2BStates.waiting_for_link)

@router.message(AtelierB2BStates.waiting_for_link, F.text)
async def process_brand_link(message: Message, state: FSMContext):
    await state.update_data(link=message.text)
    user_lang = await database.get_user_language(message.from_user.id)
    msg = "🎯 ШАГ 3: Опишите вашу ЦЕЛЕВУЮ АУДИТОРИЮ:" if user_lang == "ru" else "🎯 STEP 3: Describe your TARGET AUDIENCE:"
    await message.answer(msg)
    await state.set_state(AtelierB2BStates.waiting_for_audience)

@router.message(AtelierB2BStates.waiting_for_audience, F.text)
async def process_brand_audience(message: Message, state: FSMContext):
    await state.update_data(audience=message.text)
    user_lang = await database.get_user_language(message.from_user.id)
    msg = "📝 ШАГ 4: Кратко опишите формат желаемой ИНТЕГРАЦИИ:" if user_lang == "ru" else "📝 STEP 4: Briefly describe the desired INTEGRATION format:"
    await message.answer(msg)
    await state.set_state(AtelierB2BStates.waiting_for_description)

@router.message(AtelierB2BStates.waiting_for_description, F.text)
async def process_brand_desc(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    user_lang = await database.get_user_language(message.from_user.id)
    
    summary = (
        f"✅ **Заявка на B2B-интеграцию успешно принята!**\n\n"
        f"• 🏢 **Бренд:** {data['brand_name']}\n"
        f"• 🔗 **Ссылка:** {data['link']}\n"
        f"• 🎯 **Аудитория:** {data['audience']}\n"
        f"• 📝 **Формат:** {message.text}\n\n"
        f"Я рассмотрю ваш бренд и свяжусь с вами в ближайшее время."
    ) if user_lang == "ru" else (
        f"✅ **B2B Integration request accepted!**\n\n"
        f"• 🏢 **Brand:** {data['brand_name']}\n"
        f"• 🔗 **Link:** {data['link']}\n"
        f"• 🎯 **Audience:** {data['audience']}\n"
        f"• 📝 **Format:** {message.text}"
    )
    await message.answer(summary)
    print(f"🔥 B2B FASHION ЗАЯВКА от @{message.from_user.username}: {data['brand_name']}")

# =====================================================================
# 🍳 КУЛИНАРИЯ: ВЫГРУЗКА РЕЦЕПТОВ С АВТОПЕРЕВОДОМ ЧЕРЕЗ CLAUDE AI
# =====================================================================

@router.callback_query(F.data == "creative_culinary")
async def open_creative_culinary_main(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.CULINARY_MAIN_TEXTS.get(user_lang, menu_texts.CULINARY_MAIN_TEXTS["en"])
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.ART_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=inline_kb.get_creative_culinary_menu(user_lang)
        )
    except TelegramBadRequest:
        pass

async def fetch_and_send_recipes(call: CallbackQuery, category_key: str):
    user_lang = await database.get_user_language(call.from_user.id)

    rows = await database.get_recipes(category_key, limit=3)
            
    if not rows:
        empty_txt = menu_texts.CULINARY_EMPTY_TEXTS.get(user_lang, menu_texts.CULINARY_EMPTY_TEXTS["en"])
        await call.message.answer(empty_txt)
        return

    need_translation = user_lang != "ru"

    for row in rows:
        text, video_id, link = row
        final_text = text
        
        if need_translation and claude_client is not None:
            await call.message.bot.send_chat_action(chat_id=call.message.chat.id, action="typing")
            try:
                lang_names = {"en": "English", "fr": "French", "he": "Hebrew"}
                target_language = lang_names.get(user_lang, "English")
                
                response = await claude_client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=800,
                    system=f"You are a professional culinary translator. Translate the following recipe text strictly into {target_language}. Maintain the emojis, formatting, and ingredient structure. Do not add any conversational text or introduction, return ONLY the direct translation.",
                    messages=[{"role": "user", "content": text}]
                )
                final_text = response.content[0].text
            except Exception as e:
                print(f"⚠️ Ошибка автоперевода Claude: {e}")
        
        caption = f"{final_text}\n\n🔗 Original: {link}" if link else final_text
        
        if video_id:
            await call.message.answer_video(video=video_id, caption=caption)
        else:
            await call.message.answer(caption)

@router.callback_query(F.data == "culinary_view_breakfasts")
async def view_breakfasts_recipes(call: CallbackQuery):
    await call.answer()
    await fetch_and_send_recipes(call, "breakfasts")

@router.callback_query(F.data == "culinary_view_mains")
async def view_mains_recipes(call: CallbackQuery):
    await call.answer()
    await fetch_and_send_recipes(call, "mains")

@router.callback_query(F.data == "culinary_view_desserts")
async def view_desserts_recipes(call: CallbackQuery):
    await call.answer()
    await fetch_and_send_recipes(call, "desserts")

# =====================================================================
# 🤖 РОБОТ-АВТОМАТИЗАТОР: МОНИТОРИНГ КАНАЛА
# =====================================================================
@router.channel_post()
async def auto_listen_culinary_channel(message: Message):
    text_to_check = message.text or message.caption or ""
    hashtag_map = {"#завтраки": "breakfasts", "#горячее": "mains", "#десерты": "desserts"}
    
    detected_category = None
    for hashtag, cat_name in hashtag_map.items():
        if hashtag in text_to_check.lower():
            detected_category = cat_name
            break
            
    if detected_category:
        video_id = message.video.file_id if message.video else None
        extracted_link = None
        if message.entities:
            for entity in message.entities:
                if entity.type == "url":
                    extracted_link = text_to_check[entity.offset:entity.offset + entity.length]
                    break
        
        await database.add_recipe(detected_category, text_to_check, video_id, extracted_link)
        print(f"🍏 АВТО-СИНХРОНИЗАЦИЯ: Добавлен лот категории {detected_category}!")

# =====================================================================
# 🎨 FSM-СБОРЩИК: АНКЕТА КАРТИНЫ ХУДОЖНИКА (ИСПРАВЛЕНА СТРУКТУРА)
# =====================================================================
@router.callback_query(F.data == "art_fsm_initiate_flow")
async def start_artwork_wizard(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_lang = await database.get_user_language(call.from_user.id)
    await call.message.answer("🎨 ШАГ 1: Введите НАЗВАНИЕ вашей картины:" if user_lang == "ru" else "🎨 STEP 1: Enter the TITLE:")
    await state.set_state(ArtworkFormStates.waiting_for_title)

@router.message(ArtworkFormStates.waiting_for_title, F.text)
async def process_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    user_lang = await database.get_user_language(message.from_user.id)
    await message.answer("📅 ШАГ 2: Укажите ГОД создания картины:" if user_lang == "ru" else "📅 STEP 2: Enter the YEAR:")
    await state.set_state(ArtworkFormStates.waiting_for_year)

@router.message(ArtworkFormStates.waiting_for_year, F.text)
async def process_year(message: Message, state: FSMContext):
    await state.update_data(year=message.text)
    user_lang = await database.get_user_language(message.from_user.id)
    await message.answer("📐 ШАГ 3: Укажите МАТЕРИАЛ ПОДЛОЖКИ:" if user_lang == "ru" else "📐 STEP 3: Enter the SUBSTRATE:")
    await state.set_state(ArtworkFormStates.waiting_for_substrate)

@router.message(ArtworkFormStates.waiting_for_substrate, F.text)
async def process_substrate(message: Message, state: FSMContext):
    await state.update_data(substrate=message.text)
    user_lang = await database.get_user_language(message.from_user.id)
    await message.answer("🖌 ШАГ 4: Укажите ТИП КРАСКИ:" if user_lang == "ru" else "🖌 STEP 4: Enter the TYPE of paint:")
    await state.set_state(ArtworkFormStates.waiting_for_paint)

@router.message(ArtworkFormStates.waiting_for_paint, F.text)
async def process_paint(message: Message, state: FSMContext):
    await state.update_data(paint=message.text)
    user_lang = await database.get_user_language(message.from_user.id)
    await message.answer("📏 ШАГ 5: Введите точный РАЗМЕР картины:" if user_lang == "ru" else "📏 STEP 5: Enter the exact DIMENSIONS:")
    await state.set_state(ArtworkFormStates.waiting_for_size)

@router.message(ArtworkFormStates.waiting_for_size, F.text)
async def process_size(message: Message, state: FSMContext):
    await state.update_data(size=message.text)
    user_lang = await database.get_user_language(message.from_user.id)
    await message.answer("📸 ШАГ 6: ЗАГРУЗИТЕ ИЗОБРАЖЕНИЕ (отправьте как фото):" if user_lang == "ru" else "📸 STEP 6: UPLOAD an image:")
    await state.set_state(ArtworkFormStates.waiting_for_photo)

@router.message(ArtworkFormStates.waiting_for_photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    user_lang = await database.get_user_language(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏛 Только Выставка" if user_lang == "ru" else "🏛 Exhibition Only", callback_data="form_format_exh")],
        [InlineKeyboardButton(text="💰 Продажа" if user_lang == "ru" else "💰 For Sale", callback_data="form_format_sale")]
    ])
    await message.answer("🎯 ШАГ 7: Выберите формат размещения лота:" if user_lang == "ru" else "🎯 STEP 7: Select format:", reply_markup=kb)
    await state.set_state(ArtworkFormStates.waiting_for_format)

@router.callback_query(ArtworkFormStates.waiting_for_format, F.data == "form_format_exh")
async def format_exh_click(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_lang = await database.get_user_language(call.from_user.id)
    data = await state.get_data()
    await state.clear()
    summary = f"✅ **Заявка принята!**\n• 🖼 Название: {data['title']}\n• Формат: Выставка" if user_lang == "ru" else f"✅ **Application generated!**\n• Title: {data['title']}\n• Format: Exhibition"
    await call.message.answer_photo(photo=data['photo_id'], caption=summary, parse_mode="Markdown")

@router.callback_query(ArtworkFormStates.waiting_for_format, F.data == "form_format_sale")
async def format_sale_click(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_lang = await database.get_user_language(call.from_user.id)
    await call.message.answer("💰 Введите СТОИМОСТЬ продажи картины:" if user_lang == "ru" else "💰 Enter the SALE PRICE:")
    await state.set_state(ArtworkFormStates.waiting_for_price)

@router.message(ArtworkFormStates.waiting_for_price, F.text)
async def process_price_final(message: Message, state: FSMContext):
    price_val = message.text
    data_inner = await state.get_data()
    await state.clear()
    user_lang_i = await database.get_user_language(message.from_user.id)
    
    summary_sale = f"✅ **Заявка на продажу создана!**\n• 🖼 Название: {data_inner['title']}\n• 💵 Цена: {price_val}" if user_lang_i == "ru" else f"✅ **Sale created!**\n• Title: {data_inner['title']}\n• Price: {price_val}"
    await message.answer_photo(photo=data_inner['photo_id'], caption=summary_sale, parse_mode="Markdown")
