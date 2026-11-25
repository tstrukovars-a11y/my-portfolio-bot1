"""Моменты с корта — три дня подряд, одним оформлением.

Пересылать чужой пост нельзя: «Акцент» не лента перепечаток. А
набирать подпись руками каждый раз значит писать по-разному — то с
названием турнира, то без.
"""

import palmira


class Фото:
    def __init__(self, file_id):
        self.file_id = file_id


class Сообщение:
    video = animation = photo = None
    caption = ""


def test_подпись_всегда_начинается_турниром():
    """Читатель видит ролик в ленте среди прочего и должен понять, что
    это, не открывая комментарии."""
    текст = palmira.highlight_caption("Бублик достал невозможный мяч")
    assert текст.startswith("🎾")
    assert palmira.TOURNAMENT in текст
    assert "Бублик достал невозможный мяч" in текст


def test_без_подписи_пост_всё_равно_собирается():
    """На корте некогда писать. Ролик с одним названием турнира лучше,
    чем неопубликованный ролик."""
    текст = palmira.highlight_caption("")
    assert palmira.TOURNAMENT in текст
    assert текст.count("\n") == 0, "лишних пустых строк быть не должно"


def test_видео_фото_и_гифка_распознаются():
    for поле, вид in (("video", "video"), ("photo", "photo"),
                      ("animation", "animation")):
        m = Сообщение()
        setattr(m, поле, [Фото("abc")] if поле == "photo" else Фото("abc"))
        assert palmira._media_of(m) == (вид, "abc"), поле


def test_текст_без_вложения_не_принимается():
    """Иначе в канал ушёл бы пост-пустышка с одним названием турнира."""
    assert palmira._media_of(Сообщение()) == (None, None)


def test_каждому_виду_есть_чем_отправить():
    """Пропущенный вид уронил бы публикацию в момент, когда до матча
    минуты."""
    for вид in ("video", "photo", "animation", "video_note"):
        assert вид in palmira.MEDIA_SENDERS


def test_кнопка_хайлайта_есть_в_кабинете():
    import asyncio
    marks = [b.callback_data for row in asyncio.run(palmira.home_kb()).inline_keyboard
             for b in row]
    assert "pal_hl" in marks
