# Чужая работа на своей полке.
#
# Площадка не продаёт чужое. Художник размещается сам, платит один раз
# за размещение и договаривается с покупателем напрямую.
#
# Проверяется здесь то, что отличает эту конструкцию от продажи чужого:
# контакт продавца в объявлении, записанные согласия, маркировка
# рекламы. Ошибка в любом из трёх возвращает площадку в середину
# сделки — что бы ни было написано в правилах.
import art_market as am


# --- площадка не в сделке ----------------------------------------------

def test_the_listing_names_the_author_not_the_channel():
    """Площадка, названная продавцом, оказывается в середине сделки,
    что бы ни было написано ниже."""
    text = am.render({"title": "Работа", "price": 45000,
                      "author": "Анна Петрова"})
    assert "Анна Петрова" in text
    assert "обращаться к автору" in text


def test_the_listing_says_who_is_not_responsible():
    text = am.render({"title": "Работа", "author": "Анна"})
    assert "ответственности не несёт" in text


# --- согласия -----------------------------------------------------------

def test_every_consent_is_required():
    """Отмеченные не все — это согласие с тем, что человек не дочитал."""
    assert len(am.CONSENTS) >= 4
    keys = {k for k, _, _ in am.CONSENTS}
    assert am._consent_kb(list(keys)).inline_keyboard[-1][0].callback_data \
        == "mkt_send"


def test_a_partial_tick_offers_no_send_button():
    keys = [k for k, _, _ in am.CONSENTS][:-1]
    data = [b.callback_data for row in am._consent_kb(keys).inline_keyboard
            for b in row]
    assert "mkt_send" not in data


def test_the_consents_cover_what_can_go_wrong():
    """Каждое закрывает свой спор: за что платят, чья работа, чья
    сделка, что публикуется."""
    bodies = " ".join(b for _, _, b in am.CONSENTS).lower()
    assert "не возвращается" in bodies      # за размещение, не за продажу
    assert "автор этой работы" in bodies    # права на вещь и фотографию
    assert "не участвует" in bodies         # сделка не её
    assert "опубликован" in bodies          # персональные данные


def test_the_consent_text_is_versioned():
    """Доказывать придётся не «он согласился», а «он согласился вот с
    этим»: текст правок не переживает, версия переживает."""
    assert am.CONSENT_VERSION
    source = open("art_market.py", encoding="utf-8").read()
    assert "consent_version" in source and "consent_at" in source


# --- маркировка рекламы -------------------------------------------------

def test_a_paid_listing_is_marked_as_advertising():
    """Платное размещение чужого товара — реклама. Штраф придёт
    площадке, а не художнику."""
    text = am.render({"title": "Работа", "author": "Анна",
                      "erid": "2Vfnxw123"})
    assert "Реклама" in text
    assert "2Vfnxw123" in text


def test_publishing_without_erid_is_refused():
    source = open("art_market.py", encoding="utf-8").read()
    body = source[source.index("async def post("):]
    body = body[:body.index("@router", 10)]
    assert "len(parts) < 3" in body, "можно опубликовать без erid"


def test_publishing_before_payment_is_refused():
    source = open("art_market.py", encoding="utf-8").read()
    body = source[source.index("async def post("):]
    body = body[:body.index("@router", 10)]
    assert "paid_at" in body


# --- цена ---------------------------------------------------------------

def test_money_is_written_the_russian_way():
    assert am._money(45000) == "45 000 ₽"
    assert am._money(0) == "—"


def test_the_price_hint_comes_before_the_artist_names_his_own():
    """Названную цену человек уже защищает, и расчёт после неё
    читается как спор."""
    source = open("art_market.py", encoding="utf-8").read()
    body = source[source.index("async def got_size"):]
    body = body[:body.index("async def got_price")]
    assert "art_value" in body and "Ваша цена" in body


# --- контакт за кнопкой -------------------------------------------------
#
# Написанный в канале контакт достаётся и тем, кто пришёл не покупать:
# спам собирается по открытым каналам в первую очередь. И главное —
# нажатие видно, а переписанный глазами телеграм нет, и художник не
# узнает, сколько человек им заинтересовалось.

def test_the_contact_is_not_printed_in_the_post():
    text = am.render({"title": "Работа", "author": "Анна",
                      "contact": "@anna_art"})
    assert "@anna_art" not in text


def test_the_post_says_where_to_ask():
    text = am.render({"title": "Работа", "author": "Анна"})
    assert "обращаться к автору работы" in text
    assert "ответственности не несёт" in text


def test_the_post_carries_a_button_to_the_author():
    row = am.contact_row(3, "mybot")
    assert row and "start=lead-3" in row[0].url


def test_without_a_bot_name_there_is_no_button():
    assert am.contact_row(3, "") is None


def test_asking_for_the_contact_is_counted():
    """Считаем нажатия, а не продажи: о продаже площадка не узнаёт —
    она в сделке не участвует."""
    source = open("art_market.py", encoding="utf-8").read()
    body = source[source.index("async def give_contact"):]
    assert "listing_lead" in body[:1200]


def test_one_person_counts_once():
    """Иначе число растёт от того, что кто-то потерял переписку, и
    перестаёт что-либо значить."""
    source = open("database.py", encoding="utf-8").read()
    body = source[source.index("async def listing_lead"):]
    body = body[:body.index("async def listing_leads")]
    assert "PRIMARY KEY (listing_id, user_id)" in body
    assert "ON CONFLICT DO NOTHING" in body


def test_the_artist_learns_about_interest():
    """Это и есть то, за что он платил: не публикация сама по себе, а
    люди, которые дошли."""
    source = open("art_market.py", encoding="utf-8").read()
    body = source[source.index("async def give_contact"):]
    assert "listing[\"user_id\"]" in body[:2200]


def test_a_dead_listing_gives_no_contact():
    source = open("art_market.py", encoding="utf-8").read()
    body = source[source.index("async def give_contact"):]
    assert 'status") != "live"' in body[:1000]


# --- ИНН и правила ------------------------------------------------------
#
# Опечатка в ИНН всплывёт не в боте, а в ОРД — через несколько дней,
# когда деньги за размещение уже взяты, а объявление опубликовать
# нельзя.

def test_a_real_inn_passes():
    assert am.inn_valid("500100732259")      # физлицо, 12 цифр
    assert am.inn_valid("7707083893")        # организация, 10 цифр


def test_a_typo_in_the_inn_is_caught_here():
    """Контрольная сумма ловит почти все описки на месте."""
    assert not am.inn_valid("123456789012")
    assert not am.inn_valid("500100732258")  # последняя цифра не та
    assert not am.inn_valid("50010073225")   # потеряна цифра


def test_nonsense_is_not_an_inn():
    for raw in ("", "abc", "0", None):
        assert not am.inn_valid(raw)


def test_the_rules_say_what_the_platform_requires():
    """Условие площадки названо условием площадки, а не законом:
    написать «этого требует закон» там, где требует хозяин канала,
    значит соврать человеку в его же интересах."""
    assert "самозанятость или ИП" in am.RULES.lower() or \
           "Нужна самозанятость" in am.RULES
    assert "условие площадки, а не требование закона" in am.RULES


def test_the_rules_explain_why_the_inn_is_needed():
    assert "ИНН" in am.RULES
    assert "реклам" in am.RULES.lower()


def test_the_rules_are_a_screen_of_their_own():
    """Условия вперемешку с вопросами формы не читает никто, а потом
    выясняется, что человек не знал ни про чек, ни про ИНН."""
    source = open("art_market.py", encoding="utf-8").read()
    assert "mkt_go" in source
    body = source[source.index("async def begin("):]
    assert "Listing.photo" in body[:400]


def test_the_data_consent_mentions_the_ord():
    bodies = " ".join(b for _, _, b in am.CONSENTS)
    assert "оператору рекламных данных" in bodies
    assert "не публикуется" in bodies


def test_the_inn_never_reaches_the_post():
    text = am.render({"title": "Работа", "author": "Анна",
                      "inn": "500100732259", "erid": "2Vfn"})
    assert "500100732259" not in text


def test_the_artist_form_does_not_swallow_admin_commands():
    """«/listing» без границы слова ловил и «/listings», и
    «/listing_paid»: служебные команды открывали художнику форму
    вместо доски — и выглядело это как молчащий бот."""
    import re
    source = open("art_market.py", encoding="utf-8").read()
    start = source.index('@router.message(F.text.regexp(r"^/(разместить')
    pattern = re.compile(source[start:].split('r"')[1].split('"')[0])
    assert pattern.match("/listing")
    for other in ("/listings", "/listing_paid 3", "/listing_post 3 x",
                  "/listing_price 500"):
        assert not pattern.match(other), other
