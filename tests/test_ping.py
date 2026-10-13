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


# --- команда, набранная в канале ---------------------------------------
#
# Пост в канале приходит боту отдельным типом события, и обработчики
# команд его не видят вовсе. Для человека это выглядит так же, как
# мёртвый бот: он пишет команду за командой и не получает ничего.

class Post:
    def __init__(self, text="/пинг"):
        self.text = text
        self.bot = self

    async def send_message(self, chat, text, **kw):
        self.sent = (chat, text)


def test_a_command_in_the_channel_is_not_ignored(monkeypatch, settings):
    monkeypatch.setattr(config, "ADMIN_ID", 5)
    post = Post()
    run(ping.command_in_channel(post))
    chat, text = post.sent
    assert chat == 5
    assert "в канале" in text and "в личке" in text


def test_the_hint_names_the_command(monkeypatch, settings):
    monkeypatch.setattr(config, "ADMIN_ID", 5)
    post = Post("/art_queue")
    run(ping.command_in_channel(post))
    assert "/art_queue" in post.sent[1]


def test_the_same_command_is_not_hinted_twice(monkeypatch, settings):
    """Человек, не получивший ответа, набирает команду трижды подряд —
    три одинаковых письма раздражают сильнее молчания."""
    monkeypatch.setattr(config, "ADMIN_ID", 5)
    first = Post()
    run(ping.command_in_channel(first))
    second = Post()
    run(ping.command_in_channel(second))
    assert not hasattr(second, "sent")


def test_without_an_owner_nothing_is_sent(monkeypatch, settings):
    monkeypatch.setattr(config, "ADMIN_ID", 0)
    post = Post()
    run(ping.command_in_channel(post))
    assert not hasattr(post, "sent")


def test_the_bot_listens_to_channel_posts():
    """Иначе подсказка не сработает: обновление просто не придёт."""
    import asyncio
    from aiogram import Dispatcher
    dp = Dispatcher()
    dp.include_router(ping.router)
    assert "channel_post" in dp.resolve_used_update_types()
