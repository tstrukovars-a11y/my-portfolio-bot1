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
                 "drprize_1_2", "drmeet_1", "drsend_1", "drsched_1",
                 "drlaunch_1", "drtalk_1_42", "drstop_1", "drfinish_1"):
        assert not public.allowed(data), data


def test_only_the_join_button_works_in_the_channel():
    """«Участвовать» висит под постом канала — ей можно. И только ей."""
    import public
    assert public.allowed("drjoin_1")


def test_the_winner_reply_button_is_also_private():
    """Её нажимает призёр, но тоже в личке — под постом ей не место."""
    import public
    assert not public.allowed("drreply_1")


# ---------------------------------------------------------------------
# Расписание матчей
# ---------------------------------------------------------------------
#
# Заводится одним сообщением: по строке на матч. Вопрос по каждому
# уходит участникам в минуту начала, а не заранее — зритель отвечает,
# глядя на корт.

from datetime import date


DAY = date(2026, 11, 7)


def test_a_simple_line_is_parsed():
    good, bad = draws.parse_schedule("18:00 Окунев — Кураков", DAY)
    assert bad == []
    when, first, second = good[0]
    assert (when.hour, when.minute) == (18, 0)
    assert (first, second) == ("Окунев", "Кураков")


def test_several_lines_become_several_matches():
    good, _ = draws.parse_schedule(
        "18:00 Окунев — Кураков\n19:30 Новиков — Кабочкин", DAY)
    assert len(good) == 2
    assert good[1][0].hour == 19 and good[1][0].minute == 30


def test_any_dash_works():
    """Заставлять набирать длинное тире — верный способ получить
    «не разобралось» на половине списка."""
    for dash in ("—", "–", "-", "vs"):
        good, bad = draws.parse_schedule(f"18:00 Окунев {dash} Кураков", DAY)
        assert len(good) == 1, dash
        assert bad == [], dash


def test_a_dot_in_the_time_is_accepted():
    good, _ = draws.parse_schedule("18.45 Окунев — Кураков", DAY)
    assert good[0][0].minute == 45


def test_blank_lines_are_skipped_silently():
    good, bad = draws.parse_schedule(
        "\n18:00 Окунев — Кураков\n\n\n", DAY)
    assert len(good) == 1 and bad == []


def test_a_broken_line_is_reported_not_swallowed():
    """Молча проглотить строку расписания хуже, чем сказать «вот эту я
    не поняла»: матч бы просто не состоялся в конкурсе."""
    good, bad = draws.parse_schedule(
        "18:00 Окунев — Кураков\nкогда-нибудь вечером", DAY)
    assert len(good) == 1
    assert bad == ["когда-нибудь вечером"]


def test_a_line_without_a_second_name_is_rejected():
    good, bad = draws.parse_schedule("18:00 Окунев —", DAY)
    assert good == []
    assert len(bad) == 1


def test_a_bad_clock_is_rejected():
    good, bad = draws.parse_schedule("25:99 Окунев — Кураков", DAY)
    assert good == []
    assert len(bad) == 1


def test_the_answer_window_is_a_quarter_of_an_hour():
    """Зритель отвечает по ходу матча, а не до него."""
    assert draws.POLL_MINUTES == 15
