# Слова финалистов. Главное здесь — не нахватать чужого: в заметке о
# финале говорят оба игрока, тренер и автор, и цитата без подписи
# приписала бы человеку то, чего он не говорил.
import asyncio

import tennis_speech as ts


STORY = (
    'TOKYO -- Diana Shnaider won her fourth title on Sunday, beating '
    'Leylah Fernandez 6-4, 7-6 (7). "It was the longest week of my season '
    'and I am glad it ended this way," Shnaider said after the ceremony. '
    'Fernandez, who lost her third final of the year, said: "I will come '
    'back here next year and I will be ready for it." The crowd stayed '
    'until the end, which one official called "the best Sunday in years."'
)


def test_quote_goes_to_the_one_who_said_it():
    said = ts.quotes_in(STORY, "Shnaider", ["Leylah Fernandez"])
    assert said == ["It was the longest week of my season "
                    "and I am glad it ended this way,"]

    said = ts.quotes_in(STORY, "Fernandez", ["Diana Shnaider"])
    assert said == ["I will come back here next year and I will be ready "
                    "for it."]


def test_a_quote_without_a_name_is_nobody_s():
    """«the best Sunday in years» сказал распорядитель турнира. Рядом
    нет ни одной фамилии финалиста — значит, в пост она не идёт."""
    for who in ("Shnaider", "Fernandez"):
        assert all("best Sunday" not in q for q in ts.quotes_in(STORY, who))


def test_scraps_and_sheets_are_skipped():
    short = 'He shrugged. "No comment," Shnaider said.'
    assert ts.quotes_in(short, "Shnaider") == []

    long = 'Shnaider said: "' + ("word " * 100) + '"'
    assert ts.quotes_in(long, "Shnaider") == []


def test_typographic_quotes_count_too():
    text = '“I knew the second set would be close,” Shnaider said.'
    assert ts.quotes_in(text, "Shnaider") == [
        "I knew the second set would be close,"]


def test_the_block_is_empty_when_nobody_spoke(monkeypatch):
    async def nothing(tour, name, limit=2, others=()):
        return []
    monkeypatch.setattr(ts, "quotes_for", nothing)
    assert asyncio.run(ts.block("wta", ["Diana Shnaider"])) == ""


def test_the_block_carries_the_original_and_the_translation(monkeypatch):
    async def said(tour, name, limit=2, others=()):
        return ["It was the longest week of my season."]

    async def ru(text):
        return "Это была самая длинная неделя сезона."

    monkeypatch.setattr(ts, "quotes_for", said)
    monkeypatch.setattr(ts, "_ru", ru)
    out = asyncio.run(ts.block("wta", ["Diana Shnaider"]))

    assert "It was the longest week of my season." in out, "оригинал пропал"
    assert "Это была самая длинная неделя сезона." in out, "перевод пропал"
    assert "Шнайдер" in out, "не подписано, кто сказал"


def test_the_original_stays_even_without_a_translation(monkeypatch):
    """Перевод собирает модель, и она может промолчать. Слова игрока от
    этого никуда не деваются — публикуем их как есть."""
    async def said(tour, name, limit=2, others=()):
        return ["No regrets at all."]

    async def silent(text):
        return ""

    monkeypatch.setattr(ts, "quotes_for", said)
    monkeypatch.setattr(ts, "_ru", silent)
    out = asyncio.run(ts.block("wta", ["Diana Shnaider"]))
    assert "No regrets at all." in out
