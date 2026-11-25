"""Пауза раздела.

Когда в канале три дня идёт турнир, генетика и путешествия между
репортажами с корта не читаются. Выключать их правкой сетки нельзя:
закомментированный раздел не возвращается сам, и через месяц никто не
вспомнит, почему его нет.

Тесты сторожат четыре свойства. Раздел на паузе молчит. Соседям он при
этом не мешает — иначе пауза одного гасила бы день целиком. Кнопка
«Опубликовать сейчас» выпускает его всё равно: пауза про сетку, а не про
запрет. И снимается она тем же нажатием, которым поставлена.
"""
import asyncio
from datetime import datetime, timezone

import digest


def run(coro):
    return asyncio.run(coro)


def at(hh: int, mm: int = 0):
    """Понедельник: на выходных утренний блок уезжает на час."""
    return datetime(2026, 11, 30, hh, mm, tzinfo=timezone.utc)


def clock(monkeypatch, hh: int, mm: int = 0):
    async def now():
        return at(hh, mm)
    monkeypatch.setattr(digest, "_local_now", now)


# --- список -----------------------------------------------------------

def test_пустая_настройка_это_пустой_список(settings):
    assert run(digest.paused_slots()) == set()


def test_пауза_переключается_одним_нажатием(settings):
    assert run(digest.toggle_pause("genetics")) is True
    assert run(digest.paused_slots()) == {"genetics"}
    assert run(digest.toggle_pause("genetics")) is False
    assert run(digest.paused_slots()) == set()


def test_опечатка_в_настройку_не_попадает(settings):
    """Иначе несуществующий раздел лежал бы в списке и выглядел как
    пауза: экран показывает его молчащим, а молчать нечему."""
    run(digest.set_paused({"genetics", "генетека"}))
    assert run(digest.paused_slots()) == {"genetics"}


# --- сетка ------------------------------------------------------------

def done_before(settings, hhmm: str):
    """Отметить вышедшим всё, чьё время раньше указанного."""
    for at_, slot, _ in digest.SCHEDULE:
        if at_ < hhmm:
            settings[f"digest_slot_{slot}"] = "2026-11-30"


def test_раздел_на_паузе_не_выходит_сам(settings, monkeypatch):
    clock(monkeypatch, 13, 10)                 # время генетики — 13:00
    done_before(settings, "13:00")
    assert run(digest._due_slot())[0] == "genetics"

    run(digest.set_paused({"genetics"}))
    assert run(digest._due_slot()) is None


def test_пауза_не_забирает_очередь_у_следующих(settings, monkeypatch):
    """Самое опасное здесь. Планировщик берёт самый поздний невышедший
    слот; если бы раздел на паузе считался невышедшим, он занимал бы эту
    позицию и глушил всё, что идёт после него."""
    clock(monkeypatch, 14, 40)                 # прошли и 13:00, и 14:30
    run(digest.set_paused({"genetics"}))
    assert run(digest._due_slot())[0] == "puzzle"


def test_соседи_по_сетке_не_трогаются(settings, monkeypatch):
    clock(monkeypatch, 16, 10)                 # путешествия — 16:00
    run(digest.set_paused({"genetics"}))
    assert run(digest._due_slot())[0] == "travel"


def test_уже_вышедшее_и_пауза_не_мешают_друг_другу(settings, monkeypatch):
    clock(monkeypatch, 16, 10)
    settings["digest_slot_travel"] = at(16, 10).strftime("%Y-%m-%d")
    run(digest.set_paused({"genetics"}))
    assert run(digest._due_slot())[0] == "puzzle"


# --- ручной выпуск ----------------------------------------------------

def test_кнопкой_раздел_выпускается_и_на_паузе(settings, monkeypatch):
    """Владелица нажала сама — значит хочет. Пауза убирает раздел из
    расписания, а не запрещает его."""
    clock(monkeypatch, 13, 10)
    run(digest.set_paused({"travel"}))

    seen = {}

    async def target():
        return (None, None)

    monkeypatch.setattr(digest, "_target", target)
    # Канал не задан — дальше выбора слота публикация не пойдёт, и это
    # всё, что здесь нужно: важно, что слот выбран, а не отвергнут.
    result = run(digest.publish_slot(object(), force="travel"))
    assert result == "канал не задан", result
    assert seen == {}
