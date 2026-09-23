# Тихий вход для того, кто пришёл за одним делом.
#
# Человек нажал в канале «напомнить о матче» и получал выбор языка на
# четырёх алфавитах, приветствие про ROI-кейсы, меню из восьми разделов
# и кнопку про удаление данных. Он хотел одного напоминания.
#
# Это единственная кнопка, которая уводит из канала в бота, и отпугнуть
# на ней — значит не получить человека вовсе. Поэтому проверяем: пришёл
# за делом — получил дело, а не экскурсию.
import pytest

from conftest import run

import personal


class User:
    def __init__(self, user_id=42, code="ru"):
        self.id = user_id
        self.language_code = code


# --- язык не спрашиваем -----------------------------------------------

@pytest.mark.parametrize("code,expected", [
    ("ru", "ru"), ("en-US", "en"), ("fr", "fr"), ("he", "he"),
])
def test_language_is_taken_from_telegram(code, expected):
    """Экран с четырьмя алфавитами — вопрос, ответ на который уже есть."""
    assert personal.guess_language(User(code=code)) == expected


def test_hebrew_comes_as_the_old_code():
    """Telegram отдаёт иврит как «iw» — код из семидесятых."""
    assert personal.guess_language(User(code="iw")) == "he"


@pytest.mark.parametrize("code", ["", None, "zz", "ja"])
def test_unknown_language_falls_back(code):
    assert personal.guess_language(User(code=code)) == "ru"


def test_saved_language_is_not_overwritten(settings, monkeypatch):
    """Человек однажды выбрал французский — телефон не должен его
    переспорить."""
    import database

    async def saved(user_id):
        return "fr"

    async def put(user_id, lang):
        raise AssertionError("переписали выбранный язык")

    monkeypatch.setattr(database, "get_user_language", saved)
    monkeypatch.setattr(database, "set_user_language", put)
    assert run(personal.ensure_language(User(code="en"))) == "fr"


def test_new_person_gets_a_language_without_asking(settings, monkeypatch):
    import database

    stored = {}

    async def saved(user_id):
        return stored.get(user_id, "")

    async def put(user_id, lang):
        stored[user_id] = lang

    monkeypatch.setattr(database, "get_user_language", saved)
    monkeypatch.setattr(database, "set_user_language", put)
    assert run(personal.ensure_language(User(code="he"))) == "he"
    assert stored[42] == "he"


# --- личный экран ------------------------------------------------------

@pytest.fixture
def quiet_db(monkeypatch, settings):
    import database

    async def no_alerts(user_id):
        return 0

    monkeypatch.setattr(database, "my_alerts", no_alerts)
    return settings


def test_card_says_what_is_missing(quiet_db):
    text, _ = run(personal.card(42))
    assert "место не указано" in text
    assert "Ничего лично не присылаю" in text


def test_card_counts_awaited_matches(quiet_db, monkeypatch):
    import database

    async def three(user_id):
        return 3

    monkeypatch.setattr(database, "my_alerts", three)
    text, _ = run(personal.card(42))
    assert "Жду начала матчей: 3" in text


def test_card_offers_nothing_but_the_essentials(quiet_db):
    """Ради этого всё и делалось: ни разделов, ни предложений."""
    _, markup = run(personal.card(42))
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data == ["wx_again", "subs_open", "go_home"]


def test_the_rest_is_one_discreet_line(quiet_db):
    _, markup = run(personal.card(42))
    last = markup.inline_keyboard[-1][0]
    assert last.callback_data == "go_home"
    assert "всё остальное" in last.text.lower()


def test_quiet_puts_the_reason_first(quiet_db, monkeypatch):
    import database

    async def saved(user_id):
        return "ru"

    monkeypatch.setattr(database, "get_user_language", saved)

    class Msg:
        def __init__(self):
            self.said = []

        async def answer(self, text, **kw):
            self.said.append(text)

    message = Msg()
    run(personal.quiet(message, User(), "🔔 Напоминание поставлено."))
    assert message.said[0].startswith("🔔 Напоминание поставлено.")
    assert "Ваше" in message.said[0]


# --- матч не ведёт в меню ---------------------------------------------

def test_match_start_stops_the_tour():
    """Подписался — и остался с подпиской, а не с экскурсией по боту."""
    source = open("tennis_alerts.py", encoding="utf-8").read()
    start = source.index("async def start_with_match")
    block = source[start:start + 700]
    assert "personal.quiet" in block
    assert "SkipHandler" in block, "новый человек без подписки всё же должен " \
                                   "попадать на общий вход"
