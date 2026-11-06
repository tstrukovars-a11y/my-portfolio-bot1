"""Личное напоминание не должно уехать в канал.

Telegram не различает, кому слать: отрицательный номер — это чат, и
send_message примет его молча. Если такой номер попадёт в подписки,
личное сообщение окажется в канале, на глазах у всех.

Нажать «за канал» можно: у анонимного администратора и у поста,
отражённого в обсуждение, вместо человека приходит служебный
отправитель. Личного чата у него нет, и писать ему нечего.
"""

import inspect

import tennis_alerts as ta


def test_a_real_person_passes():
    assert ta._is_person(123456789)


def test_a_channel_id_never_passes():
    assert not ta._is_person(-1003667131485)
    assert not ta._is_person(-100)


def test_service_senders_never_pass():
    """Channel_Bot и GroupAnonymousBot — не люди, личек у них нет."""
    assert not ta._is_person(136817688)
    assert not ta._is_person(1087968824)


def test_nonsense_never_passes():
    assert not ta._is_person(None)
    assert not ta._is_person("канал")
    assert not ta._is_person(0)


def test_subscribing_checks_who_pressed():
    body = inspect.getsource(ta.toggle_match)
    assert "_is_person(call.from_user.id)" in body
    assert body.index("_is_person") < body.index("toggle_alert")


def test_sending_checks_again_on_its_own():
    """Вторая застава: подписка могла лечь до того, как появилась
    первая проверка."""
    body = inspect.getsource(ta.alerts_scheduler)
    assert "_is_person(user_id)" in body


def test_old_bad_subscriptions_are_cleaned_at_startup():
    body = inspect.getsource(ta.alerts_scheduler)
    assert "alerts_drop_nonhuman" in body


def test_the_cleanup_targets_exactly_the_bad_ids():
    import database
    body = inspect.getsource(database.alerts_drop_nonhuman)
    assert "user_id <= 0" in body
    assert "136817688" in body
