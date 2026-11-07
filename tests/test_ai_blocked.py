"""Отказ модели, который сам не пройдёт, должен дойти до владелицы.

Утром выпуск вышел без сводки, а обзор генетики не вышел вовсе. Причина
лежала в настройке «digest_last_error» — то есть была видна только
тому, кто откроет /digest. А поводов открывать нет, пока не заметишь
пропажу: так теряется день, а то и три.
"""

import inspect

import digest


class _Err(Exception):
    pass


def test_a_closed_door_is_recognised():
    """403, кончившиеся средства, отозванный ключ — не пройдёт само."""
    for text in ("PermissionDeniedError: 403 permission_error",
                 "Your credit balance is too low",
                 "billing hard limit reached",
                 "invalid_api_key",
                 "AuthenticationError"):
        assert digest._is_blocked(_Err(text)), text


def test_a_blink_is_not_a_closed_door():
    """Сеть моргнула — завтра соберётся само, беспокоить незачем."""
    for text in ("Connection timed out",
                 "overloaded_error",
                 "ReadTimeout",
                 "Temporary failure in name resolution"):
        assert not digest._is_blocked(_Err(text)), text


def test_the_owner_is_told_once_a_day():
    """Чаще — шум, который перестают читать; реже — потерянный день."""
    body = inspect.getsource(digest.alert_if_blocked)
    assert "ai_blocked_told" in body
    assert "day != today" in body


def test_the_message_says_what_to_do():
    body = inspect.getsource(digest.alert_if_blocked)
    assert "Plans" in body and "Billing" in body


def test_the_message_says_what_is_lost():
    """Чтобы было понятно, чем это грозит, а не только что сломалось."""
    body = inspect.getsource(digest.alert_if_blocked)
    assert "без сводки" in body
    assert "генетик" in body


def test_only_a_closed_door_raises_the_flag():
    body = inspect.getsource(digest._summary)
    assert "_is_blocked(e)" in body
    assert "BLOCKED_KEY" in body


def test_the_check_runs_before_publishing():
    """Сказать о закрытой двери важнее, чем выпустить ещё один урезанный
    пост."""
    body = inspect.getsource(digest.publish_slot)
    assert "alert_if_blocked" in body


# ---------------------------------------------------------------------
# Остаток в справочнике
# ---------------------------------------------------------------------
#
# В отчёте светилось «49 из 48, осталось -1». Отрицательного остатка не
# бывает, но прятать это за нулём нельзя: число опубликованного обогнало
# справочник, и это сигнал — либо из него что-то убрали, либо материал
# вышел дважды.


def test_a_normal_remainder_is_a_number():
    assert digest._stock_left(5, 30) == "осталось 25"


def test_an_exhausted_reference_says_so():
    assert digest._stock_left(13, 13) == "справочник закончился"


def test_an_overrun_is_named_not_hidden():
    got = digest._stock_left(49, 48)
    assert "-1" not in got
    assert "лишних публикаций: 1" in got


def test_an_empty_reference_does_not_look_broken():
    assert digest._stock_left(0, 0) == "справочник закончился"


def test_nothing_ever_shows_a_minus():
    for published in range(0, 60):
        for total in (0, 13, 48):
            assert "-" not in digest._stock_left(published, total)
