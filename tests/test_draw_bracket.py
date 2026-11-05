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


def test_nobody_played_so_nobody_goes_on():
    """Оба не явились — оба выбывают. Пустое место в следующем круге
    сетка переваривает как пропуск, а вот проход неявившегося обесценил
    бы само правило про явку."""
    assert b.advance(("a", "c"), {}, seeds={"a": 3, "c": 1}) is None


def test_an_empty_slot_becomes_a_bye_for_the_next_opponent():
    """Продолжение предыдущего: дыра не ломает сетку, а работает
    пропуском."""
    after_noshow = b.advance(("a", "c"), {})
    assert b.advance((after_noshow, "d"), {"d": 10}) == "d"


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


def test_four_places_come_out_of_the_final_and_the_third_place_match():
    """Четвёртое возвращается тоже: человек дошёл до последнего круга и
    проиграл один матч — ему полагается утешительный приз."""
    got = b.places(["a", "c"], ("d", "e"),
                   {"a": 40, "c": 10, "d": 5, "e": 25})
    assert got == ["a", "c", "e", "d"]


def test_only_the_top_three_are_announced():
    """Четвёртое место не объявляется: это звучит как «почти». За
    призом зовём лично."""
    loud, quiet = b.announced(["a", "c", "e", "d"], prizes=3)
    assert loud == ["a", "c", "e"]
    assert quiet == ["d"]


def test_how_many_are_announced_is_a_number_not_a_rule():
    """Захотим объявлять пятерых — меняется одно число, а не код."""
    loud, quiet = b.announced(["a", "c", "e", "d"], prizes=4)
    assert quiet == []
    assert len(loud) == 4


def test_without_a_third_place_match_only_two_places():
    assert b.places(["a", "c"], None, {"a": 40, "c": 10}) == ["a", "c"]


def test_places_need_exactly_two_finalists():
    assert b.places(["a"], None, {}) == []


def test_the_ceiling_on_players_is_sane():
    """Больше четырёх кругов вечером не сыграть — лучше отсечь по
    таблице, чем разводить неявки."""
    assert b.MAX_PLAYERS == 16
    assert b.rounds_left(b.MAX_PLAYERS) == 4


# ---------------------------------------------------------------------
# Развязка кругов
# ---------------------------------------------------------------------
#
# Финал и матч за третье место идут в ОДНОМ окне: иначе вечер
# растягивается на лишний круг ради одной бронзы. Поэтому полуфинал
# отдаёт четыре места, а не два.


def test_the_semifinal_hands_over_four_slots():
    """Двое в финал, двое — за третье место."""
    nxt, done = b.step(["a", "c", "d", "e"], round_no=1, size=4,
                       scores={"a": 30, "c": 10, "d": 5, "e": 40})
    assert done == []
    assert nxt == ["a", "e", "c", "d"]


def test_the_last_round_gives_three_places():
    nxt, done = b.step(["a", "e", "c", "d"], round_no=2, size=4,
                       scores={"a": 50, "e": 20, "c": 9, "d": 31})
    assert nxt == []
    assert done == ["a", "e", "d", "c"]


def test_a_two_player_bracket_has_no_third_place():
    nxt, done = b.step(["a", "c"], round_no=1, size=2,
                       scores={"a": 10, "c": 40})
    assert nxt == []
    assert done == ["c", "a"]


def test_an_early_round_just_halves():
    slots = b.seed_slots([1, 2, 3, 4, 5, 6, 7, 8])
    nxt, done = b.step(slots, round_no=1, size=8,
                       scores={x: x * 10 for x in range(1, 9)})
    assert done == []
    assert len(nxt) == 4


def test_an_eight_bracket_runs_exactly_three_rounds():
    """Четвертьфинал, полуфинал, последний круг — и всё."""
    assert b.last_round_no(8) == 3


def test_the_loser_of_a_pair_is_the_other_one():
    assert b.loser(("a", "c"), "a") == "c"
    assert b.loser(("a", "c"), "c") == "a"
    assert b.loser(("a", None), "a") is None


def test_a_full_eight_bracket_plays_out_to_three_winners():
    """Сквозной прогон: восемь участников, три круга, три призёра."""
    slots = b.seed_slots([1, 2, 3, 4, 5, 6, 7, 8])
    seeds = {i: i for i in range(1, 9)}
    scores = {i: 100 - i for i in range(1, 9)}   # чем выше посев, тем лучше счёт

    round_no, done = 1, []
    while not done:
        slots, done = b.step(slots, round_no, 8, scores, seeds)
        round_no += 1
        assert round_no < 10, "сетка не сошлась"

    assert len(done) == 4
    assert len(set(done)) == 4


# ---------------------------------------------------------------------
# Пара из двух пропусков
# ---------------------------------------------------------------------
#
# Матч без единого участника — худшая поломка сетки: следующий круг
# получает пустое место, и выбраться из этого он уже не может. В
# турнирном боте на это стоит отдельная защита, и не зря.


def test_no_empty_pair_in_any_lineup():
    """Перебор всех составов до шестнадцати, а не выборочная проверка."""
    for count in range(2, 17):
        slots = b.seed_slots(list(range(1, count + 1)))
        for pair in b.pairs(slots):
            assert pair != (None, None), f"игроков {count}"


def test_an_oversized_bracket_is_shrunk_instead_of_leaving_holes():
    """Восемь мест на двоих — это три пары пустых. Размер урезаем до
    необходимого, а не доверяем вызывающему."""
    slots = b.seed_slots([1, 2], size=8)
    assert len(slots) == 2
    assert b.pairs(slots) == [(1, 2)]


def test_an_oversized_bracket_never_leaves_an_empty_pair():
    for count in range(2, 9):
        for size in (8, 16):
            slots = b.seed_slots(list(range(1, count + 1)), size=size)
            for pair in b.pairs(slots):
                assert pair != (None, None), f"{count} игроков в сетке {size}"


def test_a_smaller_size_is_still_honoured():
    """Урезаем только завышенный размер. Заниженный — осознанный выбор
    вызывающего (отсечь лишних), и его не трогаем."""
    assert len(b.seed_slots([1, 2, 3, 4, 5, 6], size=4)) == 4


# ---------------------------------------------------------------------
# Равный счёт решается игрой, а не прошлым действием
# ---------------------------------------------------------------------
#
# Посев у нас задаётся тем, кто раньше ответил на прогнозы, — это другое
# действие и другой день. Человек отыграл круг и проигрывал бы за то, что
# когда-то нажал кнопку позже. Обидно и несправедливо.


def test_equal_best_is_settled_by_total_played():
    """Сумма попыток — тоже игра, просто другая её сторона."""
    got = b.advance(("a", "c"), {"a": 30, "c": 30},
                    seeds={"a": 1, "c": 9},
                    totals={"a": 40, "c": 95})
    assert got == "c"


def test_the_seed_never_outranks_the_game():
    """Верхний посев проигрывает, если наиграл меньше."""
    got = b.advance(("a", "c"), {"a": 30, "c": 30},
                    seeds={"a": 0, "c": 15},
                    totals={"a": 31, "c": 120})
    assert got == "c"


def test_the_seed_is_the_last_resort_only():
    """Когда по игре неразличимо ничем — тогда да, посев."""
    got = b.advance(("a", "c"), {"a": 30, "c": 30},
                    seeds={"a": 7, "c": 2},
                    totals={"a": 50, "c": 50})
    assert got == "c"


def test_a_clear_win_ignores_totals_entirely():
    """Кто выиграл партию, тот выиграл: сумма тут ни при чём."""
    got = b.advance(("a", "c"), {"a": 90, "c": 10},
                    totals={"a": 90, "c": 400})
    assert got == "a"


def test_totals_are_optional():
    """Старые вызовы без сумм не должны падать."""
    assert b.advance(("a", "c"), {"a": 5, "c": 9}) == "c"
