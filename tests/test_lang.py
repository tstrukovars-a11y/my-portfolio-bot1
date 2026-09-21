# Язык без языка-прокладки.
#
# Главное правило модуля проверяется здесь механически: в карточках не
# должно быть ни одной русской буквы. Перевод незаметно возвращается —
# одна «подсказка в скобках», и через месяц это уже учебник с русским.
import json
import re
from pathlib import Path

import pytest

from conftest import run

import lang

CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")
DATA = Path(__file__).resolve().parent.parent / "data" / "lang.json"


def all_cards():
    for code, data in lang.content().items():
        for topic in data["topics"].values():
            for card in topic["cards"]:
                yield code, card


def test_file_is_valid_json():
    json.loads(DATA.read_text(encoding="utf-8"))


def test_three_languages_are_there():
    assert set(lang.content()) == {"fr", "he", "en"}


@pytest.mark.parametrize("code,card", list(all_cards()),
                         ids=lambda v: v if isinstance(v, str) else v["id"])
def test_no_russian_in_cards(code, card):
    text = card["word"] + " ".join(
        line["q"] + line["a"] for line in card["lines"])
    assert not CYRILLIC.search(text), f"{card['id']}: {text}"


def test_no_russian_in_dialogs():
    for data in lang.content().values():
        for topic in data["topics"].values():
            for turn in topic.get("dialog", {}).get("turns", []):
                assert not CYRILLIC.search(turn["text"]), turn["text"]


@pytest.mark.parametrize("code,card", list(all_cards()),
                         ids=lambda v: v if isinstance(v, str) else v["id"])
def test_every_card_shows_something(code, card):
    """Значение несёт картинка — без неё карточка непонятна."""
    assert card["emoji"].strip()
    assert card["word"].strip()
    assert card["lines"] and card["lines"][0]["q"] and card["lines"][0]["a"]


def test_card_ids_are_unique():
    ids = [card["id"] for _, card in all_cards()]
    assert len(ids) == len(set(ids))


# --- урок -------------------------------------------------------------

def test_new_cards_come_before_seen_ones():
    """Повторение не должно вытеснять новое, иначе урок стоит на месте."""
    cards = lang.cards_of("fr", "ecole")
    known = {cards[0]["id"], cards[1]["id"]}
    tasks = lang.build("fr", "ecole", known)
    first = [t["card"]["id"] for t in tasks[:len(cards) - len(known)]]
    assert not (set(first) & known)


def test_lesson_is_not_endless():
    assert len(lang.build("fr", "ecole", set())) <= lang.LESSON


def test_both_kinds_of_task_appear():
    """Узнать на слух и ответить на слух — оба задания в одном уроке.

    Только узнавание — и человек понимает, но молчит; только ответы — и
    он отвечает наугад, не расслышав вопроса.
    """
    kinds = {t["kind"] for t in lang.build("fr", "ecole", set())}
    assert kinds == {"hear", "reply"}


def test_options_contain_the_right_answer_once():
    card = lang.cards_of("fr", "ecole")[0]
    for kind in ("say", "show"):
        items = lang.options("fr", card, kind)
        assert len(items) == 4
        assert sum(1 for _, cid in items if cid == card["id"]) == 1


def test_wrong_options_come_from_other_topics_too():
    """Выбор из пяти знакомых слов превращается в угадайку."""
    seen = set()
    card = lang.cards_of("fr", "ecole")[0]
    for _ in range(40):
        seen.update(cid for _, cid in lang.options("fr", card, "say"))
    assert any(cid.startswith("fr.cafe") or cid in
               {c["id"] for c in lang.cards_of("fr", "cafe")} for cid in seen)


def test_question_shows_picture_for_say_and_word_for_show():
    card = lang.cards_of("fr", "ecole")[0]
    assert card["emoji"] in lang.question("fr", {"card": card, "kind": "say"})
    assert card["word"] in lang.question("fr", {"card": card, "kind": "show"})


def test_unknown_topic_gives_no_lesson():
    assert lang.build("fr", "нет-такой-темы", set()) == []


# --- звук -------------------------------------------------------------
#
# Слушать важнее, чем читать: кривой перевод на бумаге понятен, речь на
# слух — нет. Поэтому проверяем, что озвучено то, что нужно слышать.

AUDIO = Path(__file__).resolve().parent.parent / "data" / "audio"


def test_audio_is_shipped_with_the_code():
    """Синтезировать на сервере нечем — файлы едут в репозитории."""
    assert (AUDIO / "he").is_dir()
    assert list((AUDIO / "he").glob("*.m4a"))


@pytest.mark.parametrize("code", ["he", "fr", "en"])
def test_every_word_has_a_voice(code):
    missing = [card["word"] for c, card in all_cards() if c == code
               and not lang.audio_path(code, card["word"])]
    assert not missing, f"без звука: {missing}"


def test_unknown_text_has_no_file():
    assert lang.audio_path("he", "такого текста нет") is None


def test_file_name_hides_the_phrase():
    """Имя файла видно в проигрывателе — фразу нужно узнать ухом."""
    path = lang.audio_path("he", "מרפאה")
    assert path and "מרפאה" not in path


def test_listening_comes_first():
    """Пока у фразы есть звук, читать её незачем."""
    kinds = {t["kind"] for t in lang.build("he", "mirpaa", set())}
    assert kinds <= {"hear", "reply"}


def test_sound_matches_the_task():
    card = lang.cards_of("he", "mirpaa")[0]
    assert lang.sound("he", {"card": card, "kind": "hear"}) \
        == lang.audio_path("he", card["word"])
    assert lang.sound("he", {"card": card, "kind": "reply"}) \
        == lang.audio_path("he", card["lines"][0]["q"])
    assert lang.sound("he", {"card": card, "kind": "say"}) is None


def test_generator_and_bot_agree_on_names():
    """Разойдутся имена — звук молча перестанет находиться."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "make_audio", Path(__file__).resolve().parent.parent / "tools" / "make_audio.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)

    text = "מרפאה"
    assert lang.audio_path("he", text).endswith(tool.digest(text) + ".m4a")
