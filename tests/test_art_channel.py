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


# --- цена живёт отдельно от канала ------------------------------------
#
# Цена, напечатанная в канале, живёт там вечно и для каждого одна: её
# видит и тот, кому сделали бы скидку, и тот, кто пришёл через год,
# когда цена выросла. Разговор о цене — это разговор про раму и
# доставку, и начинается он с человека, а не с числа.

def test_the_markup_does_not_ask_for_a_price():
    assert "₽" not in ac.MARKUP.split("Цену в пост")[0]
    assert "Цену в пост не ставим" in ac.MARKUP


def test_the_post_carries_a_request_button_not_a_number():
    rows = ac.try_row(7, "mybot")
    labels = [b.text for row in rows for b in row]
    assert any("Запросить цену" in t for t in labels)
    assert all("₽" not in t for t in labels)


def test_both_buttons_lead_into_the_bot():
    rows = ac.try_row(7, "@mybot")
    links = [b.url for row in rows for b in row]
    assert any("start=try-7" in u for u in links)
    assert any("start=ask-7" in u for u in links)


def test_without_a_bot_name_there_are_no_buttons():
    """Кнопка в никуда под постом хуже отсутствия кнопки."""
    assert ac.try_row(7, "") is None


def test_a_price_in_the_post_is_still_noticed():
    """Прайс отдельный — но если цена всё же напечатана, молчать
    нельзя: число уже видят подписчики."""
    assert ac.parse("Работа\n60 × 80\n45 000 ₽")["price"] == 45000


def test_the_bot_does_not_name_the_price_itself():
    """Решает, кому и какую цену назвать, автор. Бот доносит вопрос."""
    source = open("art_channel.py", encoding="utf-8").read()
    ask = source[source.index("async def start_ask"):]
    ask = ask[:ask.index("@router", 10)]
    assert "config.ADMIN_ID" in ask, "вопрос не уходит автору"
    assert "Передала вопрос" in ask


# --- метки -------------------------------------------------------------

def test_the_tag_list_is_closed():
    """«#пейзаж» и «#пейзажи» — две разные полки, на каждой по
    половине работ, и обе бесполезны."""
    assert ac.TAGS and all(ac.TAGS.values())


def test_every_tag_is_a_single_word():
    """Пробел внутри метки её обрывает: «#холст масло» — это метка
    «#холст» и слово «масло»."""
    for tags in ac.TAGS.values():
        for tag in tags:
            assert tag.startswith("#") and " " not in tag, tag


def test_no_tag_is_repeated_across_axes():
    """Метка на двух осях ломает правило «по одной с оси»."""
    seen = [t for tags in ac.TAGS.values() for t in tags]
    assert len(seen) == len(set(seen))


def test_the_size_tags_say_what_they_mean():
    """«Среднее» у каждого своё, пока не написано, сколько это в
    сантиметрах."""
    named = {tag for tag, _ in ac.TAG_SIZES}
    assert named <= set(ac.TAGS["какого размера"])
    assert all(any(ch.isdigit() for ch in what) for _, what in ac.TAG_SIZES)


def test_the_help_shows_an_example_line():
    assert "#пейзаж #холст_масло" in ac.TAG_HELP


# --- то, что уже опубликовано ------------------------------------------
#
# Новые посты приходят боту сами, а старые не придут никогда: Telegram
# историю канала не пересказывает. Значит, у висящего поста должен быть
# способ попасть в карточки — иначе первая же работа, выложенная до
# подключения бота, останется за бортом навсегда.

def test_an_edit_picks_up_a_post_published_earlier():
    source = open("art_channel.py", encoding="utf-8").read()
    body = source[source.index("async def fix_post"):]
    body = body[:body.index("# ---", 10)]
    assert "await take_post(message, bot)" in body, \
        "правка не заводит карточку для уже висящего поста"


# --- первая настоящая работа -------------------------------------------

REAL = ("Герб рода Струковых\n"
        "2026 · картон, масло · 50 × 40 см\n"
        "Геральдическая композиция.\n"
        "#герб #картон_масло #среднее #яркое")


def test_the_first_real_post_is_read_whole():
    d = ac.parse(REAL)
    assert d["title"] == "Герб рода Струковых"
    assert d["year"] == 2026
    assert d["technique"] == "картон, масло"
    assert (d["width"], d["height"]) == (50.0, 40.0)
    assert d["status"] == "available"


def test_a_story_without_a_blank_line_is_still_a_story():
    """Пустую строку перед рассказом ставят не всегда — с телефона
    особенно."""
    assert "Геральдическая" in ac.parse(REAL)["story"]


def test_the_tags_of_the_first_work_exist_in_the_list():
    """Список закрытый, и закрывали его до того, как появилась первая
    настоящая работа. Расходится список с работами — расходятся и
    полки."""
    used = {w for w in REAL.split() if w.startswith("#")}
    known = {t for tags in ac.TAGS.values() for t in tags}
    assert used <= known, f"нет в списке: {sorted(used - known)}"


def test_the_backing_is_part_of_the_technique_axis():
    """По картону и холсту вещь висит по-разному и стоит по-разному."""
    axis = ac.TAGS["чем и на чём"]
    assert "#картон_масло" in axis and "#холст_масло" in axis


# --- продано за и прошу за --------------------------------------------
#
# Это разные числа, и смешивать их нельзя. «Прошу» — намерение: оно
# меняется и бывает неверным. «Продано за» — факт: он не меняется
# никогда, и в нём весь смысл. По реализованным ценам считается, сколько
# стоит следующая работа. Одно поле на оба превращает будущую
# статистику в список догадок.

def test_the_sold_price_has_its_own_field():
    source = open("database.py", encoding="utf-8").read()
    assert "sold_price" in source and "sold_at" in source
    allowed = source[source.index('allowed = {"title"'):]
    assert "sold_price" in allowed[:300], \
        "цену продажи нельзя записать — поле не разрешено к правке"


def test_money_is_written_the_russian_way():
    assert ac._money(1500000) == "1 500 000 ₽"
    assert ac._money(45000) == "45 000 ₽"


def test_no_price_is_a_dash_not_a_zero():
    """«0 ₽» читается как «отдам даром»."""
    assert ac._money(None) == "—"
    assert ac._money(0) == "—"


def test_selling_marks_the_work_and_keeps_it():
    """Проданное из канала не исчезает: это лучший довод для
    следующего покупателя."""
    source = open("art_channel.py", encoding="utf-8").read()
    body = source[source.index("async def sold_command"):]
    body = body[:body.index("@router", 10)]
    assert 'status="sold"' in body
    assert "sold_price=value" in body
    assert "sold_at" in body, "дата продажи не записывается"


def test_a_sale_can_be_undone():
    """Отметили не ту работу — это случается, и чинить руками в базе
    владелице нечем."""
    source = open("art_channel.py", encoding="utf-8").read()
    body = source[source.index("async def sold_command"):]
    assert 'status="available"' in body[:body.index("@router", 10)]


def test_the_list_tells_asked_from_realised():
    source = open("art_channel.py", encoding="utf-8").read()
    body = source[source.index("async def price_command"):]
    assert "продана за" in body
    assert "Реализовано" in body


# --- кнопки под чужим постом -------------------------------------------
#
# Пост пишет владелица, а кнопки нужны боту: он дописывает их к чужому
# сообщению. В канале это разрешено администратору с правом править
# чужие посты, и есть ли оно у бота — заранее не известно.

def test_the_buttons_are_attached_to_the_post():
    source = open("art_channel.py", encoding="utf-8").read()
    assert "edit_message_reply_markup" in source


def test_a_refusal_is_not_silent():
    """Кнопки — единственный путь из канала в бота. Без них пост
    остаётся картинкой: примерить нельзя, цену спросить не у кого, и
    понять это по тишине невозможно."""
    assert "Редактировать сообщения других" in ac.NO_RIGHTS
    source = open("art_channel.py", encoding="utf-8").read()
    body = source[source.index("async def attach_buttons"):]
    body = body[:body.index("@router", 10)]
    assert "config.ADMIN_ID" in body, "об отказе не сообщают владелице"


def test_an_edit_is_a_second_chance_for_the_buttons():
    """Право выдали и поправили пост именно затем."""
    source = open("art_channel.py", encoding="utf-8").read()
    body = source[source.index("async def fix_post"):]
    body = body[:body.index("# ---", 10)]
    assert "attach_buttons" in body


def test_buttons_are_not_redrawn_when_already_there():
    """Иначе каждая правка текста дёргала бы Telegram впустую."""
    source = open("art_channel.py", encoding="utf-8").read()
    body = source[source.index("async def fix_post"):]
    assert "not message.reply_markup" in body[:body.index("# ---", 10)]


# --- из витрины в журнал -----------------------------------------------
#
# Канал картин — полка: там лежат все работы и там их ищут. «Акцент» —
# журнал, и у него свой голос. Слать туда каждую работу значит
# превратить журнал в ленту товаров, а читают его не за этим.

def test_the_journal_post_is_a_separate_decision():
    """Команда, а не автоматическая пересылка: решает, какая работа
    достойна журнала, человек."""
    source = open("art_channel.py", encoding="utf-8").read()
    assert "async def publish_to_journal" in source
    assert "art_post" in source


def test_a_sold_work_is_announced_differently():
    """«Новая работа» под проданной — приглашение к разговору, который
    закончится «извините, её уже нет»."""
    source = open("art_channel.py", encoding="utf-8").read()
    body = source[source.index("async def publish_to_journal"):]
    body = body[:body.index("@router", 10)]
    assert "нашла дом" in body
    assert "if username and not sold" in body, \
        "под проданной работой осталась кнопка примерки"


def test_paintings_have_their_own_section():
    """Картина в теме про генетику выглядит ошибкой, а не публикацией."""
    import digest
    assert digest.SECTION_ALIASES.get("картины") == "art"
    assert digest.SECTION_ALIASES.get("живопись") == "art"
    assert digest.CLUB_LABELS.get("art")


def test_the_club_label_asks_about_the_work():
    """У картины вопрос к людям другой, чем к новости: не «что
    думаете», а «куда бы повесили»."""
    import digest
    assert "работе" in digest.CLUB_LABELS["art"]


def test_the_buttons_reach_the_discussion_group():
    """В группе человек уже разговаривает, и «примерить» оттуда ближе,
    чем из канала, где он молча листает."""
    source = open("art_channel.py", encoding="utf-8").read()
    body = source[source.index("async def publish_to_journal"):]
    body = body[:body.index("@router", 10)]
    mirror = body[body.index("_mirror("):]
    assert "InlineKeyboardMarkup" in mirror[:200]
