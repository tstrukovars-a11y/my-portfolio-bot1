# «Что в мире»: рамку ставит человек, отбор внутри неё делает модель.
#
# Лента без отбора — двести заголовков в сутки, читать её никто не
# станет. Отбор по значимости «вообще» модель делать не должна: это
# оценка, а оценок в канале нет нигде. Поэтому темы задаёт владелица.
from conftest import run

import config
import world


def test_without_topics_there_is_nothing_to_fetch(settings):
    assert run(world.headlines()) == ""


def test_topics_survive_a_round_trip(settings):
    run(world.save_topics(["чума", "санкции против России"]))
    assert run(world.topics()) == ["чума", "санкции против России"]


def test_blank_lines_are_not_topics(settings):
    settings[world.TOPICS_KEY] = "чума\n\n   \nнефть\n"
    assert run(world.topics()) == ["чума", "нефть"]


def test_the_list_has_a_ceiling(settings):
    """Больше восьми — это уже не отбор, а лента."""
    run(world.save_topics([f"тема {i}" for i in range(20)]))
    assert len(run(world.topics())) == world.MAX_TOPICS


def test_a_topic_becomes_a_search_feed():
    """Тема — поисковый запрос, а не слово в тексте: поэтому новая тема
    не требует кода."""
    url = world.FEED.format(q="%D1%87%D1%83%D0%BC%D0%B0")
    assert url.startswith("https://news.google.com/rss/search?q=")
    assert "hl=ru" in url


def test_the_prompt_lets_a_quiet_topic_be_skipped():
    """Пустая строчка ради полноты хуже её отсутствия."""
    low = world.PROMPT.lower()
    assert "тему пропусти" in low


def test_the_prompt_forbids_taking_sides():
    low = world.PROMPT.lower()
    assert "называть виновных" in low and "занимать сторону" in low


def test_the_prompt_forbids_predictions_and_advice():
    low = world.PROMPT.lower()
    assert "предсказывать последствия" in low and "советы" in low


def test_a_service_remark_never_becomes_a_post(settings, monkeypatch):
    """Та же защита, что у теннисных пересказов и утренних сводок."""
    import digest
    assert digest.is_meta("В предоставленных заголовках нет существенного.")


def test_no_body_means_no_post(settings, monkeypatch):
    async def nothing():
        return ""

    monkeypatch.setattr(world, "build", nothing)
    assert run(world.post()) == ""


def test_the_post_carries_its_heading(settings, monkeypatch):
    async def body():
        return "Нефть подорожала на 4%."

    monkeypatch.setattr(world, "build", body)
    out = run(world.post())
    assert out.startswith(world.HEAD)
    assert "Нефть подорожала" in out
