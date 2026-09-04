# block6_vpn.py
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import common
import config
import database
import menu_texts
import inline_kb

router = Router()

# Пароль задаётся переменной окружения VPN_PASSWORD (см. config)
VPN_PASSWORD = config.VPN_PASSWORD

class VPNStates(StatesGroup):
    waiting_password = State()

VPN_TEXTS = {
    "ru": "🔌 **Цифровой суверенитет: Надежный Premium VPN**\n\nВ современных реалиях безопасный доступ к глобальным enterprise-системам, зарубежным ИИ-сервисам и международным базам данных — это критическая необходимость для бизнеса.\n\nЯ использую и рекомендую проверенный высокоскоростной VPN с защитой от блокировок. Нажмите на кнопку ниже, чтобы активировать вашу персональную скидку: 👇",
    "en": "🔌 **Digital Sovereignty: Fast Premium VPN Service**\n\nSecure access to global enterprise tools, international AI models, and cloud infrastructure data vectors is an absolute necessity for modern business orchestration.\n\nI personally utilize and recommend a verified high-velocity VPN network. Click the button below to activate your premium discount: 👇",
    "fr": "🔌 **Souveraineté Numérique : Service VPN Premium**\n\nL'accès sécurisé aux infrastructures cloud et aux outils mondiaux est une nécessité absolue. J'utilise et recommande un réseau VPN rapide. Cliquez ci-dessous pour activer votre remise : 👇",
    "he": "🔌 **ריבונות דיגיטלית: שירות VPN פרימיום מהיר**\n\nגישה מאובטחת לכלי עבודה גלובליים, מודלים של בינה מלאכותית ותשתיות ענן היא כורח המציאות בעולם העסקים המודרני. אני ממליצה על רשת VPN מהירה ומאומתת. לחץ על הכפתור למטה כדי להפעיל את הנחת הפרימיום שלך: 👇"
}

PASSWORD_PROMPT_TEXTS = {
    "ru": "🔒 Этот раздел закрыт паролем. Введите пароль, чтобы продолжить, или нажмите «Отмена»:",
    "en": "🔒 This section is password-protected. Enter the password to continue, or tap Cancel:",
    "fr": "🔒 Cette section est protégée par un mot de passe. Entrez le mot de passe, ou appuyez sur Annuler :",
    "he": "🔒 מדור זה מוגן בסיסמה. הזן את הסיסמה כדי להמשיך, או לחץ על ביטול:"
}

WRONG_PASSWORD_TEXTS = {
    "ru": "❌ Неверный пароль. Попробуйте ещё раз, или нажмите «Отмена».",
    "en": "❌ Wrong password. Please try again, or tap Cancel.",
    "fr": "❌ Mot de passe incorrect. Réessayez, ou appuyez sur Annuler.",
    "he": "❌ סיסמה שגויה. נסה שוב, או לחץ על ביטול."
}

CANCEL_TEXTS = {
    "ru": "⛔ Отмена",
    "en": "⛔ Cancel",
    "fr": "⛔ Annuler",
    "he": "⛔ ביטול"
}


def _cancel_markup(lang):
    text = CANCEL_TEXTS.get(lang, CANCEL_TEXTS["en"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data="vpn_cancel")]
    ])


@router.callback_query(F.data == "menu_vpn")
async def request_vpn_password(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_id = call.from_user.id
    try:
        user_lang = await database.get_user_language(user_id)
    except Exception:
        user_lang = "ru"

    await state.set_state(VPNStates.waiting_password)
    await state.update_data(vpn_lang=user_lang)

    prompt = PASSWORD_PROMPT_TEXTS.get(user_lang, PASSWORD_PROMPT_TEXTS["en"])
    await call.message.answer(text=prompt, reply_markup=_cancel_markup(user_lang))


@router.callback_query(F.data == "vpn_cancel", VPNStates.waiting_password)
async def cancel_vpn_password(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()

    try:
        user_lang = await database.get_user_language(call.from_user.id)
    except Exception:
        user_lang = "ru"

    caption = menu_texts.MAIN_MENU_TEXTS.get(user_lang, menu_texts.MAIN_MENU_TEXTS["en"])
    markup = inline_kb.get_main_menu(
        user_lang, config.is_admin(call.from_user.id),
        await common.is_subscriber(call.bot, call.from_user.id))

    try:
        await call.message.delete()
    except Exception:
        pass

    await call.message.answer_photo(
        photo=config.MAIN_BANNER,
        caption=caption,
        reply_markup=markup,
        parse_mode="Markdown"
    )


# Ловим ТОЛЬКО обычный текст (не команды вроде /start), чтобы не блокировать выход из состояния
@router.message(VPNStates.waiting_password, F.text, ~F.text.startswith("/"))
async def check_vpn_password(message: Message, state: FSMContext):
    data = await state.get_data()
    user_lang = data.get("vpn_lang", "ru")
    entered = message.text.strip().lower()

    expected = (await database.get_setting("vpn_password", config.VPN_PASSWORD) or "").strip().lower()
    if entered != expected:
        wrong_text = WRONG_PASSWORD_TEXTS.get(user_lang, WRONG_PASSWORD_TEXTS["en"])
        await message.answer(text=wrong_text, reply_markup=_cancel_markup(user_lang))
        return

    await state.clear()
    user_id = message.from_user.id
    await database.log_action(user_id, "menu_vpn", user_lang)

    caption = VPN_TEXTS.get(user_lang, VPN_TEXTS["en"])

    go_btn_texts = {
        "ru": "🚀 АКТИВИРОВАТЬ PREMIUM VPN СКИДКУ",
        "en": "🚀 ACTIVATE PREMIUM VPN DISCOUNT",
        "fr": "🚀 ACTIVER LA REMISE VPN PREMIUM",
        "he": "🚀 הפעל הנחת VPN פרימיום"
    }
    go_text = go_btn_texts.get(user_lang, go_btn_texts["en"])
    back_text = "⇦ В главное меню" if user_lang == "ru" else "⇦ Main Menu"

    secure_vpn_url = "https://t.me/vpmem_bot?start=Q51TXM"

    vpn_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=go_text, url=secure_vpn_url)],
        [InlineKeyboardButton(text=back_text, callback_data="go_home")]
    ])

    await message.answer(text=caption, reply_markup=vpn_markup, parse_mode="Markdown")
