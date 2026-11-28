"""Разбор лекции: объяснить то место, где человек встал.

Экзамен через три дня, и проверять тут надо не удобство, а две вещи, на
которых разбор может навредить сильнее, чем помочь.

Первая — выдуманная цифра. Государственные и муниципальные финансы это
нормативы, сроки и статьи Бюджетного кодекса; они меняются год от года,
модель помнит их на момент обучения и называет уверенно. Устаревший
норматив, принесённый на экзамен, хуже невыученного.

Вторая — чужой счёт. Раздел ходит в модель с картинками, и открытый вход
означает, что за чужую учёбу платит владелица.
"""
import asyncio

import config
import repetitor


def run(coro):
    return asyncio.run(coro)


# --- запрет на сочинительство ------------------------------------------

def test_промпт_велит_объяснять_написанное():
    low = repetitor.PROMPT.lower()
    assert "на этой странице этого нет" in low
    assert "не досочиняй" in low


def test_промпт_знает_про_меняющиеся_нормативы():
    """Это и есть причина запрета, а не общая осторожность. Без причины
    запрет в промпте живёт до первой переформулировки."""
    low = repetitor.PROMPT.lower()
    assert "бюджетного кодекса" in low
    assert "меняются" in low


def test_промпт_запрещает_угадывать_почерк():
    """Неверно прочитанный термин хуже пропущенного: пропущенный виден,
    а прочитанный неверно идёт на экзамен как знание."""
    low = repetitor.PROMPT.lower()
    assert "не угадывай" in low
    assert "неразборчиво" in low


def test_в_приветствии_сказано_то_же_самое():
    """Обещание «скажу, если на странице нет» должно стоять там, где его
    прочитают, а не только в системном промпте."""
    assert "нет" in repetitor.HELLO
    assert "фотограф" in repetitor.HELLO.lower()


# --- доступ -------------------------------------------------------------

def test_по_умолчанию_закрыто(settings):
    assert run(repetitor.allowed_ids()) == set()
    assert run(repetitor.may_use(555)) is False


def test_владелице_открыто_всегда(settings, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 777)
    assert run(repetitor.may_use(777)) is True


def test_разрешение_выдаётся_один_раз(settings):
    assert run(repetitor.allow(555)) is True
    assert run(repetitor.allow(555)) is False
    assert run(repetitor.may_use(555)) is True


def test_разрешение_переживает_перезапуск(settings):
    """Список лежит в настройке, а не в памяти процесса: деплой не должен
    отбирать доступ посреди подготовки к экзамену."""
    run(repetitor.allow(555))
    run(repetitor.allow(556))
    assert settings[repetitor.ALLOWED_KEY] == "555,556"
    assert run(repetitor.allowed_ids()) == {555, 556}


def test_мусор_в_настройке_не_открывает_доступ(settings):
    settings[repetitor.ALLOWED_KEY] = "555, не число, 556"
    assert run(repetitor.allowed_ids()) == {555, 556}


# --- страница -----------------------------------------------------------

class _Photo:
    def __init__(self, file_id):
        self.file_id = file_id


class _Doc:
    def __init__(self, file_id, mime):
        self.file_id = file_id
        self.mime_type = mime


class _Msg:
    def __init__(self, photo=None, document=None):
        self.photo = photo
        self.document = document


def test_берётся_самый_крупный_размер():
    """Мелкий почерк на превью не прочитать — ни модели, ни человеку."""
    message = _Msg(photo=[_Photo("мелкий"), _Photo("средний"), _Photo("крупный")])
    assert repetitor._photo_id(message) == "крупный"


def test_страница_файлом_тоже_страница():
    """Фотография, присланная без сжатия, приходит документом — и это
    как раз тот случай, когда почерк читается лучше всего."""
    assert repetitor._photo_id(_Msg(document=_Doc("скан", "image/jpeg"))) == "скан"


def test_не_картинка_страницей_не_считается():
    assert repetitor._photo_id(_Msg(document=_Doc("файл", "application/pdf"))) == ""
    assert repetitor._photo_id(_Msg()) == ""


# --- разговор -----------------------------------------------------------

def test_история_короче_чем_в_общем_разделе():
    """Страницы — это картинки, и они тяжёлые: длинный хвост здесь стоит
    денег за каждый следующий вопрос."""
    import block4_claude

    assert repetitor.HISTORY_TURNS < block4_claude.HISTORY_TURNS


def test_модель_выбрана_зрячая():
    """Рукопись читается не всякой моделью: это главное требование
    раздела, и понижать её ради цены нельзя молча."""
    assert repetitor.MODEL == "claude-opus-5-5"
