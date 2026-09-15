# Счётчик переходов — единственное место, где бот выступает
# перенаправителем. Без подписи по его адресу можно было бы уводить куда
# угодно, поэтому проверяем именно отказы, а не только удачный путь.
from urllib.parse import quote

from conftest import run

import links


def test_signature_is_stable():
    url = "https://www.litres.ru/book/a/?lfrom=1"
    assert links.sign(url) == links.sign(url)
    assert links.verify(url, links.sign(url))


def test_signature_belongs_to_one_url():
    mine = "https://www.litres.ru/book/a/"
    other = "https://evil.example/phishing"
    assert not links.verify(other, links.sign(mine))


def test_forged_signature_is_refused():
    url = "https://www.litres.ru/book/a/"
    code, _ = run(links.handle({"u": quote(url, safe=""), "h": "0" * 16}))
    assert code == 403


def test_foreign_url_without_signature_is_refused():
    code, _ = run(links.handle({"u": quote("https://evil.example", safe="")}))
    assert code == 403


def test_non_http_is_refused():
    code, _ = run(links.handle({"u": quote("javascript:alert(1)", safe=""),
                                "h": links.sign("javascript:alert(1)")}))
    assert code == 400


def test_signed_url_redirects(monkeypatch):
    url = "https://www.litres.ru/book/a/?lfrom=1"
    seen = {}

    async def click(link, section, title):
        seen.update(link=link, section=section, title=title)

    monkeypatch.setattr(links, "click", click)
    code, target = run(links.handle({
        "u": quote(url, safe=""), "h": links.sign(url),
        "s": "books", "t": quote("Книга", safe="")}))

    assert (code, target) == (302, url)
    assert seen["section"] == "books"


def test_click_is_not_fatal(monkeypatch):
    """Упавший счётчик не должен ломать переход: человек идёт покупать."""
    url = "https://www.litres.ru/book/a/"

    async def boom(*_args):
        raise RuntimeError("база лежит")

    monkeypatch.setattr(links, "click", boom)
    code, target = run(links.handle({"u": quote(url, safe=""),
                                     "h": links.sign(url)}))
    assert (code, target) == (302, url)


def test_wrap_and_unwrap(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://bot.onrender.com")
    url = "https://www.litres.ru/book/a/?lfrom=1"
    wrapped = links.wrap(url, "books", "Книга")
    assert wrapped.startswith("https://bot.onrender.com/go?")
    assert links.unwrap(wrapped) == url


def test_wrap_without_external_address_returns_url(monkeypatch):
    """Без внешнего адреса кнопка обязана остаться рабочей."""
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    url = "https://www.litres.ru/book/a/"
    assert links.wrap(url, "books", "Книга") == url


def test_host_of_drops_www():
    assert links.host_of("https://www.litres.ru/book/a/") == "litres.ru"
