# Проверки, которые ловят падения запуска.
#
# Две ошибки подряд уронили деплой: обращение к `bot` раньше его создания
# и локальный `import admin`, сделавший модуль локальным на всю функцию.
# Обе видны разбором кода, без запуска — и обе стоили по деплою.
import ast
import glob
import importlib
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULES = sorted(p.name[:-3] for p in ROOT.glob("*.py"))


def _tree(name: str) -> ast.Module:
    return ast.parse((ROOT / f"{name}.py").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    """Модуль обязан импортироваться: иначе бот не поднимется вовсе."""
    importlib.import_module(name)


@pytest.mark.parametrize("name", MODULES)
def test_no_local_import_shadows_a_module(name):
    """import внутри функции делает имя локальным на всю функцию.

    Из-за этого dp.include_router(admin.router) перестал видеть модуль,
    импортированный в начале файла, и запуск падал с UnboundLocalError.
    """
    tree = _tree(name)
    top = {a.asname or a.name.split(".")[0]
           for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
           for a in node.names}

    shadowed = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Import):
                for a in node.names:
                    local = a.asname or a.name.split(".")[0]
                    if local in top:
                        shadowed.append(f"{name}.py:{node.lineno} — {local}")
    assert not shadowed, "локальный import затеняет модуль: " + "; ".join(shadowed)


def test_bot_is_created_before_it_is_used():
    """Порядок в main(): объект бота нельзя трогать до создания."""
    tree = _tree("main")
    main = next(n for n in tree.body
                if isinstance(n, ast.AsyncFunctionDef) and n.name == "main")
    created = min(
        (n.lineno for n in ast.walk(main) if isinstance(n, ast.Assign)
         and any(isinstance(t, ast.Name) and t.id == "bot" for t in n.targets)),
        default=None)
    assert created, "в main() больше не создаётся бот — проверку надо обновить"

    used_earlier = [n.lineno for n in ast.walk(main)
                    if isinstance(n, ast.Name) and n.id == "bot"
                    and isinstance(n.ctx, ast.Load) and n.lineno < created]
    assert not used_earlier, f"обращение к боту в строках {used_earlier}"


def test_port_opens_before_the_slow_work():
    """Render ждёт открытого порта, а не готовности базы.

    Когда долгая часть шла первой, деплой минутами писал «No open ports
    detected» и мог не дождаться вовсе.
    """
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    main = next(n for n in tree.body
                if isinstance(n, ast.AsyncFunctionDef) and n.name == "main")

    port_line = next(i for i, line in enumerate(source.splitlines(), 1)
                     if "start_server" in line)
    slow = ("init_db", "banners.load", "tennis_rank.apply", "check_key")
    early = [n.lineno for n in ast.walk(main)
             if isinstance(n, ast.Await) and n.lineno < port_line
             and any(word in ast.unparse(n) for word in slow)]
    assert not early, f"долгая работа до открытия порта, строки {early}"


def test_every_router_is_included():
    """Роутер, забытый в include_router, молча отключает целый раздел."""
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    included = {line.split("include_router(")[1].split(".router")[0].strip()
                for line in source.splitlines() if "include_router(" in line}

    has_router = set()
    for name in MODULES:
        if name in ("main", "config"):
            continue
        text = (ROOT / f"{name}.py").read_text(encoding="utf-8")
        if "\nrouter = Router()" in text:
            has_router.add(name)

    forgotten = sorted(has_router - included)
    assert not forgotten, f"роутеры не подключены: {forgotten}"


def test_admin_buttons_have_handlers():
    """Кнопка без обработчика молчит при нажатии — и это незаметно."""
    import re

    import admin

    source = "\n".join((ROOT / f"{name}.py").read_text(encoding="utf-8")
                       for name in MODULES)
    for row in admin._admin_menu().inline_keyboard:
        for button in row:
            data = button.callback_data
            if not data:
                continue
            handled = (f'F.data == "{data}"' in source
                       or re.search(rf'F\.data\.startswith\(\s*"{data[:6]}',
                                    source))
            assert handled, f"кнопка «{button.text}» ({data}) без обработчика"
