"""Расписание дня и запись трансляции.

Два поста, которые нужны каждый день турнира, а не один раз. Утром —
к какому часу ехать, вечером — где посмотреть то, что пропустил.

Расписание берётся из той же программы, что и общий анонс: две копии
одних и тех же времён разошлись бы на первой же правке афиши, и
разошлись бы молча.
"""
import asyncio
from datetime import datetime, timezone

import palmira


def run(coro):
    return asyncio.run(coro)


def clock(monkeypatch, day: int):
    import digest

    async def now():
        return datetime(2026, 11, day, 9, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(digest, "_local_now", now)


# --- день --------------------------------------------------------------

def test_в_программе_есть_все_три_дня():
    assert [palmira.day_number(t) for t, _ in palmira.PROGRAMME] == [27, 28, 29]


def test_берётся_именно_сегодняшний_день(monkeypatch):
    clock(monkeypatch, 28)
    title, rows = run(palmira.today_programme())
    assert palmira.day_number(title) == 28
    assert any("Мутэ" in r for r in rows), rows


def test_вне_турнира_дня_нет(monkeypatch):
    """Кнопка остаётся на экране и после турнира. Пустое расписание
    лучше вчерашнего: по вчерашнему люди приедут не к тому матчу."""
    clock(monkeypatch, 30)
    assert run(palmira.today_programme()) is None


def test_день_берётся_по_часам_читателя(monkeypatch):
    """Render живёт по UTC. В три часа ночи по Москве у него ещё
    вчерашнее число — и в канал ушло бы расписание прошедшего дня."""
    import digest
    import inspect

    source = inspect.getsource(palmira.today_programme)
    assert "_local_now" in source
    assert hasattr(digest, "_local_now")


# --- текст -------------------------------------------------------------

def test_в_посте_дня_только_его_матчи(monkeypatch):
    """Три дня сразу человек не читает: ему нужен сегодняшний час."""
    clock(monkeypatch, 28)
    text = palmira.today_text(*run(palmira.today_programme()))
    assert "12:30" in text and "18:15" in text
    assert "29 ноября" not in text
    assert "27 ноября" not in text


def test_сноска_только_там_где_есть_что_объяснять(monkeypatch):
    """«Б.О.Д — будет объявлено далее» под днём без единого «Б.О.Д»
    заставляет искать глазами то, чего на экране нет."""
    clock(monkeypatch, 28)
    second = palmira.today_text(*run(palmira.today_programme()))
    assert "будет объявлено" not in second

    clock(monkeypatch, 29)
    third = palmira.today_text(*run(palmira.today_programme()))
    assert "Б.О.Д" in third and "будет объявлено" in third


def test_в_посте_дня_есть_место(monkeypatch):
    """Время без адреса — не расписание, а список."""
    clock(monkeypatch, 28)
    text = palmira.today_text(*run(palmira.today_programme()))
    assert "Арена" in text


def test_расписание_второго_дня_совпадает_с_афишей(monkeypatch):
    """Афиша сильнее наших догадок: по ней люди приходят к корту.
    Предварительная программа расходилась с ней в трёх местах."""
    clock(monkeypatch, 28)
    _, rows = run(palmira.today_programme())
    joined = "\n".join(rows)
    assert "12:30 — Рахимова — Шнайдер" in joined
    assert "14:00 — Мутэ — Хачанов" in joined
    assert "18:15" in joined, "парный сдвинулся с 19:00"
    assert "Б.О.Д" not in joined, "второй день раскрыт целиком"


# --- кнопки ------------------------------------------------------------

def test_кнопка_расписания_есть_в_кабинете(monkeypatch):
    async def nothing():
        return []

    monkeypatch.setattr(palmira, "queue", nothing)
    monkeypatch.setattr(palmira, "roster", nothing)
    marks = [b.callback_data for row in run(palmira.home_kb()).inline_keyboard
             for b in row]
    assert "pal_today" in marks


# --- ссылка на запись ---------------------------------------------------

class _Msg:
    def __init__(self, text=None, caption=None):
        self.text = text
        self.caption = caption


def test_ссылка_узнаётся_в_тексте():
    link = "https://vkvideo.ru/video-106491292_456241335"
    assert palmira._link_in(_Msg(text=f"запись первого дня {link}")) == link


def test_ссылка_узнаётся_в_подписи_к_фото():
    link = "https://example.com/x"
    assert palmira._link_in(_Msg(caption=f"вот {link}")) == link


def test_голый_текст_ссылкой_не_считается():
    """Запись у источника — это ссылка. Текст без неё — просто текст, и
    моментом с корта он не становится."""
    assert palmira._link_in(_Msg(text="сегодня было жарко")) == ""
    assert palmira._link_in(_Msg()) == ""


def test_подпись_к_ссылке_начинается_с_турнира():
    """Та же шапка, что у видео: пост узнаётся по первой строке."""
    caption = palmira.highlight_caption("Запись первого дня")
    assert caption.startswith("🎾")
    assert palmira.TOURNAMENT in caption


# --- куда уходят посты --------------------------------------------------

class _Chat:
    def __init__(self, title=None, username=None):
        self.title = title
        self.username = username


class _Bot:
    def __init__(self, chat=None, fail=False):
        self._chat = chat
        self._fail = fail

    async def get_chat(self, chat_id):
        if self._fail:
            raise RuntimeError("нет доступа")
        return self._chat


def test_адрес_называется_именем_канала(settings, monkeypatch):
    """Отчёт «список опубликован» без адреса подтверждает только, что код
    отработал. Человек читает его как «пост вышел» — и узнаёт правду из
    пустого канала."""
    import digest

    async def target():
        return (-100500, None)

    monkeypatch.setattr(digest, "_target", target)
    text = run(palmira.where_text(_Bot(_Chat(title="Акцент"))))
    assert "Акцент" in text


def test_без_канала_так_и_сказано(settings, monkeypatch):
    import digest

    async def target():
        return (None, None)

    monkeypatch.setattr(digest, "_target", target)
    assert "не задан" in run(palmira.where_text(_Bot()))


def test_если_имя_не_прочиталось_остаётся_номер(settings, monkeypatch):
    """Молчать нельзя и тут: номер хуже имени, но лучше пустоты."""
    import digest

    async def target():
        return (-100500, None)

    monkeypatch.setattr(digest, "_target", target)
    assert "100500" in run(palmira.where_text(_Bot(fail=True)))


def test_адрес_виден_в_кабинете_до_нажатия(settings, monkeypatch):
    """После нажатия узнавать поздно: пост уже ушёл."""
    import digest

    async def target():
        return (-100500, None)

    async def nothing():
        return []

    monkeypatch.setattr(digest, "_target", target)
    monkeypatch.setattr(palmira, "queue", nothing)
    monkeypatch.setattr(palmira, "roster", nothing)
    text = run(palmira.home_text(_Bot(_Chat(title="Акцент"))))
    assert "Публикую в" in text and "Акцент" in text
