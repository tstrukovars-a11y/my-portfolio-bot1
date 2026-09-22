# Доступ к навыкам и ворота перед оплатой.
#
# Две ошибки здесь стоят денег в разные стороны. Пустить незаплатившего —
# потерять выручку; не пустить заплатившего — потерять человека, и он не
# вернётся. Поэтому проверяем обе границы, а не одну.
import pytest

from conftest import run

import access
import config
import lang


@pytest.fixture
def paid(monkeypatch):
    """Кто что купил — словарём вместо базы"""
    import database

    bought = {}

    async def skill_until(user_id, skill):
        return bought.get((user_id, skill))

    async def grant_skill(user_id, skill, days, source=""):
        bought[(user_id, skill)] = days
        return True

    monkeypatch.setattr(database, "skill_until", skill_until)
    monkeypatch.setattr(database, "grant_skill", grant_skill)
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    return bought


# --- кто внутри -------------------------------------------------------

def test_stranger_has_nothing(paid):
    assert not run(access.has(42, "lang_he"))


def test_buyer_gets_in(paid):
    run(access.database.grant_skill(42, "lang_he", 30))
    assert run(access.has(42, "lang_he"))


def test_one_skill_does_not_open_another(paid):
    """За иврит заплатили — французский остаётся закрытым."""
    run(access.database.grant_skill(42, "lang_he", 30))
    assert not run(access.has(42, "lang_fr"))


def test_owner_walks_everywhere(paid):
    assert run(access.has(1, "lang_fr"))


# --- пробное ----------------------------------------------------------

@pytest.mark.parametrize("code", ["he", "fr", "en"])
def test_every_language_has_something_free(code):
    """Язык без пробного урока не продаст себя ничем."""
    free = lang.free_topics(code)
    assert free
    assert lang.cards_of(code, free[0])


@pytest.mark.parametrize("code", ["he", "fr", "en"])
def test_not_everything_is_free(code):
    topics = list(lang.content()[code]["topics"])
    assert len(topics) > len(lang.free_topics(code)), "продавать нечего"


def test_free_lesson_is_a_whole_lesson():
    """Огрызок вместо урока показал бы, что продукт плохой."""
    code = "he"
    tasks = lang.build(code, lang.free_topics(code)[0], set(), level=2)
    assert len(tasks) >= 4


# --- деньги -----------------------------------------------------------

def test_prices_are_whole_stars():
    for days, stars in access.TARIFFS.values():
        assert isinstance(stars, int) and stars > 0
        assert isinstance(days, int) and days > 0


def test_longer_access_costs_less_per_day():
    """Иначе годовой тариф бессмысленен и выглядит обманом."""
    per_day = [stars / days for days, stars in access.TARIFFS.values()]
    assert per_day == sorted(per_day, reverse=True)


def test_every_language_can_be_bought():
    for code in lang.content():
        assert lang.skill_of(code) in access.SKILLS


def test_buy_buttons_cover_all_tariffs(paid, monkeypatch):
    import database

    async def get_setting(key, default=None):
        return ""

    monkeypatch.setattr(database, "get_setting", get_setting)
    rows = run(access.buy_kb("lang_he")).inline_keyboard
    data = [b.callback_data for row in rows for b in row if b.callback_data]
    for code in access.TARIFFS:
        assert f"buy_skill_lang_he_{code}" in data


def test_card_button_appears_only_with_a_till(paid, monkeypatch):
    """Кнопка «оплатить картой» без кассы вела бы в никуда."""
    import database

    store = {}

    async def get_setting(key, default=None):
        return store.get(key, "")

    monkeypatch.setattr(database, "get_setting", get_setting)
    assert not any(b.url for row in run(access.buy_kb("lang_he")).inline_keyboard
                   for b in row)

    store["pay_url_lang_he"] = "https://example.com/pay"
    assert any(b.url == "https://example.com/pay"
               for row in run(access.buy_kb("lang_he")).inline_keyboard
               for b in row)


def test_payment_payload_survives_the_underscores():
    """«skill_lang_he_30»: в имени навыка своё подчёркивание, и наивный
    split развалил бы его на куски."""
    payload = "skill_lang_he_30"
    skill, _, tail = payload[len("skill_"):].rpartition("_")
    assert skill == "lang_he" and int(tail) == 30
    assert skill in access.SKILLS


def test_wall_talks_about_what_is_next():
    text = access.wall_text("lang_he", "Это был пробный урок целиком.")
    assert "пробный" in text
    assert "Иврит" in text


# --- касса ------------------------------------------------------------

class Msg:
    def __init__(self, text, user_id=1):
        self.text = text
        self.said = []
        self.from_user = type("U", (), {"id": user_id})()

    async def answer(self, text, **kw):
        self.said.append(text)


def test_till_link_is_saved(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    run(access.till_command(Msg("/касса lang_he https://yookassa.ru/x")))
    assert settings["pay_url_lang_he"] == "https://yookassa.ru/x"


def test_till_refuses_a_broken_link(settings, monkeypatch):
    """Telegram не примет такую кнопку — человек увидит ошибку вместо кассы."""
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    message = Msg("/касса yookassa.ru/x")
    run(access.till_command(message))
    assert "https://" in message.said[0]
    assert "pay_url" not in settings


def test_till_can_be_cleared(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    settings["pay_url"] = "https://old"
    run(access.till_command(Msg("/касса -")))
    assert settings["pay_url"] == ""


def test_till_is_not_for_readers(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    message = Msg("/касса https://yookassa.ru/x", user_id=999)
    run(access.till_command(message))
    assert not message.said and not settings


# --- что за владелицей ------------------------------------------------

def test_owed_list_starts_with_what_was_promised(settings):
    import checklist

    assert any("ЮKassa" in x for x in run(checklist._owed()))
    assert any("картин" in x for x in run(checklist._owed()))


def test_crossing_off_the_last_item_leaves_it_empty(settings):
    """Иначе вычеркнутое возвращалось бы из значений по умолчанию."""
    import checklist

    run(checklist._save_owed([]))
    assert run(checklist._owed()) == []


def test_owed_survives_a_broken_record(settings):
    import checklist

    settings[checklist.OWED_KEY] = "не json"
    assert run(checklist._owed()) == []


# --- «я оплатил переводом» --------------------------------------------
#
# Перевод приходит в банк, а не в бот: узнать о нём бот не может никак.
# Значит, единственная связь между деньгами и доступом — эта кнопка, и
# сломаться она не должна ни с одной стороны.

class Call:
    """Нажатие кнопки: данные, кто нажал и куда отвечать"""

    def __init__(self, data, user_id=42):
        self.data = data
        self.message = Msg("", user_id=user_id)
        self.from_user = type("U", (), {"id": user_id, "first_name": "Пётр",
                                        "last_name": None, "username": "petr"})()
        self.answers = []

    async def answer(self, text="", **kw):
        self.answers.append(text)


class Bot_:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text, kw.get("reply_markup")))


def test_claim_reaches_the_owner(paid, settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    bot = Bot_()
    call = Call("pay_claim_lang_he_1", user_id=42)
    run(access.claim(call, bot))

    assert bot.sent and bot.sent[0][0] == 1
    card = bot.sent[0][1]
    assert "42" in card, "без номера доступ открыть нечем"
    assert "199" in card, "не видно, сколько ждать на счету"


def test_claim_tells_the_person_to_wait(paid, settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    call = Call("pay_claim_lang_he_1", user_id=42)
    run(access.claim(call, Bot_()))
    assert any("откроет доступ" in t for t in call.message.said)


def test_second_press_does_not_spam(paid, settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    bot = Bot_()
    for _ in range(3):
        run(access.claim(Call("pay_claim_lang_he_1", user_id=42), bot))
    assert len(bot.sent) == 1, "владелице придёт три одинаковых карточки"


def test_approve_opens_exactly_what_was_asked(paid, settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    import database

    opened = {}

    async def grant_skill(user_id, skill, days, source=""):
        opened.update(user_id=user_id, skill=skill, days=days, source=source)
        return True

    monkeypatch.setattr(database, "grant_skill", grant_skill)
    run(access.approve(Call("pay_ok_42_lang_he_3", user_id=1), Bot_()))
    assert opened == {"user_id": 42, "skill": "lang_he", "days": 90,
                      "source": "перевод"}


def test_approve_is_only_for_the_owner(paid, settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    import database

    touched = []

    async def grant_skill(*args, **kwargs):
        touched.append(args)
        return True

    monkeypatch.setattr(database, "grant_skill", grant_skill)
    run(access.approve(Call("pay_ok_42_lang_he_1", user_id=999), Bot_()))
    assert not touched, "чужой человек открывает себе доступ кнопкой"


def test_buyer_learns_that_access_is_open(paid, settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    bot = Bot_()
    run(access.approve(Call("pay_ok_42_lang_he_1", user_id=1), bot))
    assert any(chat == 42 for chat, _, _ in bot.sent), "человек не узнает"


def test_transfer_button_appears_only_with_a_link(paid, settings):
    """Без ссылки «я оплатил» — кнопка в пустоту: платить некуда."""
    data = [b.callback_data for row in run(access.buy_kb("lang_he")).inline_keyboard
            for b in row]
    assert not any((d or "").startswith("pay_claim_") for d in data)

    settings["pay_url_lang_he"] = "https://example.com/pay"
    data = [b.callback_data for row in run(access.buy_kb("lang_he")).inline_keyboard
            for b in row]
    assert "pay_claim_lang_he_1" in data


def test_every_tariff_has_a_ruble_price():
    assert set(access.PRICE_RUB) == set(access.TARIFFS)


# --- учёт продаж ------------------------------------------------------
#
# Половина выручки приходит переводом, и если её не записать, она живёт
# только в банковской выписке. Сверять чеки в «Моём налоге» по памяти —
# верный способ пропустить оплату.

def test_transfer_sale_lands_in_the_ledger(paid, settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    import database
    import finance

    written = {}

    async def grant_skill(*args, **kwargs):
        return True

    async def record(**kwargs):
        written.update(kwargs)
        return "ok"

    monkeypatch.setattr(database, "grant_skill", grant_skill)
    monkeypatch.setattr(finance, "record", record)
    run(access.approve(Call("pay_ok_42_lang_he_3", user_id=1), Bot_()))

    assert written["kind"] == "income"
    assert written["asset"] == "RUB", "рубли нельзя записать как звёзды"
    assert written["amount"] == access.PRICE_RUB["3"]
    assert written["category"] == "subscription"


def test_sale_is_recorded_even_if_the_buyer_is_unreachable(paid, settings, monkeypatch):
    """Деньги пришли независимо от того, дошло ли уведомление."""
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    import database
    import finance

    calls = []

    async def grant_skill(*args, **kwargs):
        return True

    async def record(**kwargs):
        calls.append(kwargs)
        return "ok"

    class Deaf(Bot_):
        async def send_message(self, *args, **kwargs):
            raise RuntimeError("бот ему не писал")

    monkeypatch.setattr(database, "grant_skill", grant_skill)
    monkeypatch.setattr(finance, "record", record)
    run(access.approve(Call("pay_ok_42_lang_he_1", user_id=1), Deaf()))
    assert calls, "продажа потерялась из-за недоставленного сообщения"


def test_months_table_covers_the_year():
    assert len(access.MONTHS) == 13 and access.MONTHS[9] == "сентябрь"


def test_transfer_comes_before_stars(paid, settings):
    """Перевод дешевле обоим — он и должен попадаться первым."""
    settings["pay_url_lang_he"] = "https://example.com/pay"
    rows = run(access.buy_kb("lang_he")).inline_keyboard
    texts = [b.text for row in rows for b in row]
    assert texts[0].startswith("💳")
    assert any(t.startswith("⭐") for t in texts)


def test_stars_say_who_they_are_for(paid, settings):
    """Звёзды без объяснения выглядят дороже и страннее перевода."""
    settings["pay_url_lang_he"] = "https://example.com/pay"
    texts = [b.text for row in run(access.buy_kb("lang_he")).inline_keyboard
             for b in row]
    assert any("из другой страны" in t for t in texts)
    assert "российская карта" in access.wall_text("lang_he", card=True)


def test_without_a_card_link_stars_stand_alone(paid, settings):
    """Пока перевода нет, объяснять нечего — и подпись только мешает."""
    texts = [b.text for row in run(access.buy_kb("lang_he")).inline_keyboard
             for b in row]
    assert not any("из другой страны" in t for t in texts)
    assert "российская карта" not in access.wall_text("lang_he")


# --- вторая касса -----------------------------------------------------
#
# У покупателя из Израиля нет российской карты, и без второй кассы ему
# остаются звёзды — а на них до владелицы доходит около половины
# заплаченного.

def test_foreign_card_button_appears_with_its_link(paid, settings):
    data = [b.url for row in run(access.buy_kb("lang_he")).inline_keyboard
            for b in row]
    assert not any(data)

    settings["pay_intl"] = "https://pay.example.com/intl"
    urls = [b.url for row in run(access.buy_kb("lang_he")).inline_keyboard
            for b in row]
    assert "https://pay.example.com/intl" in urls


def test_two_tills_do_not_overwrite_each_other(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    run(access.till_command(Msg("/касса https://ru.example.com")))
    run(access.till_command(Msg("/касса мир https://world.example.com")))
    assert settings["pay_url"] == "https://ru.example.com"
    assert settings["pay_intl"] == "https://world.example.com"


def test_foreign_till_can_be_per_skill(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    run(access.till_command(Msg("/касса мир lang_he https://x.example.com")))
    assert settings[access.INTL_URL_KEY + "lang_he"] == "https://x.example.com"


def test_stars_stop_being_the_foreign_option(settings, paid):
    """Пока второй кассы нет, звёзды подписаны «из другой страны».
    Появилась касса — подпись лишняя и только путает."""
    settings["pay_url_lang_he"] = "https://ru.example.com"
    texts = [b.text for row in run(access.buy_kb("lang_he")).inline_keyboard
             for b in row]
    assert any("из другой страны" in t for t in texts)

    settings["pay_intl_lang_he"] = "https://world.example.com"
    texts = [b.text for row in run(access.buy_kb("lang_he")).inline_keyboard
             for b in row]
    assert not any("из другой страны" in t for t in texts)


def test_every_tariff_has_a_dollar_price():
    assert set(access.PRICE_USD) == set(access.TARIFFS)
