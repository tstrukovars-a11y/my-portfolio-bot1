# handlers/block2_creative.py
import logging

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
import translator

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
    """Живая галерея вместо статичного текста: работы, цены, заявка."""
    await call.answer()
    import art_shop
    await art_shop.show_gallery(call)

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

PAGE_SIZE = 15

LIST_HEADER = {
    "ru": "👇 Выберите рецепт из списка:",
    "en": "👇 Choose a recipe from the list:",
    "fr": "👇 Choisissez une recette dans la liste :",
    "he": "👇 בחר מתכון מהרשימה:"
}

LIST_HEADER_PAGED = {
    "ru": "👇 Выберите рецепт — страница {page} из {pages}, всего {total}:",
    "en": "👇 Choose a recipe — page {page} of {pages}, {total} in total:",
    "fr": "👇 Choisissez une recette — page {page} sur {pages}, {total} au total :",
    "he": "👇 בחרו מתכון — עמוד {page} מתוך {pages}, סה\"כ {total}:"
}


async def build_recipe_list(user_lang: str, category_key: str, page: int = 0):
    """Собирает страницу алфавитного списка рецептов: (текст, клавиатура).

    Возвращает (None, None), если в категории пока пусто.
    """
    total = await database.count_recipes(category_key)
    if not total:
        return None, None

    pages = max(1, -(-total // PAGE_SIZE))     # округление вверх
    page = max(0, min(page, pages - 1))

    rows = await database.get_recipe_titles(
        category_key, limit=PAGE_SIZE, offset=page * PAGE_SIZE
    )

    buttons = []
    for recipe_id, title in rows:
        label = (title or "Рецепт").strip()
        if len(label) > 60:
            label = label[:57].rstrip() + "…"
        buttons.append([InlineKeyboardButton(
            text=label, callback_data=f"rv_{category_key}_{page}_{recipe_id}"
        )])

    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="⬅", callback_data=f"culpage_{category_key}_{page - 1}"
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{pages}", callback_data="noop"
        ))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(
                text="➡", callback_data=f"culpage_{category_key}_{page + 1}"
            ))
        buttons.append(nav)

    back_text = "🔙 Назад" if user_lang == "ru" else "🔙 Back"
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="creative_culinary")])

    if pages > 1:
        header = LIST_HEADER_PAGED.get(user_lang, LIST_HEADER_PAGED["en"]).format(
            page=page + 1, pages=pages, total=total
        )
    else:
        header = LIST_HEADER.get(user_lang, LIST_HEADER["en"])

    return header, InlineKeyboardMarkup(inline_keyboard=buttons)


async def show_recipe_list(call: CallbackQuery, category_key: str):
    user_lang = await database.get_user_language(call.from_user.id)
    header, markup = await build_recipe_list(user_lang, category_key, page=0)

    if header is None:
        empty_txt = menu_texts.CULINARY_EMPTY_TEXTS.get(user_lang, menu_texts.CULINARY_EMPTY_TEXTS["en"])
        await call.message.answer(empty_txt)
        return

    await call.message.answer(header, reply_markup=markup)


@router.callback_query(F.data == "noop")
async def ignore_page_counter(call: CallbackQuery):
    """Счётчик страниц — не кнопка, но Telegram ждёт ответа на любое нажатие"""
    await call.answer()


@router.callback_query(F.data.startswith("culpage_"))
async def turn_recipe_page(call: CallbackQuery):
    await call.answer()
    _, category_key, page = call.data.split("_", 2)
    user_lang = await database.get_user_language(call.from_user.id)
    header, markup = await build_recipe_list(user_lang, category_key, page=int(page))

    if header is None:
        return
    try:
        await call.message.edit_text(header, reply_markup=markup)
    except TelegramBadRequest:
        await call.message.answer(header, reply_markup=markup)


@router.callback_query(F.data.startswith("rv_"))
async def view_single_recipe(call: CallbackQuery):
    await call.answer()
    user_lang = await database.get_user_language(call.from_user.id)

    # rv_<категория>_<страница>_<id>: категория и страница нужны, чтобы кнопка
    # «К списку» вернула ровно на ту страницу, с которой рецепт открыли.
    try:
        _, category_key, page, raw_id = call.data.split("_", 3)
        recipe_id = int(raw_id)
    except ValueError:
        return

    recipe = await database.get_recipe_by_id(recipe_id)
    if not recipe:
        return

    text, video_id, link, photo_id = recipe
    final_text = text

    # Перевод кэшируется в базе: раньше он заказывался заново при каждом
    # открытии рецепта, а лимит в 800 токенов обрывал длинные тексты.
    if translator.needs_translation(user_lang):
        await call.message.bot.send_chat_action(chat_id=call.message.chat.id, action="typing")
        final_text = await translator.translate("recipe", recipe_id, "body", user_lang, text)

    caption = f"{final_text}\n\n🔗 Original: {link}" if link else final_text

    back_texts = {"ru": "🔙 К списку", "en": "🔙 Back to list",
                  "fr": "🔙 Retour à la liste", "he": "🔙 חזרה לרשימה"}
    back = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=back_texts.get(user_lang, back_texts["en"]),
        callback_data=f"culpage_{category_key}_{page}"
    )]])

    # Подпись к медиа в Telegram ограничена 1024 символами, обычное сообщение —
    # 4096. Длинный рецепт с картинкой шлём двумя сообщениями, иначе Telegram
    # отклонит отправку целиком. Кнопка возврата — всегда на последнем.
    if video_id or photo_id:
        if len(caption) <= 1024:
            if video_id:
                await call.message.answer_video(video=video_id, caption=caption,
                                                parse_mode=None, reply_markup=back)
            else:
                await call.message.answer_photo(photo=photo_id, caption=caption,
                                                parse_mode=None, reply_markup=back)
        else:
            if video_id:
                await call.message.answer_video(video=video_id)
            else:
                await call.message.answer_photo(photo=photo_id)
            await call.message.answer(caption, parse_mode=None, reply_markup=back)
    else:
        await call.message.answer(caption, parse_mode=None, reply_markup=back)

@router.callback_query(F.data == "culinary_cat_video")
async def view_video_recipes(call: CallbackQuery):
    await call.answer()
    await show_recipe_list(call, "video")

@router.callback_query(F.data == "culinary_cat_recipes")
async def view_recipes_category(call: CallbackQuery):
    await call.answer()
    await show_recipe_list(call, "recipes")

@router.callback_query(F.data == "culinary_cat_useful")
async def view_useful_recipes(call: CallbackQuery):
    await call.answer()
    await show_recipe_list(call, "useful")

# =====================================================================
# 🤖 РОБОТ-АВТОМАТИЗАТОР: МОНИТОРИНГ КАНАЛА
# =====================================================================
# Порядок значим: «#рецепты» — часть слова «#видеорецепты», поэтому длинный
# хэштег обязан проверяться первым, иначе видеорецепты уедут в обычные рецепты.
CULINARY_HASHTAGS = {"#видеорецепты": "video", "#рецепты": "recipes", "#полезное": "useful"}


def _is_culinary_post(message: Message) -> bool:
    """Фильтр обязателен: без него хендлер матчил ЛЮБОЙ пост канала и,
    отработав первым, глушил сборщики книг и головоломок."""
    if not config.channel_allowed(config.CULINARY_CHANNEL, message.chat.id):
        return False
    text = (message.text or message.caption or "").lower()
    return any(tag in text for tag in CULINARY_HASHTAGS)


def detect_culinary_category(message: Message):
    """Категория рецепта по хэштегу в тексте или подписи поста"""
    text = (message.text or message.caption or "").lower()
    for hashtag, category in CULINARY_HASHTAGS.items():
        if hashtag in text:
            return category
    return None


def extract_recipe(message: Message) -> dict:
    """Вытаскивает из поста всё, что нужно рецепту: текст, видео, фото, ссылку.

    Ссылку ищем и в entities, и в caption_entities: у постов с видео или фото
    разметка лежит именно во второй, поэтому раньше ссылки на видеорецептах и
    в разделе «Полезное» терялись. Учитываем и text_link — ссылку, спрятанную
    под текстом: её адрес хранится в самой сущности, а не в тексте поста.
    """
    text = message.text or message.caption or ""

    link = None
    for entity in list(message.entities or []) + list(message.caption_entities or []):
        if entity.type == "text_link" and entity.url:
            link = entity.url
            break
        if entity.type == "url":
            # extract_from, а не срез по offset: Telegram считает смещения в
            # кодовых единицах UTF-16, и каждое эмодзи перед ссылкой сдвигало
            # срез — из «https://…» получалось «ttps://…».
            link = entity.extract_from(text)
            break

    first_line = text.strip().split("\n")[0].strip()
    title = first_line if first_line and not first_line.startswith("#") else "Рецепт"
    if len(title) > 60:
        title = title[:57].rstrip() + "…"

    return {
        "text": text,
        "title": title,
        "video_id": message.video.file_id if message.video else None,
        "photo_id": message.photo[-1].file_id if message.photo else None,
        "link": link,
    }


def recipe_source_key(message: Message) -> str:
    """Отпечаток исходного поста, чтобы одна и та же публикация не задвоилась.

    У пересланного сообщения берём координаты оригинала, у поста в канале —
    его собственные.
    """
    # Начиная с Bot API 7.0 источник пересылки лежит в forward_origin, а старые
    # поля forward_from_chat Telegram больше не заполняет. Читаем сначала новое,
    # затем прежнее — иначе один и тот же пост, пересланный дважды, считался бы
    # разными рецептами.
    origin = getattr(message, "forward_origin", None)
    if origin is not None:
        origin_chat = getattr(origin, "chat", None)
        origin_id = getattr(origin, "message_id", None)
        if origin_chat is not None and origin_id is not None:
            return f"{origin_chat.id}:{origin_id}"

    legacy = getattr(message, "forward_from_chat", None)
    if legacy is not None:
        legacy_id = getattr(message, "forward_from_message_id", None) or message.message_id
        return f"{legacy.id}:{legacy_id}"

    return f"{message.chat.id}:{message.message_id}"


@router.channel_post(_is_culinary_post)
async def auto_listen_culinary_channel(message: Message):
    category = detect_culinary_category(message)
    if not category:
        return

    data = extract_recipe(message)
    result = await database.add_recipe(
        category, data["title"], data["text"], data["video_id"],
        data["link"], data["photo_id"], recipe_source_key(message)
    )
    if result == "added":
        logging.info(f"🍏 АВТО-СИНХРОНИЗАЦИЯ: добавлен рецепт категории {category}")

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


# =====================================================================
# 📥 ИМПОРТ РЕЦЕПТОВ ПЕРЕСЫЛКОЙ (только для владельца бота)
# =====================================================================
# Историю канала Bot API читать не умеет, поэтому уже опубликованные рецепты
# попадают в бота только так: админ пересылает посты в личку.

CATEGORY_TITLES = {
    "video": "🎬 Видеорецепты",
    "recipes": "📖 Рецепты",
    "useful": "💪 Полезное",
}


class RecipeImportStates(StatesGroup):
    collecting = State()
    choosing_category = State()


def _category_markup() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=title, callback_data=f"imp_cat_{key}")]
            for key, title in CATEGORY_TITLES.items()]
    rows.append([InlineKeyboardButton(text="⏭ Пропустить пост", callback_data="imp_cat_skip")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _import_summary() -> str:
    parts = []
    for key, title in CATEGORY_TITLES.items():
        parts.append(f"{title}: <b>{await database.count_recipes(key)}</b>")
    return " · ".join(parts)


@router.message(F.text == "/recipes")
async def recipes_import_start(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return

    await state.set_state(RecipeImportStates.collecting)
    await message.answer(
        "🍳 <b>Режим импорта рецептов включён.</b>\n\n"
        f"Сейчас в базе — {await _import_summary()}\n\n"
        "Пересылайте сюда посты из кулинарного канала: по одному или пачкой. "
        "Категорию я определяю по хэштегу:\n"
        "• <code>#видеорецепты</code> → Видеорецепты\n"
        "• <code>#рецепты</code> → Рецепты\n"
        "• <code>#полезное</code> → Полезное\n\n"
        "Если хэштега в посте нет, спрошу категорию кнопками.\n\n"
        "Когда закончите — отправьте /recipes_done"
    )


@router.message(F.text == "/recipes_done", RecipeImportStates.collecting)
@router.message(F.text == "/recipes_done", RecipeImportStates.choosing_category)
async def recipes_import_stop(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(f"✅ Импорт завершён. В базе — {await _import_summary()}")


async def _save_imported(message: Message, category: str, source: Message) -> str:
    data = extract_recipe(source)
    result = await database.add_recipe(
        category, data["title"], data["text"], data["video_id"],
        data["link"], data["photo_id"], recipe_source_key(source)
    )

    marks = []
    if data["video_id"]:
        marks.append("видео")
    if data["photo_id"]:
        marks.append("фото")
    if data["link"]:
        marks.append("ссылка")
    extra = f" ({', '.join(marks)})" if marks else ""

    if result == "added":
        return (f"✅ <b>{CATEGORY_TITLES[category]}</b>{extra}\n"
                f"«{data['title']}»\n\nВ базе — {await _import_summary()}")
    if result == "duplicate":
        return f"↩️ Этот пост уже импортирован. В базе — {await _import_summary()}"

    detail = result.split(":", 1)[1] if result.startswith("error:") else "причина неизвестна"
    return f"⚠️ Рецепт не сохранён.\n\n<code>{detail[:600]}</code>"


# ~F.text.startswith("/") обязателен: без него хендлер съедал бы /start и любую
# другую команду, а пользователь оставался бы заперт в режиме импорта.
@router.message(RecipeImportStates.collecting, F.text | F.caption, ~F.text.startswith("/"))
async def recipes_import_post(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return

    category = detect_culinary_category(message)
    if category:
        await message.answer(await _save_imported(message, category, message))
        return

    # Хэштега нет — спрашиваем категорию и запоминаем сам пост, чтобы потом
    # разобрать его целиком: пересланное сообщение в состоянии не сохранить.
    await state.set_state(RecipeImportStates.choosing_category)
    await state.update_data(pending_message_id=message.message_id)
    _pending_posts[message.from_user.id] = message

    preview = (message.text or message.caption or "").strip().split("\n")[0][:60]
    await message.answer(
        f"❓ В посте «{preview}» нет знакомого хэштега.\n\nВ какой раздел его положить?",
        reply_markup=_category_markup()
    )


# Пересланный пост целиком нужен, чтобы достать из него видео, фото и ссылку.
# FSM-хранилище держит только простые значения, поэтому держим объект рядом.
_pending_posts: dict[int, Message] = {}


@router.callback_query(F.data.startswith("imp_cat_"), RecipeImportStates.choosing_category)
async def recipes_import_choose_category(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        return
    await call.answer()

    choice = call.data.removeprefix("imp_cat_")
    source = _pending_posts.pop(call.from_user.id, None)
    await state.set_state(RecipeImportStates.collecting)

    if choice == "skip" or source is None:
        await call.message.edit_text("⏭ Пост пропущен. Пересылайте следующий.")
        return

    await call.message.edit_text(await _save_imported(call.message, choice, source))


@router.message(RecipeImportStates.collecting, ~F.text.startswith("/"))
async def recipes_import_hint(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    await message.answer(
        "В этом посте нет ни текста, ни подписи — сохранять нечего. "
        "Перешлите пост с текстом или отправьте /recipes_done, чтобы выйти."
    )


# =====================================================================
# МУЗЫКА
#
# Переехала сюда из спортивного блока: игра на инструменте — творчество,
# а не спорт, и в разделе о теннисе и гольфе она стояла не на месте.
# Обработчики перенесены вместе с кнопкой, иначе код остался бы жить
# там, откуда раздел уже ушёл.
# =====================================================================

@router.callback_query(F.data == "creative_music")
async def open_music(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.MUSIC_MAIN_TEXTS.get(user_lang, menu_texts.MUSIC_MAIN_TEXTS["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.MUSIC_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_music_main_menu(user_lang))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА МУЗЫКИ: {e}")

@router.callback_query(F.data == "music_my_perf")
async def open_music_my_performance(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.MUSIC_MY_PERFORMANCE.get(user_lang, menu_texts.MUSIC_MY_PERFORMANCE["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.MUSIC_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_music_back_button(user_lang, "creative_music"))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА МУЗЫКИ: {e}")

@router.callback_query(F.data == "music_composers_hub")
async def open_music_composers_hub(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.MUSIC_COMPOSERS_LIST.get(user_lang, menu_texts.MUSIC_COMPOSERS_LIST["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.MUSIC_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_composers_grid_menu(user_lang))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА МУЗЫКИ: {e}")

@router.callback_query(F.data.startswith("comp_detail_"))
async def open_composer_biography(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        composer_key = call.data.split("_")[-1]
        data_dict = menu_texts.COMPOSER_DETAILS.get(composer_key, {})
        caption_text = data_dict.get(user_lang, data_dict.get("en", "Biography error..."))
        await call.message.edit_media(media=InputMediaPhoto(media=config.MUSIC_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_music_back_button(user_lang, "music_composers_hub"))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА МУЗЫКИ: {e}")
