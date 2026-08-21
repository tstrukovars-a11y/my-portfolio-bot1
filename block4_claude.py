import logging

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message, InputMediaPhoto, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from anthropic import AsyncAnthropic

import config
import database
import menu_texts
import inline_kb

router = Router()

# Без ключа клиент не создаём: иначе запрос падает уже внутри библиотеки,
# и пользователю прилетает техническая ошибка вместо внятного объяснения.
claude_client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else None

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1000
FREE_DAILY = 3

# Сколько реплик диалога помним. Без истории бот отвечал на каждый вопрос
# с чистого листа: «а подробнее?» было не к чему отнести. Ограничение нужно,
# чтобы разговор не разрастался в стоимости и не упирался в контекст модели.
HISTORY_TURNS = 12

LANG_NAMES = {"ru": "Russian", "en": "English", "fr": "French", "he": "Hebrew"}

SYSTEM_PROMPT = (
    "You are the AI assistant built into Tatiana Strukova's portfolio bot in Telegram. "
    "She is a project and product manager with a background in banking, logistics and "
    "manufacturing, a medical geneticist, an artist and a tennis player; the bot presents "
    "her ROI cases, a director's diary, art and atelier work, recipes, travel, tennis "
    "sections and a genetics knowledge base.\n\n"
    "Answer questions on any topic, helpfully and concisely — you are a general assistant, "
    "not a sales script. When the question touches what the bot itself offers, say which "
    "section covers it. Never invent facts about Tatiana beyond what is stated above; if "
    "you do not know, say so and suggest leaving a request through the bot.\n\n"
    "Reply in {language}. Keep answers short enough to read on a phone — a few paragraphs "
    "at most, unless the person asks for detail. Plain text or light Markdown only: no "
    "tables, no headings."
)

RESET_TEXTS = {"ru": "🔄 Сброс сессии…", "en": "🔄 Resetting the session…",
               "fr": "🔄 Réinitialisation…", "he": "🔄 מאפס את השיחה…"}

NOT_CONFIGURED = {
    "ru": "🤖 Раздел ИИ временно недоступен: не настроен ключ доступа.",
    "en": "🤖 The AI section is temporarily unavailable: the access key is not configured.",
    "fr": "🤖 La section IA est indisponible : clé d'accès non configurée.",
    "he": "🤖 מדור הבינה המלאכותית אינו זמין: מפתח הגישה לא הוגדר."
}

# Раньше здесь предлагали купить Premium, которого нельзя купить: обработчик
# платежей к боту не подключён. Человек упирался в стену без выхода, поэтому
# текст говорит правду и ведёт туда, где ответят.
LIMIT_REACHED = {
    "ru": ("⏳ Бесплатные вопросы на сегодня закончились — их {limit} в сутки.\n\n"
           "Лимит обнулится завтра. Или снимите ограничение подпиской:"),
    "en": ("⏳ You have used today's free questions — {limit} a day.\n\n"
           "The limit resets tomorrow, or you can remove it with a subscription:"),
    "fr": ("⏳ Vous avez utilisé vos questions gratuites du jour ({limit} par jour).\n\n"
           "Le compteur repart demain, ou levez la limite avec un abonnement :"),
    "he": ("⏳ נגמרו השאלות החינמיות להיום ({limit} ביום).\n\n"
           "המכסה מתאפסת מחר, או שאפשר להסיר את המגבלה עם מנוי:")
}

BTN_REQUEST = {"ru": "✉️ Оставить заявку", "en": "✉️ Send a request",
               "fr": "✉️ Envoyer une demande", "he": "✉️ שלחו בקשה"}
BTN_HOME = {"ru": "⇦ В главное меню", "en": "⇦ Main menu",
            "fr": "⇦ Menu principal", "he": "⇦ לתפריט הראשי"}

# Пользователю — понятная фраза, разработчику — настоящая ошибка в логах.
# Кончившийся баланс — не временный сбой: «попробуйте через минуту» тут врёт,
# раздел не заработает, пока владелец не пополнит счёт.
NO_CREDITS = {
    "ru": "🤖 Чат AI временно недоступен. Загляните позже — раздел скоро вернётся.",
    "en": "🤖 The AI chat is temporarily unavailable. Please check back later.",
    "fr": "🤖 Le chat IA est momentanément indisponible. Revenez plus tard.",
    "he": "🤖 צ'אט ה-AI אינו זמין כרגע. בדקו שוב מאוחר יותר."
}

API_ERROR = {
    "ru": "⚠️ Не получилось получить ответ. Попробуйте ещё раз через минуту.",
    "en": "⚠️ Could not get an answer. Please try again in a minute.",
    "fr": "⚠️ Impossible d'obtenir une réponse. Réessayez dans une minute.",
    "he": "⚠️ לא הצלחתי לקבל תשובה. נסו שוב בעוד דקה."
}

RESUMED = {"ru": "✅ Вы вернулись в чат. Продолжайте диалог:",
           "en": "✅ Session restored. Continue chatting:",
           "fr": "✅ Session restaurée. Continuez :",
           "he": "✅ חזרתם לצ'אט. המשיכו:"}

EXIT_CONFIRM = {
    "ru": "⚠ Вы точно хотите прервать сессию и выйти в главное меню?",
    "en": "⚠ Are you sure you want to end the session and return to the menu?",
    "fr": "⚠ Voulez-vous vraiment quitter le chat et retourner au menu ?",
    "he": "⚠ בטוחים שברצונכם לסיים את השיחה ולחזור לתפריט?"
}


def _t(mapping: dict, lang: str) -> str:
    return mapping.get(lang, mapping["en"])


def _exit_markup(lang: str):
    return {"ru": inline_kb.reply_exit_ru, "fr": inline_kb.reply_exit_fr,
            "he": inline_kb.reply_exit_he}.get(lang, inline_kb.reply_exit_en)


def _confirm_markup(lang: str):
    return {"ru": inline_kb.confirm_exit_ru, "fr": inline_kb.confirm_exit_fr,
            "he": inline_kb.confirm_exit_he}.get(lang, inline_kb.confirm_exit_en)


def _limit_markup(lang: str):
    """Тарифы плюс запасной путь: не всем удобно платить звёздами."""
    import payments
    rows = payments.tariff_rows(lang)
    if config.ADMIN_ID:
        rows.append([InlineKeyboardButton(text=_t(BTN_REQUEST, lang), callback_data="ads_order")])
    rows.append([InlineKeyboardButton(text=_t(BTN_HOME, lang), callback_data="go_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _over_limit(user_id: int) -> bool:
    if await database.check_subscription(user_id):
        return False
    return await database.get_ai_requests_count(user_id) >= FREE_DAILY


class ClaudeStates(StatesGroup):
    is_talking = State()
    confirming_exit = State()


# ==========================================================
# 🤖 ВХОД В ЧАТ
# ==========================================================

@router.callback_query(F.data == "menu_claude")
async def open_claude(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_id = call.from_user.id
    lang = await database.get_user_language(user_id)

    if await _over_limit(user_id):
        await call.message.answer(
            _t(LIMIT_REACHED, lang).format(limit=FREE_DAILY),
            reply_markup=_limit_markup(lang)
        )
        return

    # Новый вход — новый разговор: старая история сбивала бы модель с толку
    await state.set_state(ClaudeStates.is_talking)
    await state.update_data(history=[])

    caption = menu_texts.CLAUDE_SUCCESS_TEXTS.get(lang, menu_texts.CLAUDE_SUCCESS_TEXTS["en"])
    await call.message.answer(text=caption, reply_markup=_exit_markup(lang),
                              parse_mode="Markdown")


# ==========================================================
# 🛑 ВЫХОД С ПОДТВЕРЖДЕНИЕМ
# ==========================================================

@router.message(ClaudeStates.is_talking, F.text.in_([
    "🛑 Покинуть чат с ИИ", "🛑 Exit AI Chat", "🛑 Quitter le chat IA", "🛑 צא מצ'אט AI"
]))
async def initiate_exit_protection(message: Message, state: FSMContext):
    lang = await database.get_user_language(message.from_user.id)
    await state.set_state(ClaudeStates.confirming_exit)
    await message.answer(text=_t(EXIT_CONFIRM, lang), reply_markup=_confirm_markup(lang))


@router.message(ClaudeStates.confirming_exit, F.text.in_([
    "⚠ Да, выйти в главное меню", "⚠ Yes, return to main menu",
    "⚠ Oui, retourner au menu", "⚠ כן, לחזור לתפריט הראשי"
]))
async def process_confirmed_exit(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    lang = await database.get_user_language(user_id)

    await message.answer(text=_t(RESET_TEXTS, lang), reply_markup=ReplyKeyboardRemove())
    await message.answer_photo(
        photo=config.MAIN_BANNER,
        caption=menu_texts.MAIN_MENU_TEXTS.get(lang, menu_texts.MAIN_MENU_TEXTS["en"]),
        reply_markup=inline_kb.get_main_menu(lang, config.is_admin(user_id)),
        parse_mode="Markdown"
    )


@router.message(ClaudeStates.confirming_exit, F.text.in_([
    "🔙 Продолжить общение с Claude", "🔙 Continue chatting with Claude",
    "🔙 Continuer à discuter avec Claude", "🔙 המשך לשוחח עם קלוד"
]))
async def process_canceled_exit(message: Message, state: FSMContext):
    await state.set_state(ClaudeStates.is_talking)
    lang = await database.get_user_language(message.from_user.id)
    await message.answer(text=_t(RESUMED, lang), reply_markup=_exit_markup(lang))


# ==========================================================
# 💬 ДИАЛОГ
# ==========================================================

@router.message(ClaudeStates.is_talking, F.text)
async def handle_ai_question(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await database.get_user_language(user_id)

    if await _over_limit(user_id):
        await message.answer(_t(LIMIT_REACHED, lang).format(limit=FREE_DAILY),
                             reply_markup=_limit_markup(lang))
        return

    if claude_client is None:
        await message.answer(_t(NOT_CONFIGURED, lang))
        return

    data = await state.get_data()
    history = data.get("history", [])
    history.append({"role": "user", "content": message.text})

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        response = await claude_client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT.format(language=LANG_NAMES.get(lang, "English")),
            messages=list(history)   # копия: дальше в history дописывается ответ
        )
        answer = response.content[0].text
    except Exception as e:
        # Посетителю — понятная фраза, владельцу — настоящая причина: иначе
        # за каждой ошибкой приходится лезть в логи Render.
        logging.error(f"Claude API: {type(e).__name__}: {e}")
        text = str(e).lower()
        out_of_credits = "credit balance" in text or "billing" in text
        note = _t(NO_CREDITS if out_of_credits else API_ERROR, lang)
        if out_of_credits and config.is_admin(user_id):
            note = ("💳 <b>Закончились средства на счёте Anthropic.</b>\n\n"
                    "console.anthropic.com → Plans &amp; Billing → пополнить баланс.\n"
                    "Подписка Claude Pro на claude.ai сюда не относится, API "
                    "оплачивается отдельно.\n\n"
                    "Посетители сейчас видят «раздел временно недоступен».")
            await message.answer(note)
            return
        if config.is_admin(user_id):
            note += f"\n\n<code>{type(e).__name__}: {str(e)[:300]}</code>"
        await message.answer(note)
        return

    history.append({"role": "assistant", "content": answer})
    # Держим только хвост переписки: старое всё равно не нужно, а токены оно ест
    await state.update_data(history=history[-HISTORY_TURNS:])

    if not await database.check_subscription(user_id):
        await database.increment_ai_requests(user_id)

    # Модель иногда возвращает разметку, которую Telegram разобрать не может —
    # тогда сообщение отклоняется целиком. Показываем обычным текстом.
    try:
        await message.answer(answer, parse_mode="Markdown")
    except Exception:
        await message.answer(answer, parse_mode=None)
