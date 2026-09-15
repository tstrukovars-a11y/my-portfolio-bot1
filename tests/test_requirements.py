# Закреплённые версии.
#
# Смысл закрепления в том, чтобы сборка не менялась сама. Проверяем два
# условия: у каждой зависимости стоит точный номер и он совпадает с тем,
# что реально установлено.
import importlib.metadata as metadata
from pathlib import Path

import pytest

REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements.txt"


def _pinned():
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            yield line


def test_every_dependency_has_an_exact_version():
    loose = [line for line in _pinned() if "==" not in line]
    assert not loose, f"без точной версии: {loose}"


@pytest.mark.parametrize("line", list(_pinned()))
def test_pinned_version_is_the_one_installed(line):
    name, version = line.split("==")
    assert metadata.version(name) == version
