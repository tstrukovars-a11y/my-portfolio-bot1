"""Мини-графики в утреннем выпуске.

Столбик ▇ рисуется не текстовым шрифтом: своего знака у того нет, и
система подставляет моноширинный, где столбик выходит примерно в две
трети буквы. На обычном размере двадцать столбиков в строку влезали — а
стоило читателю увеличить шрифт, как Telegram разрывал их по любому
месту. Получался не маленький график, а два неправильных: столбики
второй строки читаются от своего нуля.

Поэтому тесты сторожат две величины, и обе про перенос, а не про
красоту: сколько столбиков в графике и сколько знаков в самой длинной
строке. Третье, что они сторожат, — что ради короткой строки не выкинули
саму цифру.
"""
import asyncio
import inspect

import fx_rates
import indices


# Столько знаков переживает самый крупный шрифт в пузыре телефона.
LIMIT = 26

BARS = set(fx_rates.BARS)


def run(coro):
    return asyncio.run(coro)


def _month(start: float, step: float) -> list:
    return [(f"2026-11-{d:02d}", start + d * step) for d in range(1, 31)]


def fx_block(monkeypatch) -> str:
    async def series():
        return {"EUR": _month(0.8500, 0.0005),
                "ILS": _month(3.2600, -0.0010),
                "RUB": _month(76.00, 0.09)}

    monkeypatch.setattr(fx_rates, "fetch_series", series)
    return run(fx_rates.morning_block())


def ix_block() -> str:
    rows = {"^GSPC": [6680 + i * 5 for i in range(30)],
            "^DJI": [47790 + i * 3 for i in range(30)],
            "^IXIC": [22650 + i * 9 for i in range(30)]}
    return indices.morning_block(rows)


def chart_lines(text: str) -> list:
    return [ln for ln in text.splitlines() if ln and set(ln) <= BARS]


# --- ширина -----------------------------------------------------------

def test_график_курсов_в_двенадцать_столбиков(monkeypatch):
    charts = chart_lines(fx_block(monkeypatch))
    assert charts, "график пропал из блока курсов"
    assert all(len(c) == 12 for c in charts), [len(c) for c in charts]


def test_график_индексов_в_двенадцать_столбиков():
    charts = chart_lines(ix_block())
    assert charts, "график пропал из блока индексов"
    assert all(len(c) == 12 for c in charts), [len(c) for c in charts]


def test_строки_курсов_переживают_крупный_шрифт(monkeypatch):
    """Длинная строка переносится и тащит за собой график: он идёт
    следующей строкой и оказывается на остатке места."""
    long = [ln for ln in fx_block(monkeypatch).splitlines() if len(ln) > LIMIT]
    assert not long, long


def test_строки_индексов_переживают_крупный_шрифт():
    long = [ln for ln in ix_block().splitlines() if len(ln) > LIMIT]
    assert not long, long


def test_экраны_в_боте_на_той_же_ширине():
    """Экран раздела рисует те же столбики и живёт в том же пузыре. Если
    ширина по умолчанию разъедется с утренней, поломка просто переедет
    на один нажим вглубь."""
    for module in (fx_rates, indices):
        width = inspect.signature(module.sparkline).parameters["width"].default
        assert width == 12, f"{module.__name__}: {width}"


# --- что единицы сказаны один раз -------------------------------------

def test_единицы_курсов_названы_один_раз(monkeypatch):
    """«за сутки» и «за месяц» в каждой из трёх строк — это тридцать
    лишних знаков там, где места нет. Шапка блока говорит это за всех."""
    text = fx_block(monkeypatch)
    assert text.count("сутки") == 1, text
    assert text.count("месяц") == 1, text


def test_единицы_индексов_названы_один_раз():
    text = ix_block()
    assert text.count("сутки") == 1, text
    assert text.count("месяц") == 1, text


def test_за_доллар_сказано_хотя_бы_раз(monkeypatch):
    """Курс без «за доллар» — просто число. Короче стало, непонятнее
    стать не должно."""
    assert "доллар" in fx_block(monkeypatch)


# --- что цифры на месте -----------------------------------------------

def test_в_курсах_остались_и_курс_и_оба_движения(monkeypatch):
    """Ради короткой строки легко выкинуть лишнее и выкинуть нужное:
    график показывает форму, а размер движения — только цифра."""
    text = fx_block(monkeypatch)
    assert "Евро" in text and "Шекель" in text and "Рубль" in text
    # Суточное движение — с двумя знаками, месячное — с одним и знаком.
    assert "%" in text
    assert "·" in text, "движения за сутки и за месяц не разделены"
    assert any(ch in text for ch in "▲▼="), "направление пропало"


def test_рубль_с_двумя_знаками_а_евро_с_четырьмя(monkeypatch):
    """У евро суточный сдвиг — тысячные, и в двух знаках он выглядит
    нулём. У рубля четыре знака — мусор."""
    text = fx_block(monkeypatch)
    assert "Евро 0.8" in text
    assert "Рубль 78." in text
