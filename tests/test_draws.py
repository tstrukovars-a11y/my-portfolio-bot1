"""Тесты на панель конкурса (draws.py).

Пять действий владелицы: начать, завести призы, разослать место
вручения, переписываться с призёрами, завершить фотографией. Здесь —
то, что проверяется без Telegram: имена для ссылок, подписи мест и
граница «служебное в канал не выходит».
"""

import draws


# ---------------------------------------------------------------------
# Короткое имя для ссылки по QR
# ---------------------------------------------------------------------


def test_russian_title_becomes_a_latin_slug():
    assert draws._slug("Северная Пальмира") == "severnaya-palmira"


def test_spaces_and_punctuation_become_single_dashes():
    assert draws._slug("Кубок  клуба — 2026") == "kubok-kluba-2026"


def test_a_slug_never_starts_or_ends_with_a_dash():
    got = draws._slug("  — Пальмира —  ")
    assert not got.startswith("-") and not got.endswith("-")


def test_an_empty_title_still_gives_a_usable_slug():
    """Пустое имя в ссылку попасть не должно — там будет «event»."""
    assert draws._slug("") == "event"
    assert draws._slug("!!!") == "event"


def test_a_slug_is_short_enough_for_a_link():
    assert len(draws._slug("Очень длинное название " * 10)) <= 40


# ---------------------------------------------------------------------
# Подписи мест
# ---------------------------------------------------------------------


def test_the_podium_has_medals():
    assert "🥇" in draws._place_word(1)
    assert "🥈" in draws._place_word(2)
    assert "🥉" in draws._place_word(3)


def test_the_fourth_place_has_no_medal():
    """Четвёртое не объявляется вслух, и медали у него нет."""
    word = draws._place_word(4)
    assert "🥇" not in word and "🥈" not in word and "🥉" not in word
    assert "4" in word


def test_three_places_are_announced_by_default():
    assert draws.DEFAULT_PRIZES == 3


# ---------------------------------------------------------------------
# Граница: служебное в канал не выходит
# ---------------------------------------------------------------------


def test_owner_buttons_never_work_under_a_channel_post():
    """Вся панель живёт в личке. Если кнопка окажется под постом,
    граница обязана её остановить."""
    import public
    for data in ("drnew", "draws_list", "drevent_1", "drprizes_1",
                 "drprize_1_2", "drmeet_1", "drsend_1", "drchat_1",
                 "drtalk_1_42", "drstop_1", "drfinish_1"):
        assert not public.allowed(data), data


def test_the_winner_reply_button_is_also_private():
    """Её нажимает призёр, но тоже в личке — под постом ей не место."""
    import public
    assert not public.allowed("drreply_1")
