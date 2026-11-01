# tennis_speech.py — слова финалистов после матча.
#
# Счёт говорит, кто выиграл. Что это была за победа, говорит человек,
# который её одержал, — и говорит он это один раз, на церемонии.
#
# Своих слов мы не сочиняем. В канал идёт то, что напечатал источник, —
# ровно в тех границах, в которых оно стоит в заметке, — и перевод рядом.
# Поэтому цитата берётся только из кавычек и только тогда, когда рядом
# с ней стоит фамилия: «сказал Шнайдер» или «Шнайдер сказала». Фраза без
# подписи — это слова автора заметки, а не игрока.
#
# Оговорка, которая важнее остальных: источник пишет по-английски, и для
# того, кто говорил по-русски или по-испански, напечатанное — уже
# перевод. Поэтому первая строка подписана «как приводит источник», а не
# «на языке оригинала»: второе было бы неправдой ровно в половине
# случаев.
import logging
import re

# Длина цитаты. Короче — это обрывок вроде «I'm happy», в котором нет
# ничего; длиннее — это абзац, который в канале никто не дочитает.
MIN_QUOTE = 30
MAX_QUOTE = 320

# Сколько знаков вокруг цитаты смотрим в поисках фамилии. Подпись стоит
# вплотную: «…", Shnaider said.» или «Shnaider said: "…».
NEAR = 90

# Кавычки у источника и прямые, и типографские.
QUOTE_RE = re.compile(r'["“]([^"”“]{%d,%d})["”]' % (MIN_QUOTE, MAX_QUOTE))

SPEECH_PROMPT = (
    "Ты переводишь на русский слова теннисиста, сказанные после матча.\n\n"
    "Переводи то, что написано, и только это. Сохраняй порядок мыслей и "
    "интонацию: сдержанную — сдержанной, радостную — радостной.\n\n"
    "Запрещено:\n"
    "— добавлять то, чего в цитате нет: имена, счёт, обстоятельства;\n"
    "— убирать то, что в ней есть;\n"
    "— пересказывать своими словами вместо перевода;\n"
    "— приписывать оценки: «эмоционально заявил», «признался», «посетовал»;\n"
    "— кавычки вокруг ответа, вступления, пояснения.\n\n"
    "В ответе — только перевод."
)


def _surname(name: str) -> str:
    """Фамилия, по которой ищем подпись под цитатой"""
    parts = [p for p in (name or "").replace("-", " ").split() if len(p) > 2]
    return parts[-1] if parts else ""


def _distance(text: str, start: int, end: int, surname: str):
    """Сколько знаков от цитаты до ближайшего упоминания фамилии.

    None — если фамилии рядом нет вовсе.
    """
    low = text.lower()
    name = surname.lower()
    best = None
    for found in re.finditer(re.escape(name), low):
        if found.end() <= start:
            gap = start - found.end()
        elif found.start() >= end:
            gap = found.start() - end
        else:
            continue  # фамилия внутри самой цитаты — это не подпись
        if gap <= NEAR and (best is None or gap < best):
            best = gap
    return best


def quotes_in(text: str, surname: str, others=()) -> list:
    """Цитаты из текста, под которыми стоит эта фамилия.

    Без подписи цитату не берём. В заметке о финале говорят оба игрока,
    тренер и распорядитель; взять первую попавшуюся — значит приписать
    человеку чужие слова.

    Одного присутствия фамилии рядом мало. Абзац «…", Shnaider said.
    Fernandez, проигравшая третий финал года, сказала: "…"» держит обе
    фамилии в одном окне, и по простому поиску вторая цитата досталась
    бы обеим. Поэтому сверяем расстояние: чья фамилия ближе к кавычкам,
    того и слова.
    """
    if not text or not surname:
        return []
    found = []
    for match in QUOTE_RE.finditer(text):
        body = match.group(1).strip()
        if not body:
            continue
        mine = _distance(text, match.start(), match.end(), surname)
        if mine is None:
            continue
        rivals = [_distance(text, match.start(), match.end(), _surname(x))
                  for x in others if _surname(x)
                  and _surname(x).lower() != surname.lower()]
        if any(gap is not None and gap <= mine for gap in rivals):
            continue
        if body not in found:
            found.append(body)
    return found


async def _articles_about(tour: str, surname: str, limit: int = 3) -> list:
    """Номера свежих заметок, в которых упомянута фамилия"""
    import tennis_alerts
    low = surname.lower()
    out = []
    for headline, description, _link, article_id in await tennis_alerts._news(tour):
        if not article_id:
            continue
        if low in f"{headline} {description}".lower():
            out.append(article_id)
        if len(out) >= limit:
            break
    return out


async def quotes_for(tour: str, name: str, limit: int = 2,
                     others=()) -> list:
    """Слова игрока из свежих заметок. Пусто — значит, не нашлись."""
    import tennis_alerts
    surname = _surname(name)
    if not surname:
        return []
    found = []
    for article_id in await _articles_about(tour, surname):
        story = await tennis_alerts._story(article_id)
        for quote in quotes_in(story, surname, others):
            if quote not in found:
                found.append(quote)
            if len(found) >= limit:
                return found
    return found


async def _ru(text: str) -> str:
    import tennis_alerts
    return await tennis_alerts._reason_ru(text, SPEECH_PROMPT)


async def block(tour: str, names: list) -> str:
    """Готовый кусок поста со словами финалистов. Пусто — если их нет."""
    import html as _html
    import players_ru

    parts = []
    for name in names:
        if not name:
            continue
        others = [x for x in names if x and x != name]
        said = await quotes_for(tour, name, others=others)
        if not said:
            continue
        lines = [f"<b>{_html.escape(players_ru.ru(name))}</b>"]
        for quote in said:
            translated = await _ru(quote)
            lines.append(f"<i>«{_html.escape(quote)}»</i>")
            if translated:
                lines.append(_html.escape(translated))
        parts.append("\n".join(lines))

    if not parts:
        return ""
    head = "💬 <b>Что сказали</b>"
    tail = "<i>Цитаты — как их приводит источник.</i>"
    return head + "\n\n" + "\n\n".join(parts) + "\n\n" + tail
