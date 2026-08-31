import logging
import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from datetime import datetime
import config
import database
import menu_texts
import inline_kb
import country_index
import fx_rates

router = Router()

NEWS_HEADER_TEXTS = {
    "ru": "📰 *Главное на {date}:*",
    "en": "📰 *Today's headlines ({date}):*",
    "fr": "📰 *À la une du {date} :*",
    "he": "📰 *הכותרות מתאריך {date}:*"
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
        if call.data == "tennis_live_matches":
            markup = inline_kb.get_tennis_live_action_menu(user_lang)
        else:
            markup = inline_kb.get_music_back_button(user_lang, "sport_tennis")
        await call.message.edit_media(media=InputMediaPhoto(media=config.TENNIS_BANNER, caption=caption_text, parse_mode="Markdown"), reply_markup=markup)
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

# Экран «tennis_shop_referral» переехал в shop.py: вместо статичного текста там
# теперь каталог по разделам «пол → тип вещи» с карточками товаров.

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


# ==========================================================
# ⛳ ЗАКРЫТЫЙ ГОЛЬФ-КАНАЛ: ССЫЛКА ВЫДАЁТСЯ ПО ПАРОЛЮ
# ==========================================================

# Пароль и ссылка живут в config: их удобнее менять переменными окружения,
# не трогая код, — пригласительные ссылки Telegram периодически истекают.
GOLF_PASSWORD = config.GOLF_PASSWORD
GOLF_INVITE_URL = config.GOLF_INVITE_URL


class GolfStates(StatesGroup):
    waiting_password = State()


GOLF_ASK_TEXTS = {
    "ru": "🔒 Вход в клуб по паролю. Введите его, чтобы получить ссылку, или нажмите «Отмена»:",
    "en": "🔒 The club is password-protected. Enter the password to get the invite link, or tap Cancel:",
    "fr": "🔒 L'accès au club est protégé par un mot de passe. Entrez-le pour obtenir le lien, ou annulez :",
    "he": "🔒 הכניסה למועדון מוגנת בסיסמה. הזינו אותה כדי לקבל קישור, או לחצו על ביטול:"
}

GOLF_WRONG_TEXTS = {
    "ru": "❌ Неверный пароль. Попробуйте ещё раз или нажмите «Отмена».",
    "en": "❌ Wrong password. Try again or tap Cancel.",
    "fr": "❌ Mot de passe incorrect. Réessayez ou annulez.",
    "he": "❌ סיסמה שגויה. נסו שוב או לחצו על ביטול."
}

GOLF_GRANTED_TEXTS = {
    "ru": ("✅ **Добро пожаловать!**\n\nВот ссылка на закрытый гольф-канал. "
           "Вступление подтверждается администратором, поэтому заявка какое-то время повисит на одобрении."),
    "en": ("✅ **Welcome!**\n\nHere is the link to the private golf channel. "
           "Membership is approved by an admin, so your request will sit pending for a little while."),
    "fr": ("✅ **Bienvenue !**\n\nVoici le lien vers le canal de golf privé. "
           "L'adhésion est validée par un administrateur, votre demande restera donc en attente un moment."),
    "he": ("✅ **ברוכים הבאים!**\n\nהנה הקישור לערוץ הגולף הסגור. "
           "ההצטרפות מאושרת על ידי מנהל, ולכן הבקשה תמתין לאישור זמן מה.")
}

GOLF_CANCEL_TEXTS = {"ru": "⛔ Отмена", "en": "⛔ Cancel", "fr": "⛔ Annuler", "he": "⛔ ביטול"}
GOLF_OPEN_TEXTS = {"ru": "⛳ Открыть канал", "en": "⛳ Open the channel",
                   "fr": "⛳ Ouvrir le canal", "he": "⛳ פתחו את הערוץ"}


def _golf_cancel_markup(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=GOLF_CANCEL_TEXTS.get(lang, GOLF_CANCEL_TEXTS["en"]), callback_data="golf_cancel"
    )]])


@router.callback_query(F.data == "golf_join_request")
async def ask_golf_password(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_lang = await database.get_user_language(call.from_user.id)
    await state.set_state(GolfStates.waiting_password)
    await state.update_data(golf_lang=user_lang)
    await call.message.answer(
        GOLF_ASK_TEXTS.get(user_lang, GOLF_ASK_TEXTS["en"]),
        reply_markup=_golf_cancel_markup(user_lang)
    )


@router.callback_query(F.data == "golf_cancel", GolfStates.waiting_password)
async def cancel_golf_password(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    user_lang = await database.get_user_language(call.from_user.id)
    caption_text = menu_texts.GOLF_MAIN_TEXTS.get(user_lang, menu_texts.GOLF_MAIN_TEXTS["en"])
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer_photo(
        photo=config.GOLF_BANNER, caption=caption_text,
        parse_mode="Markdown", reply_markup=inline_kb.get_golf_main_menu(user_lang)
    )


# ~F.text.startswith("/") обязателен, иначе состояние съест /start и выйти будет нечем
@router.message(GolfStates.waiting_password, F.text, ~F.text.startswith("/"))
async def check_golf_password(message: Message, state: FSMContext):
    data = await state.get_data()
    user_lang = data.get("golf_lang", "ru")

    expected = (await database.get_setting("golf_password", config.GOLF_PASSWORD) or "").strip().lower()
    if message.text.strip().lower() != expected:
        await message.answer(
            GOLF_WRONG_TEXTS.get(user_lang, GOLF_WRONG_TEXTS["en"]),
            reply_markup=_golf_cancel_markup(user_lang)
        )
        return

    await state.clear()
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=GOLF_OPEN_TEXTS.get(user_lang, GOLF_OPEN_TEXTS["en"]), url=GOLF_INVITE_URL)],
        [InlineKeyboardButton(
            text="⇦ Назад" if user_lang == "ru" else "⇦ Back", callback_data="sport_golf")]
    ])
    await message.answer(
        GOLF_GRANTED_TEXTS.get(user_lang, GOLF_GRANTED_TEXTS["en"]),
        parse_mode="Markdown", reply_markup=markup
    )

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
            content, fetched_at = await database.get_daily_news(sub)
            if content and fetched_at:
                try:
                    date_str = datetime.fromisoformat(fetched_at).strftime("%d.%m.%Y")
                except ValueError:
                    date_str = ""
                header = NEWS_HEADER_TEXTS.get(user_lang, NEWS_HEADER_TEXTS["en"]).format(date=date_str)
                news_message = f"{header}\n\n{content}"
            else:
                news_message = NEWS_EMPTY_TEXTS.get(user_lang, NEWS_EMPTY_TEXTS["en"])
            await call.message.answer(news_message, parse_mode="Markdown", disable_web_page_preview=True)

        # ROI-отчёты: живой сравнительный индекс четырёх стран вместо статичного текста
        if sub == "analytics":
            await call.message.answer(
                await country_index.render_index(user_lang),
                parse_mode="Markdown", disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                    text=fx_rates._t(fx_rates.BTN_RATES, user_lang),
                    callback_data="fx_rates")]])
            )
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")


# ==========================================================
# 🥎🏓 ПАДЕЛ И НАСТОЛЬНЫЙ ТЕННИС: ПРАВИЛА + ПОИСК ПАРТНЁРА
# ==========================================================

GITHUB_PAGES_BASE = "https://tstrukovars-a11y.github.io/my-portfolio-bot1"

def _build_partner_finder_markup(lang, sport_code, html_filename):
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
    web_app_url = f"{GITHUB_PAGES_BASE}/{html_filename}?sport={sport_code}"
    if render_url:
        web_app_url += f"&api={render_url}/api/partners"

    btn_text = "🤝 Найти партнёра для игры" if lang == "ru" else "🤝 Find a Playing Partner"
    back_text = "⇦ В главное меню" if lang == "ru" else "⇦ Main Menu"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, web_app=WebAppInfo(url=web_app_url))],
        [InlineKeyboardButton(text=back_text, callback_data="menu_sport")]
    ])

@router.callback_query(F.data == "sport_padel")
async def open_sport_padel(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.PADEL_MAIN_TEXTS.get(user_lang, menu_texts.PADEL_MAIN_TEXTS["en"])
        markup = _build_partner_finder_markup(user_lang, "padel", "padel_partners.html")
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.PADEL_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=markup
        )
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")

@router.callback_query(F.data == "sport_table_tennis")
async def open_sport_table_tennis(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
        caption_text = menu_texts.TABLE_TENNIS_MAIN_TEXTS.get(user_lang, menu_texts.TABLE_TENNIS_MAIN_TEXTS["en"])
        markup = _build_partner_finder_markup(user_lang, "table_tennis", "tt_partners.html")
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.TABLE_TENNIS_BANNER, caption=caption_text, parse_mode="Markdown"),
            reply_markup=markup
        )
    except TelegramBadRequest as e: logging.error(f"ОШИБКА БЛОКА 1: {e}")
