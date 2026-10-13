# Жив ли бот и узнаёт ли он владельца.
#
# Каждая служебная команда начинается с «вы владелец?», и при
# несовпадении обработчик молча выходит. Снаружи это неотличимо от
# мёртвого бота: в обоих случаях тишина.
#
# Разница огромная. Мёртвый бот чинят перезапуском, неузнанного
# владельца — одной переменной окружения. Пока их не различить, чинится
# наугад то одно, то другое.
import config
import ping
from conftest import run


class Msg:
    def __init__(self, user_id=1, chat_type="private"):
        self.text = "/пинг"
        self.said = []
        self.from_user = type("U", (), {"id": user_id})()
        self.chat = type("C", (), {"type": chat_type})()

    async def answer(self, text, **kw):
        self.said.append(text)


def _say(monkeypatch, admin=1, user_id=1, chat_type="private", db_ok=True):
    import database

    monkeypatch.setattr(config, "ADMIN_ID", admin)

    async def health():
        return {"ok": db_ok, "error": "" if db_ok else "connection refused"}

    monkeypatch.setattr(database, "health", health)
    message = Msg(user_id, chat_type)
    run(ping.ping(message))
    return message.said[0]


def test_it_answers_at_all(monkeypatch):
    """Единственное требование к этой команде: ответ приходит всегда."""
    assert "жив" in _say(monkeypatch).lower()


def test_it_answers_a_stranger_too(monkeypatch):
    """Иначе она отвечает ровно тем, кто и так всё знает."""
    assert _say(monkeypatch, admin=1, user_id=999)


def test_it_tells_the_owner_he_is_the_owner(monkeypatch):
    assert "Вы — владелец" in _say(monkeypatch, admin=5, user_id=5)


def test_it_tells_a_stranger_he_is_not(monkeypatch):
    text = _say(monkeypatch, admin=5, user_id=999)
    assert "другой номер" in text


def test_it_shouts_when_no_owner_is_set(monkeypatch):
    """Самый коварный случай: бот работает, команды есть, и ни одна не
    отвечает — переменная окружения потерялась."""
    text = _say(monkeypatch, admin=0, user_id=5)
    assert "Владелец не задан" in text
    assert "ADMIN_ID" in text


def test_it_shows_your_own_number(monkeypatch):
    """Чтобы было что вписать в переменную."""
    assert "777" in _say(monkeypatch, admin=0, user_id=777)


def test_a_dead_database_is_named(monkeypatch):
    text = _say(monkeypatch, db_ok=False)
    assert "База не отвечает" in text


def test_a_live_database_is_named(monkeypatch):
    assert "База: отвечает" in _say(monkeypatch)


def test_in_a_group_it_says_why_commands_are_silent(monkeypatch):
    text = _say(monkeypatch, chat_type="supergroup")
    assert "общий чат" in text


def test_it_is_registered_before_everything_else():
    """Диагностика не должна зависеть от того, что сломалось ниже по
    списку роутеров."""
    source = open("main.py", encoding="utf-8").read()
    assert source.index("ping.router") < source.index("planner.router")
