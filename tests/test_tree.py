# Разбор вопросами: несколько деревьев с переходами между ними.
#
# Три вещи здесь ломают разговор молча. Кнопка в несуществующий узел
# обрывает его на середине — человек решает, что сломано всё. Ветка без
# конца оставляет его с вопросом вместо ответа. А длинное имя узла не
# помещается в callback_data, и кнопка просто перестаёт работать.
#
# Поэтому дерево проверяется до людей, имена узлов переписываются на
# короткие, а черновик не становится публикацией сам.
import json

import pytest

from conftest import run

import config
import tree


def node(text, options=(), source=None):
    out = {"text": text, "options": [dict(o) for o in options]}
    if source is not None:
        out["source"] = source
    return out


GOOD = {"trees": {
    "t1": {"title": "Что такое ген", "start": "n1", "nodes": {
        "n1": node("Ген — это участок ДНК.",
                   [{"label": "Носительство", "next": "n2"},
                    {"label": "Про риск", "go": "t2"}], source=1),
        "n2": node("Носитель — не больной.", source=1),
    }},
    "t2": {"title": "Как считают риск", "start": "n1", "nodes": {
        "n1": node("Риск — это вероятность.", source=2),
    }},
}}


# --- проверка ---------------------------------------------------------

def test_good_set_passes():
    assert tree.check(GOOD) == ""


def test_empty_is_refused():
    assert tree.check({}) == "нет деревьев"
    assert tree.check({"trees": {}}) == "нет деревьев"


def test_tree_without_a_title_is_refused():
    """Без названия тему нечем подписать на кнопке выбора."""
    broken = {"trees": {"t1": {"title": " ", "start": "n1",
                               "nodes": {"n1": node("Текст")}}}}
    assert "без названия" in tree.check(broken)


def test_start_must_exist():
    broken = {"trees": {"t1": {"title": "Т", "start": "нет-такого",
                               "nodes": {"n1": node("Текст")}}}}
    assert "начало" in tree.check(broken)


def test_button_into_nowhere_is_caught():
    broken = {"trees": {"t1": {"title": "Т", "start": "n1", "nodes": {
        "n1": node("Вопрос", [{"label": "Туда", "next": "призрак"}]),
        "n2": node("Конец")}}}}
    assert "несуществующ" in tree.check(broken)


def test_crossing_into_nowhere_is_caught():
    """Переход в удалённую тему обрывает разговор так же, как битая
    кнопка внутри дерева."""
    broken = {"trees": {"t1": {"title": "Т", "start": "n1", "nodes": {
        "n1": node("Вопрос", [{"label": "Туда", "go": "t9"}]),
        "n2": node("Конец")}}}}
    assert "несуществующее дерево" in tree.check(broken)


def test_tree_without_an_ending_is_refused():
    loop = {"trees": {"t1": {"title": "Т", "start": "n1", "nodes": {
        "n1": node("Вопрос", [{"label": "Дальше", "next": "n2"}]),
        "n2": node("Ещё вопрос", [{"label": "Назад", "next": "n1"}])}}}}
    assert "конца" in tree.check(loop)


def test_too_many_topics_is_refused():
    """Длинный список тем на входе — снова список, который листают."""
    many = {"trees": {f"t{i}": {"title": f"Тема {i}", "start": "n1",
                                "nodes": {"n1": node("Текст")}}
                      for i in range(tree.MAX_TREES + 2)}}
    assert "много тем" in tree.check(many)


def test_long_label_is_refused():
    broken = {"trees": {"t1": {"title": "Т", "start": "n1", "nodes": {
        "n1": node("Вопрос", [{"label": "очень длинная подпись, которая "
                               "точно не поместится", "next": "n2"}]),
        "n2": node("Конец")}}}}
    assert "длинная" in tree.check(broken)


# --- старая запись ----------------------------------------------------

def test_single_tree_record_still_works():
    """Первое дерево лежало без обёртки. Выбросить его — значит потерять
    то, что владелица уже проверила."""
    old = {"start": "a", "nodes": {"a": node("Текст")}}
    fresh = tree.normalise(old)
    assert list(fresh["trees"]) == ["main"]
    assert tree.check(fresh) == ""


def test_normalise_ignores_rubbish():
    assert tree.normalise(None) == {}
    assert tree.normalise({"что-то": 1}) == {}


# --- короткие имена ---------------------------------------------------

def test_long_names_are_rewritten():
    """Модель зовёт узлы «что_такое_ген_подробнее». В callback_data 64
    байта на всё, и такая кнопка молча перестаёт работать."""
    wordy = {"trees": {"что_такое_ген_очень_длинное_имя": {
        "title": "Ген", "start": "первый_узел_с_длинным_именем", "nodes": {
            "первый_узел_с_длинным_именем": node(
                "Текст", [{"label": "Дальше", "next": "второй_узел"}]),
            "второй_узел": node("Конец")}}}}
    small = tree.compact(wordy)
    assert list(small["trees"]) == ["t1"]
    assert set(small["trees"]["t1"]["nodes"]) == {"n1", "n2"}
    assert small["trees"]["t1"]["start"] == "n1"
    assert small["trees"]["t1"]["nodes"]["n1"]["options"][0]["next"] == "n2"
    assert tree.check(small) == ""


def test_crossings_survive_renaming():
    renamed = tree.compact({"trees": {
        "первое": {"title": "А", "start": "x", "nodes": {
            "x": node("Текст", [{"label": "Туда", "go": "второе"}])}},
        "второе": {"title": "Б", "start": "y", "nodes": {"y": node("Конец")}},
    }})
    assert renamed["trees"]["t1"]["nodes"]["n1"]["options"][0]["go"] == "t2"


def test_dead_buttons_are_dropped():
    """Кнопка в никуда лучше исчезнет, чем оборвёт разговор у читателя."""
    small = tree.compact({"trees": {"a": {"title": "А", "start": "x", "nodes": {
        "x": node("Текст", [{"label": "В никуда", "next": "призрак"}])}}}})
    assert small["trees"]["t1"]["nodes"]["n1"]["options"] == []


def test_crossings_are_listed():
    assert tree.crossings(GOOD) == [
        ("Что такое ген", "Как считают риск", "Про риск")]


def test_unreachable_nodes_are_named_with_their_tree():
    data = json.loads(json.dumps(GOOD))
    data["trees"]["t1"]["nodes"]["n9"] = node("Никому не видно")
    assert tree.unreachable(data) == ["t1/n9"]
    assert tree.unreachable(GOOD) == []


# --- хранение ---------------------------------------------------------

def test_draft_and_live_are_different_places(settings):
    run(tree.save_tree(GOOD, tree.DRAFT_KEY))
    assert run(tree.tree(tree.DRAFT_KEY))["trees"]
    assert run(tree.tree(tree.TREE_KEY)) == {}


def test_broken_json_does_not_crash(settings):
    settings[tree.TREE_KEY] = "не json"
    assert run(tree.tree()) == {}


# --- подписи кнопок ----------------------------------------------------

@pytest.mark.parametrize("said,expected", [
    ("дальше хочу узнать про носительство", "Про носительство"),
    ("Хочу узнать, как считают риск", "Как считают риск"),
    ("расскажите подробнее о мутациях", "О мутациях"),
])
def test_filler_is_cut_from_labels(said, expected):
    assert tree.tidy_label(said) == expected


def test_label_made_only_of_filler_survives():
    """Пустая кнопка хуже лишнего слова."""
    assert tree.tidy_label("подробнее") == "Подробнее"


def test_tidy_walks_every_tree():
    data = json.loads(json.dumps(GOOD))
    data["trees"]["t1"]["nodes"]["n1"]["options"][0]["label"] = \
        "дальше хочу узнать про гены"
    assert tree.tidy(data)["trees"]["t1"]["nodes"]["n1"]["options"][0]["label"] \
        == "Про гены"


# --- границы ----------------------------------------------------------

def test_prompt_forbids_inventing_and_advising():
    low = tree.PROMPT.lower()
    assert "ничего не добавляй" in low
    assert "никаких советов" in low
    assert "не ставь диагнозов" in low


def test_prompt_says_it_is_not_an_exam():
    low = tree.PROMPT.lower()
    assert "не тест" in low and "нет верных и неверных" in low


def test_prompt_asks_for_crossings():
    """Ради этого и делалось несколько деревьев: тема, упёршаяся в
    соседнюю, должна вести туда, а не в «об этом в другой раз»."""
    assert "go" in tree.PROMPT and "другого дерева" in tree.PROMPT


# --- охват -------------------------------------------------------------

def test_used_articles_are_counted():
    assert tree.used_articles(GOOD) == {1, 2}


def test_coverage_separates_unused_from_uncut(settings, monkeypatch):
    """«Не вошло» и «не дошло до модели» — разные беды: первую лечит
    другой промпт, вторую — второе дерево."""
    import database

    async def rows(section):
        return [(1, "Ген", "текст"), (2, "Риск", "текст"),
                (3, "Скрининг", "текст"), (4, "Наследование", "текст")]

    monkeypatch.setattr(database, "get_articles_raw", rows)
    got = run(tree.coverage(dict(GOOD, given=[1, 2, 3], cut=[4])))
    assert got["all"] == 4
    assert got["used"] == [1, 2]
    assert got["unused"] == [3]
    assert got["cut"] == [4]


def test_coverage_text_names_what_is_missing(settings, monkeypatch):
    import database

    async def rows(section):
        return [(1, "Ген", "текст"), (2, "Риск", "текст"),
                (3, "Скрининг", "текст")]

    monkeypatch.setattr(database, "get_articles_raw", rows)
    text = run(tree.coverage_text(dict(GOOD, cut=[])))
    assert "2 статей из 3" in text
    assert "Скрининг" in text


def test_draft_walking_is_owner_only(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)

    class Msg:
        def __init__(self):
            self.said = []

        async def answer(self, text, **kw):
            self.said.append(text)

    class Call:
        def __init__(self, user_id):
            self.data = "trd_t1_n1"
            self.message = Msg()
            self.from_user = type("U", (), {"id": user_id})()

        async def answer(self, text="", **kw):
            pass

    run(tree.save_tree(GOOD, tree.DRAFT_KEY))
    stranger = Call(999)
    run(tree.step_draft(stranger))
    assert not stranger.message.said, "чужой человек листает черновик"


# --- два вида разбора --------------------------------------------------
#
# Механика одна, а источник и срок жизни разные. Генетика собирается из
# статей и живёт месяцами; экономика — из событий дня и устаревает
# вместе с ними.

def test_two_kinds_live_in_different_places():
    """Один ключ на оба — и экономика затрёт генетику в первое же утро."""
    assert tree.keys("g") != tree.keys("e")
    assert len(set(tree.keys("g") + tree.keys("e"))) == 4


def test_unknown_kind_falls_back_to_genetics():
    assert tree.keys("чушь") == tree.keys("g")


def test_economy_is_not_built_from_articles():
    assert tree.KINDS["e"]["articles"] is False
    assert tree.KINDS["g"]["articles"] is True


def test_economy_prompt_starts_from_the_reader():
    """«Как это касается меня» — вопрос, который у человека уже есть."""
    low = tree.ECONOMY_PROMPT.lower()
    assert "касается лично его" in low
    assert "наёмный работник" in low


def test_economy_prompt_forbids_investment_advice():
    """Совет вложиться требует лицензии, которой нет."""
    low = tree.ECONOMY_PROMPT.lower()
    for word in ("покупать", "продавать", "вкладывать", "менять валюту"):
        assert word in low, word
    assert "ни прямо, ни намёком" in low
    assert "не предсказывай" in low


def test_economy_prompt_forbids_naming_winners():
    assert "отдельные компании" in tree.ECONOMY_PROMPT.lower()


def test_kind_travels_in_the_button(settings):
    """Без вида в callback_data кнопка из экономики уведёт в генетику."""
    data = tree.compact(GOOD)
    node = data["trees"]["t1"]["nodes"]["n1"]
    marks = [b.callback_data
             for row in tree._node_kb("e", "t1", node, False).inline_keyboard
             for b in row]
    assert all(m.startswith("tre_e_") for m in marks)


def test_saving_by_kind_does_not_mix(settings):
    run(tree.save_tree(GOOD, "live", "e"))
    assert run(tree.tree("live", "e"))["trees"]
    assert run(tree.tree("live", "g")) == {}
