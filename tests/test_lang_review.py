# Проверка озвучки чужими ушами.
#
# Здесь два места, где ошибка дорого стоит. Первое — доступ: по ссылке
# приходит человек со стороны, и кнопки бота ему видны те же, что всем
# остальным. Второе — привязка ответа к фразе: перепутать их значит
# исправить не то слово, и заметить это будет уже нечем.
import pytest

from conftest import run

import config
import lang
import lang_review as review


class Msg:
    """Сообщение, которое только запоминает, что ему сказали"""

    def __init__(self, caption="", user_id=42):
        self.caption = caption
        self.from_user = type("U", (), {"id": user_id, "first_name": "Ури",
                                        "last_name": None})()
        self.said = []
        self.sent = []          # подписи к присланным записям
        self.chat = type("Chat", (), {"id": 7})()
        self.text = ""

    async def answer(self, text, **kw):
        self.said.append(text)
        return self

    async def answer_audio(self, file, caption="", **kw):
        self.sent.append(caption)
        self.caption = caption
        return self

    async def edit_reply_markup(self, **kw):
        return self


class Call:
    def __init__(self, data, user_id=42, caption=""):
        self.data = data
        self.message = Msg(caption)
        self.from_user = type("U", (), {"id": user_id, "first_name": "Ури",
                                        "last_name": None})()
        self.answers = []

    async def answer(self, text="", **kw):
        self.answers.append(text)


@pytest.fixture
def db(monkeypatch, settings):
    """База, живущая в памяти теста"""
    import database

    saved, notes = [], []

    async def save_review(code, phrase, reviewer, name, verdict, note="", voice_id=""):
        saved.append({"code": code, "phrase": phrase, "reviewer": reviewer,
                      "name": name, "verdict": verdict})
        return True

    async def review_note(code, phrase, reviewer, note="", voice_id=""):
        notes.append({"phrase": phrase, "note": note, "voice_id": voice_id})
        return True

    async def reviewed_by(code, reviewer):
        return {r["phrase"] for r in saved if r["reviewer"] == reviewer}

    monkeypatch.setattr(database, "save_review", save_review)
    monkeypatch.setattr(database, "review_note", review_note)
    monkeypatch.setattr(database, "reviewed_by", reviewed_by)
    return {"saved": saved, "notes": notes, "settings": settings}


# --- очередь ----------------------------------------------------------

def test_queue_is_what_actually_sounds():
    """Фраза без файла прислалась бы пустым сообщением."""
    for phrase in review.queue(set()):
        assert lang.audio_path(review.CODE, phrase)


def test_queue_skips_what_was_heard():
    first = review.queue(set())[0]
    assert first not in review.queue({first})


def test_queue_is_not_empty():
    assert len(review.queue(set())) > 20


def test_spelled_shows_what_the_machine_imagined():
    """Проверяющий должен видеть огласовки — по ним машина и читает."""
    marked = [p for p in review.queue(set()) if review.spelled(p)]
    assert marked, "огласовки никому не показываются"
    assert review.spelled("нет такой фразы") == ""


# --- доступ -----------------------------------------------------------

def test_link_needs_the_bot_name(db):
    assert run(review.link()) == ""
    db["settings"]["bot_username"] = "accent_hub_bot"
    assert run(review.link()).startswith("https://t.me/accent_hub_bot?start=check_")


def test_token_is_stable_until_changed(db):
    first = run(review.token())
    assert run(review.token()) == first
    assert run(review.new_token()) != first


def test_old_link_stops_working(db):
    """Смена ссылки — единственный способ её отозвать."""
    message = Msg()
    message.text = "/start check_старая"
    run(review.new_token())
    with pytest.raises(Exception):
        run(review.enter(message))
    assert not message.said


def test_right_link_lets_the_person_in(db):
    db["settings"]["bot_username"] = "accent_hub_bot"
    message = Msg()
    message.text = f"/start check_{run(review.token())}"
    run(review.enter(message))
    assert message.said and "Проверка озвучки" in message.said[0]
    assert message.sent, "первая фраза не пришла"


def test_a_stranger_cannot_vote(db):
    """Кнопку видно в чужой переписке — нажать её может кто угодно."""
    call = Call("chk_ok", user_id=999, caption="מרפאה\n1 / 46")
    run(review.verdict(call))
    assert not db["saved"]


# --- привязка ответа к фразе ------------------------------------------

def test_verdict_belongs_to_the_phrase_on_screen(db):
    db["settings"][review.CHECKER_KEY + "42"] = "1"
    call = Call("chk_ok", caption="מרפאה\nמִרְפָּאָה\n\n1 / 46")
    run(review.verdict(call))
    assert db["saved"][0]["phrase"] == "מרפאה"
    assert db["saved"][0]["verdict"] == "ok"


def test_skip_is_remembered_too(db):
    """Иначе бот предложит то же самое по кругу."""
    db["settings"][review.CHECKER_KEY + "42"] = "1"
    run(review.verdict(Call("chk_skip", caption="מרפאה\n1 / 46")))
    assert db["saved"][0]["verdict"] == "skip"


def test_bad_verdict_asks_how_it_should_sound(db):
    db["settings"][review.CHECKER_KEY + "42"] = "1"
    call = Call("chk_bad", caption="מרפאה\n1 / 46")
    run(review.verdict(call))
    assert db["saved"][0]["verdict"] == "bad"
    assert any("голосом" in text for text in call.message.said)
    assert db["settings"][review.WAIT_KEY + "42"] == "מרפאה"


def test_voice_answer_lands_on_the_right_phrase(db):
    db["settings"][review.CHECKER_KEY + "42"] = "1"
    db["settings"][review.WAIT_KEY + "42"] = "מרפאה"

    message = Msg()
    message.voice = type("V", (), {"file_id": "AgAD123"})()
    message.audio = None
    message.video_note = None
    run(review.voice_note(message))

    assert db["notes"][0] == {"phrase": "מרפאה", "note": "",
                              "voice_id": "AgAD123"}
    assert not db["settings"][review.WAIT_KEY + "42"], "ждём замечание дальше"


def test_voice_without_a_question_is_not_ours(db):
    """Голосовое в боте может быть адресовано другому разделу."""
    message = Msg()
    message.voice = type("V", (), {"file_id": "x"})()
    with pytest.raises(Exception):
        run(review.voice_note(message))
    assert not db["notes"]


# --- отчёт ------------------------------------------------------------

def test_report_names_what_to_fix(db, monkeypatch):
    import database

    async def reviews(code, only_bad=False):
        return [{"phrase": "מרפאה", "verdict": "bad", "note": "ударение",
                 "voice_id": "x", "reviewer": 42, "reviewer_name": "Ури",
                 "created_at": None},
                {"phrase": "טלפון", "verdict": "ok", "note": None,
                 "voice_id": None, "reviewer": 42, "reviewer_name": "Ури",
                 "created_at": None}]

    monkeypatch.setattr(database, "reviews", reviews)
    text = run(review.report())
    assert "Ури" in text
    assert "מרפאה" in text and "ударение" in text
    assert "🎤" in text, "не видно, что есть запись голосом"


def test_report_survives_an_empty_start(db, monkeypatch):
    import database

    async def reviews(code, only_bad=False):
        return []

    monkeypatch.setattr(database, "reviews", reviews)
    assert "Пока никто не слушал" in run(review.report())


def test_panel_is_closed_to_everyone_else(db, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    call = Call("admin_check", user_id=999)
    run(review.panel(call))
    assert not call.message.said
