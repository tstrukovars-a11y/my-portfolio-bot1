# Разбор вопросами: дерево, собранное из своих же статей.
#
# Две вещи здесь ломают разговор молча. Кнопка, ведущая в несуществующий
# узел, обрывает его на середине — и человек решает, что сломано всё.
# Ветка без конца оставляет его с вопросом вместо ответа.
#
# Поэтому дерево проверяется до людей, а не после, и черновик не
# становится публикацией сам.
import json

import pytest

from conftest import run

import config
import tree


def node(text, options=()):
    return {"text": text, "options": [{"label": l, "next": n}
                                      for l, n in options]}


GOOD = {"start": "a", "nodes": {
    "a": node("У кого нашли?", [("У меня", "b"), ("У родственника", "c")]),
    "b": node("Носитель — не больной."),
    "c": node("Риск считается иначе."),
}}


# --- проверка ---------------------------------------------------------

def test_good_tree_passes():
    assert tree.check(GOOD) == ""


def test_empty_tree_is_refused():
    assert tree.check({}) == "нет узлов"
    assert tree.check({"start": "a", "nodes": {}})


def test_start_must_exist():
    """Иначе разговор не начинается вовсе, а причина не видна."""
    broken = {"start": "нет-такого", "nodes": GOOD["nodes"]}
    assert "начало" in tree.check(broken)


def test_button_into_nowhere_is_caught():
    broken = {"start": "a", "nodes": {
        "a": node("Вопрос", [("Туда", "призрак")]),
        "b": node("Конец"),
    }}
    assert "несуществующ" in tree.check(broken)


def test_tree_without_an_ending_is_refused():
    """Разговор, обрывающийся вопросом, хуже, чем его отсутствие."""
    loop = {"start": "a", "nodes": {
        "a": node("Вопрос", [("Дальше", "b")]),
        "b": node("Ещё вопрос", [("Назад", "a")]),
    }}
    assert "конца" in tree.check(loop)


def test_empty_node_is_caught():
    broken = {"start": "a", "nodes": {"a": node("   ")}}
    assert "пуст" in tree.check(broken)


def test_nameless_button_is_caught():
    broken = {"start": "a", "nodes": {
        "a": {"text": "Вопрос", "options": [{"label": " ", "next": "b"}]},
        "b": node("Конец")}}
    assert "безымянная" in tree.check(broken)


def test_too_big_tree_is_refused():
    """Длинное дерево никто не проходит: это снова лонгрид, только хуже."""
    nodes = {str(i): node(f"Шаг {i}") for i in range(tree.MAX_NODES + 3)}
    assert "много" in tree.check({"start": "0", "nodes": nodes})


def test_unreachable_nodes_are_listed():
    data = {"start": "a", "nodes": dict(GOOD["nodes"],
                                        d=node("Никому не видно"))}
    assert tree.unreachable(data) == ["d"]
    assert tree.unreachable(GOOD) == []


# --- хранение ---------------------------------------------------------

def test_draft_and_live_are_different_places(settings):
    """Иначе собранное сразу оказывается перед людьми."""
    run(tree.save_tree(GOOD, tree.DRAFT_KEY))
    assert run(tree.tree(tree.DRAFT_KEY)) == GOOD
    assert run(tree.tree(tree.TREE_KEY)) == {}


def test_broken_json_does_not_crash(settings):
    settings[tree.TREE_KEY] = "не json"
    assert run(tree.tree()) == {}


def test_tree_without_nodes_counts_as_missing(settings):
    settings[tree.TREE_KEY] = json.dumps({"start": "a"})
    assert run(tree.tree()) == {}


# --- границы ----------------------------------------------------------

def test_prompt_forbids_inventing_and_advising():
    """Модель говорит от лица врача — здесь строже, чем в новостях."""
    low = tree.PROMPT.lower()
    assert "ничего не добавляй" in low
    assert "никаких советов" in low
    assert "не ставь диагнозов" in low


def test_node_remembers_its_article():
    """Картинка берётся из статьи, из которой узел сделан: «что такое
    ген» словами — абзац, а картинкой — секунда."""
    assert '"source"' in tree.PROMPT
    assert "[[12]]" in tree.PROMPT


def test_source_text_numbers_the_articles(settings, monkeypatch):
    import database

    async def rows(section):
        return [(7, "Что такое ген", "Длинное объяснение"), (9, "Мутации", "Текст")]

    monkeypatch.setattr(database, "get_articles_raw", rows)
    text = run(tree.source_text())
    assert "[[7]]" in text and "[[9]]" in text


def test_step_replaces_the_previous_question(settings):
    """Иначе переписка заполняется вопросами, на которые уже ответили,
    и человек перестаёт понимать, где он находится."""
    source = open(tree.__file__, encoding="utf-8").read()
    assert "replace=True" in source
    assert "edit_text" in source


def test_draft_walking_is_owner_only(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)

    class Msg:
        def __init__(self):
            self.said = []

        async def answer(self, text, **kw):
            self.said.append(text)

    class Call:
        def __init__(self, user_id):
            self.data = "trd_a"
            self.message = Msg()
            self.from_user = type("U", (), {"id": user_id})()

        async def answer(self, text="", **kw):
            pass

    run(tree.save_tree(GOOD, tree.DRAFT_KEY))
    stranger = Call(999)
    run(tree.step_draft(stranger))
    assert not stranger.message.said, "чужой человек листает черновик"


# --- подписи кнопок ----------------------------------------------------
#
# Вводные слова модель приписывает даже там, где промпт их запрещает.
# Смысла в них нет, а кнопку они удлиняют так, что название вещи не
# помещается и Телеграм режет его на середине слова.

@pytest.mark.parametrize("said,expected", [
    ("дальше хочу узнать про носительство", "Про носительство"),
    ("Хочу узнать, как считают риск", "Как считают риск"),
    ("расскажите подробнее о мутациях", "О мутациях"),
    ("дальше о рисках", "О рисках"),
])
def test_filler_is_cut_from_labels(said, expected):
    assert tree.tidy_label(said) == expected


def test_preposition_stays():
    """«Носительство» после «расскажите про» осталось бы в неверном
    падеже — склонять обратно нечем."""
    assert tree.tidy_label("расскажите про носительство") == "Про носительство"


@pytest.mark.parametrize("said", ["У родственника", "Как считают риск",
                                  "Носительство"])
def test_normal_labels_are_untouched(said):
    assert tree.tidy_label(said) == said


def test_label_made_only_of_filler_survives():
    """Пустая кнопка хуже лишнего слова."""
    assert tree.tidy_label("подробнее") == "Подробнее"
    assert tree.tidy_label("") == ""


def test_tidy_walks_the_whole_tree():
    data = {"start": "a", "nodes": {
        "a": {"text": "Вопрос", "options": [
            {"label": "дальше хочу узнать про гены", "next": "b"}]},
        "b": {"text": "Конец", "options": []}}}
    assert tree.tidy(data)["nodes"]["a"]["options"][0]["label"] == "Про гены"


def test_long_label_is_refused():
    """Телеграм обрежет её на середине слова, и человек будет выбирать
    между двумя огрызками."""
    broken = {"start": "a", "nodes": {
        "a": {"text": "Вопрос", "options": [
            {"label": "очень длинная подпись, которая точно не поместится "
                      "на кнопке", "next": "b"}]},
        "b": {"text": "Конец", "options": []}}}
    assert "длинная" in tree.check(broken)


def test_prompt_says_it_is_not_an_exam():
    """Проверка знаний отпугивает: человек пришёл разобраться, а не
    сдавать."""
    low = tree.PROMPT.lower()
    assert "не тест" in low and "не проверка знаний" in low
    assert "нет верных и неверных" in low
    assert "два-четыре слова" in low
