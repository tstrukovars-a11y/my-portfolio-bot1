# Индексы: термометр событий, а не витрина бумаг.
#
# Главное здесь не арифметика, а граница. Подборка отдельных акций, даже
# без слова «покупайте», читается как подсказка, что брать, — а это
# рекомендация по вложениям, и она требует лицензии, которой нет.
#
# Поэтому тесты сторожат две вещи: что считаем верно и что не скатываемся
# в отдельные бумаги.
import pytest

import indices


RISING = [100.0, 101.0, 102.0, 105.0]
FALLING = [200.0, 190.0, 180.0, 179.0]


# --- счёт -------------------------------------------------------------

def test_day_move_is_from_the_previous_close():
    day, _ = indices.moves([100.0, 110.0])
    assert day == pytest.approx(10.0)


def test_month_move_is_from_the_start():
    _, month = indices.moves(RISING)
    assert month == pytest.approx(5.0)


def test_single_point_moves_nothing():
    """Один день истории — не повод показать «0%» как факт."""
    assert indices.moves([100.0]) == (0.0, 0.0)
    assert indices.moves([]) == (0.0, 0.0)


def test_zero_base_does_not_divide():
    assert indices.moves([0.0, 5.0]) == (0.0, 0.0)


@pytest.mark.parametrize("value,sign", [(1.5, "▲"), (-1.5, "▼"), (0.0, "=")])
def test_arrow_matches_direction(value, sign):
    assert indices.arrow(value) == sign


def test_tiny_move_is_not_an_arrow():
    """Сотые доли процента — это шум, а стрелка означает движение."""
    assert indices.arrow(0.01) == "="


# --- столбики ---------------------------------------------------------

def test_sparkline_is_trimmed_to_width():
    assert len(indices.sparkline(list(range(100)), width=20)) == 20


def test_flat_row_does_not_divide_by_zero():
    assert indices.sparkline([5.0, 5.0, 5.0]) == indices.BARS[0] * 3


def test_sparkline_rises_with_the_row():
    line = indices.sparkline(RISING, width=4)
    assert line[0] == indices.BARS[0] and line[-1] == indices.BARS[-1]


# --- график -----------------------------------------------------------

def test_chart_compares_in_percent():
    """В абсолютных числах Dow и S&P на одной оси не совместить: меньший
    превращается в прямую."""
    url = indices.chart_url({"^GSPC": RISING})
    assert url.startswith("https://quickchart.io/chart")
    assert "%22data%22" in url
    # Первая точка приведена к нулю, последняя — к пяти процентам.
    from urllib.parse import unquote
    import json

    config = json.loads(unquote(url.split("c=", 1)[1]))
    row = config["data"]["datasets"][0]["data"]
    assert row[0] == 0 and row[-1] == pytest.approx(5.0)


def test_no_data_means_no_chart():
    assert indices.chart_url({}) == ""


def test_zero_base_is_skipped():
    assert indices.chart_url({"^GSPC": [0.0, 1.0]}) == ""


# --- блок в выпуске ---------------------------------------------------

def test_morning_block_is_empty_without_data():
    """Пустой заголовок «Индексы» хуже отсутствия блока."""
    assert indices.morning_block({}) == ""


def test_morning_block_names_all_three():
    block = indices.morning_block({s: RISING for s in indices.INDICES})
    for meta in indices.INDICES.values():
        assert meta["ru"] in block


def test_morning_block_uses_markdown():
    """Выпуск собирается одним сообщением: HTML в нём уронил бы всё."""
    block = indices.morning_block({"^GSPC": RISING})
    assert "*S&P 500*" in block
    assert "<b>" not in block


# --- граница ----------------------------------------------------------

def test_only_indices_no_single_stocks():
    """Отдельная бумага в списке читается как совет её купить."""
    assert set(indices.INDICES) == {"^GSPC", "^DJI", "^IXIC"}
    assert all(symbol.startswith("^") for symbol in indices.INDICES)


def test_screen_says_what_this_is_not():
    assert "не про то, что покупать" in indices.INTRO


def test_nothing_shown_to_people_sounds_like_advice():
    """Проверяем то, что видит читатель, а не комментарии в коде: в них
    это слово как раз и объясняет, почему его нельзя писать."""
    shown = (indices.INTRO + indices.morning_block({"^GSPC": RISING})
             + indices._screen_text({"^GSPC": RISING})).lower()
    for word in ("покупайте", "продавайте", "рекомендуем", "стоит вложить",
                 "советуем"):
        assert word not in shown, word
