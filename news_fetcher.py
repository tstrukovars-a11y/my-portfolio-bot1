# news_fetcher.py
# Загружает свежие заголовки из RSS-лент 4 стран и сохраняет их в БД.
# Обновляется автоматически раз в сутки фоновой задачей (см. main.py).

import asyncio
import logging

import httpx
import feedparser

# Заголовки живого браузера. Сами по себе они блокировку не снимают — Cloudflare
# у части изданий режет по IP дата-центра, а не по User-Agent, — но с ними
# капризные ленты отдают контент охотнее.
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Общая лента издания смешивает экономику с происшествиями, поэтому её
# приходится фильтровать по ключевым словам. Тематическим лентам фильтр не нужен.
IL_ECONOMY_KEYWORDS = [
    "econom", "shekel", "startup", "tech", "business", "market",
    "bank", "budget", "tax", "trade", "investment", "gdp", "finance"
]

# По каждой стране — цепочка источников. Берётся первый, который реально ответил
# и дал заголовки. Ленты Google News стоят запасными: они не блокируют запросы
# с серверов Render, в отличие от Times of Israel, который отдаёт оттуда 403.
FEEDS = {
    "ru": [
        ("https://www.vedomosti.ru/rss/rubric/economics", None),
        ("https://news.google.com/rss/search?q=экономика+бизнес&hl=ru&gl=RU&ceid=RU:ru", None),
    ],
    "il": [
        ("https://news.google.com/rss/search?q=Israel+economy+business&hl=en-US&gl=US&ceid=US:en", None),
        ("https://www.timesofisrael.com/feed/", IL_ECONOMY_KEYWORDS),
        ("https://www.israelhayom.com/feed/", IL_ECONOMY_KEYWORDS),
    ],
    "fr": [
        ("https://www.lemonde.fr/economie/rss_full.xml", None),
        ("https://news.google.com/rss/search?q=économie+entreprises&hl=fr&gl=FR&ceid=FR:fr", None),
    ],
    "us": [
        ("https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", None),
        ("https://news.google.com/rss/search?q=US+business+economy&hl=en-US&gl=US&ceid=US:en", None),
    ],
}

# Ленты по генетике для раздела «Новости генетики». Запросы намеренно на
# английском: корейские и китайские заголовки читатель бота не разберёт, а так
# материал остаётся понятным на любом языке интерфейса. Ключи с префиксом gen_
# не пересекаются с деловыми новостями в той же таблице.
GENETICS_FEEDS = {
    "gen_us": "https://news.google.com/rss/search?q=genetics+genomics+research+United+States&hl=en-US&gl=US&ceid=US:en",
    "gen_kr": "https://news.google.com/rss/search?q=South+Korea+genetics+genomics+research&hl=en-US&gl=US&ceid=US:en",
    "gen_il": "https://news.google.com/rss/search?q=Israel+genetics+genomics+research&hl=en-US&gl=US&ceid=US:en",
    "gen_cn": "https://news.google.com/rss/search?q=China+genetics+genomics+research&hl=en-US&gl=US&ceid=US:en",
}

# Темы, которые всегда исключаются из подборки, даже если попали в экономический раздел ленты
EXCLUDE_KEYWORDS = [
    "сво", "спецоперация", "специальная военная операция",
    "материнск", "маткапитал", "материнский капитал",
]

MAX_ITEMS = 4
MAX_TITLE_LEN = 110


def _is_excluded(title: str) -> bool:
    lowered = title.lower()
    return any(keyword in lowered for keyword in EXCLUDE_KEYWORDS)


def _is_included(title: str, include_keywords) -> bool:
    if not include_keywords:
        return True
    lowered = title.lower()
    return any(keyword in lowered for keyword in include_keywords)


def _escape_markdown(text: str) -> str:
    """Экранирует спецсимволы легаси Markdown, чтобы Telegram не падал на парсинге заголовков."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def _format_entries(entries, include_keywords=None) -> str:
    lines = []
    for entry in entries[:40]:
        if len(lines) >= MAX_ITEMS:
            break
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or _is_excluded(title):
            continue
        if not _is_included(title, include_keywords):
            continue
        if len(title) > MAX_TITLE_LEN:
            title = title[:MAX_TITLE_LEN].rstrip() + "…"
        title = _escape_markdown(title)
        if link:
            lines.append(f"• [{title}]({link})")
        else:
            lines.append(f"• {title}")
    return "\n".join(lines)


async def fetch_country_news(client: httpx.AsyncClient, country: str, sources) -> str:
    """Идёт по цепочке источников страны и возвращает первый непустой результат"""
    for url, include_keywords in sources:
        try:
            response = await client.get(url, timeout=15, headers=REQUEST_HEADERS)
            response.raise_for_status()
            content = _format_entries(feedparser.parse(response.content).entries, include_keywords)
            if content:
                logging.info(f"Новости ({country}) взяты из {url.split('/')[2]}")
                return content
            logging.warning(f"Источник {url.split('/')[2]} для {country} ответил, но заголовков не дал")
        except Exception as e:
            logging.warning(f"Источник {url.split('/')[2]} для {country} недоступен: {e}")

    logging.error(f"Ни один источник новостей для {country} не сработал")
    return ""


async def refresh_all_news(database_module):
    """Обновляет новости по всем 4 странам и сохраняет их в БД."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        countries = list(FEEDS.keys())
        results = await asyncio.gather(
            *[fetch_country_news(client, c, FEEDS[c]) for c in countries]
        )
        for country, content in zip(countries, results):
            if content:
                await database_module.save_daily_news(country, content)
                logging.info(f"Новости обновлены: {country}")
            else:
                logging.warning(f"Не удалось обновить новости: {country}")


async def refresh_genetics_news(database_module):
    """Свежие заголовки по генетике для четырёх стран"""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        keys = list(GENETICS_FEEDS.keys())
        results = await asyncio.gather(
            *[fetch_country_news(client, k, [(GENETICS_FEEDS[k], None)]) for k in keys]
        )
        for key, content in zip(keys, results):
            if content:
                await database_module.save_daily_news(key, content)
                logging.info(f"Новости генетики обновлены: {key}")


async def news_scheduler(database_module, index_module=None, claude_client=None):
    """Фоновая задача: обновляет новости сразу при старте бота, затем каждые 24 часа.

    Следом пересчитывает индекс стран — он опирается на только что загруженные
    заголовки, поэтому порядок важен.
    """
    while True:
        try:
            await refresh_all_news(database_module)
        except Exception as e:
            logging.error(f"Ошибка планировщика новостей: {e}")

        try:
            await refresh_genetics_news(database_module)
        except Exception as e:
            logging.error(f"Ошибка загрузки новостей генетики: {e}")

        if index_module is not None:
            try:
                await index_module.refresh_index(claude_client)
            except Exception as e:
                logging.error(f"Ошибка пересчёта индекса стран: {e}")

        await asyncio.sleep(24 * 60 * 60)
