"""Покрытие корта по названию турнира (surfaces.py).

В истории личных встреч покрытие — половина смысла: победа над тем же
соперником на грунте и на траве говорят о разном. У источника табло
этого поля нет, поэтому справочник свой.

Главное правило: чего не знаем — возвращаем None. Придуманное покрытие
хуже отсутствующего, потому что выглядит как факт.
"""

import surfaces as s


def test_the_slams_are_right():
    assert s.of("Australian Open") == s.HARD
    assert s.of("Roland Garros") == s.CLAY
    assert s.of("Wimbledon") == s.GRASS
    assert s.of("US Open") == s.HARD


def test_prefixes_and_sponsors_do_not_confuse_it():
    """Источник присылает «Rolex Paris Masters», а не «Paris»."""
    assert s.of("Rolex Paris Masters") == s.HARD
    assert s.of("Mutua Madrid Open") == s.CLAY
    assert s.of("Internazionali BNL d'Italia") == s.CLAY


def test_stuttgart_depends_on_the_tour():
    """Единственная пара, где у туров РАЗНОЕ покрытие: у мужчин трава,
    у женщин грунт в зале. Без тура тут не ответить."""
    assert s.of("Stuttgart Open", "atp") == s.GRASS
    assert s.of("Porsche Tennis Grand Prix Stuttgart", "wta") == s.CLAY


def test_a_longer_name_wins_over_a_shorter_one():
    """«Rio Open» — грунт, и короткий ключ «rio» не должен перебить
    более точный."""
    assert s.of("Rio Open") == s.CLAY


def test_an_unknown_tournament_gives_nothing():
    assert s.of("Кубок соседнего двора") is None
    assert s.of("") is None
    assert s.of(None) is None


def test_london_is_not_a_key():
    """Под него попал бы любой лондонский турнир, включая зальные.
    Куинс и так находится по «queen»."""
    assert "london" not in s.COMMON
    assert s.of("Queen's Club Championships") == s.GRASS


def test_every_surface_is_one_of_the_three():
    for value in list(s.COMMON.values()):
        assert value in (s.HARD, s.CLAY, s.GRASS), value
    for by_tour in s.BY_TOUR.values():
        for value in by_tour.values():
            assert value in (s.HARD, s.CLAY, s.GRASS), value


def test_keys_are_lowercase():
    """Поиск идёт по названию в нижнем регистре — ключ с заглавной
    буквой не найдётся никогда и будет молча мёртвым."""
    for key in list(s.COMMON) + list(s.BY_TOUR):
        assert key == key.lower(), key


def test_the_dictionary_is_not_empty_by_accident():
    assert s.known() > 50


# ---------------------------------------------------------------------
# Показательные турниры
# ---------------------------------------------------------------------
#
# Победа на публику и победа в основном туре значат разное, а в строке
# «счёт 3:1» выглядят одинаково. Искажение получается незаметным — тем
# оно и опасно.


def test_palmyra_is_an_exhibition():
    assert s.is_exhibition("Northern Palmyra Trophies")
    assert s.is_exhibition("Северная Пальмира")


def test_the_well_known_exhibitions_are_caught():
    for name in ("Six Kings Slam", "Laver Cup", "Mubadala World Tennis "
                 "Championship", "World Tennis League", "Kooyong Classic",
                 "Diriyah Tennis Cup", "Hopman Cup"):
        assert s.is_exhibition(name), name


def test_real_tournaments_are_not_exhibitions():
    for name in ("Australian Open", "Rolex Paris Masters", "Rio Open",
                 "Wimbledon", "Internazionali BNL d'Italia"):
        assert not s.is_exhibition(name), name


def test_an_empty_name_is_not_an_exhibition():
    assert not s.is_exhibition("")
    assert not s.is_exhibition(None)


def test_markers_are_lowercase():
    """Сравнение идёт в нижнем регистре — заглавная буква сделала бы
    метку молча мёртвой."""
    for mark in s.EXHIBITION:
        assert mark == mark.lower(), mark
