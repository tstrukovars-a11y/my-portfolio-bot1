# links.py — свой счётчик переходов по кнопкам.
#
# Партнёрская сеть показывает заказы, но только когда захочет и когда
# отдаст API. Клики можно считать самим: кнопка ведёт на наш адрес, мы
# записываем переход и тут же перенаправляем в магазин. Продажи так не
# увидеть, зато видно, что читают и по чему нажимают, — а это единственная
# цифра, которая доступна с первого дня и никем не выдаётся.
#
# Открытый редирект — дыра: по нашему адресу можно было бы уводить куда
# угодно, включая фишинг. Поэтому у каждой ссылки подпись, и без неё
# перенаправления не будет.
import hashlib
import hmac
import logging
import os
from urllib.parse import unquote_plus, urlencode, urlparse

import config
import database

SIG_LEN = 16


def _secret() -> bytes:
    """Тем же секретом подписан вебхук — отдельный заводить незачем"""
    raw = (os.getenv("WEBHOOK_SECRET") or os.getenv("BOT_TOKEN")
           or getattr(config, "BOT_TOKEN", "") or "advcake")
    return str(raw).encode("utf-8")


def sign(url: str) -> str:
    return hmac.new(_secret(), url.encode("utf-8"),
                    hashlib.sha256).hexdigest()[:SIG_LEN]


def verify(url: str, signature: str) -> bool:
    return hmac.compare_digest(sign(url), (signature or "").strip())


def base_url() -> str:
    return (os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")


def wrap(url: str, section: str = "", title: str = "") -> str:
    """Адрес нашего счётчика вместо прямой ссылки.

    Без известного внешнего адреса возвращаем ссылку как есть: считать
    переходы приятно, но ломать кнопку ради этого нельзя.
    """
    base = base_url()
    if not base or not url.startswith("http"):
        return url
    query = urlencode({"u": url, "s": section[:24], "t": title[:60],
                       "h": sign(url)})
    return f"{base}/go?{query}"


def unwrap(url: str) -> str:
    """Исходный адрес из ссылки счётчика — по нему считаются пометки"""
    if "/go?" not in (url or ""):
        return url
    from urllib.parse import parse_qs
    inner = parse_qs(urlparse(url).query).get("u") or []
    return inner[0] if inner else url


def host_of(url: str) -> str:
    return urlparse(url or "").netloc.lower().removeprefix("www.")


async def click(url: str, section: str, title: str):
    await database.add_click(section or "", host_of(url), title or "")


async def handle(query: dict):
    """(код ответа, заголовок Location или текст) для маршрута /go.

    Значения приходят как есть, в процентной кодировке: сервер разбирает
    строку запроса вручную и не раскодирует её.
    """
    def value(name):
        return unquote_plus((query.get(name) or "").strip())

    url = value("u")
    if not url.startswith(("http://", "https://")):
        return 400, "Плохая ссылка"
    if not verify(url, value("h")):
        # Чужая или подделанная ссылка: молча не пересылаем.
        logging.warning(f"Переход с неверной подписью: {host_of(url)}")
        return 403, "Ссылка не наша"
    try:
        await click(url, value("s"), value("t"))
    except Exception as e:
        logging.warning(f"Клик не записался: {e}")
    return 302, url
