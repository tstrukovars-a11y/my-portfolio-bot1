"""Расписание заводят заранее — день берётся у мероприятия."""
from datetime import date
from draws import parse_schedule


def test_день_берётся_из_мероприятия_а_не_из_сегодня():
    """Введённое за два дня до турнира получило бы сегодняшнюю дату, и
    вопросы ушли бы в ту же минуту или не ушли бы вовсе."""
    good, bad = parse_schedule("12:35 Рахимова К. — Шнайдер Д.",
                               day=date(2026, 11, 28))
    assert not bad
    when, first, second = good[0]
    assert when.date() == date(2026, 11, 28)
    assert when.hour == 12 and when.minute == 35
    assert first == "Рахимова К." and second == "Шнайдер Д."


def test_несколько_строк_разбираются_подряд():
    good, bad = parse_schedule(
        "12:00 Рахимова К. — Пушкарева А.\n"
        "13:30 Потапова А. — Шнайдер Д.\n"
        "16:30 Бублик А. — Хачанов К.", day=date(2026, 11, 29))
    assert len(good) == 3 and not bad
    assert [w.hour for w, _, _ in good] == [12, 13, 16]


def test_непонятая_строка_не_проглатывается():
    """Молча потерять матч хуже, чем сказать «эту не поняла»."""
    good, bad = parse_schedule("15:00 Б.О.Д — Б.О.Д\nчествование турнира",
                               day=date(2026, 11, 29))
    assert len(good) == 1
    assert bad == ["чествование турнира"]
