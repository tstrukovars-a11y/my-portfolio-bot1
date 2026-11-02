# Управление содержимым кнопками. Два свойства важнее остальных: чужой
# сюда не попадает, и в общем чате этих экранов нет вовсе.
import asyncio

import owner
import public


def run(coro):
    return asyncio.run(coro)


class _Call:
    def __init__(self, user_id, data=""):
        self.from_user = type("U", (), {"id": user_id})()
        self.data = data
        self.answered = False
        self.said = []

    async def answer(self, *a, **kw):
        self.answered = True

    @property
    def message(self):
        call = self

        class _M:
            async def answer(self, text, **kw):
                call.said.append(text)
        return _M()


def test_a_stranger_sees_nothing(monkeypatch):
    """Кнопку рисуем только владелице, но callback_data видно в клиенте
    и повторить её ничего не стоит."""
    import config
    monkeypatch.setattr(config, "ADMIN_ID", 777)

    call = _Call(999)
    run(owner.open_menu(call))
    assert call.said == [], "чужому показали служебный экран"

    call = _Call(777)
    run(owner.open_menu(call))
    assert call.said, "владелице экран не открылся"


def test_the_owner_screens_never_open_in_a_group():
    """Служебное не «доступно только ей», а не появляется в общем чате
    вовсе. Держится это тем, что ничего из owner.py не внесено в список
    разрешённого."""
    for mark in ("own_menu", "own_pub", "ownpub_", "ownt_", "own_set"):
        assert not any(mark.startswith(ok) or ok.startswith(mark)
                       for ok in public.PUBLIC_OK), \
            f"{mark} пролез в общий чат"


def test_the_publish_screen_is_built_from_the_schedule():
    """Список разделов не переписан руками: появится новый слот —
    появится и кнопка, без правки этого файла."""
    import digest
    marks = [b.callback_data for row in owner.pub_kb().inline_keyboard
             for b in row]
    for _, slot, _ in digest.SCHEDULE:
        assert f"ownpub_{slot}" in marks, f"слот {slot} потерялся"


def test_every_button_leads_somewhere_known():
    """Кнопка, ведущая в несуществующий экран, молчит при нажатии — и
    понять это можно только нажав."""
    known = {"own_today", "own_pub", "own_tennis", "own_set", "own_menu",
             "go_home",
             "admin_content", "admin_art", "admin_books", "admin_plan",
             "planstock", "admin_panel"}
    marks = [b.callback_data for row in owner.menu_kb().inline_keyboard
             for b in row]
    assert set(marks) <= known, f"некуда вести: {set(marks) - known}"


def test_the_preview_picks_what_the_publisher_would_pick(monkeypatch):
    """Экран «что выйдет» обязан совпадать с тем, что уйдёт в канал.
    Иначе он не предупреждает об ошибке, а прячет её."""
    import digest
    import database

    calls = {}

    async def candidates(section, limit=12):
        calls[section] = True
        return [11, 12] if section == "books" else []

    async def build(section, item_id):
        return (f"Книга {item_id}", "текст", None)

    async def art_next():
        return {"title": "Кои"}

    monkeypatch.setattr(database, "next_candidates", candidates)
    monkeypatch.setattr(database, "art_next_unannounced", art_next)
    monkeypatch.setattr(digest, "_build", build)
    monkeypatch.setattr(digest, "readiness",
                        lambda section, built: "" if built[0] == "Книга 11"
                        else "нет фотографии")

    lines, buttons = run(owner._today_lines())
    assert any("Книга 11" in x for x in lines), "первый пригодный не выбран"
    assert any("Книга 12" in x for x in lines) is False, \
        "показан тот, кто не пройдёт проверку готовности"
    assert ("ce_open_books_11" in [data for _, data in buttons]), \
        "строку нельзя открыть на правку"
    assert any("Кои" in x for x in lines), "картина дня не показана"
