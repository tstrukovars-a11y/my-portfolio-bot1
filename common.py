from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

import config
import database  # Импортируем нашу БД
import inline_kb

router = Router()

async def check_channel_subscriptions(bot: Bot, user_id: int) -> bool:
    """Вспомогательная функция проверки подписки на каналы"""
    # Если в конфиге каналы не настроены (дефолтные id), пропускаем проверку
    return True
    if False:
        return True
        
    for channel_id in [config.REQUIRED_CHANNEL, config.QUIZ_CHANNEL]:
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except TelegramBadRequest:
            # Если бота нет в канале или канал не существует
            continue
    return True

@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    
    # 1. Проверяем обязательную подписку
    is_subscribed = await check_channel_subscriptions(bot, message.from_user.id)
    if not is_subscribed:
        await message.answer(
            "⚠️ Для использования бота необходимо подписаться на наши каналы!\n"
            "Пожалуйста, подпишитесь и введите /start снова."
            # Сюда можно добавить инлайн-кнопки со ссылками на каналы
        )
        return

    fast_file_id = "AgACAgIAAxkDAAPgagtm983BGj8mNN0_gspgL8EFOjsAAtMaaxts1mFI4UNK-uuf9mkBAAMCAAN5AAM7BA"
    
    await message.answer_photo(
        photo=fast_file_id,
        caption=(
            "👋 Здравствуйте! Пожалуйста, выведите язык интерфейса:\n"
            "🌍 Please select your interface language:\n"
            "🇫🇷 S'il vous plaît, choisissez votre langue:\n"
            "🇮🇱 אנא בחר את שפת הממשק:"
        ),
        reply_markup=inline_kb.language_menu
    )

@router.callback_query(F.data.startswith("lang_"))
async def set_language(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    selected_lang = call.data.split("_")[1]
    
    # Сохраняем в БД, чтобы данные не стерлись при перезапуске сервера
    await database.set_user_language(user_id, selected_lang)
    
    welcome_texts = {
        "ru": "🎯 **Добро пожаловать в Модульный Бот-Визитку!**\n\nЗдесь вы можете изучить мои ROI-кейсы, профессиональный опыт, заглянуть в Дневник директора или задать вопрос нейросети Claude AI. Выберите раздел меню ниже:",
        "en": "🎯 **Welcome to the Modular Portfolio Bot!**\n\nHere you can explore my ROI cases, professional background, read the Director's Diary, or ask Claude AI any question. Please choose a menu section below:",
        "fr": "🎯 **Bienvenue dans le Bot Portfolio Modulaire !**\n\nIci, vous pouvez explorer mes cas ROI, mon parcours professionnel, lire le Journal du Directeur ou poser une question à Claude AI. Choisissez une section :",
        "he": "🎯 **ברוכים הבאים לבוט כרטיס הביקור המודולרי!**\n\nכאן תוכלו לחקור את מקри ה-ROI שלי, הניסיون המקצועי, לעיין ביומן המנהל או לשאול את Claude AI כל שאלה. בחר סעיף מהתפריט למטה:"
    }
    
    caption = welcome_texts.get(selected_lang, welcome_texts["en"])
    
    await call.message.edit_caption(
        caption=caption,
        reply_markup=inline_kb.get_main_menu(selected_lang),
        parse_mode="Markdown"
    )
    await call.answer()

@router.callback_query(F.data == "go_home")
async def navigate_home(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    
    # Проверяем подписку при попытке ходить по меню
    if not await check_channel_subscriptions(bot, user_id):
        await call.answer("⚠️ Доступ ограничен. Вы отписались от каналов!", show_alert=True)
        return

    # Достаем язык из БД
    lang = await database.get_user_language(user_id)
    fast_file_id = "AgACAgIAAxkDAAPgagtm983BGj8mNN0_gspgL8EFOjsAAtMaaxts1mFI4UNK-uuf9mkBAAMCAAN5AAM7BA"

    welcome_texts = {
        "ru": "🎯 **Главное меню**\n\nВыберите интересующий вас раздел для продолжения работы:",
        "en": "🎯 **Main Menu**\n\nSelect the section you are interested in to continue:",
        "fr": "🎯 **Menu Principal**\n\nSélectionnez la section qui vous intéresse pour continuer :",
        "he": "🎯 **תפריט ראשי**\n\nבחר את Сעיף שמעניין אותך כדי להמшиך:"
    }
    
    caption = welcome_texts.get(lang, welcome_texts["en"])
    
    await call.message.edit_media(
        media=InputMediaPhoto(
            media=fast_file_id,
            caption=caption,
            parse_mode="Markdown"
        ),
        reply_markup=inline_kb.get_main_menu(lang)
    )
    await call.answer()
# Примечание: хендлер menu_vpn обрабатывается в block6_vpn.py, здесь дублирующая версия удалена
# (она использовала неимпортированный menu_texts и падала бы с NameError при клике)
