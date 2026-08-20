from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InputMediaPhoto, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from anthropic import AsyncAnthropic

import config
import database  # Подключаем нашу БД
import menu_texts
import inline_kb

router = Router()

RESET_TEXTS = {"ru": "🔄 Сброс сессии...", "en": "🔄 Resetting the session…",
               "fr": "🔄 Réinitialisation…", "he": "🔄 מאפס את השיחה…"}
claude_client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

class ClaudeStates(StatesGroup):
    is_talking = State()
    confirming_exit = State()

# ==========================================================
# 🤖 ВХОД В БЛОК 4: НЕЙРОСЕТЬ CLAUDE (ПРИВАТНЫЙ)
# ==========================================================
@router.callback_query(F.data == "menu_claude")
async def open_claude(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_id = call.from_user.id
    
    # Получаем язык из базы данных (надежно)
    lang = await database.get_user_language(user_id)
    
    # 1. Проверяем платную премиум-подписку
    has_premium = await database.check_subscription(user_id)
    
    if not has_premium:
        # 2. Если премиума нет, проверяем дневной лимит бесплатных запросов (5 в день)
        current_requests = await database.get_ai_requests_count(user_id)
        if current_requests >= 5:
            caption_limit = menu_texts.CLAUDE_LIMIT_TEXTS.get(lang, menu_texts.CLAUDE_LIMIT_TEXTS["en"])
            
            # Подгружаем правильные 4-язычные сетки подписок (Английский на месте)
            if lang == "ru":
                current_pay_markup = inline_kb.get_claude_pay_menu(lang)
            elif lang == "fr":
                current_pay_markup = inline_kb.get_claude_pay_menu(lang)
            elif lang == "he":
                current_pay_markup = inline_kb.get_claude_pay_menu(lang)
            else:
                current_pay_markup = inline_kb.get_claude_pay_menu(lang)
                
            await call.message.edit_media(
                media=InputMediaPhoto(media=config.CLOD_BANNER, caption=caption_limit, parse_mode="Markdown"),
                reply_markup=current_pay_markup
            )
            return

    # 3. Если лимит не превышен или есть премиум — запускаем обычный чат
    await state.set_state(ClaudeStates.is_talking)
    caption_success = menu_texts.CLAUDE_SUCCESS_TEXTS.get(lang, menu_texts.CLAUDE_SUCCESS_TEXTS["en"])
    
    if lang == "ru": exit_markup = inline_kb.reply_exit_ru
    elif lang == "fr": exit_markup = inline_kb.reply_exit_fr
    elif lang == "he": exit_markup = inline_kb.reply_exit_he
    else: exit_markup = inline_kb.reply_exit_en
    
    await call.message.answer(text=caption_success, reply_markup=exit_markup, parse_mode="Markdown")

# ==========================================================
# 🛑 ДВУХЭТАПНАЯ ЗАЩИТА И ПОДТВЕРЖДЕНИЕ ВЫХОДА
# ==========================================================
@router.message(ClaudeStates.is_talking, F.text.in_([
    "🛑 Покинуть чат с ИИ", "🛑 Exit AI Chat", "🛑 Quitter le chat IA", "🛑 צא מצ'אט AI"
]))
async def initiate_exit_protection(message: Message, state: FSMContext):
    lang = await database.get_user_language(message.from_user.id)
    await state.set_state(ClaudeStates.confirming_exit)

    if lang == "ru":
        confirm_markup = inline_kb.confirm_exit_ru
        msg = "⚠ Вы точно хотите прервать сессию и выйти в главное меню?"
    elif lang == "fr":
        confirm_markup = inline_kb.confirm_exit_fr
        msg = "⚠ Voulez-vous vraiment quitter le chat et retourner au menu ?"
    elif lang == "he":
        confirm_markup = inline_kb.confirm_exit_he
        msg = "⚠ האם אתה בטוח שברצונך לצאת לצ'אט ולחזור לתפריט?"
    else:
        confirm_markup = inline_kb.confirm_exit_en
        msg = "⚠ Are you sure you want to terminate the session and exit to menu?"
        
    await message.answer(text=msg, reply_markup=confirm_markup)

# Шаг 2.1: Полное подтверждение выхода
@router.message(ClaudeStates.confirming_exit, F.text.in_([
    "⚠ Да, выйти в главное меню", "⚠ Yes, return to main menu", "⚠ Oui, retourner au menu", "⚠ כן, לחזור לתפריט הראשי"
]))
async def process_confirmed_exit(message: Message, state: FSMContext):
    await state.clear()
    lang = await database.get_user_language(message.from_user.id)
    caption_text = menu_texts.MAIN_MENU_TEXTS.get(lang, menu_texts.MAIN_MENU_TEXTS["en"])
    
    if lang == "ru": current_markup = inline_kb.get_main_menu("ru")
    elif lang == "fr": current_markup = inline_kb.get_main_menu("fr")
    elif lang == "he": current_markup = inline_kb.get_main_menu("he")
    else: current_markup = inline_kb.get_main_menu("en")
    
    await message.answer(text=RESET_TEXTS.get(user_lang, RESET_TEXTS["en"]), reply_markup=ReplyKeyboardRemove())
    await message.answer_photo(
        photo=config.MAIN_BANNER, 
        caption=caption_text, 
        reply_markup=current_markup, 
        parse_mode="Markdown"
    )

# Шаг 2.2: Отмена выхода
@router.message(ClaudeStates.confirming_exit, F.text.in_([
    "🔙 Продолжить общение с Claude", "🔙 Continue chatting with Claude", "🔙 Continuer à discuter avec Claude", "🔙 המשך לשוחח עם קלוד"
]))
async def process_canceled_exit(message: Message, state: FSMContext):
    await state.set_state(ClaudeStates.is_talking)
    lang = await database.get_user_language(message.from_user.id)
    
    if lang == "ru": exit_markup = inline_kb.reply_exit_ru
    elif lang == "fr": exit_markup = inline_kb.reply_exit_fr
    elif lang == "he": exit_markup = inline_kb.reply_exit_he
    else: exit_markup = inline_kb.reply_exit_en
    
    msg = "✅ Вы вернулись в чат. Продолжайте диалог:" if lang == "ru" else "✅ Session restored. Continue chatting:"
    await message.answer(text=msg, reply_markup=exit_markup)

# ==========================================================
# 💬 ХЭНДЛЕР ОБРАБОТКИ ВОПРОСОВ И ОТВЕТОВ CLAUDE API
# ==========================================================
@router.message(ClaudeStates.is_talking, F.text)
async def handle_ai_question(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await database.get_user_language(user_id)
    
    # Дополнительная проверка лимита прямо перед отправкой запроса (для безопасности)
    has_premium = await database.check_subscription(user_id)
    if not has_premium:
        current_requests = await database.get_ai_requests_count(user_id)
        if current_requests >= 5:
            await message.answer("⚠️ Your daily free limit is over. Please buy Premium in Claude Menu.")
            return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        response = await claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": message.text}]
        )
        ai_text = response.content[0].text  # Исправлено обращение к тексту ответа Anthropic
        
        # Если у пользователя нет премиума — увеличиваем счетчик бесплатных запросов в БД
        if not has_premium:
            await database.increment_ai_requests(user_id)
            
        await message.answer(ai_text, parse_mode="Markdown")
        
    except Exception as e:
        err = "❌ Ошибка Claude API:" if lang == "ru" else "❌ Claude API Error:"
        await message.answer(f"{err} {e}")
