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


# --- раннее утро следующего дня ---------------------------------------

def test_early_morning_tomorrow_is_still_ours(monkeypatch):
    """Матч в шесть утра терялся: сегодня рано, а завтрашний анонс поздно."""
    import asyncio
    from datetime import datetime, timedelta, timezone

    import tennis_live

    now = datetime(2026, 9, 16, 17, 0, tzinfo=timezone.utc)   # 20:00 у канала

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(ta, "datetime", Clock)
    monkeypatch.setattr(ta, "_shift",
                        lambda: asyncio.sleep(0, result=timedelta(hours=3)))

    def at(hours):
        return (now + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%MZ")

    matches = [
        {"id": "brosh", "date": at(-5), "completed": False},   # начался давно
        {"id": "today", "date": at(2), "completed": False},    # сегодня 22:00
        {"id": "early", "date": at(10), "completed": False},   # завтра 06:00
        {"id": "late", "date": at(20), "completed": False},    # завтра 16:00
        {"id": "done", "date": at(1), "completed": True},
    ]
    monkeypatch.setattr(tennis_live, "_singles",
                        lambda data, tour, big_only=False: matches)
    monkeypatch.setattr(tennis_live, "fetch_scoreboard",
                        lambda tour, force=False: asyncio.sleep(0, result={}))

    got = asyncio.run(ta._today("atp"))
    assert [m["id"] for m in got] == ["today", "early"]
    assert got[1].get("tomorrow") is True
    assert not got[0].get("tomorrow")


# --- под каким матчем спрашивать прогноз ------------------------------
#
# Раньше брали первый из списка, а он отсортирован по турниру и времени:
# наверху оказывался самый ранний матч случайного турнира, обычно первого
# круга. Голосовать за исход, который ничего не решает, никто не станет.

def _match(round_name, names=("Ivan Petrov", "John Doe"), date="2026-09-22T10:00Z"):
    return {"id": f"{round_name}-{date}", "round": round_name, "date": date,
            "sides": [{"athlete": {"displayName": n}} for n in names]}


def test_final_beats_the_first_round():
    early = _match("1st Round", date="2026-09-22T08:00Z")
    final = _match("Final", date="2026-09-22T19:00Z")
    assert ta._for_pick([early, final]) is final


def test_later_stage_wins():
    stages = [_match("Round of 16"), _match("Quarterfinals"), _match("Semifinals")]
    assert ta._for_pick(stages)["round"] == "Semifinals"


def test_ours_wins_at_the_same_stage(monkeypatch):
    import players_ru

    monkeypatch.setattr(players_ru, "is_nash",
                        lambda name: "Rublev" in name)
    plain = _match("Quarterfinals", ("John Doe", "Jane Roe"))
    ours = _match("Quarterfinals", ("Andrey Rublev", "Jane Roe"))
    assert ta._for_pick([plain, ours]) is ours


def test_earlier_match_wins_only_when_all_else_is_equal():
    """У раннего голосование успеет собраться до начала."""
    late = _match("Final", date="2026-09-22T20:00Z")
    early = _match("Final", date="2026-09-22T12:00Z")
    assert ta._for_pick([late, early]) is early


def test_unknown_stage_does_not_outrank_a_final():
    assert ta._for_pick(
        [_match("Exhibition"), _match("Final")])["round"] == "Final"


def test_empty_list_asks_nothing():
    assert ta._for_pick([]) is None


def test_final_is_called_a_final():
    """«Кто победит в матче» на финале теряет единственное, что делает
    этот матч особенным."""
    text = ta._pick_question(_match("Final"))
    assert "финал" in text and "титул" in text


def test_ordinary_match_keeps_the_plain_question():
    text = ta._pick_question(_match("2nd Round"))
    assert "кто победит" in text.lower()


# --- третье уведомление ------------------------------------------------
#
# Без него подписка обрывается на полуслове: человеку сказали, что матч
# начинается, и замолчали. Итог — то, ради чего он подписывался.

def test_result_line_names_the_winner_first():
    """Проигравший первым — это уже другая новость."""
    match = {"sides": [
        {"athlete": {"displayName": "Daniil Medvedev"}, "winner": False},
        {"athlete": {"displayName": "Andrey Rublev"}, "winner": True},
    ]}
    line = ta._result_line(match)
    assert line.startswith("<b>")
    assert "Рублёв" in line.split("—")[0]
    assert "Медведев" in line.split("—")[1]


def test_result_line_needs_two_players():
    assert ta._result_line({"sides": []}) == ""


def test_finished_match_is_told_apart_from_cancelled():
    """Отменённый матч — не результат: победителя в нём нет.

    Состояние лежит в поле state, а не status: перепутать их — значит
    молча считать все матчи состоявшимися.
    """
    assert ta._cancelled({"state": "postponed", "completed": False})
    assert ta._cancelled({"state": "walkover"})
    assert not ta._cancelled({"state": "final", "completed": True})
    assert not ta._cancelled({"state": ""})
