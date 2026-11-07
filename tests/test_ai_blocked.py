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


def test_a_deleted_item_is_named_not_hidden():
    """Дважды один материал в журнал не ляжет — там первичный ключ по
    разделу и номеру. Значит, опубликованное удалили из справочника,
    и «лишняя публикация» было бы неправдой."""
    got = digest._stock_left(49, 48)
    assert "-1" not in got
    assert "удалено после публикации: 1" in got


def test_an_empty_reference_does_not_look_broken():
    assert digest._stock_left(0, 0) == "справочник закончился"


def test_nothing_ever_shows_a_minus():
    for published in range(0, 60):
        for total in (0, 13, 48):
            assert "-" not in digest._stock_left(published, total)


# ---------------------------------------------------------------------
# Проверка ключа по команде
# ---------------------------------------------------------------------
#
# После пополнения счёта о том, вернулся доступ или нет, иначе узнаёшь
# только наутро — по тому, вышла сводка или не вышла.


def test_there_is_a_command_to_check_the_key():
    body = inspect.getsource(digest)
    assert '"/aicheck"' in body


def test_a_working_key_clears_the_alarm():
    """Иначе тревога висит до перезапуска и врёт."""
    body = inspect.getsource(digest.ai_check)
    assert "BLOCKED_KEY" in body
    assert "ai_blocked_told" in body


def test_success_clears_the_alarm_by_itself():
    """Не только по команде: сводка собралась — значит доступ вернулся."""
    body = inspect.getsource(digest._summary)
    assert "Доступ к модели восстановился" in body


def test_the_check_is_owner_only():
    body = inspect.getsource(digest.ai_check)
    assert "config.is_admin" in body


def test_a_failed_check_says_what_is_lost():
    body = inspect.getsource(digest.ai_check)
    assert "без сводки" in body


# ---------------------------------------------------------------------
# Источники в служебном экране
# ---------------------------------------------------------------------
#
# Лента отдаёт строки вида «• [заголовок](ссылка)», а разбор искал
# строку, начинающуюся со скобки: маркер ему мешал, совпадения не было,
# и строка уходила в запасную ветку — та приписывала второй маркер.
# В служебном экране светилось «• •», да ещё и ссылка не становилась
# ссылкой.

LENTA = ("• [Genomic data in the All of Us Research Program](https://a.test/1)\n"
         "• [Genomics - AbbVie](https://b.test/2)")


def test_the_bullet_is_not_doubled():
    assert "• •" not in digest._sources_html(LENTA)


def test_a_marked_line_still_becomes_a_link():
    got = digest._sources_html(LENTA)
    assert '<a href="https://a.test/1">' in got
    assert "Genomic data" in got


def test_a_line_without_a_marker_also_works():
    """Разные источники форматируют по-разному — полагаться на маркер
    нельзя ни в ту, ни в другую сторону."""
    got = digest._sources_html("[Заголовок](https://c.test/3)")
    assert '<a href="https://c.test/3">' in got


def test_a_line_without_a_link_keeps_one_bullet():
    got = digest._sources_html("• Просто заголовок без ссылки")
    assert got == "• Просто заголовок без ссылки"


def test_empty_lines_are_skipped():
    got = digest._sources_html("\n•\n   \n[Т](https://d.test/4)")
    assert got.count("•") == 1


def test_a_dash_marker_is_handled_too():
    got = digest._sources_html("- [Заголовок](https://e.test/5)")
    assert got.startswith("• <a href=")
