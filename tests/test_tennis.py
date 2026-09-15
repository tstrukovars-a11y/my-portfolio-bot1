# Теннис: имена в канале и разбор состояния матча.
#
# Ошибка в имени видна всем подписчикам сразу — однажды бот уже назвал
# Michael Zheng Чжэн Циньвэнь, то есть подменил человека. Ошибка в
# состоянии матча дороже: «матч отменён» уходит людям в личку.
import players_ru
import tennis_alerts as ta


# --- имена ------------------------------------------------------------

def test_known_name_comes_out_russian():
    assert players_ru.ru("Andrey Rublev") == "Андрей Рублёв"


def test_button_form_is_initial_plus_surname():
    assert players_ru.short("Andrey Rublev") == "А. Рублёв"


def test_chinese_name_is_not_swapped_for_another_person():
    """Michael Zheng и Zheng Qinwen — разные люди с общей фамилией."""
    assert "Циньвэнь" not in players_ru.ru("Michael Zheng")


def test_unknown_name_survives_as_it_is():
    out = players_ru.ru("Totally Unknown Player")
    assert out and isinstance(out, str)


def test_round_is_translated():
    assert players_ru.rnd("Final") == "финал"


# --- состояние матча --------------------------------------------------

def test_cancelled_states_are_recognised():
    for state in ("Canceled", "Postponed", "Walkover", "Suspended"):
        assert ta._cancelled({"state": state}), state


def test_normal_states_are_not_cancellations():
    for state in ("Scheduled", "In Progress", "Final", "1st Set", ""):
        assert not ta._cancelled({"state": state}), state


def test_reason_is_a_whole_russian_sentence():
    assert ta._why("Postponed") == "Матч перенесли на другой день."
    assert ta._why("Walkover").endswith(".")
    assert ta._why("что-то незнакомое") == "Матч отменён."


# --- прогнозы ---------------------------------------------------------

def test_shares_are_hidden_until_the_vote_means_something():
    row = ta._pick_labels("401", ["А. Рублёв", "Д. Медведев"], (1, 0))
    assert row[0].text == "А. Рублёв"          # «100 %» от одного голоса — враньё


def test_shares_appear_and_add_up():
    row = ta._pick_labels("401", ["А. Рублёв", "Д. Медведев"], (17, 7))
    assert row[0].text.endswith("71%")
    assert row[1].text.endswith("29%")


def test_pick_button_carries_the_match_and_the_side():
    row = ta._pick_labels("401", ["А", "Б"], (0, 0))
    assert row[0].callback_data == "tpick_401_0"
    assert row[1].callback_data == "tpick_401_1"


def test_votes_word_agrees_with_the_number():
    assert ta._votes_word(1) == "проголосовавшего"
    assert ta._votes_word(5) == "проголосовавших"
    assert ta._votes_word(11) == "проголосовавших"
    assert ta._votes_word(21) == "проголосовавшего"


def test_two_names_or_nothing():
    match = {"sides": [{"athlete": {"displayName": "Andrey Rublev"}},
                       {"athlete": {"displayName": "Daniil Medvedev"}}]}
    assert ta._names(match) == ["А. Рублёв", "Д. Медведев"]
    assert ta._names({"sides": []}) is None
