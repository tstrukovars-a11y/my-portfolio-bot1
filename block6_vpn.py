# block6_vpn.py
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import database

router = Router()

VPN_TEXTS = {
    "ru": "🔌 **Цифровой суверенитет: Надежный Premium VPN**\n\nВ современных реалиях безопасный доступ к глобальным enterprise-системам, зарубежным ИИ-сервисам и международным базам данных — это критическая необходимость для бизнеса.\n\nЯ использую и рекомендую проверенный высокоскоростной VPN с защитой от блокировок. Нажмите на кнопку ниже, чтобы активировать вашу персональную скидку по моей партнерской программе: 👇",
    "en": "🔌 **Digital Sovereignty: Fast Premium VPN Service**\n\nSecure access to global enterprise tools, international AI models, and cloud infrastructure data vectors is an absolute necessity for modern business orchestration.\n\nI personally utilize and recommend a verified high-velocity VPN network. Click the button below to activate your premium discount via my partnership link: 👇",
    "fr": "🔌 **Souveraineté Numérique : Service VPN Premium**\n\nL'accès sécurisé aux infrastructures cloud et aux outils mondiaux est une nécessité absolue. J'utilise et recommande un réseau VPN rapide. Cliquez ci-dessous pour activer votre remise via mon lien de parrainage : 👇",
    "he": "🔌 **ריבונות דיגיטלית: שירות VPN פרימיום מהיר**\n\nגישה מאובטחת לכלי עבודה גלובליים, מודלים של בינה מלאכותית ותשתיות ענן היא כורח המציאות בעולם העסקים המודרני. אני ממליצה על רשת VPN מהירה ומאומתת. לחץ על הכפתור למטה כדי להפעיל את הנחת הפרימיום שלך דרך קישור השותפים שלי: 👇"
}

@router.callback_query(F.data == "menu_vpn")
async def open_vpn_partnership(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    try:
        user_lang = await database.get_user_language(user_id)
    except Exception:
        user_lang = "ru"
        
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
    
    # Сюда мы точечно вставим реферальную ссылку
    secure_vpn_url = "https://t.me/vpmem_bot?start=Q51TXM"
    
    vpn_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=go_text, url=secure_vpn_url)],
        [InlineKeyboardButton(text=back_text, callback_data="go_home")]
    ])
    
    try:
        await call.message.edit_caption(
            caption=caption,
            reply_markup=vpn_markup,
            parse_mode="Markdown"
        )
    except Exception:
        await call.message.answer(
            text=caption,
            reply_markup=vpn_markup,
            parse_mode="Markdown"
        )
