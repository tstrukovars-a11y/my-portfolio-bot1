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

    # Игроки у всех настоящие: проверяется отбор по дате, и матч без
    # имён отсеялся бы раньше — по другой причине.
    pair = [{"athlete": {"displayName": "Andrey Rublev"}},
            {"athlete": {"displayName": "Carlos Alcaraz"}}]
    matches = [
        {"id": "brosh", "date": at(-5), "completed": False, "sides": pair},
        {"id": "today", "date": at(2), "completed": False, "sides": pair},
        {"id": "early", "date": at(10), "completed": False, "sides": pair},
        {"id": "late", "date": at(20), "completed": False, "sides": pair},
        {"id": "done", "date": at(1), "completed": True, "sides": pair},
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


# --- игроки ещё не определены -----------------------------------------
#
# Расписание строится за сутки, а нижняя половина сетки к этому часу ещё
# доигрывается. Источник всё равно отдаёт такие матчи: с пустым именем
# или со словом «Qualifier» вместо фамилии.
#
# В канал это вышло строкой «18:00 · матч» — ни имён, ни смысла. Хуже
# другое: подписка на такой матч ложилась в базу без времени начала и не
# срабатывала уже никогда. Снаружи это выглядит как «подписка есть,
# ссылки нет».

def _side(name):
    return {"athlete": {"displayName": name}}


def test_a_match_with_two_players_is_ready():
    assert ta._ready({"sides": [_side("Andrey Rublev"), _side("Carlos Alcaraz")]})


def test_an_empty_name_means_the_draw_is_not_done():
    assert not ta._ready({"sides": [_side("Andrey Rublev"), _side("")]})


def test_one_side_only_is_not_a_match():
    assert not ta._ready({"sides": [_side("Andrey Rublev")]})
    assert not ta._ready({"sides": []})


def test_no_sides_at_all():
    assert not ta._ready({})


def test_placeholders_are_not_players():
    """В сетке они законны, в анонсе — нет: смотреть нечего, подписаться
    не на кого."""
    for stub in ("TBD", "tba", "Qualifier", "Bye", "Lucky Loser", "WC"):
        assert not ta._ready({"sides": [_side("Andrey Rublev"), _side(stub)]}), \
            stub


def test_a_real_surname_is_not_mistaken_for_a_placeholder():
    """Отсев идёт по целому имени, а не по вхождению: иначе живой игрок
    однажды выпадет из расписания из-за своей фамилии."""
    assert ta._ready({"sides": [_side("Jack Qualifierson"),
                                _side("Byeong Lee")]})


def test_the_schedule_drops_undetermined_matches(monkeypatch):
    """То, с чего всё началось: пост с матчами без игроков."""
    import asyncio
    from datetime import datetime, timedelta, timezone
    import tennis_live

    now = datetime(2026, 10, 4, 10, 0, tzinfo=timezone.utc)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(ta, "datetime", Clock)
    monkeypatch.setattr(ta, "_shift",
                        lambda: asyncio.sleep(0, result=timedelta(hours=3)))

    soon = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%MZ")
    feed = [
        {"id": "real", "date": soon, "completed": False,
         "sides": [_side("Andrey Rublev"), _side("Carlos Alcaraz")]},
        {"id": "tbd", "date": soon, "completed": False,
         "sides": [_side("Qualifier"), _side("TBD")]},
        {"id": "empty", "date": soon, "completed": False,
         "sides": [_side("Andrey Rublev"), _side("")]},
    ]
    monkeypatch.setattr(tennis_live, "_singles",
                        lambda data, tour, big_only=False: feed)
    monkeypatch.setattr(tennis_live, "fetch_scoreboard",
                        lambda tour, force=False: asyncio.sleep(0, result={}))

    got = asyncio.run(ta._today("atp"))
    assert [m["id"] for m in got] == ["real"], \
        "матч без определённых игроков попал в расписание"


def test_the_time_check_looks_at_every_tournament():
    """Вторая причина молчания: сверка времени смотрела только крупные
    турниры. Матч поменьше, на который уже подписались, времени не
    получал и отмены не замечал — напоминание молчало при живой записи
    в базе."""
    source = open("tennis_alerts.py", encoding="utf-8").read()
    start = source.index("async def refresh_times")
    block = source[start:start + 1400]
    assert "big_only=False" in block, \
        "сверка времени снова отбирает матчи по величине турнира"



# --- подписка есть, ссылки нет ----------------------------------------
#
# Главный симптом: человек нажал «напомнить», увидел подтверждение и не
# получил ничего. Причина — запись без времени начала: планировщик
# выбирает по времени, а его нет, и такую запись он не видит никогда.

class _Call:
    def __init__(self, data, user_id=5):
        self.data = data
        self.from_user = type("U", (), {"id": user_id})()
        self.message = type("M", (), {"reply_markup": None})()
        self.bot = None
        self.popups = []

    async def answer(self, text="", **kw):
        self.popups.append(text)


def _no_time(monkeypatch, exists=False, saved=None):
    """Матча нет ни в расписании дня, ни в свежей табличке"""
    import asyncio
    import database

    monkeypatch.setattr(ta, "_allowed", lambda uid: asyncio.sleep(0, result=True))
    monkeypatch.setattr(ta, "_today", lambda tour: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(ta, "_find_match",
                        lambda tour, mid: asyncio.sleep(0, result=None))
    monkeypatch.setattr(database, "alert_exists",
                        lambda uid, mid: asyncio.sleep(0, result=exists))

    async def toggle(*a, **kw):
        if saved is not None:
            saved.append(a)
        # Запись была — значит, нажатие её снимает, как в настоящем
        # toggle_alert: сначала удаление, вставка только если удалять
        # было нечего.
        return (False, 0) if exists else (True, 1)

    monkeypatch.setattr(database, "toggle_alert", toggle)


def test_a_match_without_a_time_is_not_saved_as_a_dead_alert(monkeypatch):
    """Раньше запись молча ложилась в базу и висела вечно: человек видел
    «напоминание включено» и не получал ссылку никогда."""
    import asyncio

    saved = []
    _no_time(monkeypatch, exists=False, saved=saved)

    call = _Call("tmatch_atp_999")
    asyncio.run(ta.toggle_match(call))

    assert not saved, "мёртвая подписка всё-таки записалась"
    assert call.popups and "не назначено" in call.popups[0], \
        "человеку не сказали, почему не вышло"


def test_an_old_alert_can_still_be_switched_off(monkeypatch):
    """Кнопка, которая перестала отжиматься, хуже кнопки, которая не
    нажимается: подписка осталась бы навсегда."""
    import asyncio

    saved = []
    _no_time(monkeypatch, exists=True, saved=saved)

    call = _Call("tmatch_atp_999")
    asyncio.run(ta.toggle_match(call))
    assert saved, "снять старую подписку не дали"
    assert call.popups and "снято" in call.popups[0].lower()


# --- громкие события на корте -----------------------------------------
#
# Расписание говорит, что будет; итоги — что было вчера. Между ними
# пропадало главное: Медведева сняли, Соболенко проиграла той, о ком
# никто не слышал. Наутро это строка в таблице среди сорока других.

def _played(a, b, winner=None, state="", completed=True, mid="1"):
    sides = [_side(a), _side(b)]
    for s, name in zip(sides, (a, b)):
        s["winner"] = (winner == name)
    return {"id": mid, "sides": sides, "state": state,
            "completed": completed, "tournament": "Shanghai Masters"}


def test_a_famous_player_retiring_is_an_event():
    """«Сняли Медведева» — то, ради чего читатель и открывает канал."""
    m = _played("Daniil Medvedev", "Totally Unknown Player",
               winner="Totally Unknown Player", state="Retired")
    assert ta._event_kind(m) == "retired"


def test_losing_to_an_unknown_is_an_event():
    """Соболенко проиграла той, о ком никто не слышал."""
    m = _played("Aryna Sabalenka", "Totally Unknown Player",
               winner="Totally Unknown Player")
    assert ta._event_kind(m) == "upset"


def test_a_famous_player_winning_is_not_an_event():
    """Иначе канал завалит сообщениями о каждом рядовом матче."""
    m = _played("Aryna Sabalenka", "Totally Unknown Player",
               winner="Aryna Sabalenka")
    assert ta._event_kind(m) == ""


def test_two_famous_players_are_not_a_surprise():
    """Победа одного известного над другим неожиданностью не является,
    как бы ни удивлял счёт."""
    m = _played("Andrey Rublev", "Carlos Alcaraz", winner="Andrey Rublev")
    assert ta._event_kind(m) == ""


def test_two_unknowns_are_never_an_event():
    m = _played("Totally Unknown Player", "Another Unknown One",
               winner="Another Unknown One")
    assert ta._event_kind(m) == ""


def test_an_unfinished_match_is_not_a_result_yet():
    m = _played("Aryna Sabalenka", "Totally Unknown Player",
               winner=None, completed=False)
    assert ta._event_kind(m) == ""


def test_a_retirement_counts_even_before_the_match_is_closed():
    """Снятие — новость в ту же минуту, а не когда табличка досчитает."""
    m = _played("Daniil Medvedev", "Totally Unknown Player",
               winner=None, state="Retired", completed=False)
    assert ta._event_kind(m) == "retired"


def _text(kind, match, tour, monkeypatch, reason="", link=""):
    """Сообщение о событии без похода в сеть за новостями"""
    import asyncio

    async def why(t, name):
        return reason, link

    async def ru(english):
        return "Снялся из-за травмы колена." if english else ""

    monkeypatch.setattr(ta, "_why_gone", why)
    monkeypatch.setattr(ta, "_reason_ru", ru)
    return asyncio.run(ta._event_text(kind, match, tour))


def test_the_retirement_message_names_who_left(monkeypatch):
    m = _played("Daniil Medvedev", "Totally Unknown Player",
               winner="Totally Unknown Player", state="Retired")
    text = _text("retired", m, "atp", monkeypatch)
    assert "Снятие" in text
    assert "Медведев" in text and "снялся" in text


def test_a_womans_retirement_is_said_in_her_own_form(monkeypatch):
    m = _played("Aryna Sabalenka", "Totally Unknown Player",
               winner="Totally Unknown Player", state="Retired")
    assert "снялась" in _text("retired", m, "wta", monkeypatch)


def test_the_message_does_not_judge_the_played(monkeypatch):
    """«Сенсация» и «разгром» читатель поставит сам, а ошибётся в них
    бот, а не он."""
    m = _played("Aryna Sabalenka", "Totally Unknown Player",
               winner="Totally Unknown Player")
    text = _text("upset", m, "wta", monkeypatch).lower()
    for word in ("сенсац", "разгром", "позор", "провал", "шок"):
        assert word not in text, word


# --- «снят» без «из-за чего» оставляет тот же вопрос -------------------

def test_the_reason_reaches_the_reader(monkeypatch):
    m = _played("Daniil Medvedev", "Totally Unknown Player",
               winner="Totally Unknown Player", state="Retired")
    text = _text("retired", m, "atp", monkeypatch,
                 reason="injured Medvedev retires",
                 link="https://espn.com/story/1")
    assert "травмы колена" in text
    assert "espn.com/story/1" in text


def test_without_a_source_nothing_is_invented(monkeypatch):
    """Случай Медведева и показал, зачем это правило: его не сняли по
    травме, его дисквалифицировали за мяч в лицо зрителю. «Снялся
    из-за травмы» было бы не домыслом, а неправдой о живом человеке."""
    m = _played("Daniil Medvedev", "Totally Unknown Player",
               winner="Totally Unknown Player", state="Retired")
    text = _text("retired", m, "atp", monkeypatch).lower()
    for word in ("травм", "из-за", "болел", "повредил"):
        assert word not in text, word


def test_the_score_at_the_moment_is_shown(monkeypatch):
    """«Снялся при 6:4, 3:2» говорит больше, чем «снялся»: видно,
    началось ли это сразу или человек тянул два сета."""
    m = _played("Daniil Medvedev", "Totally Unknown Player",
               winner="Totally Unknown Player", state="Retired")
    m["sides"][1]["linescores"] = [{"value": 6.0}, {"value": 3.0}]
    m["sides"][0]["linescores"] = [{"value": 4.0}, {"value": 2.0}]
    assert "4:6, 2:3" in _text("retired", m, "atp", monkeypatch)


def test_a_match_that_never_started_shows_no_score(monkeypatch):
    m = _played("Daniil Medvedev", "Totally Unknown Player",
               winner="Totally Unknown Player", state="Walkover")
    assert "Доиграли" not in _text("retired", m, "atp", monkeypatch)


def test_the_ranking_gap_explains_the_surprise(monkeypatch):
    """«34-я обыграла первую» объясняет само себя."""
    m = _played("Aryna Sabalenka", "Totally Unknown Player",
               winner="Totally Unknown Player")
    m["sides"][0]["curatedRank"] = {"current": 1}
    m["sides"][1]["curatedRank"] = {"current": 34}
    text = _text("upset", m, "wta", monkeypatch)
    assert "1-я ракетка" in text and "34-я" in text


def test_an_unranked_player_is_not_called_the_99th():
    """ESPN ставит 99 тем, у кого места нет."""
    assert ta._seed({"curatedRank": {"current": 99}}) == ""
    assert ta._seed({"curatedRank": {"current": 5}}) == "5"
    assert ta._seed({}) == ""


# --- события вне корта ------------------------------------------------
#
# Дисквалификация Медведева пришла бы в табло обычным поражением:
# счёт, победитель, ничего особенного. В ленте новостей это заголовок
# из восьми слов. Поэтому третий источник — новости.

def test_a_disqualification_is_an_event():
    """Тот самый случай: «сняли Медведева» — на деле дисквалификация."""
    assert ta._loud_about(
        "Daniil Medvedev DQ'd after hitting ball into stands "
        "that strikes spectator's face", "") == "medvedev"


def test_missing_the_rest_of_the_season_is_an_event():
    assert ta._loud_about(
        "Jannik Sinner to miss rest of year due to knee inflammation",
        "") == "sinner"


def test_leaving_a_tournament_is_an_event():
    assert ta._loud_about(
        "Medvedev out of China Open after smashing ball in fan's face",
        "") == "medvedev"


def test_a_win_is_not_an_event_even_with_the_word_injury():
    """«Alcaraz retains title following injury layoff» — о возвращении,
    а не о том, что кто-то снялся."""
    assert ta._loud_about(
        "Carlos Alcaraz retains Japan Open title in big step "
        "following injury layoff", "") == ""


def test_an_ordinary_win_is_not_an_event():
    assert ta._loud_about(
        "No. 3 Alcaraz overcomes big deficit to reach Japan Open final",
        "") == ""


def test_league_news_is_about_nobody():
    assert ta._loud_about(
        "WTA passes 'major milestone' with equal prize money at WTA 1000s",
        "") == ""


def test_the_player_is_taken_from_the_headline_not_the_blurb():
    """В подводке назван и соперник: получалось «отказался Легечка»,
    когда отказался другой."""
    who = ta._loud_about(
        "Medvedev out of China Open",
        "Djokovic advances to the final Tuesday vs. Alex de Minaur.")
    assert who == "medvedev"


def test_a_surname_inside_another_word_is_not_a_player():
    """«ban» внутри «Bankova» и «rune» внутри «brunet» делали бы своим
    кого попало."""
    import players_ru
    assert players_ru.first_known("brunet wins in bankova street") == ""


def test_an_event_without_a_recap_is_not_published(monkeypatch):
    """Английский заголовок в русский канал не ставим: лучше промолчать,
    чем выдать читателю строку, которую он не прочтёт."""
    import asyncio

    async def nothing(english):
        return ""

    async def gathered(tour, name):
        return "some english text", "https://espn.com/1"

    monkeypatch.setattr(ta, "_reason_ru", nothing)
    monkeypatch.setattr(ta, "_why_gone", gathered)
    text = asyncio.run(ta._news_event_text(
        "atp", "medvedev", "Medvedev DQ'd", "", "https://espn.com/1", "1"))
    assert text == ""


def test_the_recap_reaches_the_channel(monkeypatch):
    import asyncio

    async def recap(english):
        return ("Медведев дисквалифицирован в полуфинале.\n"
                "Мяч попал зрителю в лицо.\n"
                "Он извинился перед пострадавшим.")

    async def gathered(tour, name):
        return "english story", "https://espn.com/1"

    monkeypatch.setattr(ta, "_reason_ru", recap)
    monkeypatch.setattr(ta, "_why_gone", gathered)
    text = asyncio.run(ta._news_event_text(
        "atp", "medvedev", "Medvedev DQ'd", "", "https://espn.com/1", "1"))
    assert "Вне корта" in text
    assert "дисквалифицирован" in text and "извинился" in text
    assert "espn.com/1" in text


def test_the_recap_prompt_forbids_inventing_consequences():
    """Про штраф, очки и призовые в заметке о Медведеве не сказано ни
    слова. Дописать их «по здравому смыслу» — выдумать наказание."""
    low = ta.REASON_PROMPT.lower()
    for word in ("очк", "призов", "штраф"):
        assert word in low, f"запрет про «{word}» потерялся"
    assert "не сказано" in low or "нет" in low


# --- кто вылетел ------------------------------------------------------
#
# Таблица счёта сообщает факт. Но читатель следит за людьми, и строка
# «Синнер — Музетти 6:4 6:3» означает для него не счёт, а то, что
# Музетти в турнире больше нет. Это и говорится словами.


def _exited(winner, loser, rnd="2nd Round", state="post"):
    return {
        "round": rnd,
        "state": state,
        "completed": True,
        "sides": [
            {"winner": True, "athlete": {"displayName": winner}},
            {"winner": False, "athlete": {"displayName": loser}},
        ],
    }


def test_a_followed_player_who_lost_is_mourned():
    note = ta._exit_note(_exited("Jannik Sinner", "Karolina Muchova"))
    assert "Каролина Мухова" in note
    assert "к сожалению" in note and "покидает турнир" in note


def test_the_winner_is_never_the_one_who_leaves():
    note = ta._exit_note(_exited("Karolina Muchova", "Jannik Sinner"))
    assert "Мухова" not in note


def test_an_unknown_loser_gets_no_note():
    """Проигравший есть в каждом матче. Приписка под каждой второй
    строкой перестала бы читаться."""
    assert ta._exit_note(_exited("Jannik Sinner", "Some Qualifier")) == ""


def test_a_finalist_does_not_fly_out():
    """Он дошёл дальше всех, кроме одного, — «покидает турнир» звучит
    обидно и неверно."""
    note = ta._exit_note(_exited("Jannik Sinner", "Karolina Muchova", "Final"))
    assert "уступает в финале" in note
    assert "покидает турнир" not in note


def test_a_semifinal_is_named_as_such():
    note = ta._exit_note(_exited("Jannik Sinner", "Karolina Muchova",
                                "Semifinals"))
    assert "в шаге от финала" in note


def test_a_quarterfinal_is_named_as_such():
    note = ta._exit_note(_exited("Jannik Sinner", "Karolina Muchova",
                                "Quarterfinals"))
    assert "в четвертьфинале" in note


def test_a_retirement_is_not_called_a_defeat():
    """Человек не проиграл — он не смог продолжать, и «покидает
    турнир» про травму звучит упрёком."""
    note = ta._exit_note(_exited("Jannik Sinner", "Karolina Muchova",
                                state="post retired"))
    assert "снимается" in note
    assert "к сожалению, покидает" not in note


def test_a_group_stage_loss_is_not_an_exit():
    """На Итоговом из группы выходят по сумме трёх матчей."""
    assert ta._exit_note(_exited("Jannik Sinner", "Karolina Muchova",
                                "Round Robin")) == ""


def test_the_note_survives_a_broken_match():
    assert ta._exit_note({}) == ""
    assert ta._exit_note({"sides": []}) == ""


# --- места в рейтинге --------------------------------------------------
#
# Разрыв в рейтинге и есть то, что делает поражение неожиданным: «34-я
# обыграла первую» объясняет само себя. Но ESPN проставляет место не
# всем, и строка пропадала как раз в тех матчах, ради которых пишется.


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def _side(name, place=None, winner=False):
    s = {"winner": winner, "athlete": {"displayName": name}}
    if place is not None:
        s["curatedRank"] = {"current": place}
    return s


def test_the_source_rank_is_used_when_it_is_there(settings, monkeypatch):
    ta._places_cache["atp"] = {}
    out = _run(ta._place_of(_side("Lorenzo Musetti", 8), "atp"))
    assert out == "8"


def test_our_ranking_fills_the_gap(monkeypatch):
    """Без этого строка про ракетки молчала всякий раз, когда источник
    места не дал."""
    import database
    ta._places_cache["atp"] = {}

    async def table(tour):
        return [(8, "Lorenzo Musetti"), (34, "Arthur Fils")]

    monkeypatch.setattr(database, "ranking_places", table)
    assert _run(ta._place_of(_side("Lorenzo Musetti"), "atp")) == "8"
    assert _run(ta._place_of(_side("Arthur Fils"), "atp")) == "34"


def test_an_unknown_player_has_no_place(monkeypatch):
    import database
    ta._places_cache["atp"] = {}

    async def table(tour):
        return [(8, "Lorenzo Musetti")]

    monkeypatch.setattr(database, "ranking_places", table)
    assert _run(ta._place_of(_side("Totally Unknown Player"), "atp")) == ""


def test_the_ranking_line_names_both(monkeypatch):
    import database
    ta._places_cache["atp"] = {}

    async def table(tour):
        return [(8, "Lorenzo Musetti"), (34, "Arthur Fils")]

    monkeypatch.setattr(database, "ranking_places", table)
    line = _run(ta._ranking_line(_side("Arthur Fils", winner=True),
                                _side("Lorenzo Musetti"), "atp"))
    assert "8-я ракетка" in line and "34-я" in line
    assert "Музетти" in line and "Фис" in line


def test_without_both_places_the_line_stays_silent(monkeypatch):
    """Половина сведения хуже её отсутствия: «8-я проиграла» без второго
    места не объясняет ничего."""
    import database
    ta._places_cache["atp"] = {}

    async def table(tour):
        return [(8, "Lorenzo Musetti")]

    monkeypatch.setattr(database, "ranking_places", table)
    assert _run(ta._ranking_line(_side("Someone Else", winner=True),
                                _side("Lorenzo Musetti"), "atp")) == ""


def test_the_higher_place_wins_for_a_shared_surname(monkeypatch):
    import database
    ta._places_cache["wta"] = {}

    async def table(tour):
        return [(3, "Mirra Andreeva"), (88, "Erika Andreeva")]

    monkeypatch.setattr(database, "ranking_places", table)
    assert _run(ta._place_of(_side("Mirra Andreeva"), "wta")) == "3"
