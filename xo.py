# xo.py — крестики-нолики на одном поле, прямо в переписке.
#
# Поле живёт в сообщении: девять кнопок и одна строка состояния. Ходят
# двое, видят все — поэтому игра идёт в группе, а не в личке, и клуб на
# сто тридцать человек получает повод в него заглянуть.
#
# Кто за кого, решает очередь касаний: первый нажавший играет крестиками,
# второй — ноликами. Спрашивать заранее не нужно, а значит, не нужно и
# приглашение: игра начинается с того, что кто-то ткнул в клетку.
#
# Состояние — в базе, а не в памяти процесса: деплой посреди партии не
# должен её стирать, а сообщение с полем живёт в чате неделями.
import html
import logging

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, InlineQuery,
                           InlineQueryResultArticle, InputTextMessageContent)

import config
import database

router = Router()

EMPTY = "."
MARKS = {"X": "✖️", "O": "⭕️", EMPTY: "·"}

# Восемь линий: три ряда, три столбца, две диагонали.
LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8),
         (0, 3, 6), (1, 4, 7), (2, 5, 8),
         (0, 4, 8), (2, 4, 6))


def winner(board: str):
    """«X», «O», «ничья» либо None, если партия ещё идёт"""
    for a, b, c in LINES:
        if board[a] != EMPTY and board[a] == board[b] == board[c]:
            return board[a]
    return "ничья" if EMPTY not in board else None


def line_of(board: str, mark: str):
    """Клетки выигрышной линии — их подсветим в итоговом поле"""
    for line in LINES:
        if all(board[i] == mark for i in line):
            return line
    return ()


def place(board: str, cell: int, mark: str) -> str:
    return board[:cell] + mark + board[cell + 1:]


def may_move(game: dict, user_id: int, cell: int, private: bool):
    """(можно ли, что сказать нажавшему).

    Правил всего четыре, и каждое отвечает на живой вопрос игрока:
    занято ли, моя ли очередь, играю ли я вообще и не кончилось ли.
    """
    if game.get("finished"):
        return False, "Партия уже закончена"
    if game["board"][cell] != EMPTY:
        return False, "Клетка занята"

    x_id, o_id = game.get("x_id"), game.get("o_id")

    # В личке играть вдвоём не с кем, поэтому там один человек ходит за
    # обоих — это обычный «горячий стул», и запрещать его незачем.
    if private:
        return True, ""

    if user_id not in (x_id, o_id):
        if x_id and o_id:
            return False, "Партия уже занята — дождитесь следующей"
        return True, ""          # свободное место: садится тот, кто нажал

    mine = "X" if user_id == x_id else "O"
    if mine != game["turn"]:
        return False, "Сейчас не ваш ход"
    return True, ""


def keyboard(game: dict = None, highlight=(), inline: bool = False):
    """Поле кнопками.

    У игры, отправленной в чужой чат, номера ещё нет: она заводится при
    первом касании. Поэтому там в кнопке только клетка — «xoi_4», а
    найдётся игра по номеру сообщения.
    """
    board = game["board"] if game else EMPTY * 9
    rows = []
    for row in range(3):
        line = []
        for col in range(3):
            i = row * 3 + col
            face = MARKS[board[i]]
            if i in highlight:
                face = "🔶" if board[i] == "X" else "🔷"
            data = f"xoi_{i}" if inline else f"xo_{game['id']}_{i}"
            line.append(InlineKeyboardButton(text=face, callback_data=data))
        rows.append(line)
    if game and game.get("finished") and not inline:
        rows.append([InlineKeyboardButton(text="🔁 Ещё партию",
                                          callback_data="xo_new")])
        rows.append(invite_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def invite_row() -> list:
    """Кнопка «позвать соперника».

    switch_inline_query открывает у нажавшего выбор чата и подставляет
    туда «@имя_бота» — человеку остаётся выбрать, с кем играть, и нажать
    карточку. Это короче, чем объяснять, что надо набрать имя бота руками.
    """
    return [InlineKeyboardButton(text="🤝 Позвать соперника в другой чат",
                                 switch_inline_query="")]


def _who(game: dict) -> str:
    x = html.escape(game.get("x_name") or "—")
    o = html.escape(game.get("o_name") or "—")
    return f"✖️ {x}   ⭕️ {o}"


def caption(game: dict) -> str:
    end = winner(game["board"])
    lines = ["⭕️✖️ <b>Крестики-нолики</b>", "", _who(game), ""]
    if end == "ничья":
        lines.append("Ничья. Поле кончилось раньше, чем кто-то выиграл.")
    elif end:
        name = game.get("x_name") if end == "X" else game.get("o_name")
        lines.append(f"🏆 Выиграл {MARKS[end]} {html.escape(name or end)}")
    elif not game.get("x_id"):
        lines.append("Нажмите клетку — станете крестиками.")
    elif not game.get("o_id"):
        lines.append("Крестики походили. Второй игрок — нажмите свободную клетку.")
    else:
        lines.append(f"Ход {MARKS[game['turn']]}")
    return "\n".join(lines)


def _name(user) -> str:
    name = (user.first_name or "").strip() or "Игрок"
    if user.last_name:
        name = f"{name} {user.last_name.strip()}"
    return name[:32]


@router.message(F.text.regexp(r"^/(крестики|xo|нолики)"))
async def start_game(message: Message, bot: Bot):
    """Новое поле. Работает и в группе, и в личке."""
    game = await database.xo_new(message.chat.id)
    if not game:
        await message.answer("Поле не создалось — база не отвечает.")
        return

    markup = keyboard(game)
    tail = ""
    if message.chat.type == "private":
        tail = ("\n\n<i>Здесь вы ходите за обоих. Чтобы сыграть с живым "
                "соперником — кнопка ниже.</i>")
        markup.inline_keyboard.append(invite_row())
    await message.answer(caption(game) + tail, reply_markup=markup)


@router.callback_query(F.data == "xo_open")
async def open_from_menu(call: CallbackQuery, bot: Bot):
    """Из меню игр — поле сразу, без объяснений: девять кнопок понятны."""
    game = await database.xo_new(call.message.chat.id)
    await call.answer()
    if not game:
        await call.message.answer("Поле не создалось — база не отвечает.")
        return
    markup = keyboard(game)
    markup.inline_keyboard.append(invite_row())
    await call.message.answer(
        caption(game)
        + "\n\n<i>Здесь вы ходите за обоих — чтобы попробовать.\n"
        + "В группе играют двое: первый нажавший — крестики, второй — нолики.\n"
        + "Позвать кого-то в другой чат — кнопка ниже.</i>",
        reply_markup=markup)


@router.callback_query(F.data == "xo_new")
async def again(call: CallbackQuery):
    game = await database.xo_new(call.message.chat.id)
    await call.answer("Новое поле")
    if game:
        await call.message.answer(caption(game), reply_markup=keyboard(game))


# ---------------------------------------------------------------------
# ИГРА, ОТПРАВЛЕННАЯ В ЧУЖОЙ ЧАТ
# ---------------------------------------------------------------------
#
# Пересылать доску бессмысленно: пересланное сообщение принадлежит тому,
# кто переслал, и бот не может его перерисовать — поле застынет на первом
# ходу. Telegram для этого даёт строку запроса: человек набирает в любом
# чате «@имя_бота», выбирает игру, и сообщение отправляется от имени бота.
# Такое сообщение бот менять умеет — по inline_message_id.

INLINE_HINT = ("Наберите в любом чате <code>@{bot}</code> и выберите "
               "«Крестики-нолики» — поле появится прямо там.")


@router.inline_query()
async def offer_game(query: InlineQuery):
    """Единственный результат — новое поле. Выбирать не из чего."""
    await query.answer(
        results=[InlineQueryResultArticle(
            id="xo",
            title="⭕️✖️ Крестики-нолики",
            description="Поле на двоих прямо в этом чате",
            input_message_content=InputTextMessageContent(
                message_text=caption({"board": EMPTY * 9}),
                parse_mode="HTML"),
            reply_markup=keyboard(inline=True))],
        cache_time=0, is_personal=False)


@router.callback_query(F.data.regexp(r"^xoi_\d$"), F.inline_message_id)
async def inline_move(call: CallbackQuery, bot: Bot):
    inline_id = call.inline_message_id
    game = await database.xo_by_inline(inline_id)
    if not game:
        # Первое касание — тогда и заводим партию.
        game = await database.xo_new(inline_id=inline_id)
    if not game:
        await call.answer("Поле не создалось — попробуйте ещё раз",
                          show_alert=True)
        return

    cell = int(call.data.split("_")[1])
    allowed, why = may_move(game, call.from_user.id, cell, private=False)
    if not allowed:
        await call.answer(why)
        return

    mark = _seat(game, call.from_user)
    game.update(board=place(game["board"], cell, mark),
                turn=("O" if mark == "X" else "X"))
    end = winner(game["board"])
    game["finished"] = bool(end)

    if not await database.xo_save(game):
        await call.answer("Ход не сохранился, нажмите ещё раз", show_alert=True)
        return

    try:
        await bot.edit_message_text(
            inline_message_id=inline_id, text=caption(game),
            reply_markup=keyboard(game, line_of(game["board"], end)
                                  if end and end != "ничья" else (),
                                  inline=True))
    except Exception as e:
        logging.info(f"Поле в чужом чате не перерисовалось: {e}")
    await call.answer()


def _seat(game: dict, user) -> str:
    """Кто ходит — тот и садится за свободное место"""
    if user.id == game.get("x_id"):
        return "X"
    if user.id == game.get("o_id"):
        return "O"
    if not game.get("x_id"):
        game["x_id"], game["x_name"] = user.id, _name(user)
        return "X"
    game["o_id"], game["o_name"] = user.id, _name(user)
    return "O"


@router.callback_query(F.data.regexp(r"^xo_\d+_\d$"))
async def move(call: CallbackQuery):
    _, raw_id, raw_cell = call.data.split("_")
    game = await database.xo_get(int(raw_id))
    if not game:
        await call.answer("Это поле уже не найти — начните новое: /крестики",
                          show_alert=True)
        return

    cell = int(raw_cell)
    private = call.message.chat.type == "private"
    allowed, why = may_move(game, call.from_user.id, cell, private)
    if not allowed:
        await call.answer(why, show_alert=False)
        return

    # В личке человек ходит за обоих, поэтому очередь и решает, чей знак.
    mark = game["turn"] if private else _seat(game, call.from_user)

    board = place(game["board"], cell, mark)
    end = winner(board)
    game.update(board=board, turn=("O" if mark == "X" else "X"),
                finished=bool(end))

    saved = await database.xo_save(game)
    if not saved:
        await call.answer("Ход не сохранился, нажмите ещё раз", show_alert=True)
        return

    try:
        await call.message.edit_text(
            caption(game),
            reply_markup=keyboard(game, line_of(board, end) if end and
                                  end != "ничья" else ()))
    except Exception as e:
        logging.info(f"Поле не перерисовалось: {e}")
    await call.answer()
