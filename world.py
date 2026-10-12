# world.py — «Что в мире»: темы задаёт человек, отбор делает модель.
#
# Разделение придумано не для красоты. Лента без отбора — это двести
# заголовков в сутки, и читать её никто не станет. Отбор по значимости
# «вообще» модель делать не должна: это оценка, а оценок в канале нет
# нигде. Поэтому рамку ставит владелица — список тем, за которыми она
# следит, — а внутри рамки модель решает, что существенно, и
# пересказывает по-русски.
#
# Темы — не ключевые слова для поиска по тексту, а поисковые запросы.
# Каждая превращается в ленту Google News, ровно как уже сделано для
# деловых новостей и генетики (см. news_fetcher.FEEDS). Поэтому новая
# тема не требует кода: написали «птичий грипп» — и лента появилась.
#
# Пост отдельный, а не блоком внутри утреннего выпуска. Причина та же,
# по которой из него вынесли генетику: у блока внутри поста не может
# быть своей клавиатуры, а пришедший за одним листает мимо другого.

import html
import logging
from urllib.parse import quote

from aiogram import Router, F
from aiogram.types import Message

import config
import database

router = Router()

TOPICS_KEY = "world_topics"      # темы, через перевод строки
TEXT_KEY = "world_text"          # готовый блок на сегодня
MAX_TOPICS = 8                   # больше восьми — это уже не отбор
MAX_HEADLINES = 6000             # столько заголовков показываем модели
MODEL = "claude-haiku-4-5-20251001"

HEAD = "🌐 <b>Что в мире</b>"

FEED = ("https://news.google.com/rss/search?q={q}&hl=ru&gl=RU&ceid=RU:ru")


async def topics() -> list:
    raw = await database.get_setting(TOPICS_KEY) or ""
    return [x.strip() for x in raw.split("\n") if x.strip()]


async def save_topics(items: list):
    await database.set_setting(TOPICS_KEY, "\n".join(items[:MAX_TOPICS]))


async def headlines() -> str:
    """Заголовки по всем темам одним куском, с подписью темы.

    Подпись нужна модели: без неё она не отличит «нефть» от «чумы» и
    сложит их в один абзац.
    """
    import httpx
    import news_fetcher

    found = await topics()
    if not found:
        return ""

    parts = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for topic in found:
            url = FEED.format(q=quote(topic))
            got = await news_fetcher.fetch_country_news(
                client, f"мир/{topic}", [(url, None)])
            if got:
                parts.append(f"ТЕМА: {topic}\n{got}")
    return "\n\n".join(parts)[:MAX_HEADLINES]


PROMPT = (
    "Ты собираешь короткую сводку «Что в мире» для телеграм-канала "
    "о деловой жизни. На входе — заголовки, сгруппированные по темам, "
    "которые выбрал человек.\n\n"
    "Выбери из них то, что действительно существенно: событие, которое "
    "меняет положение дел, а не очередное упоминание темы. Если по теме "
    "за сутки ничего не случилось, тему пропусти совсем — пустая строчка "
    "ради полноты хуже её отсутствия.\n\n"
    "Верни от двух до четырёх абзацев, каждый с новой строки. Абзац — "
    "одна тема: что произошло и почему это важно тому, у кого своё "
    "дело. Два-три предложения, не больше.\n\n"
    "Запрещено:\n"
    "— писать о том, чего нет в заголовках;\n"
    "— предсказывать последствия и давать советы;\n"
    "— оценки: «шок», «катастрофа», «сенсация», «беспрецедентный»;\n"
    "— называть виновных и занимать сторону;\n"
    "— вступления, заголовки, маркеры списка, кавычки вокруг ответа.\n\n"
    "Если существенного нет ни по одной теме — верни пустую строку."
)


async def build() -> str:
    """Готовый текст блока. Пусто — значит, публиковать нечего."""
    source = await headlines()
    if not source.strip():
        return ""

    try:
        import block4_claude
        client = block4_claude.claude_client
    except Exception as e:
        logging.warning(f"Что в мире: клиент недоступен: {e}")
        return ""
    if client is None:
        return ""

    try:
        answer = await client.messages.create(
            model=MODEL, max_tokens=700, system=PROMPT,
            messages=[{"role": "user", "content": source}])
        text = (answer.content[0].text or "").strip().strip('"«»')
    except Exception as e:
        logging.error(f"Что в мире не собралось: {type(e).__name__}: {e}")
        return ""

    # Модель, которой нечего сказать, вместо молчания пишет об этом
    # предложение — и оно уходит в канал как сводка (см. digest.is_meta).
    import digest
    if digest.is_meta(text):
        logging.info(f"Что в мире отброшено как служебное: {text[:80]}")
        return ""
    return text


async def post() -> str:
    """Пост целиком. Пусто — выпускать нечего, и это нормальный исход."""
    body = await build()
    if not body:
        return ""
    return f"{HEAD}\n\n{html.escape(body)}"


# ---------------------------------------------------------------------
# ТЕМЫ — КОМАНДОЙ
# ---------------------------------------------------------------------

@router.message(F.text.regexp(r"^/темы"))
async def topics_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=2)
    action = parts[1].strip().lower() if len(parts) > 1 else ""
    value = parts[2].strip() if len(parts) > 2 else ""
    found = await topics()

    if action in ("+", "добавить") and value:
        if len(found) >= MAX_TOPICS:
            await message.answer(
                f"Уже {MAX_TOPICS} тем — больше это не отбор, а лента. "
                f"Снимите лишнюю: <code>/темы - слово</code>")
            return
        if value.lower() in (x.lower() for x in found):
            await message.answer("Такая тема уже есть.")
            return
        found.append(value)
        await save_topics(found)
        await message.answer(f"✅ Слежу за темой «{html.escape(value)}».")
        return

    if action in ("-", "убрать") and value:
        kept = [x for x in found if x.lower() != value.lower()]
        if len(kept) == len(found):
            await message.answer("Такой темы нет.")
            return
        await save_topics(kept)
        await message.answer(f"Убрала «{html.escape(value)}».")
        return

    if not found:
        await message.answer(
            "🌐 <b>Что в мире</b>\n\nТем пока нет, и блок не выходит.\n\n"
            "Тема — это поисковый запрос, а не слово в тексте: пишите "
            "так, как искали бы в новостях.\n\n"
            "Добавить: <code>/темы + санкции против России</code>\n"
            "Убрать: <code>/темы - санкции против России</code>")
        return

    await message.answer(
        "🌐 <b>Что в мире</b>\n\n"
        + "\n".join(f"· {html.escape(x)}" for x in found)
        + f"\n\nВсего {len(found)} из {MAX_TOPICS}.\n\n"
          "Добавить: <code>/темы + чума</code>\n"
          "Убрать: <code>/темы - чума</code>")
