# Партнёрские ссылки на книги.
#
# Здесь ошибка стоит денег буквально: ссылка без партнёрского хвоста
# выглядит рабочей, ведёт на нужную книгу и не приносит ничего. Именно
# так и потерялись четырнадцать ссылок.
import pytest

from conftest import run

import books_seed

СЕТЬ = ("📱 Литрес | https://ad.advcake.ru/click?erid=2Vfn1&"
        "ulp=https%3A%2F%2Fwww.litres.ru%2Fsearch%2F%3Fq%3D{q}&sub1={sub}")
МЕТКА = "📱 Литрес | https://www.litres.ru/pages/biblio_search/?q={q}&lfrom=123456"
БЕЗ_МЕТКИ = "📱 Литрес | https://www.litres.ru/search/?q={q}"

КНИГА = "https://www.litres.ru/book/ben-horovic/legko-ne-budet-9128345/"


@pytest.fixture
def shop(settings):
    """Задаёт шаблон магазина для раздела книг"""
    def use(template):
        settings["shop_url_books"] = template
    return use


# --- хвост ------------------------------------------------------------

def test_tail_found_in_plain_partner_link():
    assert books_seed.tail_of(КНИГА + "?lfrom=123456") == "lfrom"


def test_no_tail_in_address_from_the_address_bar():
    assert books_seed.tail_of(КНИГА) == ""


def test_network_link_counts_as_ready():
    assert books_seed.tail_of("https://ad.advcake.ru/click?x=1")
    assert books_seed.is_affiliate("https://ad.advcake.ru/click?x=1")


def test_empty_link_has_no_tail():
    assert books_seed.tail_of("") == ""
    assert not books_seed.is_affiliate("")


# --- заворачивание ----------------------------------------------------

def test_wraps_into_network_link(shop):
    shop(СЕТЬ)
    ready, name = run(books_seed.affiliate(КНИГА))
    assert "ad.advcake.ru" in ready
    assert "legko-ne-budet" in ready
    assert name == "📱 Литрес"


def test_wrapped_link_has_no_leftover_placeholders(shop):
    shop(СЕТЬ)
    ready, _ = run(books_seed.affiliate(КНИГА))
    assert "{sub}" not in ready and "%7Bsub%7D" not in ready
    assert "{q}" not in ready


def test_carries_the_mark_onto_the_book_address(shop):
    """Второй вид ссылки: партнёра выдаёт метка, а не адрес сети."""
    shop(МЕТКА)
    ready, _ = run(books_seed.affiliate(КНИГА))
    assert ready.startswith(КНИГА)
    assert "lfrom=123456" in ready


def test_template_without_mark_wraps_nothing(shop):
    shop(БЕЗ_МЕТКИ)
    ready, _ = run(books_seed.affiliate(КНИГА))
    assert ready == ""


def test_foreign_address_is_never_wrapped(shop):
    shop(СЕТЬ)
    ready, _ = run(books_seed.affiliate("https://example.com/kniga"))
    assert ready == ""


def test_ready_link_is_left_alone(shop):
    """Ссылку из кабинета переделывать нельзя: в ней свои метки."""
    shop(МЕТКА)
    mine = КНИГА + "?lfrom=777&erid=2VfnABC"
    link, note = run(books_seed._ready_link(mine))
    assert link == mine
    assert "lfrom" in note


def test_missing_tail_is_reported_loudly(shop):
    shop(БЕЗ_МЕТКИ)
    link, note = run(books_seed._ready_link(КНИГА))
    assert link == КНИГА
    assert "нет партнёрского хвоста" in note


# --- магазины ---------------------------------------------------------

def test_shop_is_seen_through_the_network_link():
    inside = ("https://ad.advcake.ru/click?ulp="
              "https%3A%2F%2Fwww.litres.ru%2Fbook%2Fa%2F")
    assert books_seed._shop_of(inside) == "litres.ru"
    assert books_seed._mentions(inside, "litres.ru")


def test_shop_word_to_host():
    assert books_seed._shop_host("литрес") == "litres.ru"
    assert books_seed._shop_host("Читай-город") == "chitai-gorod.ru"
    assert books_seed._shop_host("амазон") == ""
