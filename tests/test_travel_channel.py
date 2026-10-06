# Подпись места в канале путешествий.
#
# Сверху место мешало: в ленте первым читается заголовок, и вместо
# начала рассказа человек получал адрес — «Ницца · Франция», когда ещё
# не знает, о чём речь. Внизу та же строка работает как подпись под
# фотографией: дочитал — и видишь, где это было.
#
# Главная ловушка переноса: подпись к фотографии обрезается по тысяче
# знаков и обрезается с конца, то есть ровно там, где теперь стоит
# место. Длинный рассказ молча съедал бы то, ради чего всё делалось.
import travel_channel as tc


def test_the_place_stands_under_the_text():
    out = tc._post_text("Франция", "Ницца", "Набережная тянется шесть километров.")
    assert out.startswith("Набережная"), "место снова оказалось заголовком"
    assert out.rstrip().endswith("Ницца")


def test_both_country_and_city_are_named():
    out = tc._post_text("Франция", "Ницца", "Текст.")
    assert "Франция" in out and "Ницца" in out


def test_the_country_comes_first():
    """По стране ищут и по стране вспоминают, а город без страны
    половине читателей ничего не говорит."""
    out = tc._post_text("Франция", "Ницца", "Текст.")
    assert out.index("Франция") < out.index("Ницца")


def test_the_flag_stays_with_the_country():
    out = tc._post_text("Франция", "Ницца", "Текст.")
    assert "🇫🇷 Франция" in out


def test_a_place_without_a_city_still_names_the_country():
    out = tc._post_text("Франция", "", "Текст.")
    assert out.rstrip().endswith("Франция")
    assert "·" not in out.rsplit("📍", 1)[-1]


def test_a_post_without_a_place_gets_no_empty_line():
    assert tc._post_text("", "", "Текст.") == "Текст."


def test_a_long_story_is_cut_but_the_place_survives():
    """Подпись режется с конца — значит, резать надо рассказ, а не
    адрес: без последней фразы пост остаётся постом, без страны и
    города это снимок без подписи."""
    long = "Набережная тянется шесть километров. " * 40
    out = tc._post_text("Франция", "Ницца", long, tc.MAX_CAPTION)
    assert len(out) <= tc.MAX_CAPTION
    assert out.rstrip().endswith("📍 🇫🇷 Франция · Ницца")


def test_a_cut_story_says_it_was_cut():
    long = "Набережная тянется шесть километров. " * 40
    out = tc._post_text("Франция", "Ницца", long, tc.MAX_CAPTION)
    assert "…" in out.split("📍")[0]


def test_a_short_story_is_not_touched():
    out = tc._post_text("Франция", "Ницца", "Коротко.", tc.MAX_CAPTION)
    assert out.startswith("Коротко.")
    assert "…" not in out


def test_the_sender_knows_which_limit_applies():
    """У поста с фотографией подпись короче вчетверо. Один предел на
    оба случая обрезал бы текстовые посты впустую — или пропускал бы
    слишком длинную подпись, и пост не вышел бы вовсе."""
    source = open("travel_channel.py", encoding="utf-8").read()
    assert "MAX_CAPTION if photo else MAX_MESSAGE" in source
    assert "body[:MAX_CAPTION]" not in source, \
        "обрезка вернулась в отправку и снова срежет место"


def test_an_edit_looks_exactly_like_a_new_post():
    """Иначе правка меняет не только текст, но и оформление, и это
    видно как мигание."""
    source = open("travel_channel.py", encoding="utf-8").read()
    body = source[source.index("async def _run"):]
    assert body.count("_post_text(") == 1, \
        "вид поста собирается в двух местах — они разойдутся"
