# puzzles.py — раздел «Головоломка»: банк задач из канала, прохождение вперемешку,
# итоговый балл, неограниченные повторы и накопительная статистика.
import logging
import random

from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery, Message, PollAnswer, InputPollOption,
    InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest

import config
import database
import menu_texts
import inline_kb

router = Router()

# Ограничения Telegram на опросы: длина вопроса и варианта ответа
MAX_QUESTION_LEN = 300
MAX_OPTION_LEN = 100

# Активные прохождения живут в памяти процесса: раунд короткий, а его потеря
# при перезапуске Render не страшна — итоги и статистика пишутся в базу сразу.
# user_id -> {"queue": [...], "idx": int, "correct": int, "control_id": int|None}
_rounds: dict[int, dict] = {}
# poll_id от Telegram -> user_id, чтобы связать входящий ответ с раундом
_poll_owner: dict[str, int] = {}


# =====================================================================
# ТЕКСТЫ
# =====================================================================

EMPTY_BANK = {
    "ru": "🧩 **Банк задач пока пуст.**\n\nЗадачи подтягиваются из канала головоломок. Загляните чуть позже.",
    "en": "🧩 **The puzzle bank is empty for now.**\n\nPuzzles are pulled from the puzzle channel. Please check back later.",
    "fr": "🧩 **La banque de puzzles est vide pour l'instant.**\n\nLes puzzles proviennent de la chaîne. Revenez plus tard.",
    "he": "🧩 **מאגר החידות ריק כרגע.**\n\nהחידות נמשכות מערוץ החידות. בדקו שוב מאוחר יותר."
}

ROUND_START = {
    "ru": "🧩 **Поехали!** {n} задач в случайном порядке.\n\nОтвечайте на опрос — следующая задача придёт сама.",
    "en": "🧩 **Let's go!** {n} puzzles in random order.\n\nAnswer the poll — the next puzzle arrives automatically.",
    "fr": "🧩 **C'est parti !** {n} puzzles en ordre aléatoire.\n\nRépondez au sondage — le suivant arrive tout seul.",
    "he": "🧩 **יוצאים לדרך!** {n} חידות בסדר אקראי.\n\nענו על הסקר — החידה הבאה תגיע מעצמה."
}

PROGRESS = {
    "ru": "Задача {cur} из {total} · правильных: {ok}",
    "en": "Puzzle {cur} of {total} · correct: {ok}",
    "fr": "Puzzle {cur} sur {total} · correctes : {ok}",
    "he": "חידה {cur} מתוך {total} · נכונות: {ok}"
}

BTN_SKIP = {"ru": "➡ Пропустить", "en": "➡ Skip", "fr": "➡ Passer", "he": "➡ דלג"}
BTN_FINISH = {"ru": "🛑 Завершить", "en": "🛑 Finish", "fr": "🛑 Terminer", "he": "🛑 סיים"}
BTN_AGAIN = {"ru": "🔄 Пройти заново", "en": "🔄 Play again", "fr": "🔄 Rejouer", "he": "🔄 שחק שוב"}
BTN_STATS = {"ru": "📊 Моя статистика", "en": "📊 My stats", "fr": "📊 Mes statistiques", "he": "📊 הסטטיסטיקה שלי"}
BTN_BACK = {"ru": "🛑 Вернуться в Дневник", "en": "🛑 Back to Diary", "fr": "🛑 Retour au Journal", "he": "🛑 חזרה ליומן"}
BTN_SOLVE = {"ru": "🧩 Решать задачи", "en": "🧩 Solve puzzles", "fr": "🧩 Résoudre", "he": "🧩 פתור חידות"}

RESULT = {
    "ru": "🏁 **Раунд завершён!**\n\nВаш результат: **{ok} из {total}** ({pct:.0f}%)\n{verdict}",
    "en": "🏁 **Round complete!**\n\nYour score: **{ok} of {total}** ({pct:.0f}%)\n{verdict}",
    "fr": "🏁 **Manche terminée !**\n\nVotre score : **{ok} sur {total}** ({pct:.0f}%)\n{verdict}",
    "he": "🏁 **הסיבוב הסתיים!**\n\nהתוצאה שלך: **{ok} מתוך {total}** ({pct:.0f}%)\n{verdict}"
}

VERDICTS = {
    "ru": ["Есть куда расти — попробуйте ещё раз.", "Неплохо, но можно лучше.", "Отличный результат!", "Безупречно! 🎯"],
    "en": ["Room to grow — give it another go.", "Decent, but you can do better.", "Great result!", "Flawless! 🎯"],
    "fr": ["Il y a de la marge — réessayez.", "Correct, mais peut mieux faire.", "Excellent résultat !", "Sans faute ! 🎯"],
    "he": ["יש מקום לשיפור — נסו שוב.", "לא רע, אפשר יותר טוב.", "תוצאה מצוינת!", "מושלם! 🎯"]
}

STATS_TEXT = {
    "ru": (
        "📊 **Ваша статистика по головоломкам**\n\n"
        "• Прохождений: **{rounds}**\n"
        "• Последний результат: **{last_correct} из {last_total}**\n"
        "• Лучший результат: **{best_correct} из {best_total}** ({best_pct:.0f}%)\n"
        "• Средний балл: **{avg_pct:.0f}%**\n"
        "• Всего ответов: **{answers}**, из них верных: **{answers_correct}**\n"
        "• Общая точность: **{accuracy:.0f}%**"
    ),
    "en": (
        "📊 **Your puzzle statistics**\n\n"
        "• Rounds played: **{rounds}**\n"
        "• Last score: **{last_correct} of {last_total}**\n"
        "• Best score: **{best_correct} of {best_total}** ({best_pct:.0f}%)\n"
        "• Average score: **{avg_pct:.0f}%**\n"
        "• Total answers: **{answers}**, correct: **{answers_correct}**\n"
        "• Overall accuracy: **{accuracy:.0f}%**"
    ),
    "fr": (
        "📊 **Vos statistiques de puzzles**\n\n"
        "• Manches jouées : **{rounds}**\n"
        "• Dernier score : **{last_correct} sur {last_total}**\n"
        "• Meilleur score : **{best_correct} sur {best_total}** ({best_pct:.0f}%)\n"
        "• Score moyen : **{avg_pct:.0f}%**\n"
        "• Réponses totales : **{answers}**, correctes : **{answers_correct}**\n"
        "• Précision globale : **{accuracy:.0f}%**"
    ),
    "he": (
        "📊 **הסטטיסטיקה שלך בחידות**\n\n"
        "• סיבובים: **{rounds}**\n"
        "• תוצאה אחרונה: **{last_correct} מתוך {last_total}**\n"
        "• תוצאה הטובה ביותר: **{best_correct} מתוך {best_total}** ({best_pct:.0f}%)\n"
        "• ציון ממוצע: **{avg_pct:.0f}%**\n"
        "• סך תשובות: **{answers}**, נכונות: **{answers_correct}**\n"
        "• דיוק כולל: **{accuracy:.0f}%**"
    )
}

STATS_EMPTY = {
    "ru": "📊 Вы ещё не проходили ни одного раунда. Решите задачи — и здесь появится статистика.",
    "en": "📊 You have not completed a round yet. Solve some puzzles and your stats will appear here.",
    "fr": "📊 Vous n'avez pas encore terminé de manche. Résolvez des puzzles et vos statistiques apparaîtront ici.",
    "he": "📊 עדיין לא סיימת סיבוב. פתרו חידות והסטטיסטיקה תופיע כאן."
}


def _t(mapping: dict, lang: str) -> str:
    return mapping.get(lang, mapping["en"])


# =====================================================================
# ЭКРАН РАЗДЕЛА
# =====================================================================

@router.callback_query(F.data == "intellect_puzzle")
async def open_puzzle_hub(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    caption = menu_texts.PUZZLE_MENU_TEXTS.get(lang, menu_texts.PUZZLE_MENU_TEXTS["en"])

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_t(BTN_SOLVE, lang), callback_data="start_solving_puzzles")],
        [InlineKeyboardButton(text=_t(BTN_STATS, lang), callback_data="puzzle_stats")],
        [InlineKeyboardButton(text="🔙 Назад" if lang == "ru" else "🔙 Back", callback_data="menu_diary")]
    ])

    try:
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.PUZZLE_BANNER, caption=caption, parse_mode="Markdown"),
            reply_markup=markup
        )
    except TelegramBadRequest:
        await call.message.answer_photo(
            photo=config.PUZZLE_BANNER, caption=caption,
            parse_mode="Markdown", reply_markup=markup
        )


# =====================================================================
# ПРОХОЖДЕНИЕ
# =====================================================================

async def _send_next(bot: Bot, chat_id: int, user_id: int, lang: str):
    """Отправляет очередную задачу раунда или подводит итог, если задачи кончились"""
    state = _rounds.get(user_id)
    if not state:
        return

    # Прошлую строку прогресса убираем, чтобы чат не зарастал
    if state.get("control_id"):
        try:
            await bot.delete_message(chat_id=chat_id, message_id=state["control_id"])
        except Exception:
            pass
        state["control_id"] = None

    if state["idx"] >= len(state["queue"]):
        await _finish_round(bot, chat_id, user_id, lang)
        return

    puzzle = state["queue"][state["idx"]]

    try:
        sent = await bot.send_poll(
            chat_id=chat_id,
            question=puzzle["question"][:MAX_QUESTION_LEN],
            options=[InputPollOption(text=o[:MAX_OPTION_LEN]) for o in puzzle["options"]],
            type="quiz",
            correct_option_id=puzzle["correct_option_id"],
            explanation=(puzzle["explanation"] or None),
            is_anonymous=False,   # обязательно: иначе бот не получит poll_answer
            protect_content=False
        )
    except Exception as e:
        # Битую задачу пропускаем, но раунд не роняем
        logging.error(f"Не удалось отправить головоломку id={puzzle['id']}: {e}")
        state["idx"] += 1
        await _send_next(bot, chat_id, user_id, lang)
        return

    _poll_owner[sent.poll.id] = user_id
    state["current_poll_id"] = sent.poll.id

    progress = _t(PROGRESS, lang).format(
        cur=state["idx"] + 1, total=len(state["queue"]), ok=state["correct"]
    )
    control = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=_t(BTN_SKIP, lang), callback_data="puzzle_skip"),
        InlineKeyboardButton(text=_t(BTN_FINISH, lang), callback_data="puzzle_finish")
    ]])
    msg = await bot.send_message(chat_id=chat_id, text=progress, reply_markup=control)
    state["control_id"] = msg.message_id


async def _finish_round(bot: Bot, chat_id: int, user_id: int, lang: str):
    """Подводит итог, пишет результат в статистику и предлагает пройти заново"""
    state = _rounds.pop(user_id, None)
    if not state:
        return

    # Чистим карту опросов целиком, включая последний неотвеченный, иначе
    # _poll_owner растёт от раунда к раунду и течёт по памяти.
    for pid in state.get("poll_ids", []):
        _poll_owner.pop(pid, None)
    if state.get("current_poll_id"):
        _poll_owner.pop(state["current_poll_id"], None)

    answered = state["idx"]
    correct = state["correct"]

    if answered == 0:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=_t(BTN_AGAIN, lang), callback_data="start_solving_puzzles")],
            [InlineKeyboardButton(text=_t(BTN_BACK, lang), callback_data="intellect_puzzle")]
        ])
        await bot.send_message(chat_id=chat_id, text=_t(STATS_EMPTY, lang), reply_markup=markup)
        return

    await database.save_puzzle_round(user_id, answered, correct)

    pct = correct / answered * 100
    verdicts = VERDICTS.get(lang, VERDICTS["en"])
    if pct >= 100:
        verdict = verdicts[3]
    elif pct >= 75:
        verdict = verdicts[2]
    elif pct >= 40:
        verdict = verdicts[1]
    else:
        verdict = verdicts[0]

    text = _t(RESULT, lang).format(ok=correct, total=answered, pct=pct, verdict=verdict)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_t(BTN_AGAIN, lang), callback_data="start_solving_puzzles")],
        [InlineKeyboardButton(text=_t(BTN_STATS, lang), callback_data="puzzle_stats")],
        [InlineKeyboardButton(text=_t(BTN_BACK, lang), callback_data="intellect_puzzle")]
    ])
    await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, parse_mode="Markdown")


@router.callback_query(F.data == "start_solving_puzzles")
async def start_round(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    lang = await database.get_user_language(user_id)
    await call.answer()

    bank = await database.get_all_puzzles()
    if not bank:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=_t(BTN_BACK, lang), callback_data="intellect_puzzle")]
        ])
        await call.message.answer(_t(EMPTY_BANK, lang), reply_markup=markup, parse_mode="Markdown")
        return

    # Перемешиваем задачи; порядок вариантов внутри задачи оставляем как в канале,
    # иначе пришлось бы пересчитывать индекс правильного ответа на каждом показе.
    queue = bank[:]
    random.shuffle(queue)

    _rounds[user_id] = {
        "queue": queue, "idx": 0, "correct": 0,
        "control_id": None, "current_poll_id": None, "poll_ids": []
    }

    await call.message.answer(
        _t(ROUND_START, lang).format(n=len(queue)), parse_mode="Markdown"
    )
    await _send_next(bot, call.message.chat.id, user_id, lang)


@router.poll_answer()
async def on_poll_answer(answer: PollAnswer, bot: Bot):
    """Ответ на опрос: засчитываем балл и сразу выдаём следующую задачу"""
    user_id = _poll_owner.get(answer.poll_id)
    if user_id is None or user_id != answer.user.id:
        return

    state = _rounds.get(user_id)
    if not state or state.get("current_poll_id") != answer.poll_id:
        return

    puzzle = state["queue"][state["idx"]]
    chosen = answer.option_ids[0] if answer.option_ids else -1
    is_correct = chosen == puzzle["correct_option_id"]

    if is_correct:
        state["correct"] += 1
    state["idx"] += 1
    state["poll_ids"].append(answer.poll_id)
    _poll_owner.pop(answer.poll_id, None)

    await database.save_puzzle_answer(user_id, puzzle["id"], is_correct)

    lang = await database.get_user_language(user_id)
    await _send_next(bot, answer.user.id, user_id, lang)


@router.callback_query(F.data == "puzzle_skip")
async def skip_puzzle(call: CallbackQuery, bot: Bot):
    await call.answer()
    user_id = call.from_user.id
    state = _rounds.get(user_id)
    if not state:
        return

    # Пропуск засчитывается как неотвеченная задача: она уходит из очереди,
    # но в статистику ответов не попадает.
    state["queue"].pop(state["idx"])
    if state.get("current_poll_id"):
        _poll_owner.pop(state["current_poll_id"], None)
        state["current_poll_id"] = None

    lang = await database.get_user_language(user_id)
    await _send_next(bot, call.message.chat.id, user_id, lang)


@router.callback_query(F.data == "puzzle_finish")
async def finish_puzzle(call: CallbackQuery, bot: Bot):
    await call.answer()
    user_id = call.from_user.id
    state = _rounds.get(user_id)
    if not state:
        return

    if state.get("control_id"):
        try:
            await bot.delete_message(chat_id=call.message.chat.id, message_id=state["control_id"])
        except Exception:
            pass
        state["control_id"] = None

    lang = await database.get_user_language(user_id)
    await _finish_round(bot, call.message.chat.id, user_id, lang)


@router.callback_query(F.data == "puzzle_stats")
async def show_stats(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    stats = await database.get_puzzle_stats(call.from_user.id)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_t(BTN_AGAIN, lang), callback_data="start_solving_puzzles")],
        [InlineKeyboardButton(text=_t(BTN_BACK, lang), callback_data="intellect_puzzle")]
    ])

    if stats["rounds"] == 0:
        await call.message.answer(_t(STATS_EMPTY, lang), reply_markup=markup)
        return

    await call.message.answer(
        _t(STATS_TEXT, lang).format(**stats), reply_markup=markup, parse_mode="Markdown"
    )


# =====================================================================
# НАПОЛНЕНИЕ БАНКА ЗАДАЧ
# =====================================================================

class ImportStates(StatesGroup):
    collecting = State()          # админ пересылает опросы
    waiting_correct = State()     # у опроса не виден правильный ответ, спрашиваем номер


def _is_admin(user_id: int) -> bool:
    return bool(config.ADMIN_ID) and user_id == config.ADMIN_ID


def _poll_to_options(poll) -> list[str]:
    return [o.text for o in poll.options]


@router.message(F.text == "/puzzles")
async def puzzles_import_start(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    await state.set_state(ImportStates.collecting)
    total = await database.count_puzzles()
    await message.answer(
        f"🧩 <b>Режим импорта головоломок включён.</b>\n\n"
        f"Сейчас в банке задач: <b>{total}</b>.\n\n"
        f"Пересылайте сюда опросы из канала — по одному или пачкой. "
        f"Я сохраню вопрос, варианты и правильный ответ.\n\n"
        f"Если Telegram не отдаёт правильный ответ (так бывает у незакрытых опросов), "
        f"я покажу варианты и спрошу его номер.\n\n"
        f"Когда закончите — отправьте /puzzles_done"
    )


@router.message(F.text == "/puzzles_done", ImportStates.collecting)
@router.message(F.text == "/puzzles_done", ImportStates.waiting_correct)
async def puzzles_import_stop(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.clear()
    total = await database.count_puzzles()
    await message.answer(f"✅ Импорт завершён. Всего задач в банке: <b>{total}</b>.")


@router.message(ImportStates.collecting, F.poll)
async def puzzles_import_poll(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    poll = message.poll
    options = _poll_to_options(poll)

    if poll.correct_option_id is not None:
        result = await database.add_puzzle(
            source_poll_id=poll.id,
            question=poll.question,
            options=options,
            correct_option_id=poll.correct_option_id,
            explanation=poll.explanation
        )
        total = await database.count_puzzles()
        if result == "added":
            await message.answer(f"✅ Добавлено: «{poll.question[:60]}». В банке: <b>{total}</b>.")
        elif result == "duplicate":
            await message.answer(f"↩️ Эта задача уже есть в банке. Всего: <b>{total}</b>.")
        else:
            await message.answer("⚠️ База недоступна, задача не сохранена. Попробуйте позже.")
        return

    # Правильный ответ не пришёл — спрашиваем у админа
    await state.set_state(ImportStates.waiting_correct)
    await state.update_data(
        pending_poll_id=poll.id,
        pending_question=poll.question,
        pending_options=options,
        pending_explanation=poll.explanation
    )
    listing = "\n".join(f"{i + 1}. {o}" for i, o in enumerate(options))
    await message.answer(
        f"❓ Telegram не отдал правильный ответ для этого опроса.\n\n"
        f"<b>{poll.question}</b>\n{listing}\n\n"
        f"Пришлите номер правильного варианта (1–{len(options)})."
    )


@router.message(ImportStates.waiting_correct, F.text.regexp(r"^\d+$"))
async def puzzles_import_correct(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    data = await state.get_data()
    options = data.get("pending_options") or []
    number = int(message.text)

    if not 1 <= number <= len(options):
        await message.answer(f"Нужен номер от 1 до {len(options)}. Попробуйте ещё раз.")
        return

    result = await database.add_puzzle(
        source_poll_id=data.get("pending_poll_id"),
        question=data.get("pending_question"),
        options=options,
        correct_option_id=number - 1,
        explanation=data.get("pending_explanation")
    )
    total = await database.count_puzzles()
    await state.set_state(ImportStates.collecting)

    if result == "added":
        await message.answer(f"✅ Добавлено, правильный вариант — «{options[number - 1]}». В банке: <b>{total}</b>.")
    elif result == "duplicate":
        await message.answer(f"↩️ Эта задача уже есть в банке. Всего: <b>{total}</b>.")
    else:
        await message.answer("⚠️ База недоступна, задача не сохранена.")


@router.message(ImportStates.collecting, ~F.text.startswith("/"))
async def puzzles_import_hint(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer(
        "Это не опрос. Перешлите именно quiz-опрос из канала "
        "или отправьте /puzzles_done, чтобы выйти из режима импорта."
    )


def _is_puzzle_post(message: Message) -> bool:
    return config.channel_allowed(config.QUIZ_CHANNEL, message.chat.id)


@router.channel_post(F.poll, _is_puzzle_post)
async def auto_collect_channel_puzzle(message: Message):
    """Новые опросы, опубликованные в канале головоломок, попадают в банк сами.

    Фильтр F.poll обязателен: без него этот хендлер перехватывал бы вообще все
    посты канала и ломал сборщики рецептов и книг. Проверка канала стоит тоже в
    фильтре, а не в теле: иначе опрос из чужого канала считался бы обработанным
    и до других сборщиков не дошёл бы.
    """
    poll = message.poll
    if poll.correct_option_id is None:
        logging.warning(
            f"Опрос {poll.id} из канала пришёл без правильного ответа — "
            f"добавьте его вручную через /puzzles"
        )
        return

    result = await database.add_puzzle(
        source_poll_id=poll.id,
        question=poll.question,
        options=_poll_to_options(poll),
        correct_option_id=poll.correct_option_id,
        explanation=poll.explanation
    )
    if result == "added":
        logging.info(f"🧩 АВТО-ГОЛОВОЛОМКИ: добавлена задача «{poll.question[:60]}»")
