# Срочная публикация: то, что не ждёт расписания.
#
# Пост в канал уходит один раз и правится плохо. Поэтому здесь важнее
# обычного две вещи: что разбор черновика не теряет и не путает части, и
# что без подтверждения ничего не улетает.
import pytest

from conftest import run

import config
import urgent


class Msg:
    def __init__(self, text, user_id=1):
        self.text = text
        self.said = []
        self.from_user = type("U", (), {"id": user_id})()

    async def answer(self, text, **kw):
        self.said.append(text)


# --- разбор черновика --------------------------------------------------

def test_text_button_and_photo_are_told_apart():
    draft = urgent.parse(
        "Вышло приложение.\n"
        "Вторая строка.\n"
        "кнопка: Поставить | https://apps.apple.com/app/id1\n"
        "фото: data/cards/x.png")
    assert draft["text"] == "Вышло приложение.\nВторая строка."
    assert draft["button"] == ("Поставить", "https://apps.apple.com/app/id1")
    assert draft["photo"] == "data/cards/x.png"


def test_plain_text_needs_nothing_else():
    draft = urgent.parse("Просто новость")
    assert draft["text"] == "Просто новость"
    assert draft["button"] is None and draft["photo"] is None


def test_button_without_a_link_is_refused():
    """Кнопка без адреса — это кнопка в никуда прямо в канале."""
    draft = urgent.parse("Текст\nкнопка: Поставить")
    assert draft["button"] is None


def test_button_with_a_broken_link_is_refused():
    draft = urgent.parse("Текст\nкнопка: Поставить | зайдите на сайт")
    assert draft["button"] is None


def test_colon_inside_the_text_survives():
    """«Счёт: 40:30» — обычная строка, а не разметка."""
    draft = urgent.parse("Счёт: 40:30 и это важно")
    assert draft["text"] == "Счёт: 40:30 и это важно"


# --- вид публикации ----------------------------------------------------

def test_two_kinds_have_different_heads():
    """Новость о мире и новость о канале — разные вещи для читателя."""
    draft = {"text": "Текст"}
    assert urgent.render("news", draft) != urgent.render("changes", draft)
    assert "Срочно" in urgent.render("news", draft)
    assert "Что нового" in urgent.render("changes", draft)


def test_unknown_kind_falls_back_to_news():
    assert "Срочно" in urgent.render("чушь", {"text": "Текст"})


# --- ничего не улетает само -------------------------------------------

def test_empty_command_only_explains(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    message = Msg("/срочно")
    run(urgent.urgent_command(message))
    assert "Срочная публикация" in message.said[0]
    assert not settings.get(urgent.DRAFT_KEY)


def test_missing_photo_stops_the_preview(settings, monkeypatch):
    """Публикация упала бы уже после подтверждения — а пост к тому
    моменту считается отправленным."""
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    message = Msg("/срочно Текст\nфото: нет/такого/файла.png")
    run(urgent.urgent_command(message))
    assert "Файла нет" in message.said[0]
    assert not settings.get(urgent.DRAFT_KEY)


def test_preview_saves_the_draft(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    run(urgent.urgent_command(Msg("/срочно Вышло приложение")))
    assert "Вышло приложение" in settings[urgent.DRAFT_KEY]


# --- команду зовут как придётся ---------------------------------------

@pytest.mark.parametrize("command", [
    "/срочно", "/срочная новость", "/срочная", "/Срочная Новость",
])
def test_every_form_of_the_name_works(settings, monkeypatch, command):
    """Человек торопится и пишет то имя, которое всплыло в голове.
    Заставлять его вспоминать точную форму — ставить препятствие ровно
    там, где он спешит."""
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    run(urgent.urgent_command(Msg(f"{command} Вышло приложение")))
    assert "Вышло приложение" in settings[urgent.DRAFT_KEY]


def test_the_command_does_not_leak_into_the_post(settings, monkeypatch):
    """«новость» — часть команды, а не первое слово заголовка."""
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    run(urgent.urgent_command(Msg("/срочная новость Вышло приложение")))
    draft = settings[urgent.DRAFT_KEY]
    assert "новость Вышло" not in draft
    assert "срочн" not in draft.lower()


def test_a_post_may_start_with_the_word_news(settings, monkeypatch):
    """«/срочно Новость о…» — «Новость» здесь заголовок, не команда."""
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    run(urgent.urgent_command(Msg("/срочно Новость о приложении")))
    assert "Новость о приложении" in settings[urgent.DRAFT_KEY]


@pytest.mark.parametrize("command", ["/новое", "/что нового"])
def test_changes_answers_to_both_names(settings, monkeypatch, command):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    run(urgent.changes_command(Msg(f"{command} Появилась подписка")))
    draft = settings[urgent.DRAFT_KEY]
    assert "Появилась подписка" in draft
    assert '"kind": "changes"' in draft


def test_routers_match_the_same_names():
    """Разбор и фильтр роутера берут один и тот же образец: иначе бот
    молча не отвечает на команду, которую сам же умеет разбирать."""
    source = open("urgent.py", encoding="utf-8").read()
    assert "F.text.regexp(URGENT)" in source
    assert "F.text.regexp(CHANGES)" in source


def test_strangers_cannot_publish(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    message = Msg("/срочно Чужой текст", user_id=999)
    run(urgent.urgent_command(message))
    assert not message.said
    assert not settings.get(urgent.DRAFT_KEY)


def test_cancel_clears_the_draft(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    settings[urgent.DRAFT_KEY] = '{"kind": "news", "text": "Текст"}'

    class Call:
        def __init__(self):
            self.message = Msg("")
            self.answers = []

        from_user = type("U", (), {"id": 1})()

        async def answer(self, text="", **kw):
            self.answers.append(text)

    run(urgent.cancel(Call()))
    assert settings[urgent.DRAFT_KEY] == ""
