# Задача дня: разбор важнее счёта.
#
# Две беды, которые тут случились на живых людях. «Верно 0 из 1» —
# приговор единственному, кто не угадал, и показывать это в канале
# незачем. А объяснение жило только во всплывающем окошке: Telegram
# обрезает его на двухстах знаках, окошко исчезает через секунду, и
# перечитать нечем.
import pytest

from conftest import run

import puzzle_daily


PUZZLE = {"id": 7, "question": "Сколько будет 2+2?",
          "options": ["3", "4", "5"], "correct_option_id": 1,
          "explanation": "Это сложение: к двум прибавляем два."}


@pytest.fixture
def bank(monkeypatch):
    import database

    async def all_puzzles():
        return [PUZZLE]

    monkeypatch.setattr(database, "get_all_puzzles", all_puzzles)


def _with_stat(monkeypatch, stat):
    import database

    async def last():
        return stat

    monkeypatch.setattr(database, "last_puzzle_result", last)


# --- цифра появляется, когда что-то значит ----------------------------

def test_single_answer_is_not_a_score(bank, monkeypatch):
    """«Верно 0 из 1» читается как приговор одному человеку."""
    _with_stat(monkeypatch, {"puzzle_id": 7, "answers": 1, "correct": 0})
    text = run(puzzle_daily.yesterday_line())
    assert "0 из 1" not in text
    assert "Справились" not in text


def test_score_appears_when_there_are_enough(bank, monkeypatch):
    _with_stat(monkeypatch, {"puzzle_id": 7, "answers": 5, "correct": 3})
    assert "Справились 3 из 5" in run(puzzle_daily.yesterday_line())


# --- разбор выходит всегда --------------------------------------------

def test_explanation_lives_in_the_next_post(bank, monkeypatch):
    """Единственное место, где объяснение можно спокойно дочитать."""
    _with_stat(monkeypatch, {"puzzle_id": 7, "answers": 1, "correct": 0})
    text = run(puzzle_daily.yesterday_line())
    assert "Это сложение" in text


def test_right_answer_is_named(bank, monkeypatch):
    _with_stat(monkeypatch, {"puzzle_id": 7, "answers": 0, "correct": 0})
    text = run(puzzle_daily.yesterday_line())
    assert "Б. 4" in text


def test_nothing_to_show_without_a_previous_puzzle(bank, monkeypatch):
    _with_stat(monkeypatch, None)
    assert run(puzzle_daily.yesterday_line()) == ""


def test_broken_puzzle_does_not_break_the_post(bank, monkeypatch):
    """Задача из банка могла исчезнуть — выпуск от этого не падает."""
    _with_stat(monkeypatch, {"puzzle_id": 999, "answers": 4, "correct": 2})
    assert run(puzzle_daily.yesterday_line()) == ""


def test_index_out_of_range_is_survived(monkeypatch):
    import database

    async def all_puzzles():
        return [dict(PUZZLE, correct_option_id=9)]

    monkeypatch.setattr(database, "get_all_puzzles", all_puzzles)
    _with_stat(monkeypatch, {"puzzle_id": 7, "answers": 4, "correct": 2})
    assert run(puzzle_daily.yesterday_line()) == ""


def test_puzzle_without_explanation_still_names_the_answer(monkeypatch):
    import database

    async def all_puzzles():
        return [dict(PUZZLE, explanation=None)]

    monkeypatch.setattr(database, "get_all_puzzles", all_puzzles)
    _with_stat(monkeypatch, {"puzzle_id": 7, "answers": 4, "correct": 2})
    text = run(puzzle_daily.yesterday_line())
    assert "Б. 4" in text


def test_post_promises_the_explanation():
    """Человек должен знать, что разбор будет, — иначе он его не дождётся."""
    assert "разбор" in puzzle_daily.TAIL.lower()


# --- задача, где нельзя ответить верно ---------------------------------
#
# Человек знал ответ, нажал и получил «мимо». Так бывает, когда верный
# вариант не показан: шесть кнопок, а правильный седьмой. Винит он при
# этом себя, а не задачу, — и больше не отвечает.

def test_seventh_right_answer_was_unreachable():
    """Ради этого и поднят предел: до десяти вариантов Telegram рисует."""
    assert puzzle_daily.MAX_OPTIONS == 10


@pytest.mark.parametrize("puzzle,why", [
    ({"options": ["а"], "correct_option_id": 0}, "меньше двух"),
    ({"options": ["а", "б"], "correct_option_id": None}, "не указан"),
    ({"options": ["а", "б"], "correct_option_id": 5}, "вне списка"),
    ({"options": ["а", "б"], "correct_option_id": -1}, "вне списка"),
])
def test_broken_puzzles_are_named(puzzle, why):
    assert why in puzzle_daily.broken(puzzle)


def test_answer_beyond_the_buttons_is_refused():
    many = {"options": [str(i) for i in range(12)], "correct_option_id": 11}
    assert "не поместится" in puzzle_daily.broken(many)


def test_good_puzzle_passes():
    assert puzzle_daily.broken(PUZZLE) == ""


def test_broken_puzzle_never_goes_out(monkeypatch):
    """Выпустить её — значит сделать неправым каждого, кто ответит."""
    import database

    async def bank():
        return [{"id": 1, "question": "Битая", "options": ["а", "б"],
                 "correct_option_id": 9, "explanation": None}]

    async def used():
        return []

    monkeypatch.setattr(database, "get_all_puzzles", bank)
    monkeypatch.setattr(database, "published_puzzle_ids", used)
    assert run(puzzle_daily._pick()) is None
