"""В карточке конкурса видно, куда уйдёт объявление.

После репетиции у мероприятия остаётся свой закрытый канал, и по
карточке этого не было видно. Разница между «вышло в „Акценте“» и
«вышло в пустой репетиционный канал» обнаруживалась уже после нажатия.
"""

import asyncio

import pytest

import draws
import database


def card(event, monkeypatch):
    async def none(_):
        return []
    monkeypatch.setattr(database, "draw_prizes", none)
    monkeypatch.setattr(database, "draw_winners", none)
    return asyncio.run(draws._panel_text(event))


BASE = {"id": 1, "title": "Пальмира", "slug": "palmira", "status": "draft"}


def test_мероприятие_без_своего_канала_идёт_в_акцент(monkeypatch):
    text = card(dict(BASE), monkeypatch)
    assert "общий" in text and "Акцент" in text


def test_свой_канал_назван_и_помечен_как_не_акцент(monkeypatch):
    """Самый опасный случай: репетиция прошла, канал остался, а
    настоящий конкурс уходит в пустоту."""
    text = card(dict(BASE, channel_id=-1003667131485), monkeypatch)
    assert "-1003667131485" in text
    assert "не «Акцент»" in text


def test_день_мероприятия_виден(monkeypatch):
    """По нему расписание получает дату. Ошибка в дне — вопросы уйдут не
    в тот день, и заметить это можно только здесь."""
    text = card(dict(BASE, event_date="2026-11-28"), monkeypatch)
    assert "2026-11-28" in text
