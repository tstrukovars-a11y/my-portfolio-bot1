"""Тесты на картинку сетки (draw_image.py).

Знак участника выдаём мы, а не берём фотографию профиля: человек ставил
её для друзей, а не для рассылки, которую получат все участники. Значит,
знак обязан быть узнаваемым и постоянным — на этом тут половина проверок.
"""

import draw_image as di


# ---------------------------------------------------------------------
# Знак участника
# ---------------------------------------------------------------------


def test_the_same_person_always_gets_the_same_mark():
    """Иначе в сетке себя не узнать."""
    assert di.mark_of(123456) == di.mark_of(123456)


def test_neighbouring_ids_get_different_shapes():
    """Пока номер делили без перемешивания, у соседних номеров выходила
    ОДНА фигура, и вся сетка была из одинаковых значков разного цвета."""
    shapes = {di.mark_of(uid)[1] for uid in range(101, 109)}
    assert len(shapes) >= 4


def test_marks_use_the_declared_palette_and_shapes():
    colour, shape = di.mark_of(777)
    assert colour in di.PALETTE
    assert shape in di.SHAPES


def test_a_negative_id_does_not_break_the_mark():
    colour, shape = di.mark_of(-5)
    assert colour in di.PALETTE and shape in di.SHAPES


def test_every_shape_can_actually_be_drawn():
    """Опечатка в имени фигуры рисовала бы пустой кружок молча."""
    for shape in di.SHAPES:
        uid = next(u for u in range(1, 5000) if di.mark_of(u)[1] == shape)
        img = di.avatar(uid, 48)
        assert img.size == (48, 48)
        assert img.getbbox() is not None, shape


# ---------------------------------------------------------------------
# Подписи колонок
# ---------------------------------------------------------------------


def test_columns_are_named_by_slots_not_by_survivors():
    """Шесть игроков в сетке на восемь — это четвертьфинал с двумя
    проходами, а не «1/3 финала»."""
    titles = di.column_titles([[1] * 8, [1] * 4, [1] * 4])
    assert titles[0] == "Четвертьфинал"


def test_the_last_column_says_both_matches_are_there():
    """Из четырёх боксов подряд иначе не понять, кто за что играет."""
    titles = di.column_titles([[1] * 8, [1] * 4, [1] * 4])
    assert titles[-1] == "Финал и матч за третье место"


def test_a_two_player_bracket_is_just_a_final():
    assert di.column_titles([[1, 2]]) == ["Финал"]


def test_a_sixteen_bracket_starts_at_one_eighth():
    titles = di.column_titles([[1] * 16, [1] * 8, [1] * 4, [1] * 4])
    assert titles[0] == "1/8 финала"


# ---------------------------------------------------------------------
# Сама картинка
# ---------------------------------------------------------------------


def _png(data):
    return data[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_full_bracket_renders_to_a_png():
    rounds = [[1, None, 4, 5, 2, None, 3, 6], [1, 4, 2, 3], [1, 2, 4, 3]]
    names = {i: f"Игрок{i}" for i in range(1, 7)}
    data = di.render(rounds, names, {1: 30, 2: 12})
    assert _png(data)
    assert len(data) > 1000


def test_byes_are_named_in_russian_not_left_blank():
    """Пустой бокс читается как ошибка отрисовки."""
    import inspect
    assert "проход без игры" in inspect.getsource(di.render)


def test_an_empty_bracket_still_produces_a_picture():
    """Пустая картинка лучше исключения в середине рассылки."""
    assert _png(di.render([], {}))


def test_a_very_long_surname_is_trimmed():
    assert di._short("Константинопольский", 14).endswith("…")
    assert len(di._short("Константинопольский", 14)) == 14


def test_a_missing_name_does_not_render_as_empty():
    assert di._short("") == "участник"
    assert di._short(None) == "участник"
