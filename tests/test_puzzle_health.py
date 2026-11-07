"""Почему головоломки перестали выходить — должно быть видно.

Задача без верного ответа молча выбрасывается из отбора. Если негодны
все, слот каждый день возвращает «банк задач пуст» — в лог Render, куда
никто не смотрит. Со стороны это «посты пропали», без единой подсказки.
"""

import inspect

import puzzle_daily as pd


def test_an_empty_bank_says_where_to_add():
    line = pd.health_line({"total": 0, "good": 0, "published": 0,
                           "fresh": 0, "broken": []})
    assert "банк пуст" in line
    assert "/puzzles" in line


def test_a_bank_full_of_broken_puzzles_is_named_loudly():
    """Это и есть невидимый случай: задачи есть, а выпускать нечего."""
    line = pd.health_line({"total": 12, "good": 0, "published": 0,
                           "fresh": 0, "broken": [(3, "не указан верный ответ")]})
    assert "НИ ОДНА не годится" in line


def test_a_healthy_bank_shows_what_is_left():
    line = pd.health_line({"total": 20, "good": 20, "published": 15,
                           "fresh": 5, "broken": []})
    assert "15 из 20" in line
    assert "осталось 5" in line


def test_running_out_is_not_an_error():
    """Повтор — не сбой: через месяц задача читается заново."""
    line = pd.health_line({"total": 9, "good": 9, "published": 9,
                           "fresh": 0, "broken": []})
    assert "по второму кругу" in line


def test_broken_puzzles_are_named_with_the_reason():
    """Чтобы чинить, надо знать, какую и что в ней не так."""
    line = pd.health_line({"total": 20, "good": 18, "published": 15,
                           "fresh": 3,
                           "broken": [(3, "не указан верный ответ")]})
    assert "№3" in line
    assert "не указан верный ответ" in line


def test_only_a_few_broken_ones_are_listed():
    """Двадцать строк с номерами — уже не отчёт, а свалка."""
    broken = [(i, "не указан верный ответ") for i in range(1, 21)]
    line = pd.health_line({"total": 20, "good": 0, "published": 0,
                           "fresh": 0, "broken": broken})
    assert line.count("№") <= 3


def test_the_reason_reaches_the_report():
    """Раньше отказ был только в логах Render."""
    import digest
    body = inspect.getsource(digest.publish_slot)
    assert 'f"задача дня: {result}"' in body


def test_the_report_shows_the_bank():
    import digest
    body = inspect.getsource(digest)
    assert "puzzle_daily.health_line" in body
