"""Кнопка из канала открывает бота, а не рассказывает про него.

Раньше граница присылала копию кнопки в личку и показывала «Открыла у
вас в личке» — а человек должен был сам туда пойти. Половина не шла.
Это касается всех таких кнопок сразу: «Как это касается меня» под
новостями и генетикой в том числе.
"""

import inspect

import public


def test_the_boundary_answers_with_a_link():
    body = inspect.getsource(public.keep_private)
    assert "event.answer(url=url)" in body


def test_the_link_is_built_through_the_shared_resolver():
    """Имя бота доспрашивается у Telegram — настройка может быть пустой."""
    body = inspect.getsource(public.keep_private)
    assert "common.deep_link" in body


def test_a_closed_private_chat_still_gets_the_link():
    """Не писал боту — именно ссылка и нужна: по ней он туда попадёт."""
    body = inspect.getsource(public.keep_private)
    assert body.index("opened = False") < body.index("event.answer(url=url)")


def test_the_old_popups_remain_as_a_fallback():
    """Ссылку построить не из чего — тогда честнее надпись, чем
    нажатие, которое ничего не делает."""
    body = inspect.getsource(public.keep_private)
    assert "MOVED if opened else CLOSED" in body


def test_the_open_payload_does_not_spam_the_welcome():
    """Нужное сообщение в личке уже последнее. Приветствие и меню из
    восьми разделов спрятали бы то, ради чего человек нажал."""
    import common
    body = inspect.getsource(common.start_open)
    assert "personal.quiet" in body
