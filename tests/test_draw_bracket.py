"""Тесты на олимпийскую сетку розыгрыша (draw_bracket.py).

Сетка нужна, когда «угадал всё» набралось больше, чем призов: три приза
между восемью не делятся. Здесь только арифметика — ни базы, ни Telegram,
поэтому проверить её можно целиком.
"""

import draw_bracket as b


# ---------------------------------------------------------------------
# Размер
# ---------------------------------------------------------------------


def test_size_rounds_up_to_a_power_of_two():
    assert b.bracket_size(6) == 8
    assert b.bracket_size(8) == 8
    assert b.bracket_size(9) == 16
    assert b.bracket_size(2) == 2


def test_one_player_needs_no_bracket():
    """Один угадавший — приз без игры, а не сетка на одного."""
    assert b.bracket_size(1) == 0
    assert b.bracket_size(0) == 0


# ---------------------------------------------------------------------
# Посев и пропуски круга
# ---------------------------------------------------------------------


def test_top_seeds_are_in_different_halves():
    """Первый и второй посевы должны встретиться только в финале."""
    slots = b.seed_slots([1, 2, 3, 4, 5, 6, 7, 8])
    half = len(slots) // 2
    assert 1 in slots[:half]
    assert 2 in slots[half:]


def test_the_first_seed_meets_the_last():
    slots = b.seed_slots([1, 2, 3, 4, 5, 6, 7, 8])
    assert b.pairs(slots)[0] == (1, 8)


def test_byes_go_to_the_top_seeds():
    """Шестеро в сетке на восемь: два пропуска — сильнейшим по таблице,
    как принято везде."""
    slots = b.seed_slots([1, 2, 3, 4, 5, 6])
    first_round = b.pairs(slots)
    with_bye = [p[0] if p[1] is None else p[1]
                for p in first_round if None in p]
    assert sorted(with_bye) == [1, 2]


def test_every_slot_is_filled_or_a_bye():
    slots = b.seed_slots([1, 2, 3, 4, 5])
    assert len(slots) == 8
    assert sorted(x for x in slots if x is not None) == [1, 2, 3, 4, 5]
    assert slots.count(None) == 3


def test_a_full_bracket_has_no_byes():
    assert None not in b.seed_slots([1, 2, 3, 4])


# ---------------------------------------------------------------------
# Кто проходит дальше
# ---------------------------------------------------------------------


def test_a_higher_score_wins():
    assert b.advance(("a", "c"), {"a": 12, "c": 30}) == "c"


def test_a_bye_passes_through():
    assert b.advance(("a", None), {}) == "a"
    assert b.advance((None, "c"), {}) == "c"


def test_the_only_one_who_played_wins_even_with_one_point():
    """Явка важнее счёта: круги короткие, и «пришёл и сыграл» — это
    ровно то, о чём мы просим."""
    assert b.advance(("a", "c"), {"a": 1}) == "a"


def test_nobody_played_so_the_better_seed_goes_on():
    """Снять обоих нельзя — в следующем круге осталось бы пустое место."""
    assert b.advance(("a", "c"), {}, seeds={"a": 3, "c": 1}) == "c"


def test_an_equal_score_is_settled_by_seed():
    got = b.advance(("a", "c"), {"a": 20, "c": 20}, seeds={"a": 5, "c": 2})
    assert got == "c"


def test_an_empty_pair_advances_nobody():
    assert b.advance((None, None), {}) is None


# ---------------------------------------------------------------------
# Круги
# ---------------------------------------------------------------------


def test_a_round_halves_the_field():
    slots = b.seed_slots([1, 2, 3, 4, 5, 6, 7, 8])
    nxt = b.next_round(slots, {x: x for x in range(1, 9)})
    assert len(nxt) == 4


def test_byes_survive_the_first_round_without_playing():
    slots = b.seed_slots([1, 2, 3, 4, 5, 6])
    nxt = b.next_round(slots, {3: 50, 4: 10, 5: 70, 6: 20},
                       seeds={i: i for i in range(1, 7)})
    assert 1 in nxt and 2 in nxt


def test_rounds_left_counts_correctly():
    assert b.rounds_left(8) == 3
    assert b.rounds_left(4) == 2
    assert b.rounds_left(2) == 1


def test_round_names_are_russian_and_plain():
    assert b.round_name(2) == "Финал"
    assert b.round_name(4) == "Полуфинал"
    assert b.round_name(8) == "Четвертьфинал"
    assert b.round_name(16) == "1/8 финала"


# ---------------------------------------------------------------------
# Призовые места
# ---------------------------------------------------------------------


def test_three_places_come_out_of_the_final_and_the_third_place_match():
    got = b.places(["a", "c"], ("d", "e"),
                   {"a": 40, "c": 10, "d": 5, "e": 25})
    assert got == ["a", "c", "e"]


def test_without_a_third_place_match_only_two_places():
    assert b.places(["a", "c"], None, {"a": 40, "c": 10}) == ["a", "c"]


def test_places_need_exactly_two_finalists():
    assert b.places(["a"], None, {}) == []


def test_the_ceiling_on_players_is_sane():
    """Больше четырёх кругов вечером не сыграть — лучше отсечь по
    таблице, чем разводить неявки."""
    assert b.MAX_PLAYERS == 16
    assert b.rounds_left(b.MAX_PLAYERS) == 4
