"""Состояния диалогов переживают перезапуск (fsm_storage.py).

Dispatcher() без аргументов держит их в памяти процесса. На Render
процесс перезапускается при каждом деплое — и все незаконченные диалоги
исчезают: человек отвечает на четвёртый вопрос, выходит деплой, и его
следующее сообщение не подходит ни к одному шагу. Бот молчит, а
выглядит это как поломка опросника.

Молчание и есть худшее: ни ошибки, ни подсказки.
"""

import asyncio
import inspect
import json

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

import fsm_storage


KEY = StorageKey(bot_id=1, chat_id=2, user_id=3)


def test_it_is_a_real_aiogram_storage():
    assert issubclass(fsm_storage.PgStorage, BaseStorage)


def test_nothing_abstract_is_left_unimplemented():
    """Иначе aiogram упадёт при создании, а не при первом диалоге."""
    for name, member in inspect.getmembers(BaseStorage, inspect.isfunction):
        if getattr(member, "__isabstractmethod__", False):
            assert hasattr(fsm_storage.PgStorage, name), name
    fsm_storage.PgStorage()        # создаётся без ошибок


def test_the_key_separates_different_people():
    a = fsm_storage._key(StorageKey(bot_id=1, chat_id=2, user_id=3))
    b = fsm_storage._key(StorageKey(bot_id=1, chat_id=2, user_id=4))
    assert a != b


def test_the_key_separates_different_chats():
    a = fsm_storage._key(StorageKey(bot_id=1, chat_id=2, user_id=3))
    b = fsm_storage._key(StorageKey(bot_id=1, chat_id=9, user_id=3))
    assert a != b


def test_a_missing_database_does_not_raise(monkeypatch):
    """Сбой хранилища не должен ронять обработчик: человек получит
    молчание вместо ответа, а это и есть исходная поломка."""
    monkeypatch.setattr(fsm_storage.database, "get_pool",
                        lambda: asyncio.sleep(0, result=None))
    storage = fsm_storage.PgStorage()
    assert asyncio.run(storage.get_state(KEY)) is None
    assert asyncio.run(storage.get_data(KEY)) == {}
    asyncio.run(storage.set_state(KEY, "Filling:note"))
    asyncio.run(storage.set_data(KEY, {"a": 1}))


def test_clearing_the_state_keeps_the_data():
    """aiogram очищает данные отдельным вызовом. Затереть их здесь
    значит потерять то, что ещё понадобится."""
    body = inspect.getsource(fsm_storage.PgStorage.set_state)
    assert "SET state = NULL" in body
    assert "data" not in body.split("SET state = NULL")[1].split("else")[0]


def test_a_state_object_is_stored_by_its_name():
    body = inspect.getsource(fsm_storage.PgStorage.set_state)
    assert "isinstance(state, State)" in body


def test_dates_do_not_break_the_data():
    """В данные диалога иногда попадает дата, а json её не умеет.
    Потерять шаг из-за этого нельзя."""
    body = inspect.getsource(fsm_storage.PgStorage.set_data)
    assert "default=str" in body


def test_abandoned_dialogues_are_forgotten():
    """Человек начал и ушёл: иначе состояние поймает его через полгода
    на ровном месте — он напишет боту другое, а попадёт в четвёртый
    вопрос прошлой зимы."""
    assert "DELETE FROM" in inspect.getsource(fsm_storage.forget_old)


def test_the_dispatcher_falls_back_to_memory():
    """База не поднялась — бот должен запуститься всё равно."""
    import pathlib
    body = pathlib.Path("main.py").read_text()
    assert "Dispatcher(storage=fsm_storage.PgStorage())" in body
    assert "dp = Dispatcher()" in body


# ---------------------------------------------------------------------
# Память впереди базы
# ---------------------------------------------------------------------
#
# aiogram спрашивает состояние у КАЖДОГО обновления, а у большинства
# людей его нет. Пул здесь на три соединения и общий с утренним сбором
# новостей: в первое же утро после переезда состояний в базу выпуск
# остался без новостей и без генетики — запросы не дождались соединения.


class _CountingPool:
    def __init__(self):
        self.trips = 0

        class Conn:
            async def fetchrow(_s, *a):
                self.trips += 1
                return None

            async def execute(_s, *a):
                self.trips += 1
                return "OK"

        class Acq:
            async def __aenter__(_s):
                return Conn()

            async def __aexit__(_s, *a):
                return False

        self._acq = Acq

    def acquire(self):
        return self._acq()


def _with_pool(monkeypatch):
    pool = _CountingPool()
    monkeypatch.setattr(fsm_storage.database, "get_pool",
                        lambda: asyncio.sleep(0, result=pool))
    fsm_storage._cache.clear()
    return pool


def test_repeated_updates_do_not_hit_the_database(monkeypatch):
    """Главная причина утренней поломки: по четыре запроса на каждое
    сообщение при пуле из трёх соединений."""
    pool = _with_pool(monkeypatch)
    storage = fsm_storage.PgStorage()
    for _ in range(20):
        asyncio.run(storage.get_state(KEY))
        asyncio.run(storage.get_data(KEY))
    assert pool.trips == 1, "промах должен быть один, после перезапуска"


def test_a_saved_state_is_read_from_memory(monkeypatch):
    pool = _with_pool(monkeypatch)
    storage = fsm_storage.PgStorage()
    asyncio.run(storage.set_state(KEY, "Filling:note"))
    before = pool.trips
    for _ in range(5):
        assert asyncio.run(storage.get_state(KEY)) == "Filling:note"
    assert pool.trips == before, "чтение из памяти не должно ходить в базу"


def test_writing_still_reaches_the_database(monkeypatch):
    """Память переживает запросы, база — перезапуск. Нужно и то и другое."""
    pool = _with_pool(monkeypatch)
    storage = fsm_storage.PgStorage()
    asyncio.run(storage.set_state(KEY, "Filling:years"))
    assert pool.trips >= 1


def test_data_survives_in_memory_between_calls(monkeypatch):
    _with_pool(monkeypatch)
    storage = fsm_storage.PgStorage()
    asyncio.run(storage.set_data(KEY, {"match_id": "42"}))
    assert asyncio.run(storage.get_data(KEY)) == {"match_id": "42"}


def test_the_cache_does_not_grow_without_bound():
    """Переполнение памяти страшнее промаха."""
    assert fsm_storage.CACHE_LIMIT > 0
    body = inspect.getsource(fsm_storage._remember)
    assert "CACHE_LIMIT" in body


def test_forgetting_clears_memory_too():
    """Иначе забытый диалог останется жить в процессе и поймает
    человека, хотя в базе его уже нет."""
    assert "_cache.clear()" in inspect.getsource(fsm_storage.forget_old)
