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

def test_the_listing_carries_the_seller_contact():
    """Контакт площадки в объявлении возвращает её в середину сделки,
    что бы ни было написано ниже."""
    text = am.render({"title": "Работа", "price": 45000,
                      "contact": "@artist", "author": "Анна Петрова"})
    assert "@artist" in text
    assert "Продаёт автор" in text


def test_the_listing_says_who_is_not_responsible():
    text = am.render({"title": "Работа", "author": "Анна"})
    assert "в сделке не участвует" in text


# --- согласия -----------------------------------------------------------

def test_all_four_consents_are_required():
    """Три из четырёх — это согласие с тем, что человек не дочитал."""
    assert len(am.CONSENTS) == 4
    keys = {k for k, _, _ in am.CONSENTS}
    assert am._consent_kb(list(keys)).inline_keyboard[-1][0].callback_data \
        == "mkt_send"


def test_a_partial_tick_offers_no_send_button():
    keys = [k for k, _, _ in am.CONSENTS][:3]
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
