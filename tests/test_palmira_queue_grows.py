"""Заготовка состава доезжает не только в первый раз.

Состав объявляют по частям, иногда за день до турнира. Раньше
заготовка подставлялась ровно однажды — при самом первом обращении, —
и дописанное в неё после этого не попадало в очередь никогда. Из-за
этого в канал ушёл список из шести человек вместо десяти.
"""

import asyncio

import pytest

import palmira


class Память:
    """Настройки в памяти — вместо базы."""
    def __init__(self):
        self.store = {}

    async def get_setting(self, key):
        return self.store.get(key)

    async def set_setting(self, key, value):
        self.store[key] = value


@pytest.fixture
def память(monkeypatch):
    m = Память()
    monkeypatch.setattr(palmira.database, "get_setting", m.get_setting)
    monkeypatch.setattr(palmira.database, "set_setting", m.set_setting)
    return m


def имена(rows):
    return [r["name"] for r in rows]


def test_первое_обращение_кладёт_всю_заготовку(память):
    rows = asyncio.run(palmira.queue())
    assert имена(rows) == palmira.SEED


def test_дописанное_в_заготовку_доезжает_позже(память, monkeypatch):
    """Ровно тот случай, из-за которого список вышел неполным."""
    monkeypatch.setattr(palmira, "SEED", ["Первый", "Второй"])
    asyncio.run(palmira.queue())

    monkeypatch.setattr(palmira, "SEED", ["Первый", "Второй", "Третий"])
    rows = asyncio.run(palmira.queue())

    assert имена(rows) == ["Первый", "Второй", "Третий"]


def test_имя_не_предлагается_дважды(память, monkeypatch):
    monkeypatch.setattr(palmira, "SEED", ["Первый"])
    asyncio.run(palmira.queue())
    rows = asyncio.run(palmira.queue())
    assert имена(rows) == ["Первый"]


def test_убранное_имя_не_возвращается(память, monkeypatch):
    """Иначе отклонённый человек всплывал бы при каждом заходе, и
    убрать его было бы нельзя вообще."""
    monkeypatch.setattr(palmira, "SEED", ["Первый", "Второй"])
    asyncio.run(palmira.queue())

    # Владелица убрала второго из очереди.
    asyncio.run(palmira._save(palmira.QUEUE_KEY, [{"name": "Первый"}]))

    rows = asyncio.run(palmira.queue())
    assert имена(rows) == ["Первый"]


def test_подтверждённое_имя_в_очередь_не_возвращается(память, monkeypatch):
    monkeypatch.setattr(palmira, "SEED", ["Первый", "Второй"])
    asyncio.run(palmira.queue())
    asyncio.run(palmira._save(palmira.QUEUE_KEY, []))
    asyncio.run(palmira._save(palmira.ROSTER_KEY, [{"name": "Первый"},
                                                   {"name": "Второй"}]))
    assert asyncio.run(palmira.queue()) == []
