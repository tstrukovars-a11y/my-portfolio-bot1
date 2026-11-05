#  draws_runner.py — автоматическая часть конкурса.
#
#  Панель (draws.py) — то, что владелица делает руками: завела конкурс,
#  призы, расписание, нажала «объявить». Дальше вечер должен идти сам, и
#  это он.
#
#  ПОРЯДОК ВЕЧЕРА:
#    1. пришло время матча -> вопрос уходит участникам;
#    2. через 15 минут приём закрывается;
#    3. бот спрашивает ВЛАДЕЛИЦУ, кто выиграл, — матчей Пальмиры нет ни
#       в одной ленте, и сам он этого не узнает;
#    4. когда исход известен у всех матчей, считаются угадавшие всё;
#    5. их больше, чем призов, — строится сетка, и круги идут по времени;
#    6. призёры записаны, владелице доложено.
#
#  ПОЧЕМУ ТАЙМЕР, А НЕ ОЖИДАНИЕ. Каждый шаг ограничен по времени и
#  проходит даже если кто-то не ответил: вечер нельзя останавливать из-за
#  одного человека, который ушёл домой.

import asyncio
import html
import logging

from aiogram import Bot, F, Router
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup)

import config
import database
import draw_bracket
import draws

router = Router()

# Сколько минут даётся на круг игры. Короткий намеренно: круги идут после
# матчей, и растянуть их на час — значит не дождаться никого.
ROUND_MINUTES = 10


# ---------------------------------------------------------------------
# 1. Вопрос участникам
# ---------------------------------------------------------------------

def _answer_kb(poll_id: int, option_a: str, option_b: str):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=option_a[:28],
                             callback_data=f"drans_{poll_id}_0"),
        InlineKeyboardButton(text=option_b[:28],
                             callback_data=f"drans_{poll_id}_1"),
    ]])


async def dispatch_polls(bot: Bot) -> int:
    """Разослать вопросы, которым пришло время."""
    sent_total = 0
    for poll in await database.draw_polls_to_send():
        members = await database.draw_members(poll["event_id"])
        text = (f"🎾 <b>{html.escape(poll['question'])}</b>\n\n"
                f"<i>Ответ принимается {draws.POLL_MINUTES} минут. "
                f"Передумать внутри этого времени можно, после — нет.</i>")
        for user_id in members:
            try:
                await bot.send_message(
                    user_id, text,
                    reply_markup=_answer_kb(poll["id"], poll["option_a"],
                                            poll["option_b"]))
                sent_total += 1
            except Exception:
                continue        # заблокировал бота — не наша забота
            await asyncio.sleep(0.05)
        await database.draw_poll_mark_sent(poll["id"])
        logging.info(f"Конкурс: вопрос {poll['id']} ушёл {len(members)} участникам")
    return sent_total


@router.callback_query(F.data.startswith("drans_"))
async def take_answer(call: CallbackQuery):
    """Ответ участника. Окно проверяет база — спор «я успел» решается там."""
    try:
        _, poll_id, side = call.data.split("_")
        poll_id, side = int(poll_id), int(side)
    except ValueError:
        await call.answer()
        return

    result = await database.draw_answer(poll_id, call.from_user.id, side)
    if result == "закрыт":
        await call.answer("Приём ответов по этому матчу закрыт.",
                          show_alert=True)
        return
    if result != "принят":
        await call.answer("Не получилось записать. Нажмите ещё раз.",
                          show_alert=True)
        return

    poll = await database.draw_poll(poll_id)
    chosen = (poll or {}).get("option_a" if side == 0 else "option_b", "")
    # Имя после двоеточия: склонять фамилии автоматически нельзя
    await call.answer(f"Ваш ответ: {chosen}", show_alert=True)


# ---------------------------------------------------------------------
# 2-3. Закрытие приёма и вопрос владелице
# ---------------------------------------------------------------------

async def close_polls(bot: Bot) -> int:
    """Закрыть приём там, где вышло время, и спросить, кто выиграл."""
    closed = 0
    for poll in await database.draw_polls_due():
        await database.draw_poll_close(poll["id"])
        closed += 1
        if not config.ADMIN_ID:
            continue
        counts = await database.draw_poll_counts(poll["id"])
        try:
            await bot.send_message(
                config.ADMIN_ID,
                f"🏁 <b>Приём закрыт</b>\n\n"
                f"{html.escape(poll['question'])}\n"
                f"Ответов: {sum(counts)}\n\n"
                f"Кто выиграл?",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text=poll["option_a"][:28],
                        callback_data=f"drwon_{poll['id']}_0"),
                    InlineKeyboardButton(
                        text=poll["option_b"][:28],
                        callback_data=f"drwon_{poll['id']}_1"),
                ]]))
        except Exception as e:
            logging.warning(f"Вопрос об исходе {poll['id']} не ушёл: {e}")
    return closed


@router.callback_query(F.data.startswith("drwon_"))
async def mark_winner(call: CallbackQuery):
    """Владелица отмечает победителя матча.

    Это единственный источник правды об исходе: матчей Пальмиры нет ни в
    одной ленте, и выдумывать их бот не станет.
    """
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    try:
        _, poll_id, side = call.data.split("_")
        poll_id, side = int(poll_id), int(side)
    except ValueError:
        await call.answer()
        return

    await database.draw_poll_close(poll_id, correct=side)
    poll = await database.draw_poll(poll_id)
    if not poll:
        await call.answer()
        return
    name = poll["option_a"] if side == 0 else poll["option_b"]
    await call.answer(f"Записано: {name}")

    # Все ли матчи разобраны — тогда пора считать угадавших
    polls = await database.draw_polls_of_event(poll["event_id"])
    left = [p for p in polls if p["correct"] is None]
    if left:
        await call.message.answer(
            f"✅ {html.escape(name)}.\n\n"
            f"Осталось матчей без исхода: {len(left)}.")
        return

    await call.message.answer("✅ Все матчи разобраны. Считаю угадавших…")
    await start_bracket(call.bot, poll["event_id"])


# ---------------------------------------------------------------------
# 4-5. Сетка
# ---------------------------------------------------------------------

async def _name_of(bot: Bot, user_id: int) -> str:
    """Имя участника. Не достали — покажем номер, но не промолчим."""
    try:
        chat = await bot.get_chat(user_id)
        name = (chat.first_name or "").strip()
        if chat.last_name:
            name = f"{name} {chat.last_name.strip()}".strip()
        return name[:64] or str(user_id)
    except Exception:
        return str(user_id)


async def start_bracket(bot: Bot, event_id: int) -> str:
    """Собрать сетку из угадавших всё — или раздать призы без неё."""
    event = await database.draw_event(event_id=event_id)
    if not event:
        return "конкурс не найден"
    prizes = event.get("prizes") or draws.DEFAULT_PRIZES

    guessed = await database.draw_all_guessed(event_id)
    if not guessed:
        if config.ADMIN_ID:
            await bot.send_message(
                config.ADMIN_ID,
                "Все матчи разобраны, но всё угадавших нет. "
                "Призы остаются до следующего конкурса.")
        return "угадавших нет"

    players = [user_id for user_id, _, _ in guessed]

    # Угадавших не больше, чем призов, — сетка не нужна: разыгрывать
    # нечего, места уже определены порядком ответов.
    if len(players) <= prizes:
        ordered = [(uid, await _name_of(bot, uid)) for uid in players]
        await database.draw_winners_set(event_id, ordered)
        if config.ADMIN_ID:
            await bot.send_message(
                config.ADMIN_ID,
                f"🏆 Угадавших всё: {len(players)} — это не больше числа "
                f"призов, сетка не нужна. Призёры записаны, можно рассылать.")
        return "призёры определены без сетки"

    if len(players) > draw_bracket.MAX_PLAYERS:
        # Отсекаем по таблице: кто ответил раньше, тот и в сетке. Пять
        # кругов вечером не сыграть.
        players = players[:draw_bracket.MAX_PLAYERS]

    size = draw_bracket.bracket_size(len(players))
    slots = draw_bracket.seed_slots(players, size)
    bracket_id = await database.bracket_create(
        event_id, slots, size, round_minutes=ROUND_MINUTES)
    if not bracket_id:
        return "сетка не создалась"

    await _announce_round(bot, bracket_id, event, round_no=1)
    return f"сетка на {size} запущена"


async def _bracket_picture(bot: Bot, bracket_id: int, bracket, event):
    """Картинка сетки со всеми кругами, что уже известны.

    Присылается каждому участнику вместе с его парой: человек узнаёт
    себя по знаку — цвету и фигуре, — а не по фотографии. Фотографию
    профиля он ставил для друзей, а не для общей рассылки.
    """
    rounds, names = [], {}
    for round_no in range(1, (bracket["round_no"] or 1) + 1):
        slots = await database.bracket_slots(bracket_id, round_no)
        if not slots:
            continue
        rounds.append(slots)
        for user_id in slots:
            if user_id is not None and user_id not in names:
                names[user_id] = await _name_of(bot, user_id)

    scores = await database.bracket_round_scores(bracket_id)
    try:
        import draw_image
        return draw_image.render(
            rounds, names, scores,
            title=f"{event['title']} — сетка"), names
    except Exception as e:
        logging.warning(f"Картинка сетки не нарисовалась: {e}")
        return None, names


def _game_kb():
    """Кнопка с игрой. Нет внешнего адреса — нет и кнопки: нажатие,
    которое ничего не открывает, хуже её отсутствия."""
    import rally
    url = rally.game_url()
    if not url:
        return None
    from aiogram.types import WebAppInfo
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="🎾 Играть круг", web_app=WebAppInfo(url=url))]])


async def _announce_round(bot: Bot, bracket_id: int, event,
                          round_no: int) -> None:
    """Разослать участникам круга их пару, срок и картинку сетки."""
    slots = await database.bracket_slots(bracket_id, round_no)
    bracket = await database.bracket_get(bracket_id)
    if not bracket:
        return
    stage = draw_bracket.round_name(len(slots)) if len(slots) > 2 else "Финал"
    if round_no >= draw_bracket.last_round_no(bracket["size"]) and len(slots) >= 4:
        stage = "Финал и матч за третье место"

    picture, _ = await _bracket_picture(bot, bracket_id, bracket, event)
    keyboard = _game_kb()

    for first, second in draw_bracket.pairs(slots):
        for me, rival in ((first, second), (second, first)):
            if me is None:
                continue
            if rival is None:
                body = (f"🎾 <b>{stage}</b>\n\n"
                        f"Вам достался проход без игры — вы сразу в "
                        f"следующем круге.")
            else:
                rival_name = await _name_of(bot, rival)
                body = (f"🎾 <b>{stage}</b>\n\n"
                        f"Ваш соперник: {html.escape(rival_name)}\n\n"
                        f"Откройте игру «Розыгрыш» и сыграйте в ближайшие "
                        f"{ROUND_MINUTES} минут. Дальше проходит тот, у кого "
                        f"длиннее розыгрыш.\n\n"
                        f"<i>Не сыграете — засчитывается поражение: круги "
                        f"короткие, иначе вечер не кончится.</i>")
            try:
                if picture:
                    from aiogram.types import BufferedInputFile
                    await bot.send_photo(
                        me,
                        BufferedInputFile(picture, filename="bracket.png"),
                        caption=body, reply_markup=keyboard)
                else:
                    await bot.send_message(me, body, reply_markup=keyboard)
            except Exception:
                continue
            await asyncio.sleep(0.05)


async def advance_brackets(bot: Bot) -> int:
    """Подвести круги, у которых вышло время."""
    moved = 0
    for bracket in await database.brackets_due():
        bracket_id = bracket["id"]
        slots = await database.bracket_slots(bracket_id, bracket["round_no"])
        scores = await database.bracket_round_scores(bracket_id)
        seeds = await database.bracket_seeds(bracket_id)

        nxt, done = draw_bracket.step(slots, bracket["round_no"],
                                      bracket["size"], scores, seeds)
        event = await database.draw_event(event_id=bracket["event_id"])

        if done:
            ordered = [(uid, await _name_of(bot, uid)) for uid in done]
            await database.draw_winners_set(bracket["event_id"], ordered)
            await database.bracket_finish(bracket_id)
            if config.ADMIN_ID and event:
                lines = ["🏆 <b>Сетка доиграна</b>", ""]
                for place, (uid, name) in enumerate(ordered, start=1):
                    lines.append(f"{draws._place_word(place)} — "
                                 f"{html.escape(name)}")
                lines.append("")
                lines.append("Можно рассылать призёрам место вручения.")
                try:
                    await bot.send_message(config.ADMIN_ID, "\n".join(lines))
                except Exception:
                    pass
        elif nxt:
            await database.bracket_next_round(bracket_id, nxt,
                                              round_minutes=ROUND_MINUTES)
            if event:
                await _announce_round(bot, bracket_id, event,
                                      bracket["round_no"] + 1)
        else:
            await database.bracket_finish(bracket_id)
        moved += 1
    return moved


# ---------------------------------------------------------------------
# Планировщик
# ---------------------------------------------------------------------

async def scheduler(bot: Bot) -> None:
    """Раз в минуту: разослать вопросы, закрыть приём, подвинуть круги.

    Минута, а не пять: вопрос должен уйти в начале матча, а не через
    четверть часа после — к тому времени окно ответа уже закрылось бы.
    """
    await asyncio.sleep(45)
    while True:
        try:
            await dispatch_polls(bot)
            await close_polls(bot)
            await advance_brackets(bot)
        except Exception as e:
            logging.error(f"Конкурс: обход не прошёл: {e}")
        await asyncio.sleep(60)
