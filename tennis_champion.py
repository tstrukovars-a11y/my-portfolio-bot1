# tennis_champion.py — пост о победителе турнира.
#
# Итоги дня дают строку со счётом. Для финала этого мало: выигранный
# турнир — то, ради чего весь год и играется, а в таблице он выглядит
# как любой другой матч второго круга.
#
# Поэтому отдельный пост: фотография, счёт финала, что эта победа дала
# — новое место в рейтинге, сколько титулов и шлемов стало, сколько
# призовых за карьеру. И поздравление.
#
# Цифры берём из двух мест, и оба настоящие.
#
#   Рейтинг — у ESPN: там он свежий, с прошлой позицией рядом, и видно
#   движение. «Первая ракетка» без «была второй» — половина новости.
#
#   Титулы, шлемы и призовые — из карточки Википедии. ESPN их не знает
#   вовсе, а придумывать числа о живом человеке нельзя: ошибка в
#   призовых за карьеру — это не опечатка, это неправда.
#
# Чего не нашли — о том молчим. Пост без строки о призовых остаётся
# постом; пост с выдуманными призовыми — повод для опровержения.
import asyncio
import html
import logging
import re

from aiogram import Router, F, Bot
from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton)

import config
import database
import players_ru
import tennis_live

router = Router()

SEEN_KEY = "tennis_champions_seen"
SEEN_MEMORY = 40

# Фотографии лежат по номеру игрока. Номер есть в ссылке на карточку,
# которую ESPN кладёт рядом с именем.
PHOTO = "https://a.espncdn.com/i/headshots/tennis/players/full/{id}.png"
RANKS = "https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/rankings"
WIKI = "https://en.wikipedia.org/w/api.php"

# Википедия просит называться: без имени и обратного адреса она отвечает
# отказом, и строка ниже — не вежливость, а условие доступа.
#
# В обратном адресе стоит репозиторий, а не почта владелицы: личный
# адрес в заголовке каждого запроса к чужой службе — это рассылка её
# почты по всему интернету ради одной строки о призовых.
WIKI_UA = ("AkcentBot/1.0 "
           "(+https://github.com/tstrukovars-a11y/my-portfolio-bot1)")

HEAD = "🏆 <b>Чемпион</b>"
WISH = "Поздравляем — и новых побед."


def _athlete_id(side) -> str:
    """Номер игрока у источника — из ссылки на его карточку"""
    for link in ((side.get("athlete") or {}).get("links") or []):
        found = re.search(r"/id/(\d+)", link.get("href") or "")
        if found:
            return found.group(1)
    return ""


def _name(side) -> str:
    return ((side.get("athlete") or {}).get("displayName") or "").strip()


def is_final(match) -> bool:
    """Настоящий финал турнира.

    «Qualifying Final» — финал квалификации: человек всего лишь попал в
    основную сетку. Поздравлять с ним как с титулом нельзя, а по
    вхождению слова «final» он проходит первым.
    """
    name = ((match.get("round") or "") or "").strip().lower()
    return name in ("final", "finals", "the final")


# ---------------------------------------------------------------------
# ЦИФРЫ
# ---------------------------------------------------------------------

_rank_cache = {"atp": {"at": 0, "rows": {}}, "wta": {"at": 0, "rows": {}}}
RANK_TTL = 1800


async def rank_of(tour: str, player_id: str, name: str):
    """(место, прошлое место, очки) — либо (0, 0, 0).

    Ищем по номеру игрока, а не по имени: «Zheng Qinwen» и
    «Qinwen Zheng» — один человек и две строки.
    """
    import time
    cache = _rank_cache.setdefault(tour, {"at": 0, "rows": {}})
    if time.time() - cache["at"] > RANK_TTL or not cache["rows"]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                answer = await client.get(RANKS.format(tour=tour),
                                          headers=tennis_live.API_HEADERS)
                answer.raise_for_status()
                data = answer.json()
            rows = {}
            for table in data.get("rankings") or []:
                for row in table.get("ranks") or []:
                    athlete = row.get("athlete") or {}
                    key = str(athlete.get("id") or "")
                    if key:
                        rows[key] = (int(row.get("current") or 0),
                                     int(row.get("previous") or 0),
                                     int(row.get("points") or 0))
            cache.update(at=time.time(), rows=rows)
        except Exception as e:
            logging.warning(f"Рейтинг {tour} не пришёл: {e}")
            return 0, 0, 0
    return cache["rows"].get(str(player_id), (0, 0, 0))


_wiki_cache = {}

SLAM_FIELDS = ("AustralianOpenresult", "FrenchOpenresult",
               "Wimbledonresult", "USOpenresult")


async def _wikitext(name: str) -> str:
    if name in _wiki_cache:
        return _wiki_cache[name]
    try:
        import httpx
        async with httpx.AsyncClient(timeout=25, follow_redirects=True,
                                     headers={"User-Agent": WIKI_UA}) as client:
            answer = await client.get(WIKI, params={
                "action": "parse", "format": "json", "prop": "wikitext",
                "redirects": 1, "page": name})
            answer.raise_for_status()
            text = answer.json()["parse"]["wikitext"]["*"]
    except Exception as e:
        logging.info(f"Википедия молчит про «{name}»: {e}")
        text = ""
    # Нужна только карточка в начале статьи: дальше идут сто тысяч
    # знаков биографии, в которых те же слова значат другое.
    _wiki_cache[name] = text[:6000]
    if len(_wiki_cache) > 60:
        _wiki_cache.pop(next(iter(_wiki_cache)))
    return _wiki_cache[name]


def _field(text: str, name: str) -> str:
    found = re.search(rf"\|\s*{re.escape(name)}\s*=\s*([^\n]*)", text)
    return found.group(1).strip() if found else ""


def _plain(value: str) -> str:
    """Вики-ссылку [[2008 Australian Open|2008]] — к видимой части.

    Без этого каждый год считался дважды: он стоит и в адресе ссылки, и
    в подписи к ней. Джокович выходил с сорока восемью шлемами вместо
    двадцати четырёх — число, которое читатель заметит раньше нас.
    """
    return re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1",
                  value).replace("[[", "").replace("]]", "")


def _slams(text: str) -> int:
    """Сколько турниров Большого шлема выиграно.

    Победа в карточке помечается жирным W, рядом в скобках годы. Считаем
    годы, а не отметки: четыре строки — это четыре турнира, а титулов
    в них бывает по десять.
    """
    total = 0
    for field in SLAM_FIELDS:
        value = _field(text, field)
        if "'''W'''" not in value and not value.lstrip().startswith("W "):
            continue
        years = set(re.findall(r"\b(?:19|20)\d{2}\b", _plain(value)))
        total += len(years)
    return total


def _prize(text: str) -> str:
    """Призовые за карьеру, уже по-русски: «53 222 999 $»"""
    raw = _field(text, "careerprizemoney")
    if not raw:
        return ""
    digits = re.sub(r"[^\d]", "", raw.split("<ref")[0].replace(".00", ""))
    if not digits or len(digits) < 4:
        return ""
    # Пробелы вместо запятых: по-русски разряды разделяют так.
    return f"{int(digits):,}".replace(",", " ") + " $"


def _titles(text: str) -> int:
    """Титулов в одиночке.

    У одних это просто число, у других — ссылка на отдельную статью со
    статистикой: «[[Novak Djokovic career statistics|102]]». Поэтому
    сначала разворачиваем ссылку, а уже потом читаем число.
    """
    raw = _plain(_field(text, "singlestitles").split("<ref")[0]).strip()
    found = re.search(r"\b(\d{1,3})\b", raw)
    return int(found.group(1)) if found else 0


async def achievements(name: str) -> dict:
    """Титулы, шлемы и призовые. Пусто там, где источник молчит."""
    text = await _wikitext(name)
    if not text:
        return {}
    return {"titles": _titles(text), "slams": _slams(text),
            "prize": _prize(text)}


# ---------------------------------------------------------------------
# ПОСТ
# ---------------------------------------------------------------------

def _word_titles(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "титул"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "титула"
    return "титулов"


def _word_wins(n: int) -> str:
    """«24 шлема Большого шлема» — то, что получается, если не считать
    слова. Поэтому считаем победы, а шлем остаётся турниром."""
    if n % 10 == 1 and n % 100 != 11:
        return "победа"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "победы"
    return "побед"


def _move(current: int, previous: int) -> str:
    """Что победа дала в таблице. Без движения — просто место."""
    if not current:
        return ""
    if previous and previous > current:
        return f"<b>{current}-е место</b> в рейтинге (было {previous}-е)"
    if previous and previous < current:
        return f"{current}-е место в рейтинге (было {previous}-е)"
    return f"<b>{current}-е место</b> в рейтинге"


async def champion_text(match, tour: str) -> str:
    """Пост о победителе. Пусто — если победителя в матче нет."""
    sides = (match.get("sides") or [])[:2]
    win = next((s for s in sides if s.get("winner")), None)
    lose = next((s for s in sides if not s.get("winner")), None)
    if not win:
        return ""

    event = players_ru.event(match.get("tournament") or "")
    lines = [HEAD, ""]
    who = tennis_live._named(win)
    lines.append(f"<b>{html.escape(who)}</b> выигрывает "
                 f"{html.escape(event or 'турнир')}.")

    if lose:
        score = tennis_live._score(win, lose)
        tail = f" — {html.escape(tennis_live._named(lose))}"
        lines.append(f"Финал: <code>{html.escape(score)}</code>{tail}"
                     if score else f"В финале{tail}.")

    facts = []
    current, previous, _ = await rank_of(tour, _athlete_id(win), _name(win))
    move = _move(current, previous)
    if move:
        facts.append(move)

    got = await achievements(_name(win))
    if got.get("titles"):
        facts.append(f"{got['titles']} {_word_titles(got['titles'])} "
                     f"в одиночном разряде")
    if got.get("slams"):
        facts.append(f"{got['slams']} {_word_wins(got['slams'])} "
                     f"на турнирах Большого шлема")
    if got.get("prize"):
        facts.append(f"призовых за карьеру — {got['prize']}")

    if facts:
        lines.append("")
        lines.extend(f"• {fact}" for fact in facts)

    lines.append("")
    lines.append(WISH)
    return "\n".join(lines)


async def _seen() -> set:
    raw = await database.get_setting(SEEN_KEY) or ""
    return {x for x in raw.split(",") if x}


async def _remember(keys) -> None:
    kept = list(await _seen() | set(keys))[-SEEN_MEMORY:]
    await database.set_setting(SEEN_KEY, ",".join(kept))


async def finals(tour: str):
    """Сыгранные финалы, о которых ещё не писали"""
    try:
        data = await tennis_live.fetch_scoreboard(tour)
    except Exception as e:
        logging.warning(f"Финалы {tour}: табличка не пришла ({e})")
        return []
    out = []
    for match in tennis_live._singles(data, tour, big_only=False):
        if not match.get("id") or not match.get("completed"):
            continue
        if not is_final(match):
            continue
        if not any(s.get("winner") for s in (match.get("sides") or [])):
            continue
        out.append(match)
    return out


async def publish(bot: Bot, chat: int, thread=None) -> str:
    """Пост о чемпионе — с фотографией, если она нашлась"""
    seen = await _seen()
    posted, fresh = 0, []

    for tour in ("wta", "atp"):
        for match in await finals(tour):
            key = f"{tour}:{match['id']}"
            if key in seen:
                continue
            text = await champion_text(match, tour)
            if not text:
                continue

            win = next(s for s in match["sides"] if s.get("winner"))
            photo = PHOTO.format(id=_athlete_id(win)) if _athlete_id(win) else ""
            rows = [[InlineKeyboardButton(
                text=f"🗓 Сетка {tennis_live.TOURS[tour]['title']}",
                url=tennis_live.TOURS[tour]["draws"])]]
            markup = InlineKeyboardMarkup(inline_keyboard=rows)
            try:
                if photo:
                    # Подпись к фотографии — тысяча знаков; пост о
                    # чемпионе короче, но если фотографии нет вовсе,
                    # Telegram откажет, и тогда уходит просто текст.
                    try:
                        await bot.send_photo(chat, photo, caption=text[:1024],
                                             message_thread_id=thread,
                                             reply_markup=markup)
                    except Exception as e:
                        logging.info(f"Фото чемпиона не взялось ({e}) — текстом")
                        await bot.send_message(chat, text, message_thread_id=thread,
                                               reply_markup=markup,
                                               disable_web_page_preview=True)
                else:
                    await bot.send_message(chat, text, message_thread_id=thread,
                                           reply_markup=markup,
                                           disable_web_page_preview=True)
            except Exception as e:
                logging.error(f"Чемпион {key} не вышел: {e}")
                continue
            fresh.append(key)
            posted += 1
            # Копию — тем, кто выбрал чемпионов: один пост в неделю на
            # турнир, и ради него человек и отмечал этот вид.
            try:
                import subs
                await subs.deliver(bot, "tennis_champion", text)
            except Exception as e:
                logging.warning(f"Рассылка чемпиона не прошла: {e}")
            await asyncio.sleep(3.2)

    if fresh:
        await _remember(fresh)
    return f"чемпионов: {posted}" if posted else "сыгранных финалов нет"


@router.message(F.text.startswith("/tennis_champion"))
async def champion_command(message: Message, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return
    import digest
    chat, thread = await digest._target()
    if not chat:
        await message.answer("❌ Канал не задан: <code>/digest chat -100…</code>")
        return
    await message.answer(f"🎾 {await publish(bot, chat, thread)}")
