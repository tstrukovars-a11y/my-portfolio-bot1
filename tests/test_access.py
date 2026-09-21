# Доступ к навыкам и ворота перед оплатой.
#
# Две ошибки здесь стоят денег в разные стороны. Пустить незаплатившего —
# потерять выручку; не пустить заплатившего — потерять человека, и он не
# вернётся. Поэтому проверяем обе границы, а не одну.
import pytest

from conftest import run

import access
import config
import lang


@pytest.fixture
def paid(monkeypatch):
    """Кто что купил — словарём вместо базы"""
    import database

    bought = {}

    async def skill_until(user_id, skill):
        return bought.get((user_id, skill))

    async def grant_skill(user_id, skill, days, source=""):
        bought[(user_id, skill)] = days
        return True

    monkeypatch.setattr(database, "skill_until", skill_until)
    monkeypatch.setattr(database, "grant_skill", grant_skill)
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    return bought


# --- кто внутри -------------------------------------------------------

def test_stranger_has_nothing(paid):
    assert not run(access.has(42, "lang_he"))


def test_buyer_gets_in(paid):
    run(access.database.grant_skill(42, "lang_he", 30))
    assert run(access.has(42, "lang_he"))


def test_one_skill_does_not_open_another(paid):
    """За иврит заплатили — французский остаётся закрытым."""
    run(access.database.grant_skill(42, "lang_he", 30))
    assert not run(access.has(42, "lang_fr"))


def test_owner_walks_everywhere(paid):
    assert run(access.has(1, "lang_fr"))


# --- пробное ----------------------------------------------------------

@pytest.mark.parametrize("code", ["he", "fr", "en"])
def test_every_language_has_something_free(code):
    """Язык без пробного урока не продаст себя ничем."""
    free = lang.free_topics(code)
    assert free
    assert lang.cards_of(code, free[0])


@pytest.mark.parametrize("code", ["he", "fr", "en"])
def test_not_everything_is_free(code):
    topics = list(lang.content()[code]["topics"])
    assert len(topics) > len(lang.free_topics(code)), "продавать нечего"


def test_free_lesson_is_a_whole_lesson():
    """Огрызок вместо урока показал бы, что продукт плохой."""
    code = "he"
    tasks = lang.build(code, lang.free_topics(code)[0], set(), level=2)
    assert len(tasks) >= 4


# --- деньги -----------------------------------------------------------

def test_prices_are_whole_stars():
    for days, stars in access.TARIFFS.values():
        assert isinstance(stars, int) and stars > 0
        assert isinstance(days, int) and days > 0


def test_longer_access_costs_less_per_day():
    """Иначе годовой тариф бессмысленен и выглядит обманом."""
    per_day = [stars / days for days, stars in access.TARIFFS.values()]
    assert per_day == sorted(per_day, reverse=True)


def test_every_language_can_be_bought():
    for code in lang.content():
        assert lang.skill_of(code) in access.SKILLS


def test_buy_buttons_cover_all_tariffs(paid, monkeypatch):
    import database

    async def get_setting(key, default=None):
        return ""

    monkeypatch.setattr(database, "get_setting", get_setting)
    rows = run(access.buy_kb("lang_he")).inline_keyboard
    data = [b.callback_data for row in rows for b in row if b.callback_data]
    for code in access.TARIFFS:
        assert f"buy_skill_lang_he_{code}" in data


def test_card_button_appears_only_with_a_till(paid, monkeypatch):
    """Кнопка «оплатить картой» без кассы вела бы в никуда."""
    import database

    store = {}

    async def get_setting(key, default=None):
        return store.get(key, "")

    monkeypatch.setattr(database, "get_setting", get_setting)
    assert not any(b.url for row in run(access.buy_kb("lang_he")).inline_keyboard
                   for b in row)

    store["pay_url_lang_he"] = "https://example.com/pay"
    assert any(b.url == "https://example.com/pay"
               for row in run(access.buy_kb("lang_he")).inline_keyboard
               for b in row)


def test_payment_payload_survives_the_underscores():
    """«skill_lang_he_30»: в имени навыка своё подчёркивание, и наивный
    split развалил бы его на куски."""
    payload = "skill_lang_he_30"
    skill, _, tail = payload[len("skill_"):].rpartition("_")
    assert skill == "lang_he" and int(tail) == 30
    assert skill in access.SKILLS


def test_wall_talks_about_what_is_next():
    text = access.wall_text("lang_he", "Это был пробный урок целиком.")
    assert "пробный" in text
    assert "Иврит" in text
