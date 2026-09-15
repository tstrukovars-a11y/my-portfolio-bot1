# Общая обвязка тестов.
#
# Модули бота читают окружение прямо при импорте, поэтому переменные
# выставляем до первого import. Настоящие ключи тестам не нужны и не
# должны быть нужны: всё, что здесь проверяется, работает без сети и без
# базы — иначе это уже не тест, а поход в интернет.
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/test")
os.environ.setdefault("ORGANIZER_TELEGRAM_ID", "1")

import pytest


@pytest.fixture
def settings(monkeypatch):
    """Подменяет настройки в базе обычным словарём.

    Половина проверяемых функций читает настройки: шаблоны магазинов,
    часовой пояс, имя бота. Настоящая база для этого не нужна, а без
    подмены тесты стучались бы в неё и падали по таймауту.
    """
    import asyncio
    import database

    store = {}

    async def get(key, default=None):
        return store.get(key, default if default is not None else "")

    async def put(key, value):
        store[key] = value
        return True

    monkeypatch.setattr(database, "get_setting", get)
    monkeypatch.setattr(database, "set_setting", put)
    return store


def run(coro):
    """Синхронная обёртка: без неё каждый тест тянул бы pytest-asyncio"""
    import asyncio
    return asyncio.run(coro)
