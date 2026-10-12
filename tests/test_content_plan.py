# План публикаций. Проверяем то, из-за чего он был бы бесполезен:
# выдуманные цифры и отметки, которые не сохраняются.
from datetime import datetime

from conftest import run

import content_plan as cp


def test_week_id_is_stable_within_a_week():
    monday = datetime(2026, 9, 14)
    friday = datetime(2026, 9, 18)
    assert cp._week_id(monday) == cp._week_id(friday)
    assert cp._week_id(monday) != cp._week_id(datetime(2026, 9, 21))


def test_marks_survive_and_can_be_removed(settings):
    week = cp._week_id()
    run(cp._mark(week, 0, True))
    assert 0 in run(cp._done(week))
    run(cp._mark(week, 0, False))
    assert 0 not in run(cp._done(week))


def test_marks_of_one_week_do_not_leak_into_another(settings):
    run(cp._mark("2026-38", 0, True))
    assert run(cp._done("2026-39")) == set()


def test_every_template_keeps_the_author_slots():
    """В шаблоне должно остаться место для своих слов, иначе это не шаблон."""
    for key, (_, body) in cp.TEMPLATES.items():
        assert "{" in body, key


def test_facts_block_is_empty_for_no_facts():
    assert cp._facts_block({}) == ""


def test_facts_count_real_tests(monkeypatch, settings):
    """Цифра в посте о своей работе проверяема — выдумывать нельзя."""
    import asyncio

    import database

    # База тестам не нужна: без подмены facts() стучится в localhost и
    # ждёт таймаута на каждом запуске.
    monkeypatch.setattr(database, "books_link_stats",
                        lambda: asyncio.sleep(0, result={"total": 29, "done": 26}))
    monkeypatch.setattr(database, "clicks_stats",
                        lambda days=30: asyncio.sleep(0, result=(41, [], [], [])))
    monkeypatch.setattr(database, "count_travel_places",
                        lambda: asyncio.sleep(0, result=120))

    data = run(cp.facts())
    assert data["тестов в коде"] > 50
    assert data["книг"] == 29


def test_filled_template_has_no_placeholder_left(monkeypatch, settings):
    import asyncio

    import database

    monkeypatch.setattr(database, "books_link_stats",
                        lambda: asyncio.sleep(0, result={"total": 29, "done": 26}))
    monkeypatch.setattr(database, "clicks_stats",
                        lambda days=30: asyncio.sleep(0, result=(41, [], [], [])))
    monkeypatch.setattr(database, "count_travel_places",
                        lambda: asyncio.sleep(0, result=120))

    text = run(cp.filled("цифры"))
    assert "{факты}" not in text
    assert "тестов в коде" in text


def test_plan_does_not_steal_the_calendar_command():
    """Латинское /plan принадлежит календарю — забирать его нельзя."""
    source = (cp.__file__)
    with open(source, encoding="utf-8") as f:
        code = f.read()
    assert '"^/(план|plan)' not in code
    assert "/(план|контент)" in code


# --- запасы -----------------------------------------------------------

def test_stock_marks_by_urgency():
    assert cp._stock_mark(0) == "🔴"
    assert cp._stock_mark(cp.CRITICAL) == "🔴"
    assert cp._stock_mark(cp.LOW) == "⚠️"
    assert cp._stock_mark(cp.LOW + 1) == "✅"


def test_days_word_agrees_with_the_number():
    assert cp._days_word(1) == "1 день"
    assert cp._days_word(2) == "2 дня"
    assert cp._days_word(5) == "5 дней"
    assert cp._days_word(11) == "11 дней"
    assert cp._days_word(21) == "21 день"


def _fake_stock(monkeypatch, values):
    import asyncio

    import database

    monkeypatch.setattr(database, "section_stock",
                        lambda s: asyncio.sleep(0, result=values.get(s, (0, 0, 0))))
    monkeypatch.setattr(database, "count_puzzles",
                        lambda: asyncio.sleep(0, result=0))
    monkeypatch.setattr(database, "published_puzzle_ids",
                        lambda: asyncio.sleep(0, result=[]))


def test_empty_section_is_not_shown(monkeypatch):
    """Раздела без материалов вовсе не бывает «на исходе» — его просто нет."""
    _fake_stock(monkeypatch, {"books": (0, 0, 0), "genetics": (40, 12, 28)})
    rows = run(cp.stock())
    assert [title for _, title, *_ in rows] == ["🧬 Генетика"]


def test_running_out_is_reported(monkeypatch):
    _fake_stock(monkeypatch, {"books": (29, 27, 2), "genetics": (40, 12, 28)})
    text = run(cp.stock_text())
    assert "🔴" in text
    assert "2 дня" in text
    assert "Скоро закончится" in text


def test_enough_everywhere_says_so(monkeypatch):
    _fake_stock(monkeypatch, {"books": (29, 1, 28), "genetics": (40, 1, 39)})
    assert "хватает больше чем на неделю" in run(cp.stock_text())


# --- задание на картинку ----------------------------------------------
#
# Материал без фотографии в канал не идёт и молча остаётся в очереди.
# Ждать он может месяцами: узнать о нём можно было, только открыв
# «Что править» и вспомнив, что такой экран есть.

import config
import content_plan as cp


class _Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text, kw.get("reply_markup")))


def test_a_missing_photo_becomes_a_task(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 77)
    bot = _Bot()
    assert run(cp.ask_photo(bot, "travel", 12, "Живерни")) is True
    who, text, markup = bot.sent[0]
    assert who == 77, "задание ушло не владелице"
    assert "Живерни" in text and "нет фотографии" in text
    marks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert marks == ["photofor_travel_12"]


def test_the_same_material_is_asked_about_once(settings, monkeypatch):
    """Напоминать про тот же — учить не читать сообщения от бота."""
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    bot = _Bot()
    run(cp.ask_photo(bot, "travel", 12, "Живерни"))
    run(cp.ask_photo(bot, "travel", 12, "Живерни"))
    assert len(bot.sent) == 1


def test_another_material_is_asked_about_separately(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    bot = _Bot()
    run(cp.ask_photo(bot, "travel", 12, "Живерни"))
    run(cp.ask_photo(bot, "travel", 13, "Онфлёр"))
    assert len(bot.sent) == 2


def test_a_section_that_needs_no_picture_is_left_alone(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    bot = _Bot()
    assert run(cp.ask_photo(bot, "genetics", 5, "Что такое ген")) is False
    assert not bot.sent


def test_every_section_knows_where_to_put_the_file():
    """Иначе фото уедет в никуда, а человек увидит «готово»."""
    import database
    for section, (name, setter) in cp.PHOTO_TASK.items():
        assert hasattr(database, setter), f"{section}: нет {setter}"
