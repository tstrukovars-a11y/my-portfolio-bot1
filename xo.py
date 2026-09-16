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
                           InlineKeyboardButton)

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


def keyboard(game: dict, highlight=()) -> InlineKeyboardMarkup:
    board = game["board"]
    rows = []
    for row in range(3):
        line = []
        for col in range(3):
            i = row * 3 + col
            face = MARKS[board[i]]
            if i in highlight:
                face = "🔶" if board[i] == "X" else "🔷"
            line.append(InlineKeyboardButton(
                text=face, callback_data=f"xo_{game['id']}_{i}"))
        rows.append(line)
    if game.get("finished"):
        rows.append([InlineKeyboardButton(text="🔁 Ещё партию",
                                          callback_data="xo_new")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
async def start_game(message: Message):
    """Новое поле. Работает и в группе, и в личке."""
    game = await database.xo_new(message.chat.id)
    if not game:
        await message.answer("Поле не создалось — база не отвечает.")
        return
    await message.answer(caption(game), reply_markup=keyboard(game))


@router.callback_query(F.data == "xo_open")
async def open_from_menu(call: CallbackQuery):
    """Из меню игр — поле сразу, без объяснений: девять кнопок понятны."""
    game = await database.xo_new(call.message.chat.id)
    await call.answer()
    if not game:
        await call.message.answer("Поле не создалось — база не отвечает.")
        return
    await call.message.answer(
        caption(game) + "\n\n<i>В группе играют двое: первый нажавший — "
        "крестики, второй — нолики. Здесь, в личке, вы ходите за обоих.</i>",
        reply_markup=keyboard(game))


@router.callback_query(F.data == "xo_new")
async def again(call: CallbackQuery):
    game = await database.xo_new(call.message.chat.id)
    await call.answer("Новое поле")
    if game:
        await call.message.answer(caption(game), reply_markup=keyboard(game))


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

    # Кто ходит — тот и садится за свободное место.
    mark = game["turn"]
    if not private:
        if call.from_user.id == game.get("x_id"):
            mark = "X"
        elif call.from_user.id == game.get("o_id"):
            mark = "O"
        elif not game.get("x_id"):
            mark = "X"
            game["x_id"], game["x_name"] = call.from_user.id, _name(call.from_user)
        else:
            mark = "O"
            game["o_id"], game["o_name"] = call.from_user.id, _name(call.from_user)

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
