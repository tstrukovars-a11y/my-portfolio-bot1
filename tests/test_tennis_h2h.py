"""Тесты на личные встречи перед матчем (tennis_h2h.py).

Статистику присылает владелица: у источника табло истории встреч нет, а
выдумывать её запрещено тем же правилом, по которому отложено движение
по рейтингу. Значит, главное здесь — чтобы присланное попало в пост без
искажений, а неправдоподобное не попало вовсе.
"""

import tennis_h2h as h2h


# ---------------------------------------------------------------------
# Разбор заголовка матча
# ---------------------------------------------------------------------


def test_names_are_split_on_a_long_dash():
    assert h2h._names("Рублёв — Алькарас") == ("Рублёв", "Алькарас")


def test_names_survive_a_short_dash():
    """Заголовок приходит из разных мест, и тире в нём не всегда одно."""
    assert h2h._names("Рублёв - Алькарас") == ("Рублёв", "Алькарас")


def test_a_title_without_a_dash_does_not_crash():
    assert h2h._names("матч") == ("матч", "")


# ---------------------------------------------------------------------
# Текст про встречи
# ---------------------------------------------------------------------


def _block(**fields):
    return h2h._stats_block("Рублёв", "Алькарас", fields)


def test_no_meetings_is_said_plainly():
    """«Личные встречи: 0» — отписка. Человек хочет прочесть фразу."""
    assert _block(meetings=0) == "Играют между собой впервые."


def test_score_is_counted_from_one_number():
    """Второе число считает бот: два введённых могли бы противоречить
    друг другу, и в посте оказалось бы 3:3 из четырёх встреч."""
    text = _block(meetings=4, wins_first=1)
    assert "Личные встречи: 4" in text
    assert "Счёт — 1:3" in text


def test_the_leader_is_named_after_a_colon():
    """Фамилии нельзя склонять автоматически, поэтому имя ставится после
    двоеточия, а не в середину фразы."""
    assert "впереди: Алькарас" in _block(meetings=4, wins_first=1)
    assert "впереди: Рублёв" in _block(meetings=4, wins_first=3)


def test_an_even_score_names_nobody():
    text = _block(meetings=4, wins_first=2)
    assert "поровну" in text
    assert "впереди" not in text


def test_surfaces_and_years_appear_when_given():
    text = _block(meetings=2, wins_first=1, surfaces="хард, грунт",
                  years="2024, 2025")
    assert "Покрытия: хард, грунт" in text
    assert "Годы: 2024, 2025" in text


def test_skipped_fields_leave_no_empty_lines():
    text = _block(meetings=2, wins_first=1, surfaces=None, years=None)
    assert "Покрытия" not in text
    assert "Годы" not in text


def test_the_note_goes_last():
    text = _block(meetings=2, wins_first=1, note="Оба идут без поражений.")
    assert text.rstrip().endswith("Оба идут без поражений.")


def test_html_in_the_note_is_escaped():
    """Владелица пишет текст руками, и «<» в нём не должен ронять пост."""
    text = _block(meetings=1, wins_first=1, note="матч <b>года")
    assert "&lt;b&gt;" in text


# ---------------------------------------------------------------------
# Что уходит в канал
# ---------------------------------------------------------------------


def test_preview_has_a_heading_and_the_pair():
    row = {"title": "Рублёв — Алькарас", "meetings": 4, "wins_first": 1,
           "surfaces": "хард", "years": "2025", "note": None}
    text = h2h.preview_text(row)
    assert "Перед матчем" in text
    assert "Рублёв — Алькарас" in text
    assert "Счёт — 1:3" in text


def test_preview_works_for_a_first_ever_meeting():
    row = {"title": "Рублёв — Алькарас", "meetings": 0, "wins_first": 0}
    assert "впервые" in h2h.preview_text(row)


# ---------------------------------------------------------------------
# Пропуск необязательного
# ---------------------------------------------------------------------


def test_dashes_and_words_both_mean_skip():
    for word in ("-", "–", "—", "нет", "Пропустить", " далее "):
        assert h2h._skipped(word), word


def test_a_real_answer_is_not_a_skip():
    assert not h2h._skipped("хард, грунт")
    assert not h2h._skipped("2024")


# ---------------------------------------------------------------------
# Граница «служебное не выходит в канал»
# ---------------------------------------------------------------------


def test_filling_buttons_are_not_allowed_under_channel_posts():
    """Диалог заполнения живёт только в личке у владелицы. Если такая
    кнопка однажды окажется под постом, граница её не пропустит."""
    import public
    assert not public.allowed("h2hfill_atp_123")
    assert not public.allowed("h2hgo_atp_123")


def test_there_is_a_ceiling_on_meetings():
    """Защита не от злого умысла, а от опечатки: «44» вместо «4» уехало
    бы в канал как факт."""
    assert 0 < h2h.MAX_MEETINGS <= 100
