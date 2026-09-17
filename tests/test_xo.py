# Крестики-нолики. Правила игры — единственное место, где ошибка видна
# сразу всем участникам чата, поэтому проверяем их целиком, а не выборочно.
import pytest

import xo

E = xo.EMPTY
FRESH = E * 9


def game(board=FRESH, turn="X", x=None, o=None, finished=False):
    return {"id": 1, "board": board, "turn": turn, "x_id": x, "o_id": o,
            "x_name": "Аня", "o_name": "Борис", "finished": finished}


# --- кто выиграл ------------------------------------------------------

@pytest.mark.parametrize("board,expected", [
    ("XXX" + E * 6, "X"),
    (E * 3 + "XXX" + E * 3, "X"),
    (E * 6 + "OOO", "O"),
    ("O" + E * 2 + "O" + E * 2 + "O" + E * 2, "O"),
    (E + "X" + E * 2 + "X" + E * 2 + "X" + E, "X"),
    ("X" + E * 3 + "X" + E * 3 + "X", "X"),
    (E * 2 + "O" + E + "O" + E + "O" + E * 2, "O"),
])
def test_every_line_wins(board, expected):
    assert xo.winner(board) == expected


def test_full_board_without_a_line_is_a_draw():
    assert xo.winner("XOXXOOOXX") == "ничья"


def test_unfinished_game_has_no_winner():
    assert xo.winner(FRESH) is None
    assert xo.winner("XO" + E * 7) is None


def test_winning_line_is_reported_for_highlight():
    assert xo.line_of("XXX" + E * 6, "X") == (0, 1, 2)
    assert xo.line_of(FRESH, "X") == ()


# --- ходы -------------------------------------------------------------

def test_place_touches_one_cell():
    assert xo.place(FRESH, 4, "X") == E * 4 + "X" + E * 4


def test_occupied_cell_is_refused():
    ok, why = xo.may_move(game("X" + E * 8, x=1, o=2), 1, 0, private=False)
    assert not ok and "занята" in why


def test_finished_game_takes_no_moves():
    ok, why = xo.may_move(game("XXX" + E * 6, x=1, o=2, finished=True),
                          2, 4, private=False)
    assert not ok and "закончена" in why


def test_wrong_turn_is_refused():
    """Оба игрока сели — дальше очередь строгая."""
    ok, why = xo.may_move(game(turn="O", x=1, o=2), 1, 4, private=False)
    assert not ok and "не ваш ход" in why


def test_right_turn_passes():
    ok, _ = xo.may_move(game(turn="O", x=1, o=2), 2, 4, private=False)
    assert ok


def test_free_seat_is_taken_by_whoever_taps():
    ok, _ = xo.may_move(game(), 777, 0, private=False)
    assert ok


def test_third_person_cannot_join_a_full_game():
    ok, why = xo.may_move(game(x=1, o=2), 333, 4, private=False)
    assert not ok and "занята" in why


def test_in_private_one_person_plays_both_sides():
    """В личке играть вдвоём не с кем — «горячий стул» это нормально."""
    ok, _ = xo.may_move(game(turn="O", x=1, o=1), 1, 4, private=True)
    assert ok


# --- как это выглядит -------------------------------------------------

def test_board_has_nine_buttons_and_stable_data():
    rows = xo.keyboard(game()).inline_keyboard
    assert [len(r) for r in rows] == [3, 3, 3]
    assert rows[0][0].callback_data == "xo_1_0"
    assert rows[2][2].callback_data == "xo_1_8"


def test_finished_board_offers_another_round():
    rows = xo.keyboard(game("XXX" + E * 6, finished=True)).inline_keyboard
    assert any(b.callback_data == "xo_new" for row in rows for b in row)


def test_caption_invites_the_first_player():
    assert "станете крестиками" in xo.caption(game())


def test_caption_names_the_winner():
    text = xo.caption(game("XXX" + E * 6, x=1, o=2, finished=True))
    assert "Выиграл" in text and "Аня" in text


def test_caption_escapes_names():
    """Имя приходит от человека и попадает в HTML-разметку."""
    bad = game()
    bad["x_name"] = "<b>взлом</b>"
    assert "<b>взлом</b>" not in xo.caption(bad)
    assert "&lt;b&gt;" in xo.caption(bad)


# --- игра, отправленная в чужой чат -----------------------------------

def test_inline_board_has_no_game_number_yet():
    """Партия заводится при первом касании, поэтому в кнопке только клетка."""
    rows = xo.keyboard(inline=True).inline_keyboard
    assert rows[0][0].callback_data == "xoi_0"
    assert rows[2][2].callback_data == "xoi_8"


def test_inline_board_has_no_replay_button():
    """Кнопка «ещё партию» отправила бы новое сообщение, а его там нет."""
    finished = game("XXX" + E * 6, finished=True)
    rows = xo.keyboard(finished, inline=True).inline_keyboard
    assert len(rows) == 3
    assert all(b.callback_data.startswith("xoi_") for r in rows for b in r)


def test_seat_is_taken_in_order():
    g = game()
    аня = type("U", (), {"id": 1, "first_name": "Аня", "last_name": None})()
    борис = type("U", (), {"id": 2, "first_name": "Борис", "last_name": None})()
    g["x_id"] = g["o_id"] = None
    assert xo._seat(g, аня) == "X" and g["x_id"] == 1
    assert xo._seat(g, борис) == "O" and g["o_id"] == 2
    assert xo._seat(g, аня) == "X"      # уже сидит — место не меняется


def test_invite_button_opens_the_chat_picker():
    """switch_inline_query подставляет имя бота в выбранный чат сам —
    объяснять человеку, что его надо набрать руками, не приходится."""
    button = xo.invite_row()[0]
    assert button.switch_inline_query == ""
    assert button.callback_data is None


def test_finished_board_offers_both_replay_and_invite():
    rows = xo.keyboard(game("XXX" + E * 6, finished=True)).inline_keyboard
    assert rows[-2][0].callback_data == "xo_new"
    assert rows[-1][0].switch_inline_query == ""


def test_game_without_a_chat_is_allowed_by_the_schema():
    """Игра в чужом чате заводится без chat_id.

    Колонка с NOT NULL ломала ровно это: карточка отправлялась, а первое
    касание отвечало «поле не создалось».
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "database.py").read_text(
        encoding="utf-8")
    start = source.index("CREATE TABLE IF NOT EXISTS {SCHEMA}.xo_games")
    table = source[start:source.index(')"""', start)]
    chat_line = next(line for line in table.splitlines()
                     if "chat_id" in line and "--" not in line)
    assert "NOT NULL" not in chat_line, chat_line
    assert "ALTER COLUMN chat_id DROP NOT NULL" in source, \
        "старым базам нужно снять NOT NULL отдельно"


def test_marks_come_from_one_place():
    """Шапка и поле не должны расходиться: значок задан один раз."""
    text = xo.caption(game("XXX" + E * 6, x=1, o=2, finished=True))
    assert xo.MARKS["X"] in text
    assert "✖️" not in text


def test_winning_line_keeps_the_colours_of_the_marks():
    rows = xo.keyboard(game("XXX" + E * 6), highlight=(0, 1, 2)).inline_keyboard
    assert [b.text for b in rows[0]] == ["🟩", "🟩", "🟩"]
