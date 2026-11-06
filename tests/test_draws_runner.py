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


def test_a_set_is_short_on_purpose():
    """Три сета по десять минут растянули бы один круг на полчаса, а
    кругов за вечер три или четыре."""
    assert runner.SET_MINUTES == 5
    assert runner.SET_MINUTES * runner.MAX_SETS <= 15


def test_a_round_is_best_of_three():
    """Сеты заведены ради понятного результата: человек, который
    отыграл, не должен гадать, прошёл он или нет."""
    assert runner.SETS_TO_WIN == 2
    assert runner.MAX_SETS == 3


def test_the_set_result_goes_out_immediately():
    """Ради этого сеты и затевались — счёт соперника человек не видит,
    и «сравним числа в конце круга» оставляло его в неведении."""
    import inspect
    assert "Счёт по сетам" in inspect.getsource(runner._tell_set_result)


def test_advancing_counts_sets_not_points():
    import inspect
    body = inspect.getsource(runner.advance_brackets)
    assert "bracket_set_wins" in body


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


# ---------------------------------------------------------------------
# Галочка у выбранного ответа
# ---------------------------------------------------------------------
#
# Ответ окончательный, и человек должен видеть, что именно он выбрал,
# когда вернётся к сообщению через час. Всплывающее окошко к тому
# времени давно закрылось.


def test_before_answering_there_is_no_tick():
    kb = runner._answer_kb(7, "Окунев", "Кураков")
    assert all("✅" not in b.text for b in kb.inline_keyboard[0])


def test_the_chosen_side_gets_the_tick():
    kb = runner._answer_kb(7, "Окунев", "Кураков", chosen=1)
    texts = [b.text for b in kb.inline_keyboard[0]]
    assert texts[0] == "Окунев"
    assert texts[1].startswith("✅")


def test_the_tick_does_not_move_to_the_other_side():
    kb = runner._answer_kb(7, "Окунев", "Кураков", chosen=0)
    assert kb.inline_keyboard[0][0].text.startswith("✅")
    assert "✅" not in kb.inline_keyboard[0][1].text


def test_the_buttons_keep_working_after_the_tick():
    """Данные кнопок не должны меняться: по ним считается ответ."""
    kb = runner._answer_kb(7, "Окунев", "Кураков", chosen=0)
    assert [b.callback_data for b in kb.inline_keyboard[0]] == [
        "drans_7_0", "drans_7_1"]


def test_the_handler_redraws_the_buttons():
    import inspect
    body = inspect.getsource(runner.take_answer)
    assert "edit_reply_markup" in body
    assert "chosen=side" in body
