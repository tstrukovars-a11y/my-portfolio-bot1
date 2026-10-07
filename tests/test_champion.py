# Пост о победителе турнира.
#
# Итоги дня дают строку со счётом: в таблице выигранный турнир выглядит
# как любой другой матч второго круга. Отдельный пост говорит, что эта
# победа дала — место в рейтинге, титулы, шлемы, призовые.
#
# Цифры здесь о живом человеке. Ошибка в призовых за карьеру — это не
# опечатка, это неправда, и проверяется она читателем за пять секунд.
import asyncio

import tennis_champion as tc


def _side(name, pid, winner, games):
    return {
        "athlete": {"displayName": name,
                    "links": [{"href": f"https://www.espn.com/tennis/player/_/id/{pid}/x"}]},
        "winner": winner,
        "linescores": [{"value": float(g)} for g in games],
    }


def _final(round_name="Final"):
    return {"id": "1", "tournament": "China Open", "round": round_name,
            "completed": True,
            "sides": [_side("Novak Djokovic", "296", True, [6, 7]),
                      _side("Alex de Minaur", "4379", False, [4, 5])]}


# --- что считать финалом ----------------------------------------------

def test_a_final_is_a_final():
    assert tc.is_final(_final())


def test_a_qualifying_final_is_not_a_title():
    """Финал квалификации — это попадание в основную сетку. Поздравлять
    с ним как с титулом нельзя, а по вхождению слова «final» он
    проходит первым."""
    assert not tc.is_final(_final("Qualifying Final"))


def test_a_semifinal_is_not_a_final():
    for name in ("Semifinal", "Semifinals", "Quarterfinal", "2nd Round"):
        assert not tc.is_final(_final(name)), name


# --- цифры из карточки ------------------------------------------------

AO = ("| AustralianOpenresult = '''W''' ([[2008 Australian Open|2008]], "
      "[[2011 Australian Open|2011]])\n")
RG = "| FrenchOpenresult = F ([[2025 French Open|2025]])\n"
WB = "| Wimbledonresult = '''W''' ([[2011 Wimbledon|2011]])\n"
US = "| USOpenresult = '''W''' ([[2015 US Open|2015]])\n"


def test_years_inside_a_link_are_counted_once():
    """Год стоит и в адресе ссылки, и в подписи к ней. Джокович выходил
    с сорока восемью шлемами вместо двадцати четырёх — число, которое
    читатель заметит раньше нас."""
    assert tc._slams(AO + RG + WB + US) == 4


def test_a_final_is_not_a_win():
    """F — это проигранный финал. Засчитать его как титул значит
    приписать человеку победу, которой не было."""
    assert tc._slams(RG) == 0


def test_titles_hidden_behind_a_link_are_read():
    text = "| singlestitles = [[Novak Djokovic career statistics|102]] (3rd)"
    assert tc._titles(text) == 102


def test_a_plain_number_of_titles_is_read():
    assert tc._titles("| singlestitles = 24\n") == 24


def test_prize_money_comes_out_in_russian_spacing():
    text = "| careerprizemoney = US$ 53,222,999<ref>whatever</ref>"
    assert tc._prize(text) == "53 222 999 $"


def test_a_missing_field_stays_missing():
    """Чего не нашли — о том молчим. Пост без строки о призовых
    остаётся постом; пост с выдуманными — повод для опровержения."""
    assert tc._prize("") == ""
    assert tc._titles("") == 0
    assert tc._slams("") == 0


# --- сам пост ----------------------------------------------------------

def _text(monkeypatch, rank=(8, 11, 0), got=None):
    async def ranks(tour, pid, name):
        return rank

    async def facts(name):
        return got if got is not None else {"titles": 102, "slams": 24,
                                            "prize": "194 814 547 $"}

    monkeypatch.setattr(tc, "rank_of", ranks)
    monkeypatch.setattr(tc, "achievements", facts)
    return asyncio.run(tc.champion_text(_final(), "atp"))


def test_the_post_names_the_champion_and_the_tournament(monkeypatch):
    text = _text(monkeypatch)
    assert "Джокович" in text and "China Open" in text


def test_the_post_carries_the_final_score(monkeypatch):
    assert "6-4" in _text(monkeypatch)


def test_the_post_shows_the_move_up(monkeypatch):
    """«Восьмая ракетка» без «была одиннадцатой» — половина новости."""
    text = _text(monkeypatch, rank=(8, 11, 0))
    assert "8-е место" in text and "было 11-е" in text


def test_a_rank_that_did_not_move_is_said_plainly(monkeypatch):
    text = _text(monkeypatch, rank=(1, 1, 0))
    assert "1-е место" in text and "было" not in text


def test_slams_are_wins_not_slams(monkeypatch):
    """«24 шлема Большого шлема» — то, что получается, если не считать
    слова."""
    text = _text(monkeypatch)
    assert "24 победы на турнирах Большого шлема" in text
    assert "шлема Большого шлема" not in text


def test_the_post_congratulates(monkeypatch):
    text = _text(monkeypatch)
    assert "Поздравляем" in text and "побед" in text


def test_nothing_is_invented_when_wikipedia_is_silent(monkeypatch):
    """Википедия может не ответить, а поздравить человека надо всё
    равно: пост выходит короче, но без выдуманных цифр."""
    text = _text(monkeypatch, got={})
    assert "Джокович" in text and "Поздравляем" in text
    for word in ("титул", "шлем", "призов"):
        assert word not in text, word


def test_the_photo_is_taken_by_player_number():
    assert tc._athlete_id(_final()["sides"][0]) == "296"
    assert tc._athlete_id({"athlete": {}}) == ""
