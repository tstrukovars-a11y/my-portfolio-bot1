# Откуда берётся цена работы.
#
# Цена без объяснения — число. С объяснением — довод. Разница видна на
# первом же вопросе «а почему столько».
#
# Главное, что здесь проверяется: бот не выдаёт расчёт за экспертизу.
# Сервисы, принимающие фотографию и называющие сумму, считают по
# истории аукционных продаж автора. У автора без такой истории считать
# не из чего, и число у них берётся из воздуха — ровно этого здесь и
# не должно быть.
import pytest

import art_value as av


# --- арифметика --------------------------------------------------------

def test_a_bigger_work_costs_more():
    small = av.estimate(30, 40)["middle"]
    big = av.estimate(60, 80)["middle"]
    assert big > small


def test_the_price_grows_slower_than_the_area():
    """Цена по площади делает большой холст неподъёмным. Метод
    линейного сантиметра — то, чем пользуются сами художники."""
    small = av.estimate(30, 40)["middle"]
    double = av.estimate(60, 80)["middle"]      # площадь вчетверо
    assert double < small * 4


def test_watercolour_is_not_oil():
    assert av.estimate(60, 80, "акварель")["middle"] < \
           av.estimate(60, 80, "холст, масло")["middle"]


def test_sales_history_is_the_main_multiplier():
    """Пока продаж нет, цену держит только размер."""
    none = av.estimate(60, 80, "масло", 0)["middle"]
    some = av.estimate(60, 80, "масло", 5)["middle"]
    many = av.estimate(60, 80, "масло", 20)["middle"]
    assert none < some < many


def test_materials_are_never_lost():
    """Ниже стоимости холста и красок работать в минус."""
    assert av.estimate(10, 10)["middle"] > av.MATERIALS


def test_the_answer_is_a_range_not_a_point():
    """Точное число в рублях — обещание, которого расчёт не даёт."""
    got = av.estimate(60, 80)
    assert got["low"] < got["middle"] < got["high"]


def test_nonsense_sizes_give_nothing():
    assert av.estimate(0, 80) == {}
    assert av.estimate(-5, 80) == {}


# --- заказную работу формулой не считают -------------------------------

@pytest.mark.parametrize("title", [
    "Герб рода Струковых", "Портрет Анны", "Работа на заказ",
])
def test_commissions_are_not_measured_in_centimetres(title):
    """За заказ платят не за размер, а за то, чего нет ни у кого
    другого. Родовой знак существует в одном экземпляре."""
    assert av.is_commission(title)


def test_a_landscape_is_not_a_commission():
    assert not av.is_commission("Тишина в полдень", "холст, масло")


def test_the_commission_answer_explains_instead_of_counting():
    text = av.explain(50, 40, "картон, масло", 1, "Герб рода Струковых")
    assert "формулой не считают" in text
    assert "₽" not in text, "заказу всё-таки подставили цену"


# --- честность ---------------------------------------------------------

def test_the_answer_says_it_is_not_an_appraisal():
    """Оценку даёт эксперт и выдаёт документом. Программа этого не
    умеет — ей неоткуда взять то, что знает эксперт."""
    text = av.explain(60, 80, "масло", 0)
    assert "не оценка" in text
    assert "эксперт" in text


def test_the_arithmetic_is_shown():
    """Непрозрачный расчёт убедителен ровно до первого недоверчивого
    человека, а показанный работает и с ним."""
    text = av.explain(60, 80, "холст, масло", 0)
    assert "60 + 80" in text
    assert "350" in text
    assert "материалы" in text


def test_an_author_without_sales_is_told_what_moves_the_price():
    """Самое полезное для автора — не число, а то, что его двигает."""
    text = av.explain(60, 80, "масло", 0)
    assert "Что поднимает цену" in text


def test_a_selling_author_is_not_lectured():
    text = av.explain(60, 80, "масло", 10)
    assert "Что поднимает цену" not in text


# --- разбор размера ----------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("60 на 80", (60, 80)), ("60x80", (60, 80)), ("60х80 см", (60, 80)),
    ("24,5 × 30", (24.5, 30)),
])
def test_the_size_is_read_however_it_is_written(text, expected):
    assert av.parse_size(text) == expected


def test_unreadable_size_gives_zero():
    assert av.parse_size("большая такая") == (0.0, 0.0)
