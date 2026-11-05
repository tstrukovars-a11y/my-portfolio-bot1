"""Тесты на автоматическую часть конкурса (draws_runner.py).

Панель — то, что владелица делает руками. Это — то, что идёт само:
вопрос ушёл по времени, приём закрылся, круг подвинулся. Главное
свойство всего модуля: каждый шаг проходит, даже если кто-то не
ответил. Вечер нельзя останавливать из-за одного человека, который
ушёл домой.
"""

import draws_runner as runner


# ---------------------------------------------------------------------
# Кнопки ответа
# ---------------------------------------------------------------------


def test_the_answer_buttons_carry_the_poll_and_the_side():
    kb = runner._answer_kb(42, "Окунев", "Кураков")
    data = [b.callback_data for b in kb.inline_keyboard[0]]
    assert data == ["drans_42_0", "drans_42_1"]


def test_the_answer_buttons_are_named_by_the_players():
    kb = runner._answer_kb(42, "Окунев", "Кураков")
    assert [b.text for b in kb.inline_keyboard[0]] == ["Окунев", "Кураков"]


def test_a_very_long_surname_is_trimmed_to_fit_a_button():
    kb = runner._answer_kb(1, "Х" * 60, "Кураков")
    assert len(kb.inline_keyboard[0][0].text) <= 28


# ---------------------------------------------------------------------
# Граница: ответы и отметки — только в личке
# ---------------------------------------------------------------------


def test_answering_never_works_under_a_channel_post():
    """Вопрос приходит в личку, и отвечают там же. Под постом канала
    такой кнопке делать нечего: ответ увидели бы все."""
    import public
    assert not public.allowed("drans_42_0")


def test_marking_the_match_winner_is_owner_only():
    """Исход матча отмечает владелица, и только в личке."""
    import public
    assert not public.allowed("drwon_42_1")


# ---------------------------------------------------------------------
# Время
# ---------------------------------------------------------------------


def test_a_round_is_short_on_purpose():
    """Круги идут после матчей. Растянуть их на час — значит не
    дождаться никого."""
    assert runner.ROUND_MINUTES == 10


def test_the_scheduler_ticks_every_minute():
    """Вопрос должен уйти в начале матча, а не через четверть часа
    после: к тому времени окно ответа уже закрылось бы."""
    import inspect
    body = inspect.getsource(runner.scheduler)
    assert "sleep(60)" in body


# ---------------------------------------------------------------------
# Когда показывать сетку
# ---------------------------------------------------------------------


def test_the_bracket_picture_waits_for_the_last_eight():
    """На тридцати двух именах сетка нечитаема с телефона: своё имя в
    ней ищут дольше, чем идёт круг."""
    assert runner.SHOW_BRACKET_FROM == 8


def test_the_owner_gets_the_bracket_as_a_file_not_a_photo():
    """Картинку в переписке Telegram сжимает, и на печати она
    расплывается. Документ сохраняется в исходном размере."""
    import inspect
    body = inspect.getsource(runner._send_owner_sheet)
    assert "send_document" in body
    assert "send_photo" not in body
