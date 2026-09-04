from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InputMediaPhoto,
                           InlineKeyboardMarkup, InlineKeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

import config
import database  # Импортируем нашу БД
import inline_kb

router = Router()

async def is_subscriber(bot: Bot, user_id: int) -> bool:
    """Подписан ли человек на канал дайджеста.

    Нужно ровно для одного: не предлагать подписаться тому, кто уже
    подписан. Ошибку глотаем и считаем, что не подписан — предложить
    лишний раз безобиднее, чем спрятать кнопку у того, кому она нужна.
    """
    try:
        chat = await database.get_setting("digest_chat")
        if not chat:
            return False
        member = await bot.get_chat_member(chat_id=int(chat), user_id=user_id)
        return member.status not in ("left", "kicked")
    except Exception:
        return False


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

# Куда ведёт глубокая ссылка. Кнопка под постом в канале должна открывать
# нужный экран, а не главное меню: человек, пришедший заказывать разбор
# генов, не обязан искать его сам.
#
# Ключ короткий и осмысленный — он виден в адресе, а адрес показывается
# читателю при переходе.
DEEP_LINKS = {
    "genetics": "genetics_order",
    "shop": "tennis_shop_referral",
    "tennis": "sport_tennis",
    "books": "intellect_books",
    "travel": "sport_travel",
    "ai": "menu_claude",
}


@router.message(F.text.startswith("/start"))
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()

    # «/start genetics» — переход из канала. Запоминаем, откуда пришли:
    # без этого не узнать, какие посты приводят людей, а какие нет.
    payload = message.text.split(maxsplit=1)
    source = payload[1].strip()[:32] if len(payload) > 1 else ""
    if source:
        try:
            await database.log_action(message.from_user.id, f"from_{source}",
                                      await database.get_user_language(message.from_user.id))
        except Exception:
            pass
        await state.update_data(deep_link=source)
    
    # 1. Проверяем обязательную подписку
    is_subscribed = await check_channel_subscriptions(bot, message.from_user.id)
    if not is_subscribed:
        await message.answer(
            "⚠️ Для использования бота необходимо подписаться на наши каналы!\n"
            "Пожалуйста, подпишитесь и введите /start снова."
            # Сюда можно добавить инлайн-кнопки со ссылками на каналы
        )
        return

    # Картинка стартового экрана была вписана прямо сюда и настройку не
    # читала: /banner главная сохранял фото, а экран показывал прежнее.
    fast_file_id = config.MAIN_BANNER
    
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

    # Пришедшему по ссылке сразу даём дорогу туда, зачем он шёл. Отдельным
    # сообщением, а не заменой языкового экрана: язык всё равно нужно
    # выбрать, а искать свой раздел человек не обязан.
    target = DEEP_LINKS.get(source)
    if target:
        labels = {
            "genetics_order": "🧬 Заказать расшифровку",
            "tennis_shop_referral": "🎾 Теннисный магазин",
            "sport_tennis": "🎾 Большой теннис",
            "intellect_books": "📚 Книжная полка",
            "sport_travel": "🌍 Путешествия",
            "menu_claude": "🤖 Чат AI",
        }
        await message.answer(
            "Вы пришли по ссылке — вот она:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=labels.get(target, "Открыть"),
                                     callback_data=target)]]))

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
        reply_markup=inline_kb.get_main_menu(
            selected_lang, config.is_admin(user_id),
            await is_subscriber(bot, user_id)),
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
    # Картинка стартового экрана была вписана прямо сюда и настройку не
    # читала: /banner главная сохранял фото, а экран показывал прежнее.
    fast_file_id = config.MAIN_BANNER

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
        reply_markup=inline_kb.get_main_menu(
            lang, config.is_admin(user_id),
            await is_subscriber(bot, user_id))
    )
    await call.answer()
# Примечание: хендлер menu_vpn обрабатывается в block6_vpn.py, здесь дублирующая версия удалена
# (она использовала неимпортированный menu_texts и падала бы с NameError при клике)
