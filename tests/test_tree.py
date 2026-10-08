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


# --- автосборка к утру -------------------------------------------------
#
# Кнопка «Как это касается меня» появляется под постом только тогда,
# когда дерево опубликовано. Поэтому забытая сборка выглядит не
# поломкой, а отсутствием кнопки: в канале просто нечего нажать, и
# узнать об этом можно было только от читателя.
#
# Чинится это НЕ автопубликацией. Генетика — медицина, и очередь
# «сначала владелица, потом люди» в tree.py заведена намеренно. Поэтому
# к утру собирается черновик, а открывает его людям по-прежнему человек.

class Bot:
    """Бот, который только запоминает, кому и что написал."""

    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text, kw.get("reply_markup")))


class Note:
    def __init__(self, user_id, data):
        self.data = data
        self.from_user = type("U", (), {"id": user_id})()
        self.popped = []
        self.markup_cleared = False
        self.message = self

    async def answer(self, text="", **kw):
        self.popped.append(text)

    async def edit_reply_markup(self, **kw):
        self.markup_cleared = True


def test_published_tree_needs_no_morning_work(settings, monkeypatch):
    """Генетика живёт месяцами — пересобирать её к каждому утру незачем."""
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    run(tree.save_tree(GOOD, "live", "g"))

    def refuse(kind="g"):
        raise AssertionError("собирали, хотя людям уже есть что показать")

    monkeypatch.setattr(tree, "build", refuse)
    bot = Bot()
    assert run(tree.prepare(bot, "g")) == ""
    assert not bot.sent


def test_missing_tree_is_built_and_reported(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 77)

    async def built(kind="g"):
        return GOOD, ""

    monkeypatch.setattr(tree, "build", built)
    bot = Bot()
    assert run(tree.prepare(bot, "g"))

    assert run(tree.tree("draft", "g"))["trees"], "черновик не сохранён"
    assert run(tree.tree("live", "g")) == {}, "показали людям без спроса"

    assert len(bot.sent) == 1
    who, text, markup = bot.sent[0]
    assert who == 77, "про черновик сказали не владелице"
    assert "не виден" in text


def test_the_note_carries_a_publish_button(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)

    async def built(kind="g"):
        return GOOD, ""

    monkeypatch.setattr(tree, "build", built)
    bot = Bot()
    run(tree.prepare(bot, "g"))
    marks = [b.callback_data
             for row in bot.sent[0][2].inline_keyboard for b in row]
    assert marks == ["trpub_g"], "без вида кнопка опубликует не то дерево"


def test_the_same_draft_is_mentioned_once(settings, monkeypatch):
    """Ежеутреннее «опубликуйте разбор» о том же самом учит не читать."""
    monkeypatch.setattr(config, "ADMIN_ID", 1)

    async def built(kind="g"):
        return GOOD, ""

    monkeypatch.setattr(tree, "build", built)
    bot = Bot()
    run(tree.prepare(bot, "g"))
    run(tree.prepare(bot, "g"))
    run(tree.prepare(bot, "g"))
    assert len(bot.sent) == 1


def test_a_failed_build_stays_quiet(settings, monkeypatch):
    """Сказать «не собралось» владелице нечего: сделать она с этим
    ничего не может, а утро у неё начнётся с сообщения об ошибке."""
    monkeypatch.setattr(config, "ADMIN_ID", 1)

    async def failed(kind="g"):
        return {}, "в разделе нет статей"

    monkeypatch.setattr(tree, "build", failed)
    bot = Bot()
    assert run(tree.prepare(bot, "g")) == ""
    assert not bot.sent


# --- публикация из письма ----------------------------------------------

def test_publishing_from_the_note_is_owner_only(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    run(tree.save_tree(GOOD, "draft", "g"))

    run(tree.publish_from_note(Note(999, "trpub_g")))
    assert run(tree.tree("live", "g")) == {}, "чужой человек открыл разбор"


def test_publishing_from_the_note_shows_people_the_draft(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    run(tree.save_tree(GOOD, "draft", "g"))

    note = Note(1, "trpub_g")
    run(tree.publish_from_note(note))
    assert run(tree.tree("live", "g"))["trees"]
    assert note.markup_cleared, "кнопку можно нажать второй раз"


def test_a_broken_draft_is_not_published_from_the_note(settings, monkeypatch):
    """Та же проверка, что у команды: кнопка в несуществующий узел
    обрывает разговор на середине."""
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    broken = {"trees": {"t1": {"title": "Тема", "start": "нет",
                               "nodes": {"n1": node("Текст")}}}}
    run(tree.save_tree(broken, "draft", "g"))

    note = Note(1, "trpub_g")
    run(tree.publish_from_note(note))
    assert run(tree.tree("live", "g")) == {}
    assert any("нельзя" in t for t in note.popped)


def test_an_unknown_kind_publishes_nothing(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    run(tree.save_tree(GOOD, "draft", "g"))
    run(tree.publish_from_note(Note(1, "trpub_чушь")))
    assert run(tree.tree("live", "g")) == {}


# --- единый вид --------------------------------------------------------
#
# Разборов три вида, а вопрос у читателя один. Пока за каждым видом
# стояла своя кнопка с одинаковой подписью, человек, нажавший под
# новостями, не узнавал, что генетика вообще существует.

ECO = {"trees": {"t1": {"title": "Ставка", "start": "n1",
                        "nodes": {"n1": node("Ставка — это цена денег.")}}}}


def test_all_kinds_come_in_one_list(settings):
    run(tree.save_tree(GOOD, "live", "g"))
    run(tree.save_tree(ECO, "live", "e"))
    items = run(tree.all_trees())
    assert {k for k, _, _ in items} == {"g", "e"}
    assert len(items) == 3


def test_every_button_keeps_its_own_kind(settings):
    """Без вида в кнопке тема из экономики уведёт в генетику."""
    run(tree.save_tree(GOOD, "live", "g"))
    run(tree.save_tree(ECO, "live", "e"))
    kb = tree._all_kb(run(tree.all_trees()), False)
    marks = [b.callback_data for row in kb.inline_keyboard for b in row
             if b.callback_data and b.callback_data.startswith("tre_")]
    assert any(m.startswith("tre_g_") for m in marks)
    assert any(m.startswith("tre_e_") for m in marks)


def test_the_list_says_where_a_topic_came_from(settings):
    run(tree.save_tree(ECO, "live", "e"))
    kb = tree._all_kb(run(tree.all_trees()), False)
    assert kb.inline_keyboard[0][0].text.startswith("📊")


def test_old_buttons_in_published_posts_keep_working():
    """`tree_open` и `eco_open` стоят под уже вышедшими постами и
    останутся там навсегда — переименовать их в канале нельзя."""
    import inspect
    src = inspect.getsource(tree.open_tree)
    assert "learn_open" in src and "tree_open" in src and "eco_open" in src


def test_end_of_a_branch_returns_to_the_common_list(settings):
    """Дочитавшему про ставку незачем объяснять, что генетика живёт за
    другой кнопкой."""
    kb = tree._node_kb("e", "t1", node("Конец."), False)
    marks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert f"tre_{tree.ALL}_list" in marks


def test_the_common_view_has_no_tree_of_its_own(settings):
    """Узел в нём искать негде — он только список."""
    run(tree.save_tree(GOOD, "live", "g"))

    said = []

    class Msg:
        async def answer(self, text, **kw):
            said.append(text)

    run(tree.show(Msg(), "t1_n1", tree.ALL))
    assert said and "касается меня" in said[0]


# --- книги -------------------------------------------------------------
#
# Модель книгу не читала. Разбор она может собрать только по конспекту,
# а по витринной аннотации в две фразы — лишь выдумать.

def test_books_are_a_kind_of_their_own(settings):
    assert tree.keys("b") != tree.keys("g") != tree.keys("e")
    assert len(set(tree.keys("g") + tree.keys("e") + tree.keys("b"))) == 6


def test_books_have_no_article_coverage():
    """Охват считается по статьям раздела генетики; у книг его нет."""
    assert tree.KINDS["b"]["articles"] is False
    assert tree.KINDS["b"]["source"] == "books"


def _shelf(monkeypatch, books):
    import books_seed
    monkeypatch.setattr(books_seed, "load_seed", lambda: books)


def test_a_book_without_a_summary_is_skipped(monkeypatch):
    """«Чему научит: две фразы» — это витрина полки, а не её
    содержание. Развернуть её модель может только выдумкой."""
    _shelf(monkeypatch, [{"author": "Бен Хоровиц", "title": "Легко не будет",
                          "learn": "Что делать, когда решения нет."}])
    assert run(tree.books_source())[0] == ""


def test_a_real_summary_is_taken(monkeypatch):
    _shelf(monkeypatch, [{"author": "Бен Хоровиц", "title": "Легко не будет",
                          "summary": "Мысль книги. " * 60}])
    out, took, cut = run(tree.books_source())
    assert "Хоровиц" in out and "Легко не будет" in out
    assert took == ["Легко не будет"] and cut == []


def test_thin_books_do_not_ride_along_with_thick_ones(monkeypatch):
    """Порог стоит на книге, а не на сумме: двадцать аннотаций в сумме
    длинные, а знания в них по-прежнему нет."""
    _shelf(monkeypatch, [
        {"author": "А", "title": "Толстая", "summary": "Мысль. " * 120},
        {"author": "Б", "title": "Тонкая", "learn": "Ничему."},
    ])
    out, took, cut = run(tree.books_source())
    assert "Толстая" in out and "Тонкая" not in out
    assert cut == [], "пропуск по тонкости — не потеря, а осознанный отказ"


def test_the_channel_post_is_not_the_source(monkeypatch):
    """Конспект берётся из файла, а не из того, что ушло в канал: пост
    с конспектом разбух бы до нечитаемого."""
    import database

    async def boom(*a, **kw):
        raise AssertionError("полезли в таблицу книг за конспектом")

    monkeypatch.setattr(database, "get_books", boom)
    _shelf(monkeypatch, [{"author": "А", "title": "К", "summary": "Х. " * 400}])
    assert run(tree.books_source())


def test_books_prompt_forbids_inventing_the_book():
    low = tree.BOOKS_PROMPT.lower()
    assert "ты книгу не читала" in low
    assert "пересказывать книгу целиком" in low
    assert "не тому автору" in low


def test_books_have_their_own_command():
    """Соседняя команда, отличающаяся одной буквой от поиска книги, —
    способ однажды собрать дерево вместо поиска."""
    assert tree._cmd("b") == "/книгиразбор"
    assert tree._cmd("b") not in ("/книга", "/книгу")


def test_a_book_that_did_not_fit_is_counted(monkeypatch):
    """Книга, не попавшая даже в исходник, не могла оказаться в дереве.
    Знать об этом надо до того, как удивляться, почему темы нет."""
    _shelf(monkeypatch, [
        {"author": "А", "title": "Первая", "summary": "Мысль. " * 120},
        {"author": "Б", "title": "Вторая", "summary": "Мысль. " * 120},
    ])
    out, took, cut = run(tree.books_source(limit=100))
    assert took == ["Первая"]
    assert cut == ["Вторая"]


def test_the_whole_shelf_fits_by_default():
    """Разбор группирует книги по общей мысли, а мысль, собранная по
    трети полки, — не та же самая."""
    out, took, cut = run(tree.books_source())
    assert not cut, f"не поместились: {cut}"
    assert len(took) == 29
