#  fsm_storage.py — состояния диалогов живут в базе, а не в памяти.
#
#  ЗАЧЕМ. Dispatcher() без аргументов берёт хранилище в памяти процесса.
#  На Render процесс перезапускается при каждом деплое и засыпает в
#  простое — и вместе с ним исчезают ВСЕ незаконченные диалоги. Человек
#  отвечает на четвёртый вопрос, в эту минуту выходит деплой, и его
#  следующее сообщение не подходит ни к одному шагу: бот молчит, а
#  выглядит это как поломка опросника.
#
#  Молча — и есть худшее здесь. Ни ошибки, ни подсказки: диалог просто
#  обрывается на середине, и человек не знает, что делать.
#
#  Касается не только анкеты про встречи: так же устроены заполнение
#  конкурса, книги, планировщик — всё, где есть состояние.

import json
import logging

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

import database

TABLE = "fsm_states"


async def ensure_table() -> None:
    """Создать таблицу состояний. Зовётся при запуске, до диспетчера."""
    pool = await database.get_pool()
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {database.SCHEMA}.{TABLE} (
            key TEXT PRIMARY KEY,
            state TEXT,
            data TEXT NOT NULL DEFAULT '{{}}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")


def _key(key: StorageKey) -> str:
    """Один ключ на пару «чат и человек» — как в хранилище aiogram."""
    return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.destiny}"


# ПАМЯТЬ ВПЕРЕДИ БАЗЫ — и это не ускорение ради ускорения.
#
# aiogram спрашивает состояние у КАЖДОГО обновления, а у большинства
# людей его нет вовсе. Ходить за этим в базу по четыре раза на сообщение
# нельзя: пул здесь на три соединения, и он общий с утренним сбором
# новостей. В первое же утро после переезда состояний в базу выпуск
# остался без новостей и без генетики — запросы не дождались
# соединения.
#
# Поэтому: читаем из памяти, в базу идём только при промахе (после
# перезапуска) и при записи. Память переживает запросы, база —
# перезапуск; вместе они дают то, что нужно.
_cache = {}
CACHE_LIMIT = 5000      # примерно на столько людей хватит одного процесса


def _remember(key: str, state=None, data=None) -> None:
    kept = _cache.get(key) or {"state": None, "data": {}}
    if state is not Ellipsis:
        kept["state"] = state
    if data is not Ellipsis:
        kept["data"] = data
    if key not in _cache and len(_cache) >= CACHE_LIMIT:
        # Переполнение памяти страшнее промаха: самый старый ключ
        # уходит, а понадобится — прочитается из базы.
        _cache.pop(next(iter(_cache)), None)
    _cache[key] = kept


class PgStorage(BaseStorage):
    """Хранилище состояний в Postgres.

    Падать не имеет права: сбой записи состояния не должен ронять
    обработчик, иначе человек получит молчание вместо ответа. Поэтому
    ошибки пишутся в лог, а диалог продолжается — пусть и без памяти.
    """

    async def set_state(self, key: StorageKey, state=None) -> None:
        name = state.state if isinstance(state, State) else state
        _remember(_key(key), state=name, data=Ellipsis)
        pool = await database.get_pool()
        if not pool:
            return
        try:
            async with pool.acquire() as conn:
                if name is None:
                    # Снятие состояния данные НЕ трогает: aiogram
                    # очищает их отдельным вызовом, и затереть их здесь
                    # значит потерять то, что ещё понадобится.
                    await conn.execute(
                        f"UPDATE {database.SCHEMA}.{TABLE} "
                        f"SET state = NULL, updated_at = NOW() WHERE key = $1",
                        _key(key))
                else:
                    await conn.execute(
                        f"""INSERT INTO {database.SCHEMA}.{TABLE}
                            (key, state) VALUES ($1, $2)
                            ON CONFLICT (key) DO UPDATE SET
                                state = EXCLUDED.state, updated_at = NOW()""",
                        _key(key), name)
        except Exception as e:
            logging.warning(f"Состояние не сохранилось: {e}")

    async def get_state(self, key: StorageKey):
        name = _key(key)
        if name in _cache:
            return _cache[name]["state"]
        await self._load(name)
        return _cache.get(name, {}).get("state")

    async def set_data(self, key: StorageKey, data: dict) -> None:
        _remember(_key(key), state=Ellipsis, data=dict(data or {}))
        pool = await database.get_pool()
        if not pool:
            return
        try:
            # default=str: в данные диалога иногда попадает дата, а
            # json её не умеет. Потерять шаг из-за этого нельзя.
            payload = json.dumps(data or {}, ensure_ascii=False, default=str)
            async with pool.acquire() as conn:
                await conn.execute(
                    f"""INSERT INTO {database.SCHEMA}.{TABLE}
                        (key, data) VALUES ($1, $2)
                        ON CONFLICT (key) DO UPDATE SET
                            data = EXCLUDED.data, updated_at = NOW()""",
                    _key(key), payload)
        except Exception as e:
            logging.warning(f"Данные диалога не сохранились: {e}")

    async def get_data(self, key: StorageKey) -> dict:
        name = _key(key)
        if name not in _cache:
            await self._load(name)
        return dict(_cache.get(name, {}).get("data") or {})

    async def _load(self, name: str) -> None:
        """Промах памяти — один поход в базу, и больше по этому ключу
        мы туда не ходим. Промахи случаются только после перезапуска."""
        pool = await database.get_pool()
        if not pool:
            _remember(name, state=None, data={})
            return
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"SELECT state, data FROM {database.SCHEMA}.{TABLE} "
                    f"WHERE key = $1", name)
            _remember(name,
                      state=row["state"] if row else None,
                      data=json.loads(row["data"]) if row and row["data"] else {})
        except Exception as e:
            logging.warning(f"Состояние не прочиталось: {e}")
            _remember(name, state=None, data={})

    async def close(self) -> None:
        """Пул закрывает сам database — здесь закрывать нечего."""
        return None


async def forget_old(days: int = 7) -> int:
    """Убрать заброшенные диалоги.

    Человек начал заполнять и ушёл — его состояние будет ждать вечно и
    однажды поймает его на ровном месте: он напишет боту что-то другое,
    а попадёт в четвёртый вопрос полугодовой давности.
    """
    pool = await database.get_pool()
    if not pool:
        return 0
    try:
        async with pool.acquire() as conn:
            status = await conn.execute(
                f"DELETE FROM {database.SCHEMA}.{TABLE} "
                f"WHERE updated_at < NOW() - ($1 || ' days')::interval",
                str(int(days)))
        # И из памяти тоже: иначе забытый диалог останется жить в
        # процессе и поймает человека, хотя в базе его уже нет.
        _cache.clear()
        return int(status.rsplit(" ", 1)[-1]) if status else 0
    except Exception as e:
        logging.warning(f"Старые состояния не убрались: {e}")
        return 0
