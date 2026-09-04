# handlers/profiles.py
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import common
import config
import database
import menu_texts
import inline_kb

router = Router()

# Пароль задаётся переменной окружения PROFILES_PASSWORD (см. config)
PROFILES_PASSWORD = config.PROFILES_PASSWORD

class ProfilesStates(StatesGroup):
    waiting_password = State()

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
        [InlineKeyboardButton(text=text, callback_data="profiles_cancel")]
    ])


@router.callback_query(F.data == "menu_profiles")
async def request_profiles_password(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_lang = await database.get_user_language(call.from_user.id)

    await state.set_state(ProfilesStates.waiting_password)
    await state.update_data(profiles_lang=user_lang)

    prompt = PASSWORD_PROMPT_TEXTS.get(user_lang, PASSWORD_PROMPT_TEXTS["en"])
    await call.message.answer(text=prompt, reply_markup=_cancel_markup(user_lang))


@router.callback_query(F.data == "profiles_cancel", ProfilesStates.waiting_password)
async def cancel_profiles_password(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()

    user_lang = await database.get_user_language(call.from_user.id)
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
@router.message(ProfilesStates.waiting_password, F.text, ~F.text.startswith("/"))
async def check_profiles_password(message: Message, state: FSMContext):
    data = await state.get_data()
    user_lang = data.get("profiles_lang", "ru")
    entered = message.text.strip().lower()

    expected = (await database.get_setting("profiles_password", config.PROFILES_PASSWORD) or "").strip().lower()
    if entered != expected:
        wrong_text = WRONG_PASSWORD_TEXTS.get(user_lang, WRONG_PASSWORD_TEXTS["en"])
        await message.answer(text=wrong_text, reply_markup=_cancel_markup(user_lang))
        return

    await state.clear()
    text = menu_texts.PROFILES_MENU_TEXTS.get(user_lang, menu_texts.PROFILES_MENU_TEXTS["en"])
    await message.answer_photo(
        photo=config.SCIENCE_BANNER,
        caption=text,
        parse_mode="Markdown",
        reply_markup=inline_kb.get_profiles_menu(user_lang)
    )

@router.callback_query(F.data == "sub_bank")
async def sub_bank(call: CallbackQuery):
    user_lang = await database.get_user_language(call.from_user.id)
    await call.message.edit_reply_markup(reply_markup=inline_kb.get_bank_submenu(user_lang))
    await call.answer()

@router.callback_query(F.data == "sub_logistics")
async def sub_logistics(call: CallbackQuery):
    user_lang = await database.get_user_language(call.from_user.id)
    await call.message.edit_reply_markup(reply_markup=inline_kb.get_logistics_submenu(user_lang))
    await call.answer()

@router.callback_query(F.data == "sub_agro")
async def sub_agro(call: CallbackQuery):
    user_lang = await database.get_user_language(call.from_user.id)
    await call.message.edit_reply_markup(reply_markup=inline_kb.get_agro_submenu(user_lang))
    await call.answer()

@router.callback_query(F.data == "sub_production")
async def sub_production(call: CallbackQuery):
    user_lang = await database.get_user_language(call.from_user.id)
    await call.message.edit_reply_markup(reply_markup=inline_kb.get_production_submenu(user_lang))
    await call.answer()

@router.callback_query(F.data.startswith("p_"))
async def show_project_details(call: CallbackQuery):
    user_lang = await database.get_user_language(call.from_user.id)

    if call.data == "p_universal":
        back_markup = inline_kb.get_profiles_menu(user_lang)
    elif call.data in {"p_sb_dist", "p_sb_risk", "p_sb_cash", "p_sb_ml", "p_rsb"}:
        back_markup = inline_kb.get_bank_submenu(user_lang, exclude_prj=call.data)
    elif call.data in {"p_lg_sms", "p_lg_cust", "p_lg_fts", "p_lg_fulfill", "p_lg_acq", "p_lg_unit", "p_ev_adm", "p_ev_pro"}:
        back_markup = inline_kb.get_logistics_submenu(user_lang, exclude_prj=call.data)
    elif call.data == "p_agroeco":
        back_markup = inline_kb.get_agro_submenu(user_lang)
    else:
        back_markup = inline_kb.get_production_submenu(user_lang)

    data_map = {
        "p_universal": menu_texts.TEXT_UNIVERSAL,
        "p_sb_dist": menu_texts.TEXT_SBER_DIST,
        "p_sb_risk": menu_texts.TEXT_SBER_RISK,
        "p_sb_cash": menu_texts.TEXT_SBER_CASH,
        "p_sb_ml": menu_texts.TEXT_SBER_ML,
        "p_rsb": menu_texts.TEXT_RSB,
        "p_lg_sms": menu_texts.TEXT_SPSR_SMS,
        "p_lg_cust": menu_texts.TEXT_SPSR_CUSTOMS,
        "p_lg_fts": menu_texts.TEXT_SPSR_FTS,
        "p_lg_fulfill": menu_texts.TEXT_SPSR_FULFILL,
        "p_lg_acq": menu_texts.TEXT_SPSR_ACQ,
        "p_lg_unit": menu_texts.TEXT_SPSR_UNIT,
        "p_ev_adm": menu_texts.TEXT_EVROSET_ADM,
        "p_ev_pro": menu_texts.TEXT_EVROSET_PRO,
        "p_agroeco": menu_texts.TEXT_AGROECO,
        "p_vaso_sap": menu_texts.TEXT_VASO_SAP,
        "p_vaso_1c": menu_texts.TEXT_VASO_1C,
    }
    
    txt_dict = data_map.get(call.data, {"ru": "Ошибка"})
    caption_text = txt_dict.get(user_lang, txt_dict.get("ru", ""))
    
    # КЛЮЧЕВАЯ УМНАЯ ПРОВЕРКА ЛИМИТОВ: 
    # Если текст длиннее 1000 символов, удаляем медиа-сообщение и присылаем лонгрид чистым текстом (лимит 4096).
    # Если текст короткий, бесшовно меняем его прямо под стэнфордской фотографией!
    if len(caption_text) > 1000:
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer(text=caption_text, parse_mode="Markdown", reply_markup=back_markup)
    else:
        try:
            await call.message.edit_media(
                media=InputMediaPhoto(media=config.SCIENCE_BANNER, caption=caption_text, parse_mode="Markdown"),
                reply_markup=back_markup
            )
        except Exception:
            # Если прошлое сообщение уже было чистым текстом, edit_media упадет. В этом случае просто присылаем новый текст.
            try:
                await call.message.delete()
            except Exception:
                pass
            await call.message.answer(text=caption_text, parse_mode="Markdown", reply_markup=back_markup)
            
    await call.answer()
