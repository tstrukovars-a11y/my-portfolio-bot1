# translator.py — перевод пользовательских публикаций на язык читателя.
#
# Материалы приходят из каналов на русском. Англоязычному посетителю показывать
# их как есть — значит показывать половину бота нечитаемой.
#
# Каждый перевод сохраняется в базу: один и тот же пост переводится один раз на
# язык, а не при каждом открытии. Без кэша это и деньги за каждый просмотр, и
# секунды ожидания перед появлением текста.
import asyncio
import json
import logging

import database
from block2_creative import claude_client

LANG_NAMES = {"en": "English", "fr": "French", "he": "Hebrew", "ru": "Russian"}

# Хватает на длинный пост целиком. Прежний лимит в 800 обрывал текст на середине.
MAX_TOKENS = 4096

SYSTEM = (
    "You translate posts from a personal Telegram bot into {target}. "
    "Keep emojis, line breaks and any list structure exactly as they are. "
    "Translate proper names only if a well-established form exists in {target}, "
    "otherwise leave them as written. Return only the translation, with no "
    "preface, notes or quotes around it."
)


def needs_translation(lang: str) -> bool:
    """Русский оригинал русскому читателю переводить незачем"""
    return bool(claude_client) and lang in ("en", "fr", "he")


async def translate(source: str, source_id: int, field: str, lang: str, original: str) -> str:
    """Перевод одной записи. Возвращает оригинал, если перевести не вышло."""
    if not original or not needs_translation(lang):
        return original

    cached = await database.get_translations(source, [source_id], field, lang)
    if source_id in cached:
        return cached[source_id]

    try:
        response = await claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=MAX_TOKENS,
            system=SYSTEM.format(target=LANG_NAMES.get(lang, "English")),
            messages=[{"role": "user", "content": original}]
        )
        text = response.content[0].text.strip()
    except Exception as e:
        logging.warning(f"Перевод {source}/{source_id} на {lang} не удался: {e}")
        return original

    await database.save_translation(source, source_id, field, lang, text)
    return text


async def translate_titles(source: str, items: list, lang: str) -> dict:
    """Заголовки списка одним запросом: {id: перевод}.

    По запросу на строку список из пятнадцати глав открывался бы полминуты,
    поэтому непереведённые уходят в модель одной пачкой.
    """
    if not items or not needs_translation(lang):
        return {}

    ids = [i for i, _ in items]
    cached = await database.get_translations(source, ids, "title", lang)
    missing = [(i, t) for i, t in items if i not in cached and t]
    if not missing:
        return cached

    payload = json.dumps({str(i): t for i, t in missing}, ensure_ascii=False)
    try:
        response = await claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=MAX_TOKENS,
            system=(
                f"Translate every value of this JSON object into "
                f"{LANG_NAMES.get(lang, 'English')}. Keep the keys unchanged and keep "
                f"any emojis. Return raw JSON only."
            ),
            messages=[{"role": "user", "content": payload}]
        )
        raw = response.content[0].text.strip()
        start, end = raw.find("{"), raw.rfind("}")
        translated = json.loads(raw[start:end + 1]) if start != -1 else {}
    except Exception as e:
        logging.warning(f"Пакетный перевод заголовков {source} на {lang} не удался: {e}")
        return cached

    result = dict(cached)
    for key, value in translated.items():
        try:
            item_id = int(key)
        except ValueError:
            continue
        result[item_id] = value
        await database.save_translation(source, item_id, "title", lang, value)
    return result
