"""Имя бота для глубоких ссылок (common.bot_username).

На нём держатся все кнопки из канала. Имя кладётся в настройку при
запуске, но если в ту секунду не ответила база, настройка останется
пустой — и ссылки молча перестанут строиться до перезапуска: кнопки
есть, ведут в никуда. Поэтому имя доспрашивается на месте.
"""

import asyncio

import common


class _Me:
    def __init__(self, username):
        self.username = username


class _FakeBot:
    def __init__(self, username="AkcentBot"):
        self.asked = 0
        self._me = _Me(username)

    async def get_me(self):
        self.asked += 1
        return self._me


def _clear():
    common._username_cache.clear()


def test_the_setting_is_used_when_it_is_filled(monkeypatch):
    _clear()
    monkeypatch.setattr(common.database, "get_setting",
                        lambda key, default=None: asyncio.sleep(0, result="AkcentBot"))
    bot = _FakeBot()
    assert asyncio.run(common.bot_username(bot)) == "AkcentBot"
    assert bot.asked == 0, "спрашивать Telegram было незачем"


def test_an_empty_setting_falls_back_to_telegram(monkeypatch):
    """Главный случай: база не ответила при запуске, и настройка пуста."""
    _clear()
    monkeypatch.setattr(common.database, "get_setting",
                        lambda key, default=None: asyncio.sleep(0, result=None))
    monkeypatch.setattr(common.database, "set_setting",
                        lambda key, value: asyncio.sleep(0, result=True))
    bot = _FakeBot("AkcentBot")
    assert asyncio.run(common.bot_username(bot)) == "AkcentBot"
    assert bot.asked == 1


def test_the_answer_is_remembered(monkeypatch):
    """Дёргать Telegram на каждую кнопку незачем."""
    _clear()
    monkeypatch.setattr(common.database, "get_setting",
                        lambda key, default=None: asyncio.sleep(0, result=None))
    monkeypatch.setattr(common.database, "set_setting",
                        lambda key, value: asyncio.sleep(0, result=True))
    bot = _FakeBot()
    asyncio.run(common.bot_username(bot))
    asyncio.run(common.bot_username(bot))
    assert bot.asked == 1


def test_a_leading_at_is_stripped(monkeypatch):
    """В настройку могли вписать «@AkcentBot» — ссылка с двумя собаками
    не откроется."""
    _clear()
    monkeypatch.setattr(common.database, "get_setting",
                        lambda key, default=None: asyncio.sleep(0, result="@AkcentBot"))
    link = asyncio.run(common.deep_link("tm-atp-1"))
    assert link == "https://t.me/AkcentBot?start=tm-atp-1"


def test_without_a_bot_and_without_a_setting_the_link_is_empty(monkeypatch):
    """Пустая ссылка честнее кнопки, которая никуда не ведёт."""
    _clear()
    monkeypatch.setattr(common.database, "get_setting",
                        lambda key, default=None: asyncio.sleep(0, result=None))
    assert asyncio.run(common.deep_link("tm-atp-1")) == ""


def test_telegram_failing_does_not_raise(monkeypatch):
    """Упасть на построении ссылки нельзя: кнопку нажали посреди матча."""
    _clear()
    monkeypatch.setattr(common.database, "get_setting",
                        lambda key, default=None: asyncio.sleep(0, result=None))

    class _Broken:
        async def get_me(self):
            raise RuntimeError("Telegram недоступен")

    assert asyncio.run(common.bot_username(_Broken())) == ""
