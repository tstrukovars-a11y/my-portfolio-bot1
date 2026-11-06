"""Накопленная история — наблюдение, а не факт.

Вчера сыграли, сегодня в статистике одна встреча, а позавчера их было
пять, и мы о них не знаем: своя история начинается с того дня, как мы
начали записывать. Выдать наблюдение за полную историю — соврать, и
соврать правдоподобно.
"""

import tennis_h2h as h2h


FIGURES = {"meetings": 3, "wins_first": 2, "surfaces": "грунт",
           "years": "2025, 2026"}


def test_accumulated_stats_say_what_they_are():
    text = h2h._stats_block("Крыстя", "Шелтон", FIGURES, partial=True)
    assert "Мы видели встреч: 3" in text
    assert "Личные встречи" not in text


def test_manual_stats_stay_a_statement_of_fact():
    """Заполненное владелицей — полная история пары, и оговорка там
    только мешала бы."""
    text = h2h._stats_block("Крыстя", "Шелтон", FIGURES)
    assert "Личные встречи: 3" in text
    assert "видели сами" not in text


def test_accumulated_stats_carry_the_caveat():
    text = h2h._stats_block("Крыстя", "Шелтон", FIGURES, partial=True)
    assert "более ранние встречи сюда не вошли" in text


def test_an_empty_accumulated_history_says_nothing_at_all():
    """«Играют впервые» по пустой своей истории — прямая неправда: мы
    просто не видели их матчей."""
    assert h2h._stats_block("А", "Б", {"meetings": 0}, partial=True) == ""


def test_an_empty_manual_history_does_say_it():
    assert h2h._stats_block("А", "Б", {"meetings": 0}) == "Играют между собой впервые."


def test_the_batch_request_skips_pairs_already_filled():
    """Именно ПАРЫ, а не матчи: те же двое могут встретиться на другом
    турнире — матч новый, а история та же."""
    import inspect
    body = inspect.getsource(h2h.request_batch)
    assert "h2h_filled_pairs" in body
    assert "pair_key" in body


def test_the_batch_request_is_one_message_not_twenty():
    import inspect
    body = inspect.getsource(h2h.request_batch)
    assert "len(rows) >= 10" in body


def test_the_surface_answer_reaches_matches_already_played():
    """Ответ, который достаётся только будущим матчам, оставил бы уже
    сыгранные без покрытия навсегда."""
    import inspect
    assert "h2h_fill_surface" in inspect.getsource(h2h.set_surface)


def test_surface_buttons_are_owner_only():
    import public
    assert not public.allowed("surf_clay_rome")
