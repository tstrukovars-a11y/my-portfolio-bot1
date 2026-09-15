# Список команд собирается из кода. Проверяем, что он не врёт в обе
# стороны: показанного не существует или существующее не показано.
import re
from pathlib import Path

import pytest

import commands

ROOT = Path(__file__).resolve().parent.parent


def _all_listed():
    return [c for _, group in commands.collect() for c in group]


def test_something_is_found():
    assert len(_all_listed()) > 40


@pytest.mark.parametrize("command", _all_listed())
def test_listed_command_exists_in_code(command):
    """Показать несуществующую команду хуже, чем не показать редкую."""
    needle = command.lstrip("/")
    found = any(needle in path.read_text(encoding="utf-8")
                for path in ROOT.glob("*.py"))
    assert found, f"{command} в списке, но в коде его нет"


@pytest.mark.parametrize("command", ["/доход", "/погода", "/книга", "/todo",
                                     "/zvat", "/db", "/clicks", "/banner",
                                     "/tennis_test", "/book_links"])
def test_everyday_commands_are_listed(command):
    """Команды, которыми пользуются, обязаны быть в шпаргалке."""
    assert command in _all_listed()


def test_groups_point_at_existing_modules():
    for module, _ in commands.GROUPS:
        assert (ROOT / f"{module}.py").exists(), module


def test_screen_fits_a_telegram_message():
    assert len(commands.text()) <= 4096
