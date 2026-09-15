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
