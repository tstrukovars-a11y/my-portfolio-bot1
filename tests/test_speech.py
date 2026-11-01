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


# --- речь с церемонии --------------------------------------------------
#
# На сайте тура речь напечатана целиком, абзацами. По газетному обычаю
# каждый следующий абзац открывается кавычкой, а закрывается только
# последний — и разбор по парам кавычек на таком тексте сбивается:
# продолжение речи попадает в «слова автора».

CEREMONY = (
    'Four of her six titles have now come on hard courts, including her '
    'third WTA 500 crown in Tokyo today. "Firstly, I would like to '
    'congratulate Leylah on an amazing week," Shnaider said during the '
    'on-court presentation ceremony. "Congrats to you, your coach, your '
    'family back home. "I also want to thank my coach, who is here with '
    'me. It means a lot." The victory is projected to lift Shnaider back '
    'to a career-high No. 11 in the WTA PIF Rankings, her best position '
    'since the summer of last year, when she reached the fourth round at '
    'Wimbledon and then won in Budapest.'
)


def test_the_whole_speech_comes_through_not_the_first_line():
    said = ts.speech_of(CEREMONY, "Shnaider", ["Leylah Fernandez"])
    assert "Firstly, I would like to congratulate Leylah" in said
    assert "Congrats to you, your coach" in said, "второй абзац потерян"
    assert "I also want to thank my coach" in said, \
        "третий абзац принят за слова автора"


def test_the_speech_stops_where_the_article_resumes():
    said = ts.speech_of(CEREMONY, "Shnaider", ["Leylah Fernandez"])
    assert "projected to lift" not in said, "текст заметки попал в речь"
    assert "Wimbledon" not in said


def test_the_comma_that_holds_the_attribution_becomes_a_full_stop():
    said = ts.speech_of(CEREMONY, "Shnaider")
    assert "an amazing week. Congrats" in said


def test_nothing_for_the_one_who_was_not_quoted():
    assert ts.speech_of(CEREMONY, "Fernandez", ["Diana Shnaider"]) == ""
