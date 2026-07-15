import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest
import config
import database
import menu_texts
import inline_kb

router = Router()

NEWS_HEADER_TEXTS = {
    "ru": "📰 *Главное на сегодня:*",
    "en": "📰 *Today's headlines:*",
    "fr": "📰 *À la une aujourd'hui :*",
    "he": "📰 *הכותרות של היום:*"
}
NEWS_EMPTY_TEXTS = {
    "ru": "Свежие новости появятся здесь в течение суток после запуска бота.",
    "en": "Fresh headlines will appear here within a day of the bot going live.",
    "fr": "Les dernières actualités apparaîtront ici dans les 24h suivant le démarrage du bot.",
    "he": "כותרות טריות יופיעו כאן תוך יממה מהפעלת הבוט."
}

@router.callback_query(F.data == "menu_sport")
async def open_sport(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption = menu_texts.SPORT_MENU_TEXTS.get(user_lang, menu_texts.SPORT_MENU_TEXTS["en"])
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.SPORT_BANNER, caption=caption, parse_mode="Markdown"),
            reply_markup=inline_kb.get_sport_menu(user_lang)
        )
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data == "sport_music")
async def open_sport_music(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.MUSIC_MAIN_TEXTS.get(user_lang, menu_texts.MUSIC_MAIN_TEXTS["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.MUSIC_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_music_main_menu(user_lang))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data == "music_my_perf")
async def open_music_my_performance(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.MUSIC_MY_PERFORMANCE.get(user_lang, menu_texts.MUSIC_MY_PERFORMANCE["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.MUSIC_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_music_back_button(user_lang, "sport_music"))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data == "music_composers_hub")
async def open_music_composers_hub(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.MUSIC_COMPOSERS_LIST.get(user_lang, menu_texts.MUSIC_COMPOSERS_LIST["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.MUSIC_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_composers_grid_menu(user_lang))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data.startswith("comp_detail_"))
async def open_composer_biography(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        composer_key = call.data.split("_")[-1]
        data_dict = menu_texts.COMPOSER_DETAILS.get(composer_key, {})
        caption_text = data_dict.get(user_lang, data_dict.get("en", "Biography error..."))
        await call.message.edit_media(media=InputMediaPhoto(media=config.MUSIC_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_music_back_button(user_lang, "music_composers_hub"))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data == "sport_travel")
async def open_sport_travel(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.TRAVEL_MAIN_TEXTS.get(user_lang, menu_texts.TRAVEL_MAIN_TEXTS["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.TRAVEL_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_travel_main_menu(user_lang))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data.in_(["travel_geography", "travel_toolkit"]))
async def open_travel_sub(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        txt_source = menu_texts.TRAVEL_GEOGRAPHY_TEXTS if call.data == "travel_geography" else menu_texts.TRAVEL_TOOLKIT_TEXTS
        caption_text = txt_source.get(user_lang, txt_source["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.TRAVEL_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_travel_back_button(user_lang, "sport_travel"))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")
@router.callback_query(F.data == "sport_tennis")
async def open_sport_tennis(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.TENNIS_MAIN_TEXTS.get(user_lang, menu_texts.TENNIS_MAIN_TEXTS["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.TENNIS_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_tennis_main_menu(user_lang))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data.in_(["tennis_geography", "tennis_live_matches"]))
async def open_tennis_sub(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        txt_source = menu_texts.TENNIS_GEO_TEXTS if call.data == "tennis_geography" else menu_texts.TENNIS_LIVE_TEXTS
        caption_text = txt_source.get(user_lang, txt_source["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.TENNIS_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_music_back_button(user_lang, "sport_tennis"))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data == "tennis_shop_referral")
async def open_tennis_shop(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.TENNIS_SHOP_TEXTS.get(user_lang, menu_texts.TENNIS_SHOP_TEXTS["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.TENNIS_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_tennis_shop_action_menu(user_lang))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data == "tennis_premium_theory")
async def open_tennis_theory(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.TENNIS_THEORY_TEXTS.get(user_lang, menu_texts.TENNIS_THEORY_TEXTS["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.TENNIS_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_tennis_pay_action_menu(user_lang))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data == "tennis_buy_subscription")
async def process_tennis_sub(call: CallbackQuery):
    user_lang = await database.get_user_language(call.from_user.id)
    await call.answer(text="💰 Интеграция..." if user_lang == "ru" else "💰 Integration...", show_alert=True)

@router.callback_query(F.data == "sport_horse")
async def open_sport_horse(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.HORSE_MAIN_TEXTS.get(user_lang, menu_texts.HORSE_MAIN_TEXTS["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.HORSE_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_horse_main_menu(user_lang))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data == "horse_riding_experience")
async def open_horse_riding(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.HORSE_RIDING_TEXTS.get(user_lang, menu_texts.HORSE_RIDING_TEXTS["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.HORSE_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_music_back_button(user_lang, "sport_horse"))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data == "horse_racing_analytics")
async def open_horse_analytics(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.HORSE_RACING_TEXTS.get(user_lang, menu_texts.HORSE_RACING_TEXTS["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.HORSE_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_horse_channel_action_menu(user_lang))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data == "horse_ai_bot_market")
async def open_horse_robot(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.HORSE_ROBOT_TEXTS.get(user_lang, menu_texts.HORSE_ROBOT_TEXTS["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.HORSE_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_horse_bot_action_menu(user_lang))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data == "horse_buy_robot_click")
async def process_horse_robot(call: CallbackQuery):
    user_lang = await database.get_user_language(call.from_user.id)
    await call.answer(text="💳 Перенаправление..." if user_lang == "ru" else "💳 Redirecting...", show_alert=True)

@router.callback_query(F.data == "sport_golf")
async def open_sport_golf(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.GOLF_MAIN_TEXTS.get(user_lang, menu_texts.GOLF_MAIN_TEXTS["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.GOLF_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_golf_main_menu(user_lang))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data.in_(["golf_rules", "golf_places"]))
async def open_golf_sub(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        txt_source = menu_texts.GOLF_RULES_TEXTS if call.data == "golf_rules" else menu_texts.GOLF_PLACES_TEXTS
        caption_text = txt_source.get(user_lang, txt_source["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.GOLF_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_music_back_button(user_lang, "sport_golf"))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data == "golf_join_community")
async def open_golf_community(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.GOLF_COMMUNITY_TEXTS.get(user_lang, menu_texts.GOLF_COMMUNITY_TEXTS["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.GOLF_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_golf_join_action_menu(user_lang))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data == "golf_submit_form_click")
async def process_golf_submit(call: CallbackQuery):
    user_lang = await database.get_user_language(call.from_user.id)
    msgs = {"ru": "🎉 Заявка отправлена!", "en": "🎉 Submitted!", "fr": "🎉 Envoyée!", "he": "🎉 הבקשה נשלחה!"}
    await call.answer(text=msgs.get(user_lang, msgs["en"]), show_alert=True)

@router.callback_query(F.data == "sport_news")
async def open_sport_news(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.NEWS_MAIN_TEXTS.get(user_lang, menu_texts.NEWS_MAIN_TEXTS["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.NEWS_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_news_main_menu(user_lang))
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data.startswith("news_sub_"))
async def open_news_sub(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        sub = call.data.split("_")[-1]
        keys = {"ru": menu_texts.NEWS_RU_TEXTS, "il": menu_texts.NEWS_IL_TEXTS, "fr": menu_texts.NEWS_FR_TEXTS, "us": menu_texts.NEWS_US_TEXTS, "analytics": menu_texts.NEWS_ANALYTICS_TEXTS}
        txt_source = keys.get(sub, menu_texts.NEWS_US_TEXTS)
        caption_text = txt_source.get(user_lang, txt_source["en"])
        await call.message.edit_media(media=InputMediaPhoto(media=config.NEWS_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=inline_kb.get_music_back_button(user_lang, "sport_news"))

        # Живые заголовки за сегодня (обновляются фоновой задачей раз в сутки)
        if sub in {"ru", "il", "fr", "us"}:
            content, _ = await database.get_daily_news(sub)
            header = NEWS_HEADER_TEXTS.get(user_lang, NEWS_HEADER_TEXTS["en"])
            if content:
                news_message = f"{header}\n\n{content}"
            else:
                news_message = NEWS_EMPTY_TEXTS.get(user_lang, NEWS_EMPTY_TEXTS["en"])
            await call.message.answer(news_message, parse_mode="Markdown", disable_web_page_preview=True)
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")
