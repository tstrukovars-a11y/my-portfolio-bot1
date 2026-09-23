# Сборка поста и расписание дня.
#
# Две вещи, за которые отвечает этот файл, стоят дорого: маркировка
# рекламы, которая обязана остаться в самом объявлении, и порядок
# выпусков, который на выходных сдвигается.
from datetime import datetime

import pytest

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


# --- имя бота ---------------------------------------------------------

class _Me:
    def __init__(self, username):
        self.username = username


class _Bot:
    def __init__(self, username):
        self._me = _Me(username)

    async def get_me(self):
        return self._me


def test_new_name_is_picked_up(settings):
    """Имя меняют в BotFather, а бот узнаёт о нём только при запуске."""
    settings[digest.BOT_KEY] = "old_bot"
    assert run(digest.refresh_bot_name(_Bot("accent_hub_bot"))) is True
    assert settings[digest.BOT_KEY] == "accent_hub_bot"


def test_same_name_is_not_rewritten(settings):
    settings[digest.BOT_KEY] = "accent_hub_bot"
    assert run(digest.refresh_bot_name(_Bot("accent_hub_bot"))) is False


def test_telegram_silence_does_not_erase_the_name(settings):
    """Потерять известное имя хуже, чем не узнать новое."""
    settings[digest.BOT_KEY] = "accent_hub_bot"

    class Broken:
        async def get_me(self):
            raise RuntimeError("нет сети")

    assert run(digest.refresh_bot_name(Broken())) is False
    assert settings[digest.BOT_KEY] == "accent_hub_bot"


# --- обзор генетики ---------------------------------------------------
#
# Источники англоязычные: термины в переводе плывут. Значит, сводка —
# единственное место, где читатель вообще поймёт, о чём речь, и без неё
# блок публиковать нельзя.

def test_genetics_block_needs_a_summary(monkeypatch, settings):
    async def headlines():
        return "US scientists map the genome of…"

    async def no_summary(*args, **kwargs):
        return ""

    monkeypatch.setattr(digest, "_genetics_text", headlines)
    monkeypatch.setattr(digest, "_summary", no_summary)
    assert run(digest._genetics_post()) == ""


def test_genetics_block_is_skipped_without_headlines(monkeypatch, settings):
    async def nothing():
        return ""

    monkeypatch.setattr(digest, "_genetics_text", nothing)
    assert run(digest._genetics_post()) == ""


def test_genetics_block_shows_summary_and_links(monkeypatch, settings):
    async def headlines():
        return "[Первый](http://a)\n[Второй](http://b)\n[Третий](http://c)\n[Лишний](http://d)"

    async def summary(text, prompt, key, what):
        return "Короткий разбор."

    monkeypatch.setattr(digest, "_genetics_text", headlines)
    monkeypatch.setattr(digest, "_summary", summary)
    post = run(digest._genetics_post())
    assert "🧬" in post and "Короткий разбор" in post
    assert "Первый" in post and "Лишний" not in post, "в пост лезет всё подряд"


def test_genetics_prompt_forbids_medical_advice():
    """Канал ведёт врач, и намёк на рекомендацию здесь дороже ошибки."""
    low = digest.GEN_PROMPT.lower()
    assert "нельзя" in low
    assert "мышах" in low or "клетках" in low, "нет запрета выдавать опыт за лечение"
    assert "учёные доказали" in low


def test_summaries_do_not_share_a_slot():
    """Одна настройка на две темы — и генетика затрёт экономику."""
    assert digest.GEN_SUMMARY_KEY != digest.SUMMARY_KEY


def test_rates_heading_has_no_time_of_day():
    import fx_rates

    assert "утром" not in fx_rates.morning_block.__doc__.split("\n")[0].lower()
    source = open(fx_rates.__file__, encoding="utf-8").read()
    assert '"💱 *Курсы*' in source


# --- вступление, которого не просили ----------------------------------
#
# Промпт запрещает вступления, модель их всё равно приписывает. Просить
# второй раз бесполезно: срезаем механически.

@pytest.mark.parametrize("text,expected", [
    ("Вот сводка по заголовкам:\n\nГеном прочитан.", "Геном прочитан."),
    ("Краткий обзор: геном прочитан.", "геном прочитан."),
    ("Сводка:\nГеном прочитан.", "Геном прочитан."),
    ("  Геном прочитан.  ", "Геном прочитан."),
])
def test_intro_is_cut_off(text, expected):
    assert digest._no_intro(text) == expected


@pytest.mark.parametrize("text", [
    "Главное: геном пшеницы прочитан.",
    "Учёные из Израиля: работа идёт третий год.",
    "Итого получилось три исследования, и все на мышах.",
])
def test_real_text_is_not_cut(text):
    """Узкое правило: двоеточие бывает и в живой фразе."""
    assert digest._no_intro(text) == text


def test_empty_summary_stays_empty():
    assert digest._no_intro("") == ""
    assert digest._no_intro(None) == ""


# --- источники --------------------------------------------------------

def test_sources_become_links():
    """Лента приходит в markdown, служебные экраны — в HTML: без перевода
    читатель увидел бы квадратные скобки вместо ссылок."""
    out = digest._sources_html("[Genome mapped](http://a)\n[CRISPR](http://b)")
    assert '<a href="http://a">Genome mapped</a>' in out
    assert out.count("•") == 2


def test_sources_survive_a_line_without_a_link():
    out = digest._sources_html("просто строка")
    assert "просто строка" in out and "<a" not in out


def test_channel_block_names_its_sources(monkeypatch, settings):
    async def headlines():
        return "[Первый](http://a)\n[Второй](http://b)"

    async def summary(text, prompt, key, what):
        return "Разбор."

    monkeypatch.setattr(digest, "_genetics_text", headlines)
    monkeypatch.setattr(digest, "_summary", summary)
    post = run(digest._genetics_post())
    assert "Источники" in post and "http://a" in post


# --- метки в генетике --------------------------------------------------
#
# Врач-генетик просила не пропускать наследственные опухоли. Пропущенная
# новость здесь — не досадная мелочь: ради неё и читают ленту.

@pytest.mark.parametrize("line,expected", [
    ("BRCA1 carriers study", "BRCA"),
    ("Novel 5382insC findings", "5382insC"),
    ("A 185delAG variant described", "185delAG"),
    ("6174delT in a new cohort", "6174delT"),
    ("Olaparib trial results", "olaparib"),
])
def test_watched_words_are_found(line, expected):
    hits = digest.gen_hits(line, digest.GEN_WATCH_DEFAULT)
    assert any(expected.lower() == h.lower() for h in hits), hits


def test_similar_mutations_are_caught_by_shape():
    """«И похожие» — это форма записи, а не список: таких вариантов сотни,
    и перечислить их заранее нельзя."""
    assert digest.gen_hits("The 1100delC variant", []) == ["1100delC"]
    assert digest.gen_hits("c.68_69del reported", [])


def test_ordinary_news_is_not_marked():
    assert digest.gen_hits("Ancient wheat genome sequenced",
                           digest.GEN_WATCH_DEFAULT) == []


def test_one_headline_gives_one_hit():
    """«BRCA» и «BRCA1» в одной строке — одна находка, а не две."""
    hits = digest.gen_hits("BRCA1 and BRCA2 compared", ["BRCA", "BRCA1", "BRCA2"])
    assert len(hits) == 1


def test_marked_headlines_rise_to_the_top():
    lines = ["Wheat genome", "BRCA1 study", "Rice genome"]
    assert digest.gen_sort(lines, digest.GEN_WATCH_DEFAULT)[0] == "BRCA1 study"


def test_sorting_keeps_everything():
    lines = ["A", "BRCA1", "B"]
    assert sorted(digest.gen_sort(lines, ["BRCA"])) == sorted(lines)


def test_watch_list_can_be_emptied_without_breaking_shape_rule(settings):
    """Даже с пустым списком мутации ловятся: правило не зависит от слов."""
    settings[digest.GEN_WATCH_KEY] = "[]"
    assert run(digest.gen_watch()) == []
    assert digest.gen_hits("5382insC", [])


def test_broken_watch_list_falls_back(settings):
    settings[digest.GEN_WATCH_KEY] = "не json"
    assert "BRCA" in run(digest.gen_watch())


# --- помощь со звонком под публикацией ---------------------------------
#
# Человек читает про поездку — и ровно там у него возникает «а как я
# позвоню». По разделам никто не ходит; кнопка должна стоять там, где
# вопрос рождается, а не там, где её удобно положить.

def test_call_row_only_where_it_makes_sense(settings, monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://bot.example.com")
    assert run(digest._call_row("travel")) is not None
    assert run(digest._call_row("books")) is None
    assert run(digest._call_row("puzzle")) is None


def test_call_row_needs_a_public_address(settings, monkeypatch):
    """Микрофон браузер даёт только на https: локально кнопки нет."""
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    assert run(digest._call_row("travel")) is None


def test_call_sections_can_be_changed(settings, monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://bot.example.com")
    settings[digest.CALL_KEY] = "books"
    assert run(digest._call_row("books")) is not None
    assert run(digest._call_row("travel")) is None
