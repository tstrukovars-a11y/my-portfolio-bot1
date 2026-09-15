# Мелкие помощники, которые видит читатель: погода, деньги, склонения.
# Ошибка здесь не ломает бота, но выходит в канал и в личку.
import checklist
import weather


# --- погода -----------------------------------------------------------

def test_degrees_always_carry_a_sign():
    """Без знака ноль и минус выглядят одинаково."""
    assert weather._degrees(18) == "+18°"
    assert weather._degrees(-7) == "-7°"
    assert weather._degrees(0) == "+0°"


def test_degrees_survive_nonsense():
    assert weather._degrees(None) == "—"
    assert weather._degrees("тепло") == "—"


def test_weather_code_is_described():
    assert weather._describe(0) == ("☀️", "ясно")
    assert weather._describe(95)[1] == "гроза"
    assert weather._describe(12345)[1] == ""      # незнакомый код не выдумываем


def _hours(codes, chances):
    return {"hourly": {"time": [f"2026-09-15T{h:02d}:00" for h in range(24)],
                       "weather_code": codes, "precipitation_probability": chances}}


def test_umbrella_advice_when_rain_is_likely_in_the_evening():
    codes = [61] * 24
    chances = [0] * 16 + [70] * 8
    assert "зонт" in weather._evening(_hours(codes, chances))


def test_no_advice_when_rain_is_unlikely():
    assert weather._evening(_hours([61] * 24, [10] * 24)) == ""


def test_morning_rain_does_not_count():
    """К вечеру важен вечер: утренний дождь уже никого не касается."""
    chances = [90] * 12 + [0] * 12
    assert weather._evening(_hours([61] * 24, chances)) == ""


def test_snow_is_advised_differently():
    chances = [0] * 16 + [80] * 8
    assert "теплее" in weather._evening(_hours([73] * 24, chances))


def test_empty_forecast_is_silent():
    assert weather._evening({}) == ""


# --- деньги и названия ------------------------------------------------

def test_money_is_grouped_and_rounded():
    assert checklist._money(1250) == "1 250 ₽"
    assert checklist._money(0) == "0 ₽"
    assert checklist._money(1234567.4) == "1 234 567 ₽"


def test_money_survives_nonsense():
    assert checklist._money(None) == "— ₽"
    assert checklist._money("много") == "— ₽"


def test_shop_name_from_a_human_word():
    assert checklist._shop_name("литрес") == "Литрес"
    assert checklist._shop_name("ЧИТАЙ") == "Читай-город"
    assert checklist._shop_name("книжный") == "Книжный"
