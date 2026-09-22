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
    async def no_rate(src=None, dst=None):
        return 0.035

    monkeypatch.setattr(exchange, "cross_rate", no_rate)
    text = run(exchange.report(50000))
    assert "сервисов пока нет" in text


def test_report_survives_missing_rates(settings, monkeypatch):
    async def no_rate(src=None, dst=None):
        return None

    monkeypatch.setattr(exchange, "cross_rate", no_rate)
    run(exchange.save_services([SERVICE]))
    text = run(exchange.report(50000))
    assert "Курс сейчас недоступен" in text
    assert "0 ₪" not in text, "показали ноль вместо честного «не знаю»"


def test_report_shows_the_gap_in_money(settings, monkeypatch):
    async def rate(src=None, dst=None):
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
    async def rate(src=None, dst=None):
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


# --- четыре страны ----------------------------------------------------
#
# Карты будут в России, Израиле, США и Франции. Направлений между ними
# двенадцать, и половина ошибок здесь — перепутанная сторона: считать
# комиссию в валюте получателя значит соврать в разы.

@pytest.mark.parametrize("text,expected", [
    ("USD→ILS", ("USD", "ILS")),
    ("rub-ils", ("RUB", "ILS")),
    ("₽ → ₪", ("RUB", "ILS")),
    ("eur usd", ("EUR", "USD")),
])
def test_direction_is_understood_in_any_form(text, expected):
    assert exchange.parse_pair(text) == expected


@pytest.mark.parametrize("text", ["чушь", "RUB→RUB", "USD", ""])
def test_nonsense_is_not_a_direction(text):
    assert exchange.parse_pair(text) is None


def test_service_remembers_its_direction():
    item = exchange.parse_service("Wise | USD→EUR | https://w.com | 0.6%")
    assert (item["from"], item["to"]) == ("USD", "EUR")


def test_service_without_direction_falls_back():
    """Старые записи заводились без направления — они не должны пропасть."""
    item = exchange.parse_service("Старый сервис | 1%")
    assert (item["from"], item["to"]) == exchange.DEFAULT_PAIR


def test_report_shows_only_its_own_direction(settings, monkeypatch):
    async def rate(src=None, dst=None):
        return 0.9

    monkeypatch.setattr(exchange, "cross_rate", rate)
    run(exchange.save_services([
        {"name": "Для шекелей", "from": "RUB", "to": "ILS", "percent": 1},
        {"name": "Для евро", "from": "USD", "to": "EUR", "percent": 1},
    ]))
    text = run(exchange.report(500, "USD", "EUR"))
    assert "Для евро" in text
    assert "Для шекелей" not in text, "смешали направления"


def test_empty_direction_says_so(settings, monkeypatch):
    async def rate(src=None, dst=None):
        return 0.9

    monkeypatch.setattr(exchange, "cross_rate", rate)
    run(exchange.save_services([{"name": "Только рубли", "from": "RUB", "to": "ILS"}]))
    assert "по этому направлению сервисов пока нет" in \
        run(exchange.report(500, "USD", "EUR")).lower()


def test_fee_is_shown_in_the_sending_currency(settings, monkeypatch):
    """Комиссия берётся с того, что отправляем, и в той же валюте."""
    async def rate(src=None, dst=None):
        return 0.9

    monkeypatch.setattr(exchange, "cross_rate", rate)
    run(exchange.save_services([
        {"name": "Сервис", "from": "USD", "to": "EUR", "fixed": 5}]))
    text = run(exchange.report(500, "USD", "EUR"))
    assert "5.00 $" in text or "5 $" in text


def test_only_filled_directions_get_buttons(settings):
    items = [{"name": "A", "from": "RUB", "to": "ILS"},
             {"name": "B", "from": "USD", "to": "EUR"},
             {"name": "C", "from": "RUB", "to": "ILS"}]
    assert exchange.pairs_with_services(items) == [("RUB", "ILS"), ("USD", "EUR")]


def test_amount_steps_fit_the_currency():
    """Сто тысяч долларов так же нелепы, как пятьсот рублей."""
    assert max(exchange.MONEY["RUB"]["steps"]) > max(exchange.MONEY["USD"]["steps"])
    assert all(code in exchange.MONEY for code in ("RUB", "USD", "EUR", "ILS"))


def test_all_four_currencies_have_a_rate_source():
    """Курс берётся из fx_rates — валюты без ряда там посчитать нечем."""
    import fx_rates

    known = set(fx_rates.CURRENCIES) | {"USD"}
    assert set(exchange.MONEY) <= known


# --- свои переводы ----------------------------------------------------
#
# Витрина показывает курс, а не итог, и почти всегда лучше правды.
# Единственный источник настоящих цифр — собственная выписка, поэтому
# расчёт потери должен быть точным: на нём потом строится сравнение.

def test_loss_is_counted_from_the_exchange_rate():
    """Точка отсчёта — сколько дошло бы по биржевому курсу."""
    assert exchange.real_loss(50000, 1736, 0.0351) == pytest.approx(
        (50000 * 0.0351 - 1736) / (50000 * 0.0351) * 100)


def test_perfect_transfer_loses_nothing():
    assert exchange.real_loss(1000, 35, 0.035) == pytest.approx(0)


def test_loss_never_goes_negative():
    """Курс на день записи и на день перевода разные — в минус уходить
    нельзя, иначе получится «сервис доплатил»."""
    assert exchange.real_loss(1000, 40, 0.035) == 0


def test_loss_survives_a_zero_rate():
    assert exchange.real_loss(1000, 35, 0) == 0


def test_average_is_per_service_and_direction():
    rows = [
        {"name": "A", "from": "RUB", "to": "ILS", "loss": 2.0},
        {"name": "A", "from": "RUB", "to": "ILS", "loss": 4.0},
        {"name": "A", "from": "USD", "to": "EUR", "loss": 1.0},
    ]
    average = exchange.loss_by_service(rows)
    assert average[("A", "RUB", "ILS")] == 3.0
    assert average[("A", "USD", "EUR")] == 1.0


def test_checked_services_are_marked(settings, monkeypatch):
    """Проверенное своим переводом и переписанное с витрины — разные по
    надёжности вещи, и человек вправе это видеть."""
    async def rate(src=None, dst=None):
        return 0.035

    monkeypatch.setattr(exchange, "cross_rate", rate)
    run(exchange.save_services([
        {"name": "Проверенный", "from": "RUB", "to": "ILS", "percent": 1},
        {"name": "С витрины", "from": "RUB", "to": "ILS", "percent": 1.2},
    ]))
    run(exchange.save_log([{"name": "Проверенный", "from": "RUB", "to": "ILS",
                            "sent": 50000, "got": 1700, "loss": 3.0}]))
    text = run(exchange.report(50000, "RUB", "ILS"))
    assert "Проверенный ✓" in text
    assert "С витрины ✓" not in text
    assert "проверены своим переводом" in text


def test_log_keeps_only_the_last_records(settings):
    run(exchange.save_log([{"name": str(i), "from": "RUB", "to": "ILS",
                            "sent": 1, "got": 1, "loss": 0}
                           for i in range(exchange.LOG_MAX + 20)]))
    kept = run(exchange.log())
    assert len(kept) == exchange.LOG_MAX
    assert kept[-1]["name"] == str(exchange.LOG_MAX + 19), "выбросили свежие"
