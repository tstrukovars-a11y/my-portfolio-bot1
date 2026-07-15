# handlers/profiles.py
from aiogram import Router, F
from aiogram.types import CallbackQuery, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
import config
import database
import menu_texts
import inline_kb

router = Router()

@router.callback_query(F.data == "menu_profiles")
async def open_profiles(call: CallbackQuery):
    user_lang = await database.get_user_language(call.from_user.id)
    text = menu_texts.PROFILES_MENU_TEXTS.get(user_lang, menu_texts.PROFILES_MENU_TEXTS["en"])
    try:
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.SCIENCE_BANNER, caption=text, parse_mode="Markdown"),
            reply_markup=inline_kb.get_profiles_menu(user_lang)
        )
    except Exception:
        await call.message.delete()
        await call.message.answer_photo(
            photo=config.SCIENCE_BANNER,
            caption=text,
            parse_mode="Markdown",
            reply_markup=inline_kb.get_profiles_menu(user_lang)
        )
    await call.answer()

@router.callback_query(F.data == "sub_bank")
async def sub_bank(call: CallbackQuery):
    await call.message.edit_reply_markup(reply_markup=inline_kb.get_bank_submenu())
    await call.answer()

@router.callback_query(F.data == "sub_logistics")
async def sub_logistics(call: CallbackQuery):
    await call.message.edit_reply_markup(reply_markup=inline_kb.get_logistics_submenu())
    await call.answer()

@router.callback_query(F.data == "sub_agro")
async def sub_agro(call: CallbackQuery):
    await call.message.edit_reply_markup(reply_markup=inline_kb.get_agro_submenu())
    await call.answer()

@router.callback_query(F.data == "sub_production")
async def sub_production(call: CallbackQuery):
    await call.message.edit_reply_markup(reply_markup=inline_kb.get_production_submenu())
    await call.answer()

@router.callback_query(F.data.startswith("p_"))
async def show_project_details(call: CallbackQuery):
    user_lang = await database.get_user_language(call.from_user.id)

    if call.data == "p_universal":
        back_markup = inline_kb.get_profiles_menu(user_lang)
    elif call.data in {"p_sb_dist", "p_sb_risk", "p_sb_cash", "p_sb_ml", "p_rsb"}:
        back_markup = inline_kb.get_bank_submenu(exclude_prj=call.data)
    elif call.data in {"p_lg_sms", "p_lg_cust", "p_lg_fts", "p_lg_fulfill", "p_lg_acq", "p_lg_unit", "p_ev_adm", "p_ev_pro"}:
        back_markup = inline_kb.get_logistics_submenu(exclude_prj=call.data)
    elif call.data == "p_agroeco":
        back_markup = inline_kb.get_agro_submenu()
    else:
        back_markup = inline_kb.get_production_submenu()

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
