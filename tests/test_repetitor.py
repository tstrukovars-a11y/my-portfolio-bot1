"""Репетитор: объяснить то, что написано, а понятнее не стало.

Человек читает свою тетрадь и не понимает. Почерк тут ни при чём, и
первая версия раздела путала эти две задачи: в ней стояло правило
«объясняй только то, что на странице». В лекции записано сжато,
непонятное место на той же странице не объясняется никогда — и правило
запрещало ровно то, ради чего сюда приходят.

Поэтому тесты сторожат границу, а не запрет. Смысл объясняется шире
конспекта; величины берутся из конспекта. Третье, что они сторожат, —
чужой счёт: раздел ходит в модель, и открытый вход означает, что за
чужую учёбу платит владелица.
"""
import asyncio

import config
import repetitor


def run(coro):
    return asyncio.run(coro)


# --- граница: смысл свободно, величины строго --------------------------

def test_промпт_разрешает_объяснять_шире_конспекта():
    """Главный тест файла. Запрет выходить за страницу выглядит
    осторожным, а на деле запрещает единственное, зачем сюда приходят:
    в лекции записано сжато, и непонятное место на той же странице не
    объясняется."""
    low = repetitor.PROMPT.lower()
    assert "шире конспекта" in low
    assert "примеры" in low


def test_промпт_держит_величины_в_конспекте():
    low = repetitor.PROMPT.lower()
    assert "только если они есть в присланном" in low
    assert "по памяти не называй" in low


def test_промпт_называет_причину_а_не_просто_запрещает():
    """Запрет без причины живёт до первой переформулировки."""
    low = repetitor.PROMPT.lower()
    assert "бюджетного кодекса" in low
    assert "меняются год от года" in low


def test_в_промпте_граница_показана_примером():
    """«Смысл свободно, величины строго» — правило, которое легко понять
    наоборот. Пара «дотация/субвенция» против норматива показывает, где
    именно проходит черта."""
    low = repetitor.PROMPT.lower()
    assert "субвенции" in low and "от года не зависит" in low
    assert "норматив" in low and "зависит" in low


def test_промпт_ищет_пробел_а_не_отвечает_буквально():
    """Непонятно обычно не то место, о котором спрашивают, а то, на
    которое оно опирается."""
    low = repetitor.PROMPT.lower()
    assert "пробел" in low
    assert "более раннего понятия" in low


def test_про_почерк_осталась_одна_строка():
    """Фотография здесь — способ не перепечатывать, а не задача
    распознавания. Но нечитаемое слово всё равно нельзя угадывать."""
    low = repetitor.PROMPT.lower()
    assert "не угадывай" in low


def test_приветствие_зовёт_спрашивать_а_не_фотографировать():
    """Человек приходит с вопросом, а не со страницей. Первая строка
    экрана решает, с чем он сюда придёт в следующий раз."""
    first = repetitor.HELLO.split("\n\n")[1]
    assert "спросите" in first.lower()
    assert "конспекта" in repetitor.HELLO


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


def test_модель_не_понижена_молча():
    """Здесь объясняют то, что человек уже прочитал и не понял. Это не
    пересказ страницы, а поиск пробела — и дешёвая модель пересказывает
    вместо того, чтобы объяснить."""
    assert repetitor.MODEL == "claude-opus-5-5"
