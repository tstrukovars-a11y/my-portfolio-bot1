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


# Слова с самой церемонии лежат не в агентской заметке, а на сайте тура:
# там речь приведена целиком, абзац за абзацем. ESPN из неё берёт одну
# фразу или не берёт ничего.
#
# У WTA сайт открыт. У ATP — Cloudflare и отказ 403 на любой запрос, и
# обходить его мы не будем: мужские слова остаются на ESPN, пока не
# найдётся источник, который отдаёт их по-человечески.
WTA_SITE = "https://www.wtatennis.com"
WTA_NEWS = WTA_SITE + "/news"
BROWSER = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/140.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}
PAGE_TTL = 1800
_pages = {}

# Речь на церемонии печатается абзацами, и по газетному обычаю каждый
# следующий абзац открывается кавычкой, а закрывается только последний.
# Разбор по парам кавычек на таком тексте сбивается: продолжение речи
# попадает в «слова автора». Поэтому куски между кавычками разбираются
# по смыслу: там, где стоит «Shnaider said», — автор, остальное — речь.
ATTRIBUTION = re.compile(r"\b(said|says|added|told|continued|explained|"
                         r"noted|asked|replied)\b", re.I)
# Длинный кусок без кавычек — это уже не вставка «сказала она», а возврат
# к тексту заметки: речь кончилась.
NARRATION_MAX = 160

# Сколько речи выносим в канал. Благодарственное слово бывает длинным,
# а пост читают с телефона; режем по границе предложения, чтобы фраза
# не обрывалась на половине.
SPEECH_MAX = 900


async def _page(url: str) -> str:
    """Текст страницы без разметки. Пусто — значит, не достали."""
    import time
    hit = _pages.get(url)
    if hit and time.time() - hit[0] < PAGE_TTL:
        return hit[1]
    try:
        import httpx
        async with httpx.AsyncClient(timeout=25, follow_redirects=True,
                                     headers=BROWSER) as client:
            answer = await client.get(url)
            answer.raise_for_status()
            raw = answer.text
    except Exception as e:
        logging.warning(f"Страница {url} не пришла: {e}")
        return ""
    import html as _html
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    text = _html.unescape(re.sub(r"<[^>]+>", " ", body))
    text = re.sub(r"\s+", " ", text).strip()
    _pages[url] = (time.time(), text)
    if len(_pages) > 40:
        _pages.pop(next(iter(_pages)))
    return text


async def _wta_report(surname: str) -> str:
    """Текст свежей заметки WTA про этого игрока. Пусто — если нет."""
    listing = await _page(WTA_NEWS)
    if not listing:
        return ""
    # Адреса остаются в тексте страницы после снятия разметки не всегда,
    # поэтому список берём из самой разметки — отдельным запросом её не
    # тянем, она уже в кэше в виде текста. Проще поискать ссылки заново.
    try:
        import httpx
        async with httpx.AsyncClient(timeout=25, follow_redirects=True,
                                     headers=BROWSER) as client:
            answer = await client.get(WTA_NEWS)
            answer.raise_for_status()
            html_text = answer.text
    except Exception as e:
        logging.warning(f"Лента WTA не пришла: {e}")
        return ""
    low = surname.lower()
    for path in re.findall(r'href="(/news/\d+/[a-z0-9-]+)"', html_text):
        if low in path:
            return await _page(WTA_SITE + path)
    return ""


def speech_of(text: str, surname: str, others=()) -> str:
    """Речь игрока целиком, одним куском. Пусто — если её нет.

    Берём от первой кавычки, подписанной этой фамилией, и дальше, пока
    идёт речь. Вставки «сказала она на церемонии» выбрасываем, а на
    длинном куске текста заметки останавливаемся: речь кончилась.
    """
    if not text or not surname:
        return ""
    parts = re.split(r'["“”]', text)
    if len(parts) < 3:
        return ""

    low = surname.lower()
    rivals = [_surname(x).lower() for x in others
              if _surname(x) and _surname(x).lower() != low]

    def is_narration(chunk: str) -> bool:
        plain = chunk.lower()
        return bool(ATTRIBUTION.search(plain)) or low in plain \
            or any(r in plain for r in rivals)

    # Где начинается: первый кусок в кавычках, рядом с которым стоит
    # наша фамилия и не стоит чужая ближе.
    start = None
    position = len(parts[0])
    for index in range(1, len(parts)):
        chunk = parts[index]
        if index % 2 == 1 and not is_narration(chunk):
            gap_start, gap_end = position + 1, position + 1 + len(chunk)
            mine = _distance(text, gap_start, gap_end, surname)
            if mine is not None:
                theirs = [_distance(text, gap_start, gap_end, r)
                          for r in rivals]
                if not any(g is not None and g <= mine for g in theirs):
                    start = index
                    break
        position += len(chunk) + 1

    if start is None:
        return ""

    said = []
    for chunk in parts[start:]:
        if is_narration(chunk):
            # Чужая подпись — речь закончилась и началась не наша.
            if any(r in chunk.lower() for r in rivals):
                break
            if len(chunk.strip()) > NARRATION_MAX:
                break
            continue
        body = chunk.strip()
        if not body:
            continue
        # «…Asia Swing," Shnaider said» — запятая здесь не авторская, она
        # заменяет точку, чтобы прицепить подпись. Без неё фраза
        # кончается там, где кончилась у говорившего.
        if body.endswith(","):
            body = body[:-1] + "."
        said.append(body)

    joined = re.sub(r"\s+", " ", " ".join(said)).strip()
    if len(joined) > SPEECH_MAX:
        cut = joined[:SPEECH_MAX]
        stop = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        joined = (cut[:stop + 1] if stop > MIN_QUOTE else cut.rstrip()) + " …"
    return joined if len(joined) >= MIN_QUOTE else ""


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

    # Сначала сайт тура: там речь с церемонии приведена целиком.
    if tour == "wta":
        report = await _wta_report(surname)
        if report:
            whole = speech_of(report, surname, others)
            if whole:
                return [whole]

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
    """Перевод речи. Длиннее обычного пересказа: речь — это абзац-два,
    и обрезанная на полуслове благодарность тренеру хуже, чем её нет."""
    import tennis_alerts
    return await tennis_alerts._reason_ru(text, SPEECH_PROMPT,
                                          limit=SPEECH_MAX + 400,
                                          max_tokens=900)


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
