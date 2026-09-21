# Курсы: содержание и ворота.
#
# Вопрос с двумя правильными ответами или с разбором, противоречащим
# ответу, дискредитирует курс сильнее, чем его отсутствие: человек решает,
# что здесь просто не разбираются. Поэтому содержание проверяется
# механически, целиком, а не выборочно.
import re

import pytest

from conftest import run

import access
import config
import courses

CYRILLIC_OK = re.compile(r"[A-Za-zА-Яа-яЁё0-9]")


def all_items():
    for course in courses.content():
        for topic in courses.topics_of(course):
            for item in courses.items_of(course, topic):
                yield course, topic, item


ITEMS = list(all_items())


def test_both_courses_are_there():
    assert set(courses.content()) == {"mba", "ai"}


def test_there_is_enough_to_sell():
    assert len(ITEMS) >= 30


@pytest.mark.parametrize("course,topic,item", ITEMS,
                         ids=[i[2]["id"] for i in ITEMS])
def test_question_is_whole(course, topic, item):
    assert item["q"].strip()
    assert len(item["options"]) == 4, "четыре варианта, иначе выбор другой"
    assert all(str(o).strip() for o in item["options"])
    assert item["why"].strip(), "без разбора вопрос бесполезен"


@pytest.mark.parametrize("course,topic,item", ITEMS,
                         ids=[i[2]["id"] for i in ITEMS])
def test_right_answer_exists_and_is_alone(course, topic, item):
    assert 0 <= item["right"] < len(item["options"])
    assert len(set(item["options"])) == 4, "повтор варианта — два верных ответа"


@pytest.mark.parametrize("course,topic,item", ITEMS,
                         ids=[i[2]["id"] for i in ITEMS])
def test_explanation_is_an_explanation(course, topic, item):
    """Разбор короче строки — это не разбор, а отговорка."""
    assert len(item["why"]) > 60


def test_ids_are_unique():
    ids = [item["id"] for _, _, item in ITEMS]
    assert len(ids) == len(set(ids))


def test_right_answers_are_not_always_first():
    """Если верный всегда первый, тест сдаётся не думая."""
    places = {item["right"] for _, _, item in ITEMS}
    assert len(places) >= 3


def test_buttons_mark_exactly_one_right(monkeypatch):
    for _, _, item in ITEMS:
        rows = courses._answers_kb(item).inline_keyboard
        marks = [b.callback_data for row in rows for b in row]
        assert marks.count("crs_a_1") == 1, item["id"]


# --- доступ -----------------------------------------------------------

@pytest.fixture
def paid(monkeypatch):
    import database

    bought = {}

    async def skill_until(user_id, skill):
        return bought.get((user_id, skill))

    monkeypatch.setattr(database, "skill_until", skill_until)
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    return bought


@pytest.mark.parametrize("course", ["mba", "ai"])
def test_each_course_can_be_bought(course):
    assert courses.skill_of(course) in access.SKILLS


@pytest.mark.parametrize("course", ["mba", "ai"])
def test_first_topic_is_free_and_full(course):
    free = courses.free_topics(course)
    assert len(free) == 1
    assert len(courses.items_of(course, free[0])) >= 5, "огрызок не продаст курс"


@pytest.mark.parametrize("course", ["mba", "ai"])
def test_there_is_something_behind_the_wall(course):
    assert len(courses.topics_of(course)) > len(courses.free_topics(course))


def test_locked_topics_are_visible(paid):
    """Спрятанное не купят: замок должен быть виден."""
    rows = courses._topics_kb("ai", paid=False).inline_keyboard
    texts = [b.text for row in rows for b in row]
    assert any(t.startswith("🔒") for t in texts)
    assert sum(1 for t in texts if t.startswith("🔒")) == \
        len(courses.topics_of("ai")) - 1


def test_paid_sees_no_locks(paid):
    rows = courses._topics_kb("ai", paid=True).inline_keyboard
    assert not any(b.text.startswith("🔒") for row in rows for b in row)


def test_owner_pays_nothing(paid):
    assert run(access.has(1, "course_ai"))
    assert not run(access.has(42, "course_ai"))


def test_ai_course_covers_cicd():
    """Ради этого курс и заводился."""
    assert "cicd" in courses.topics_of("ai")
    text = " ".join(item["q"] + " ".join(item["options"]) + item["why"]
                    for item in courses.items_of("ai", "cicd"))
    for word in ("версию модели", "eval", "трафика"):
        assert word in text
