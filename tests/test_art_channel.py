# Канал с картинами: одна работа — один пост.
#
# Все работы одним постом — это альбом, а не витрина. На отдельную
# картину нельзя дать ссылку, под ней нельзя поставить кнопку, её
# нельзя посчитать.
#
# Писать приходится в канале, одной рукой, с телефона. Поэтому разметка
# здесь прощает: пост, который бот отказался понять, хуже неполной
# карточки. Это и проверяется — что пропущенное не ломает, а лишнее не
# попадает не туда.
import pytest

import art_channel as ac


FULL = ("Тишина в полдень\n"
        "2024 · холст, масло · 60 × 80 см\n"
        "45 000 ₽\n\n"
        "Писала с балкона, когда гроза уже ушла.\n\n"
        "#живопись #пейзаж")


# --- полный пост -------------------------------------------------------

def test_everything_is_taken_apart():
    d = ac.parse(FULL)
    assert d["title"] == "Тишина в полдень"
    assert d["year"] == 2024
    assert d["technique"] == "холст, масло"
    assert d["size"] == "60 × 80 см"
    assert d["price"] == 45000
    assert d["status"] == "available"


def test_the_story_is_what_sells():
    """Размер говорит, поместится ли вещь; рассказ — зачем она нужна."""
    assert "гроза" in ac.parse(FULL)["story"]


def test_tags_stay_out_of_the_story():
    assert "#живопись" not in ac.parse(FULL)["story"]


def test_the_price_line_stays_out_of_the_story():
    assert "45" not in ac.parse(FULL)["story"]


# --- разметка прощает --------------------------------------------------

@pytest.mark.parametrize("size_text,expected", [
    ("60 × 80 см", (60, 80)),
    ("60x80", (60, 80)),
    ("60х80 см", (60, 80)),      # русская «х»
    ("60 на 80", (60, 80)),
    ("24,5 × 30", (24.5, 30)),
])
def test_the_size_is_written_however_it_comes_to_hand(size_text, expected):
    """Икс бывает латинский, русский и типографский — человек ставит
    тот, что попался под руку."""
    d = ac.parse(f"Работа\n{size_text}")
    assert (d["width"], d["height"]) == expected


def test_one_line_is_still_a_post():
    """Ничего не нашлось — останется название. Пост, который бот
    отказался понять, хуже неполной карточки."""
    d = ac.parse("Только название")
    assert d["title"] == "Только название"
    assert d["size"] == ""


def test_an_empty_post_gives_nothing():
    assert ac.parse("") == {}
    assert ac.parse("   \n\n ") == {}


def test_order_inside_the_line_does_not_matter():
    first = ac.parse("Работа\n2024 · 60 × 80 см · холст")
    second = ac.parse("Работа\nхолст · 60 × 80 см · 2024")
    assert first["technique"] == second["technique"] == "холст"
    assert first["year"] == second["year"] == 2024


def test_the_technique_survives_sharing_a_line_with_the_size():
    """«холст 40х50» — и техника, и размер в одной строке. Выброшенный
    кусок уносил бы с собой холст."""
    d = ac.parse("Без названия\nхолст 40х50, 2019")
    assert d["technique"] == "холст"
    assert d["width"] == 40


def test_a_long_title_is_cut_not_dropped():
    d = ac.parse("А" * 200 + "\n60 × 80")
    assert len(d["title"]) <= 80 and d["title"].endswith("…")


# --- проданное ---------------------------------------------------------

def test_a_sold_work_is_marked():
    assert ac.parse("Работа\n60 × 80\nпродана")["status"] == "sold"


def test_the_sold_mark_is_not_part_of_the_story():
    """В карточке она уже учтена статусом; повторять её текстом значит
    писать покупателю «продана» дважды."""
    assert ac.parse("Работа\n60 × 80\nпродана")["story"] == ""


def test_an_unsold_work_stays_available():
    assert ac.parse(FULL)["status"] == "available"


# --- примерка ----------------------------------------------------------

def test_the_size_for_the_mockup_comes_from_the_card():
    assert ac._size_of("60 × 80 см") == (60.0, 80.0)


def test_a_card_without_a_size_cannot_be_tried_on():
    """Лучше сказать, чем показать работу неизвестного размера: ради
    размера примерка и существует."""
    assert ac._size_of("") == (0.0, 0.0)
    assert ac._size_of("большая") == (0.0, 0.0)


def test_the_try_on_asks_for_one_measurement():
    """Без него масштаб можно только угадать, а угаданный выглядит как
    ответ и обманывает сильнее, чем его отсутствие."""
    assert "сантиметров стены" in ac.ASK_WIDTH
    assert ac.WIDTHS and all(w > 0 for w in ac.WIDTHS)


def test_the_result_says_the_scale_is_an_estimate():
    """Цифра пришла от человека на глаз — и пост обязан это назвать."""
    source = open("art_channel.py", encoding="utf-8").read()
    assert "по вашей оценке" in source


# --- связь с постом ----------------------------------------------------

def test_an_edit_changes_the_card_not_adds_one():
    """Альбом и так был одним постом — плодить копии значило бы
    заменить одну беду другой."""
    source = open("art_channel.py", encoding="utf-8").read()
    assert "art_by_channel_msg" in source
    assert "art_set_channel_msg" in source


def test_the_markup_help_shows_a_real_example():
    """Разметку читают один раз и по примеру, а не по описанию."""
    assert "60 × 80 см" in ac.MARKUP
    assert "/art_channel" in ac.MARKUP
