# Кнопки служебного меню.
#
# Всё, что за ними стоит, существовало и раньше — но командами, которые
# надо помнить. Помнил их не бот, а человек, и ровно поэтому полка
# кончилась, а ссылки остались непроставленными: работа была возможна,
# но каждый раз начиналась с вопроса «как это называлось».
#
# Кнопки ничего нового не умеют. Они делают возможное очевидным — и
# проверять тут надо именно связность: что кнопка есть, что она ведёт к
# обработчику и что обработчик один, а не скопирован.
import re

import admin
import art_channel
import books_seed


def _menu_data():
    kb = admin._admin_menu()
    return [b.callback_data for row in kb.inline_keyboard for b in row]


def test_books_and_art_are_in_the_service_menu():
    data = _menu_data()
    assert "admin_books" in data
    assert "admin_art" in data


def test_every_menu_button_has_a_handler():
    """Кнопка без обработчика молчит, и это неотличимо от поломки."""
    sources = "".join(open(f, encoding="utf-8").read() for f in
                      ("admin.py", "books_seed.py", "art_channel.py",
                       "digest.py", "urgent.py", "content_plan.py",
                       "lang_review.py"))
    for data in _menu_data():
        if data in ("go_home",):
            continue
        assert f'"{data}"' in sources, f"кнопка {data} никуда не ведёт"


def test_the_books_screen_offers_the_three_jobs():
    """Добавить книгу, проставить ссылки, загрузить обложки — всё, ради
    чего в этот экран заходят."""
    source = open("books_seed.py", encoding="utf-8").read()
    body = source[source.index("async def _books_screen"):]
    body = body[:body.index("async def books_screen")]
    for data in ("bk_new", "bk_links", "bookcovers"):
        assert data in body, data


def test_the_books_screen_says_how_many_links_are_missing():
    """Число без действия — просто цифра. Видно должно быть, велика ли
    работа."""
    source = open("books_seed.py", encoding="utf-8").read()
    body = source[source.index("async def _books_screen"):]
    body = body[:body.index("async def books_screen")]
    assert "Без ссылки" in body


def test_the_button_calls_the_same_code_as_the_command():
    """Два пути к одному и тому же расходятся на первой же правке: один
    чинят, про второй забывают."""
    source = open("art_channel.py", encoding="utf-8").read()
    body = source[source.index("async def prices_button"):]
    assert "price_command(" in body[:400]
    assert "_as_command" in body[:400]


def test_adding_a_book_asks_for_the_shelf_first():
    """Полка — выбор из трёх, и спрашивать её текстом значит ждать
    опечатки."""
    source = open("books_seed.py", encoding="utf-8").read()
    body = source[source.index("async def new_book("):]
    body = body[:body.index("async def new_book_shelf")]
    assert "bk_s_" in body
    assert "NewBook.shelf" in body


def test_a_new_book_needs_author_and_title_on_the_first_line():
    """По первой строке ищется дубль — без неё повторная загрузка
    задвоит книгу."""
    source = open("books_seed.py", encoding="utf-8").read()
    body = source[source.index("async def new_book_text"):]
    assert "add_book_unique" in body
    assert "автор и название" in body


def test_the_art_screen_shows_what_was_realised():
    source = open("art_channel.py", encoding="utf-8").read()
    body = source[source.index("async def art_screen"):]
    body = body[:body.index("def _as_command")]
    assert "Реализовано" in body
    assert "art_waiting" in body


def test_the_books_screen_shows_which_ones_lack_links():
    """Карусель ведёт по одной книге и не показывает, сколько их
    впереди и где лежит ссылка без партнёрского хвоста."""
    source = open("books_seed.py", encoding="utf-8").read()
    body = source[source.index("async def _books_screen"):]
    body = body[:body.index("async def books_screen")]
    assert "bk_show" in body


def test_the_list_button_calls_the_same_command():
    source = open("books_seed.py", encoding="utf-8").read()
    body = source[source.index("async def show_button"):]
    assert "links_show(" in body[:700]


def test_links_can_be_entered_before_the_shop_templates_exist():
    """Иначе работа упирается в настройку, которой может не быть
    сегодня: ссылка сохранится как есть, а завернуть её можно потом
    одной командой."""
    source = open("books_seed.py", encoding="utf-8").read()
    body = source[source.index("async def _ready_link"):]
    body = body[:body.index("@router.message", body.index("async def _ready_link"))]
    assert "return raw" in body, "без шаблона ссылка теряется"


def test_the_rewrap_report_mentions_books_it_did_not_touch():
    """Команда перезаворачивает только существующие ссылки. Книги без
    ссылки в отчёт не попадают — и числа перестают сходиться с
    размером полки: выходит, будто часть книг потерялась."""
    source = open("books_seed.py", encoding="utf-8").read()
    body = source[source.index("🔗 <b>Перезавернула ссылки</b>"):]
    body = body[:body.index("@router.message", body.index("await message.answer"))]
    assert "Книг без ссылки" in body
    assert "books_link_stats" in body


# --- «Моя галерея» ведёт в канал ---------------------------------------
#
# Канал — полка: там все работы, по одной на пост, с метками и поиском.
# Экран бота показывает тридцать штук списком и упирается в длину
# сообщения, а канал не упирается ни во что.

def test_the_gallery_offers_the_channel():
    source = open("art_shop.py", encoding="utf-8").read()
    assert "async def _channel_row" in source
    body = source[source.index("async def show_gallery"):]
    body = body[:body.index("@router.callback_query")]
    assert "_channel_row" in body


def test_the_empty_gallery_offers_it_too():
    """Пустой экран без выхода — тупик, а в канале работы уже есть."""
    source = open("art_shop.py", encoding="utf-8").read()
    body = source[source.index("async def show_gallery"):]
    body = body[:body.index("rows = []")]
    assert "channel" in body.split("Галерея пока пуста")[1][:300]


def test_the_gallery_and_the_import_share_one_channel_setting():
    """Иначе кнопка поведёт в один канал, а работы придут из другого."""
    import art_shop
    import art_channel
    assert art_shop.CHANNEL_KEY == art_channel.CHANNEL_KEY


def test_changing_the_channel_forgets_the_cached_name():
    """Кэш иначе врёт, и кнопка ведёт в прежний канал — туда, где новых
    работ уже не появится."""
    source = open("art_channel.py", encoding="utf-8").read()
    body = source[source.index("async def set_channel"):]
    assert 'set_setting("art_channel_username", "")' in body
