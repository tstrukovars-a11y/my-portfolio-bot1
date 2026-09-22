# Свежесть справочников и два новых раздела путешествий.
#
# Справочник цен устаревает молча: сервис меняет тариф, а на экране
# остаётся старое число. Ошибается по нему читатель, а отвечает тот, кто
# показал. Поэтому дата проверки — не украшение, и её отсутствие должно
# ломать тесты, а не тишину.
from datetime import date, timedelta

import pytest

from conftest import run

import config
import esim
import freshness
import hotels


def aged(days):
    return {"name": "Тариф",
            "checked": (date.today() - timedelta(days=days)).isoformat()}


# --- возраст ----------------------------------------------------------

def test_fresh_record_is_marked_with_a_tick():
    assert freshness.label(aged(1)).startswith("✓")


def test_middle_aged_record_states_the_date_without_alarm():
    text = freshness.label(aged(45))
    assert text.startswith("проверено") and "⚠️" not in text


def test_old_record_warns():
    assert "⚠️" in freshness.label(aged(200))
    assert freshness.is_stale(aged(200))


def test_record_without_a_date_counts_as_old():
    """Неизвестно — значит давно. Иначе запись без даты выглядит свежей."""
    assert freshness.is_stale({"name": "Без даты"})
    assert freshness.age({"name": "Без даты"}) is None
    assert "⚠️" in freshness.label({"name": "Без даты"})


def test_broken_date_does_not_crash():
    assert freshness.is_stale({"checked": "вчера"})


def test_stamp_makes_it_fresh():
    item = freshness.stamp({"name": "Новый"})
    assert not freshness.is_stale(item)
    assert item["checked"] == date.today().isoformat()


# --- предупреждения ---------------------------------------------------

def test_warning_appears_only_when_something_is_old():
    assert freshness.warning([aged(2), aged(5)]) == ""
    assert "⚠️" in freshness.warning([aged(2), aged(200)])


def test_stale_report_skips_healthy_sections():
    text = freshness.stale_report({"Связь": [aged(1)],
                                   "Отели": [aged(400)]})
    assert "Отели" in text and "Связь" not in text


def test_stale_report_is_empty_when_all_is_fresh():
    assert freshness.stale_report({"Связь": [aged(1)]}) == ""


# --- связь ------------------------------------------------------------

def test_plan_needs_a_name_and_a_country():
    assert esim.parse_plan("Airalo") is None
    assert esim.parse_plan("") is None
    assert esim.parse_plan("Airalo | Израиль") is not None


def test_plan_reads_price_and_number():
    item = esim.parse_plan("Airalo | Израиль | https://a.com | 4.5 | номер нет")
    assert item["price"] == 4.5
    assert item["number"] is False
    assert item["url"] == "https://a.com"
    assert not freshness.is_stale(item), "новая запись сразу устарела"


def test_local_number_is_not_confused_with_its_absence():
    """«номер есть» и «номер нет» отличаются словом, а значат разное."""
    assert esim.parse_plan("A | Кипр | номер есть")["number"] is True
    assert esim.parse_plan("A | Кипр | без номера")["number"] is False


def test_plans_are_sorted_by_price_per_gigabyte():
    items = [{"name": "Дорогой", "country": "Израиль", "price": 9},
             {"name": "Дешёвый", "country": "Израиль", "price": 3},
             {"name": "Чужой", "country": "Франция", "price": 1}]
    picked = esim.for_country(items, "израиль")
    assert [i["name"] for i in picked] == ["Дешёвый", "Дорогой"]


def test_plan_without_a_price_sinks_to_the_bottom():
    """Ноль в цене — это «не записано», а не «бесплатно»."""
    items = [{"name": "Без цены", "country": "Кипр", "price": 0},
             {"name": "С ценой", "country": "Кипр", "price": 5}]
    assert esim.for_country(items, "Кипр")[0]["name"] == "С ценой"


def test_intro_answers_the_three_traps():
    for word in ("бесплатно", "Коды от банков", "*#06#"):
        assert word in esim.BEFORE, word


def test_report_shows_the_check_date(settings):
    run(esim.save_plans([esim.parse_plan("Airalo | Израиль | 4.5")]))
    assert "проверено" in run(esim.report("Израиль"))


def test_plans_are_owner_only(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)

    class Msg:
        def __init__(self, text, user_id):
            self.text = text
            self.said = []
            self.from_user = type("U", (), {"id": user_id})()

        async def answer(self, text, **kw):
            self.said.append(text)

    stranger = Msg("/тарифы + Свой | Кипр", 999)
    run(esim.plans_command(stranger))
    assert not stranger.said
    assert run(esim.plans()) == []


# --- отели ------------------------------------------------------------

def test_rules_name_what_actually_costs_money():
    for word in ("напрямую", "отмена", "налог", "депозит"):
        assert word in hotels.RULES.lower(), word


def test_rules_show_up_even_without_services(settings):
    text = run(hotels.report())
    assert "Бронирование" in text and "не заведены" in text


def test_hotel_service_keeps_its_link(settings):
    item = hotels.parse_place("Островок | https://o.ru | Россия | без комиссии")
    assert item["url"] == "https://o.ru"
    assert item["where"] == "Россия"
    assert not freshness.is_stale(item)


@pytest.mark.parametrize("module", [esim, hotels])
def test_neither_module_pretends_to_sell(module):
    """Продажа связи или бронирование — чужая лицензия и чужая
    ответственность."""
    source = open(module.__file__, encoding="utf-8").read()
    assert "не прода" in source or "не бронирует" in source


# --- меню -------------------------------------------------------------

def test_travel_menu_has_no_dead_ends():
    """Каждая кнопка должна вести к действию, а не к тексту-заглушке."""
    import inline_kb

    data = [b.callback_data for row in
            inline_kb.get_travel_main_menu("ru").inline_keyboard for b in row]
    assert "travel_geography" not in data
    assert "travel_toolkit" not in data
    assert "sim_open" in data and "hotel_open" in data
