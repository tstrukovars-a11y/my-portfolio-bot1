# Сборка поста и расписание дня.
#
# Две вещи, за которые отвечает этот файл, стоят дорого: маркировка
# рекламы, которая обязана остаться в самом объявлении, и порядок
# выпусков, который на выходных сдвигается.
from datetime import datetime

from conftest import run

import digest

ПОМЕТКИ = ("\n\nРеклама. ООО «ЛитРес», ИНН 7719571260, erid: 2Vfn1AbC\n"
           "Реклама. АО «Читай-город», ИНН 7710000000, erid: 2Vfn9XyZ")


# --- маркировка не должна уезжать из поста ----------------------------

def test_short_post_keeps_everything():
    text = "Заголовок\n\nКороткое описание."
    assert digest._fit(text, ПОМЕТКИ, True) == text + ПОМЕТКИ


def test_long_post_loses_description_not_the_marking():
    text = "Заголовок\n\n" + "Очень длинное описание книги. " * 80
    out = digest._fit(text, ПОМЕТКИ, True)
    assert len(out) <= digest.MAX_CAPTION
    assert out.endswith(ПОМЕТКИ)
    assert "erid: 2Vfn9XyZ" in out


def test_message_without_media_has_a_bigger_limit():
    text = "Заголовок\n\n" + "Длинное описание. " * 200
    out = digest._fit(text, ПОМЕТКИ, False)
    assert len(out) <= digest.MAX_MESSAGE
    assert out.endswith(ПОМЕТКИ)


def test_cut_does_not_break_a_word():
    text = "Заголовок\n\n" + "слово " * 400
    out = digest._fit(text, ПОМЕТКИ, True)
    assert "слов…" not in out


# --- рекламный токен --------------------------------------------------

def test_erid_is_taken_from_the_link():
    assert digest._erid("https://ad.ru/?erid=2Vfn1AbC&x=1") == "2Vfn1AbC"


def test_no_erid_no_invention():
    assert digest._erid("https://www.litres.ru/book/a/") == ""
    assert digest._erid("") == ""


# --- расписание -------------------------------------------------------

def test_weekday_schedule_is_untouched():
    friday = datetime(2026, 9, 4)
    assert digest._slot_at("08:00", "morning", friday) == (8, 0)
    assert digest._slot_at("08:40", "results", friday) == (8, 40)


def test_weekend_morning_block_moves_an_hour_later():
    saturday = datetime(2026, 9, 5)
    assert digest._slot_at("08:00", "morning", saturday) == (9, 0)
    assert digest._slot_at("08:40", "results", saturday) == (9, 40)
    assert digest._slot_at("09:30", "tennis", saturday) == (10, 30)


def test_weekend_keeps_the_order_of_the_day():
    """Сдвиг одного утра пустил бы итоги матчей раньше него."""
    sunday = datetime(2026, 9, 6)
    times = [digest._slot_at(at, slot, sunday) for at, slot, _ in digest.SCHEDULE]
    assert times == sorted(times)


def test_afternoon_stays_where_it_was():
    saturday = datetime(2026, 9, 5)
    assert digest._slot_at("13:00", "genetics", saturday) == (13, 0)


# --- фраза дня --------------------------------------------------------

def test_motto_is_the_same_all_day_and_changes_tomorrow():
    day = datetime(2026, 9, 7)
    assert digest._motto(day) == digest._motto(datetime(2026, 9, 7, 23, 59))
    assert digest._motto(day) != digest._motto(datetime(2026, 9, 8))


def test_weekend_motto_comes_from_the_gentler_list():
    assert digest._motto(datetime(2026, 9, 5)) in digest.MOTTOS_WEEKEND
    assert digest._motto(datetime(2026, 9, 7)) in digest.MOTTOS


def test_mottos_do_not_break_markdown():
    """Выпуск разбирается как Markdown: звёздочка уронит всё сообщение."""
    for phrase in digest.MOTTOS + digest.MOTTOS_WEEKEND:
        assert not set(phrase) & set("_*`[")


# --- магазины раздела -------------------------------------------------

def test_several_shops_one_per_line(settings):
    settings["shop_url_books"] = ("📱 Литрес | https://a.ru/?q={q}\n"
                                 "📗 Читай-город | https://b.ru/?q={q}")
    found = run(digest._shop_templates("books"))
    assert [label for label, _ in found] == ["📱 Литрес", "📗 Читай-город"]


def test_single_line_behaves_as_before(settings):
    settings["shop_url_books"] = "https://a.ru/?q={q}"
    label, template = run(digest._shop_template("books"))
    assert label is None and template == "https://a.ru/?q={q}"


def test_query_is_substituted_and_encoded():
    url = digest._shop_url("https://a.ru/?q={q}&s={sub}",
                           "Бен Хоровиц — Легко не будет", "books")
    assert "%D0%91%D0%B5%D0%BD" in url      # «Бен» в процентной кодировке
    assert url.endswith("s=books")
    assert "—" not in url


def test_shop_label_by_host():
    assert digest._shop_label("https://www.litres.ru/x") == "📱 Литрес"
    assert digest._shop_label("https://unknown.example/x") == "🛒 Купить"


def test_buttons_are_laid_out_two_per_row():
    row = ["a", "b", "c", "d"]
    assert digest._pairs(row) == [["a", "b"], ["c", "d"]]
    assert digest._pairs(["a"]) == [["a"]]
    assert digest._pairs([]) == []


# --- пометка о рекламе ------------------------------------------------
#
# Вид пометки задан не нами: так её оформляют рекламодатели, и по ней
# проверяющий узнаёт рекламу с первого взгляда.

def test_mark_looks_like_the_advertisers_write_it(settings):
    settings["shop_note_litres"] = "РЕКЛАМА. ООО «ЛитРес». ИНН 7719571260"
    mark = run(digest._ad_mark("https://www.litres.ru/book/a?erid=2Vtzqvwp4GN"))
    assert mark == "РЕКЛАМА. ООО «ЛитРес». ИНН 7719571260. ERID: 2Vtzqvwp4GN"


def test_trailing_period_is_not_doubled(settings):
    settings["shop_note_litres"] = "РЕКЛАМА. ООО «ЛитРес». ИНН 7719571260."
    mark = run(digest._ad_mark("https://www.litres.ru/a?erid=2Vabc"))
    assert ".. ERID" not in mark
    assert mark.endswith(". ERID: 2Vabc")


def test_advertiser_is_found_behind_the_network(settings):
    """У ссылки через сеть в адресе стоит сеть, а магазин внутри параметра.

    По одному хосту рекламодатель не находился, и в пост уходил голый
    токен — без ООО и ИНН, то есть неполная маркировка.
    """
    settings["shop_note_litres"] = "РЕКЛАМА. ООО «ЛитРес». ИНН 7719571260"
    url = ("https://ad.advcake.ru/click?erid=2Vtzqvwp4GN"
           "&ulp=https%3A%2F%2Fwww.litres.ru%2Fbook%2Fa")
    assert "ООО «ЛитРес»" in run(digest._ad_mark(url))


def test_token_alone_when_advertiser_is_unknown(settings):
    assert run(digest._ad_mark("https://unknown.example/x?erid=2Vabc")) == "ERID: 2Vabc"


def test_no_link_no_mark(settings):
    assert run(digest._ad_mark("https://www.litres.ru/book/a/")) == ""
