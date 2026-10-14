# Наполнить, поправить, удалить — любой раздел.
#
# До сих пор материал правился четырьмя разными путями, и пути были
# неравны: книге можно было заменить обложку, путешествию нельзя, а
# удалить нельзя было почти ничего — только через базу руками.
#
# Отсюда и копился мусор: испорченный импортом текст оставался в очереди
# навсегда, потому что убрать его было нечем.
import content_edit as ce
import database


# --- одна дверь на все разделы -----------------------------------------

def test_every_section_is_reachable():
    data = [b.callback_data for row in ce._sections_kb().inline_keyboard
            for b in row]
    for section in database.CONTENT:
        assert f"ce_list_{section}_0" in data, section


def test_the_four_sections_are_the_ones_that_publish():
    """Разделы здесь те же, что в дневной сетке: экран правки, где нет
    того, что выходит в канал, бесполезен ровно наполовину."""
    import digest
    publishing = set(digest.SLOT_SECTION.values())
    assert publishing <= set(database.CONTENT), \
        f"не правятся: {publishing - set(database.CONTENT)}"


def test_table_names_come_from_the_dictionary_only():
    """Подстановка имени таблицы в запрос безопасна ровно до тех пор,
    пока имя не приходит снаружи."""
    source = open("database.py", encoding="utf-8").read()
    body = source[source.index("def _content_meta"):]
    assert "CONTENT.get(section)" in body[:300]
    assert "raise ValueError" in body[:300]


def test_an_unknown_section_is_refused():
    import pytest
    with pytest.raises(ValueError):
        database._content_meta("'; DROP TABLE books; --")


# --- карточка ----------------------------------------------------------

def test_the_card_offers_all_three_actions():
    data = [b.callback_data for row in ce._card_kb("books", 7).inline_keyboard
            for b in row]
    assert "ce_text_books_7" in data
    assert "ce_photo_books_7" in data
    assert "ce_del_books_7" in data


def test_the_card_leads_back_to_the_list():
    data = [b.callback_data for row in ce._card_kb("books", 7).inline_keyboard
            for b in row]
    assert any(d.startswith("ce_list_books") for d in data)


# --- удаление спрашивает ------------------------------------------------

def test_deleting_asks_first():
    """Текст можно переписать обратно, фотографию прислать заново —
    остальное здесь обратимо. Удаление необратимо."""
    source = open("content_edit.py", encoding="utf-8").read()
    body = source[source.index("async def ask_delete"):]
    body = body[:body.index("async def do_delete")]
    assert "content_delete" not in body, "удаляет без подтверждения"
    assert "ce_gone_" in body


def test_the_confirmation_names_what_will_be_lost():
    """«Удалить?» без названия — вопрос, на который нельзя ответить."""
    source = open("content_edit.py", encoding="utf-8").read()
    body = source[source.index("async def ask_delete"):]
    body = body[:body.index("async def do_delete")]
    assert "content_get" in body


def test_only_the_owner_gets_in():
    source = open("content_edit.py", encoding="utf-8").read()
    handlers = source.count("@router.callback_query") + source.count("@router.message")
    guards = source.count("config.is_admin")
    # Обработчики состояний проверять не обязаны: состояние задаётся
    # только изнутри, но все входные точки — обязаны.
    assert guards >= handlers - 4, "есть вход без проверки владельца"


# --- список ------------------------------------------------------------

def test_an_item_without_a_title_still_shows_something():
    """Пустая строка в списке — кнопка, на которую не нажать."""
    source = open("database.py", encoding="utf-8").read()
    body = source[source.index("async def content_list"):]
    body = body[:body.index("async def content_get")]
    assert "без текста" in body


def test_paging_appears_only_when_there_is_where_to_go():
    """Две одинокие стрелки под восемью строками читаются как поломка."""
    source = open("content_edit.py", encoding="utf-8").read()
    body = source[source.index("async def show_list"):]
    body = body[:body.index("def _card_kb")]
    assert "if page > 0" in body and "if page + 1 < pages" in body
