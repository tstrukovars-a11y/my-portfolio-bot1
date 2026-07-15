# news_fetcher.py
# Загружает свежие заголовки из RSS-лент 4 стран и сохраняет их в БД.
# Обновляется автоматически раз в сутки фоновой задачей (см. main.py).

import asyncio
import logging

import httpx
import feedparser

FEEDS = {
    "ru": "https://ria.ru/export/rss2/index.xml",
    "il": "https://www.timesofisrael.com/feed/",
    "fr": "https://www.lemonde.fr/rss/une.xml",
    "us": "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
}

MAX_ITEMS = 4
MAX_TITLE_LEN = 110


def _escape_markdown(text: str) -> str:
    """Экранирует спецсимволы легаси Markdown, чтобы Telegram не падал на парсинге заголовков."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def _format_entries(entries) -> str:
    lines = []
    for entry in entries[:MAX_ITEMS]:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title:
            continue
        if len(title) > MAX_TITLE_LEN:
            title = title[:MAX_TITLE_LEN].rstrip() + "…"
        title = _escape_markdown(title)
        if link:
            lines.append(f"• [{title}]({link})")
        else:
            lines.append(f"• {title}")
    return "\n".join(lines)


async def fetch_country_news(client: httpx.AsyncClient, country: str, url: str) -> str:
    try:
        response = await client.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        return _format_entries(feed.entries)
    except Exception as e:
        logging.error(f"Ошибка загрузки новостей ({country}): {e}")
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


async def news_scheduler(database_module):
    """Фоновая задача: обновляет новости сразу при старте бота, затем каждые 24 часа."""
    while True:
        try:
            await refresh_all_news(database_module)
        except Exception as e:
            logging.error(f"Ошибка планировщика новостей: {e}")
        await asyncio.sleep(24 * 60 * 60)
