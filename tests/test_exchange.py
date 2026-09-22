# Сколько дойдёт при переводе.
#
# Ошибка здесь стоит чужих денег: человек выберет сервис по нашему
# расчёту и потеряет разницу. Поэтому арифметику проверяем целиком, а не
# на одном примере.
#
# И отдельно — границу: модуль считает и ссылается, но не принимает
# заявки и не сводит людей. Стоит этому измениться, и справочник
# превращается в посредника, которого лицензируют в двух странах.
import pytest

from conftest import run

import config
import exchange


SERVICE = {"name": "Сервис", "url": "https://a.ru",
           "percent": 1.5, "fixed": 100.0, "markup": 0.8}


# --- арифметика -------------------------------------------------------

def test_fee_is_taken_before_the_exchange():
    """Комиссия съедает рубли, а меняется уже остаток."""
    row = exchange.arrives(50000, SERVICE, 0.035)
    assert row["fee"] == pytest.approx(50000 * 0.015 + 100)
    assert row["out"] == pytest.approx((50000 - 850) * 0.035 * 0.992)


def test_markup_makes_the_rate_worse():
    plain = exchange.arrives(10000, {"name": "A"}, 0.035)
    marked = exchange.arrives(10000, {"name": "B", "markup": 2}, 0.035)
    assert marked["out"] < plain["out"]
    assert marked["rate"] == pytest.approx(0.035 * 0.98)


def test_service_without_numbers_takes_nothing():
    row = exchange.arrives(1000, {"name": "Без комиссии"}, 0.035)
    assert row["fee"] == 0
    assert row["out"] == pytest.approx(35)


def test_huge_fee_does_not_go_negative():
    """Иначе на маленькой сумме бот покажет минус шекелей."""
    row = exchange.arrives(50, {"name": "Дорогой", "fixed": 500}, 0.035)
    assert row["out"] == 0


def test_cheapest_rate_does_not_always_win():
    """Реклама показывает курс, а решает итог — ради этого всё и считаем."""
    nice_rate = {"name": "Красивый курс", "markup": 0, "percent": 5}
    plain = {"name": "Скучный", "markup": 1, "percent": 0.5}
    rows = exchange.compare(50000, [nice_rate, plain], 0.035)
    assert rows[0]["name"] == "Скучный"


def test_order_is_by_what_arrives():
    rows = exchange.compare(50000, [
        {"name": "A", "percent": 3},
        {"name": "B", "percent": 1},
        {"name": "C", "percent": 2},
    ], 0.035)
    assert [r["name"] for r in rows] == ["B", "C", "A"]


# --- разбор строки ----------------------------------------------------

def test_percent_and_roubles_are_told_apart():
    """Перепутать их местами легко, а ошибка врёт в деньгах."""
    item = exchange.parse_service("Имя | https://x.ru | 1.5% | 100 | 0.8%")
    assert item["percent"] == 1.5
    assert item["fixed"] == 100
    assert item["markup"] == 0.8
    assert item["url"] == "https://x.ru"


def test_name_alone_is_enough():
    item = exchange.parse_service("Просто имя")
    assert item["name"] == "Просто имя"
    assert item["percent"] == 0 and item["fixed"] == 0


def test_empty_line_is_not_a_service():
    assert exchange.parse_service("") is None
    assert exchange.parse_service("  |  ") is None


# --- экран ------------------------------------------------------------

def test_empty_list_says_so(settings, monkeypatch):
    async def no_rate():
        return 0.035

    monkeypatch.setattr(exchange, "cross_rate", no_rate)
    text = run(exchange.report(50000))
    assert "пуст" in text


def test_report_survives_missing_rates(settings, monkeypatch):
    async def no_rate():
        return None

    monkeypatch.setattr(exchange, "cross_rate", no_rate)
    run(exchange.save_services([SERVICE]))
    text = run(exchange.report(50000))
    assert "Курс сейчас недоступен" in text
    assert "0 ₪" not in text, "показали ноль вместо честного «не знаю»"


def test_report_shows_the_gap_in_money(settings, monkeypatch):
    async def rate():
        return 0.035

    monkeypatch.setattr(exchange, "cross_rate", rate)
    run(exchange.save_services([
        {"name": "Дешёвый", "percent": 0.5},
        {"name": "Дорогой", "percent": 5},
    ]))
    text = run(exchange.report(50000))
    assert "Дешёвый" in text and "Дорогой" in text
    assert "−" in text, "не видно, сколько теряешь на худшем"


# --- граница ----------------------------------------------------------

def test_disclaimer_is_always_there(settings, monkeypatch):
    """Человек должен понимать, с кем имеет дело, в любом состоянии."""
    async def rate():
        return 0.035

    monkeypatch.setattr(exchange, "cross_rate", rate)
    assert exchange.DISCLAIMER in run(exchange.report(50000))
    run(exchange.save_services([SERVICE]))
    assert exchange.DISCLAIMER in run(exchange.report(50000))


def test_bot_says_plainly_that_it_does_not_transfer():
    low = exchange.DISCLAIMER.lower()
    assert "не переводит деньги" in low
    assert "не принимает заявки" in low


def test_no_way_to_leave_an_order():
    """Приём заявок и сведение людей — это уже посредничество."""
    source = open(exchange.__file__, encoding="utf-8").read()
    for word in ("заявк", "обмен между", "найти человека"):
        assert f'callback_data=f"{word}' not in source


def test_service_list_is_owner_only(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)

    class Msg:
        def __init__(self, text, user_id):
            self.text = text
            self.said = []
            self.from_user = type("U", (), {"id": user_id})()

        async def answer(self, text, **kw):
            self.said.append(text)

    stranger = Msg("/сервисы + Свой | 0%", 999)
    run(exchange.services_command(stranger))
    assert not stranger.said
    assert run(exchange.services()) == []
