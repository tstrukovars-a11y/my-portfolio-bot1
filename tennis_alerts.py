# tennis_alerts.py — расписание матчей в канале и личные напоминания.
#
# Задача, которая казалась неразрешимой: канал общий, а напоминание должно
# быть личным. Развязка в том, что это разные каналы связи.
#
#   пост в канале   — общий, его видят все;
#   нажатие кнопки  — callback, его видит только бот;
#   ссылка к началу — личное сообщение, его получает один человек.
#
# Никто из подписчиков не видит, кто и что отметил. Счётчик на кнопке
# показывает лишь число — сколько людей собирается смотреть.
import asyncio
import html
import logging
import re
from datetime import datetime, timedelta, timezone

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.exceptions import TelegramForbiddenError
from aiogram.dispatcher.event.bases import SkipHandler

import config
import database
import players_ru
import tennis_live

router = Router()

MAX_MATCHES = 10         # больше кнопок под постом не читается
CHECK_EVERY = 60         # раз в минуту: слать надо в момент начала,
                         # а не «когда-нибудь в ближайшие две»
# За сколько минут до начала слать. Десять — чтобы успеть включить
# трансляцию. Ноль означал бы «в момент начала».
LEAD_DEFAULT = 10
LEAD_KEY = "tennis_lead"
MAX_MESSAGE = 4000       # запас до телеграмовских 4096


def _title(match) -> str:
    """Кто с кем — инициал и фамилия, для кнопки"""
    sides = match.get("sides") or []
    names = []
    for side in sides[:2]:
        raw = ((side.get("athlete") or {}).get("displayName") or "")
        names.append(players_ru.short(raw) if raw else "")
    return " — ".join(n for n in names if n) or "матч"


def _with_flags(match) -> str:
    """Кто с кем, с флагами — для строки поста и для напоминания.

    На кнопке флагов нет: там дорог каждый символ, Telegram обрезает
    подпись, и имена важнее.
    """
    sides = match.get("sides") or []
    names = [tennis_live._named(s) for s in sides[:2]]
    return " — ".join(n for n in names if n) or "матч"


def _event(match) -> str:
    """Название турнира по-русски"""
    return players_ru.event(match.get("tournament") or "")


def _full_title(match) -> str:
    """Матч с турниром — для напоминания в личку.

    В канале турнир стоит заголовком над группой матчей, а в личное
    сообщение приходит один матч, и без турнира непонятно, о чём речь.
    """
    short = _with_flags(match)
    event = _event(match)
    return f"{event} · {short}" if event else short


def _starts(match):
    """Время начала как datetime либо None"""
    raw = match.get("date")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


# Заглушки, которыми источник подписывает ещё не определённого игрока.
# В сетке они законны: «победитель квалификации», «освобождён от круга».
# В анонсе — нет: читателю нечего смотреть, а подписаться не на кого.
PLACEHOLDERS = {"tbd", "tba", "bye", "qualifier", "lucky loser",
                "winner", "loser", "q", "ll", "wc"}


def _ready(match) -> bool:
    """Оба игрока известны.

    Расписание строится за сутки, а нижняя половина сетки к этому часу
    ещё доигрывается. Источник всё равно отдаёт такие матчи — с пустым
    именем или со словом «Qualifier» вместо фамилии.

    В посте это выглядело как строка «18:00 · матч»: времени нет, имён
    нет, нажимать не на что. Хуже того, подписка на такой матч ложилась
    в базу без времени начала — и не срабатывала уже никогда, потому
    что срабатывать было не по чему.
    """
    sides = (match.get("sides") or [])[:2]
    if len(sides) < 2:
        return False
    for side in sides:
        raw = ((side.get("athlete") or {}).get("displayName") or "").strip()
        if not raw or raw.lower() in PLACEHOLDERS:
            return False
    return True


def _notable(match) -> bool:
    """Есть ли в матче тот, ради кого его стоит анонсировать"""
    for side in (match.get("sides") or [])[:2]:
        name = ((side.get("athlete") or {}).get("displayName") or "")
        if players_ru.notable(name):
            return True
    return False


def _names(match):
    """Два коротких имени по отдельности — для кнопок прогноза"""
    out = []
    for side in (match.get("sides") or [])[:2]:
        raw = ((side.get("athlete") or {}).get("displayName") or "")
        out.append(players_ru.short(raw) if raw else "")
    return out if len(out) == 2 and all(out) else None


# Пока голосов мало, доля врёт: один человек — это «100 % за Рублёва».
# До этого числа показываем просто имена.
PICK_MIN = 5


def _tops(match) -> int:
    """Сколько игроков из первой двадцатки"""
    return sum(1 for side in (match.get("sides") or [])[:2]
               if players_ru.is_top(((side.get("athlete") or {})
                                     .get("displayName") or "")))


def _ours(match) -> bool:
    return any(players_ru.is_nash(((side.get("athlete") or {})
                                   .get("displayName") or ""))
               for side in (match.get("sides") or [])[:2])


def _for_pick(matches: list):
    """Матч, под которым стоит спрашивать прогноз.

    Раньше брали первый из списка — а список отсортирован по турниру и
    времени, и наверху оказывался самый ранний матч случайного турнира.
    Первый круг никому не интересен: голосуют за исход, который чего-то
    стоит. Поэтому сначала стадия, потом свои, потом сила игроков — и
    лишь при полном равенстве тот, что начнётся раньше: у голосования
    будет больше времени собраться до начала.
    """
    if not matches:
        return None
    return sorted(matches, key=lambda m: (
        -players_ru.stage(m.get("round") or ""),
        0 if _ours(m) else 1,
        -_tops(m),
        m.get("date") or ""))[0]


# Вопрос под кнопками. На финале спрашивать «кто победит в матче» — терять
# то единственное, что делает этот матч особенным.
PICK_ASK = {
    "финал": "Сегодня финал: {who} — кто возьмёт титул?",
    "1/2 финала": "Полуфинал: {who} — кто выйдет в финал?",
    "1/4 финала": "Четвертьфинал: {who} — кто пройдёт дальше?",
}


def _pick_question(match) -> str:
    who = html.escape(_title(match))
    stage_name = players_ru.rnd(match.get("round") or "")
    ask = PICK_ASK.get(stage_name)
    if ask:
        return ask.format(who=who) + " Нажмите — покажу, что думают остальные."
    return (f"А кто победит в матче {who}? Нажмите — покажу, "
            f"что думают остальные.")


def _pick_labels(match_id: str, names, counts) -> list:
    """Кнопки прогноза с долями, когда доли уже что-то значат"""
    total = sum(counts)
    rows = []
    for i, name in enumerate(names):
        share = ""
        if total >= PICK_MIN:
            share = f" · {round(counts[i] * 100 / total)}%"
        rows.append(InlineKeyboardButton(
            text=f"{name[:22]}{share}", callback_data=f"tpick_{match_id}_{i}"))
    return rows


async def _pick_row(match):
    """Строка «кто победит» под матчем дня"""
    names = _names(match)
    if not names or not match.get("id"):
        return None
    counts = await database.pick_counts(match["id"])
    return _pick_labels(match["id"], names, counts)


# До какого часа завтрашнего дня матчи считаются «нашими».
#
# Расписание выходит утром. Матч, который начинается в шесть утра
# следующего дня, в сегодняшний анонс не попадал, а завтрашний выходит
# уже после его начала — и он терялся молча. Австралия и Азия играют
# ровно в эти часы, так что терялось не редкое исключение.
#
# Граница — полдень: к этому времени утренний выпуск давно вышел, и
# дальше матч подхватывает обычное расписание.
TOMORROW_UNTIL = 12


async def _today(tour: str):
    """Матчи, которые ещё предстоят: сегодняшние и раннее утро завтра.

    Источник отдаёт турнир целиком: на «Шлеме» это три недели и три сотни
    матчей. Отбора по дате не было, и в расписание лезли матчи недельной
    давности — «не completed» они потому, что так и не состоялись.

    День считаем по часам канала, а не сервера: Render живёт по UTC.
    """
    shift = await _shift()
    local_now = datetime.now(timezone.utc) + shift
    today = local_now.date()
    tomorrow = today + timedelta(days=1)

    data = await tennis_live.fetch_scoreboard(tour)
    out = []
    for match in tennis_live._singles(data, tour, big_only=True):
        if match.get("completed") or not match.get("id"):
            continue
        # Матч без второго игрока анонсировать нечем: ни строки, ни
        # кнопки, ни напоминания — подписка на него мертва с рождения.
        if not _ready(match):
            continue
        when = _starts(match)
        if not when:
            continue
        local = when + shift

        if local.date() == today:
            # Начавшийся три часа назад и до сих пор не закрытый матч —
            # это брошенная запись источника, а не то, что стоит анонсировать.
            if local < local_now - timedelta(hours=3):
                continue
        elif local.date() == tomorrow and local.hour < TOMORROW_UNTIL:
            match["tomorrow"] = True
        else:
            continue
        out.append(match)
    out.sort(key=lambda m: m.get("date") or "")
    return out


async def _lead() -> int:
    """За сколько минут предупреждать. Меняется без передеплоя."""
    try:
        return max(0, min(60, int(await database.get_setting(LEAD_KEY)
                                  or LEAD_DEFAULT)))
    except (TypeError, ValueError):
        return LEAD_DEFAULT


def _minutes_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "минуту"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "минуты"
    return "минут"


def _lead_phrase(lead: int) -> str:
    if lead <= 0:
        return "Напомню, когда матч начнётся."
    return f"Напомню за {lead} {_minutes_word(lead)} до начала."


async def _shift():
    """Разница между часами канала и UTC.

    Округляем до минуты: разность двух «сейчас» тянет за собой микросекунды,
    и матч в 18:00 превращался в 17:59.
    """
    import digest
    raw = await digest._local_now() - datetime.now(timezone.utc)
    return timedelta(minutes=round(raw.total_seconds() / 60))


def _split(text: str):
    """Длинный текст — на сообщения, по границам строк"""
    parts, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_MESSAGE and current:
            parts.append(current)
            current = ""
        current += (line if not current else "\n" + line)
    if current:
        parts.append(current)
    return parts


def _matches_word(n: int) -> str:
    """матч / матча / матчей"""
    if n % 10 == 1 and n % 100 != 11:
        return "матч"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "матча"
    return "матчей"


def _watch_link(tour: str) -> str:
    return tennis_live.TOURS[tour]["schedule"]


def _watch_rows(tour: str):
    """Куда идти смотреть. Порядок неслучайный: сначала свои площадки —
    они на русском, без подписки и без региональных замков, — потом живой
    счёт на случай, если трансляции для этого матча нет."""
    return [
        [InlineKeyboardButton(text="📺 Канал «Больше»",
                              url=tennis_live.BOLSHE_URL)],
        [InlineKeyboardButton(text="📡 Прайм спорт",
                              url=tennis_live.PRIME_SPORT_URL)],
        [InlineKeyboardButton(text=f"📊 Счёт вживую · {tennis_live.TOURS[tour]['title']}",
                              url=_watch_link(tour))],
        [InlineKeyboardButton(text=f"🗓 Сетка {tennis_live.TOURS[tour]['title']}",
                              url=tennis_live.TOURS[tour]["draws"])],
    ]


# =====================================================================
# РАСПИСАНИЕ В КАНАЛ
# =====================================================================

async def publish_schedule(bot: Bot, chat: int, thread=None) -> str:
    """Один пост на тур со списком матчей и кнопками «напомнить»"""
    # Часы канала: у источника время в UTC, а в посте оно должно совпадать
    # с тем, что читатель видит на своих часах.
    shift = await _shift()
    lead = await _lead()

    posted = 0
    for tour in ("wta", "atp"):
        day = await _today(tour)
        if not day:
            continue

        # Из полутора сотен матчей «Шлема» в анонс идут те, где играют свои
        # или первая двадцатка: остальные фамилии читателю ничего не
        # говорят, а кнопок под постом всё равно ограниченное число.
        picked = [m for m in day if _notable(m)] or day
        matches = sorted(picked[:MAX_MATCHES],
                         key=lambda m: (_event(m), m.get("date") or ""))
        rest = len(picked) - len(matches)

        lines = [f"🎾 <b>{tennis_live.TOURS[tour]['title']} — сегодня</b>"]
        rows = []
        # Матчи сгруппированы по турниру: без него список читается как
        # набор фамилий, а турнир — половина того, ради чего смотрят.
        current = None
        for m in matches:
            event = _event(m)
            if event != current:
                current = event
                lines.append(f"\n<b>{html.escape(event)}</b>" if event else "")
            when = _starts(m)
            clock = (when + shift).strftime("%H:%M") if when else "—"
            # Ранний матч следующего дня подписываем: «06:30» без пометки
            # читается как сегодняшнее утро, которое уже прошло.
            if m.get("tomorrow"):
                clock = f"завтра {clock}"
            title = _title(m)
            rnd = players_ru.rnd(m.get("round") or "")
            lines.append(f"{clock} · {html.escape(_with_flags(m))}"
                         + (f" · <i>{html.escape(rnd)}</i>" if rnd else ""))
            rows.append([InlineKeyboardButton(
                text=f"🔔 {title[:38]}", callback_data=f"tmatch_{tour}_{m['id']}")])

        lines.append("")
        skipped = len(day) - len(picked)
        if rest:
            lines.append(f"И ещё {rest} {_matches_word(rest)} с участием "
                         f"сильнейших — в сетке.")
        elif skipped:
            lines.append(f"Всего сегодня {len(day)} {_matches_word(len(day))}, "
                         f"полная сетка по кнопке ниже.")
        lines.append(
            f"Нажмите на матч — пришлю ссылку на трансляцию в личные "
            f"сообщения, {('за ' + str(lead) + ' ' + _minutes_word(lead) + ' до начала') if lead else 'к началу'}.")

        # Прогноз — только на один матч поста, самый заметный. Две кнопки
        # к каждому из десяти превратили бы пост в стену: спрашивать надо
        # там, где человеку и правда интересно ответить.
        top = _for_pick(matches)
        picks = await _pick_row(top) if top else None
        if picks:
            lines.append("\n" + _pick_question(top))
            rows.append(picks)

        # Сетка — последней строкой кнопок: список матчей на сегодня
        # отвечает «что смотреть», сетка — «кто с кем дальше».
        rows.append([InlineKeyboardButton(
            text=f"🗓 Сетка {tennis_live.TOURS[tour]['title']}",
            url=tennis_live.TOURS[tour]["draws"])])

        body = "\n".join(lines)
        try:
            await bot.send_message(chat, body,
                                   message_thread_id=thread,
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            posted += 1
        except Exception as e:
            logging.error(f"Расписание {tour} не вышло: {e}")
        # Подписчикам — сам список, а не «смотрите в канале». Так было
        # раньше, и это ровно то нажатие, на котором теряется половина.
        # Кнопок «напомнить» в копии нет: они общие на канал, а в личке
        # счёт на них всё равно не обновится.
        await _to_subscribers("tennis", bot, body)
        await asyncio.sleep(3.2)

    return f"расписание: постов {posted}" if posted else "матчей на сегодня нет"


@router.message(F.text == "/tennis_schedule")
async def schedule_command(message: Message, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return
    import digest
    chat, thread = await digest._target()
    if not chat:
        await message.answer("❌ Канал не задан: <code>/digest chat -100…</code>")
        return
    await message.answer(f"🎾 {await publish_schedule(bot, chat, thread)}")


async def _finished(tour: str, day):
    """Сыгранные матчи названного дня, по часам канала"""
    shift = await _shift()
    data = await tennis_live.fetch_scoreboard(tour)
    out = []
    for match in tennis_live._singles(data, tour, big_only=True):
        if not match.get("completed"):
            continue
        when = _starts(match)
        if not when or (when + shift).date() != day:
            continue
        out.append(match)
    out.sort(key=lambda m: m.get("date") or "")
    return out


def _result_line(match) -> str:
    """Победитель жирным, счёт в конце — как в газетной таблице"""
    sides = sorted(match.get("sides") or [], key=lambda s: not s.get("winner"))
    if len(sides) < 2:
        return ""
    win, lose = sides[0], sides[1]
    score = tennis_live._score(win, lose)
    pair = (f"<b>{html.escape(tennis_live._named(win))}</b> — "
            f"{html.escape(tennis_live._named(lose))}")
    return pair + (f"  <code>{html.escape(score)}</code>" if score else "")


async def _pick_verdict(match) -> str:
    """Чем кончилось голосование под вчерашним постом.

    Ради этой строчки прогноз и затевался: нажать «кто победит» интересно
    только тогда, когда назавтра узнаёшь, угадала ли толпа.
    """
    names = _names(match)
    if not names or not match.get("id"):
        return ""
    counts = await database.pick_counts(match["id"])
    total = sum(counts)
    if total < PICK_MIN:
        return ""

    sides = match.get("sides") or []
    if len(sides) < 2:
        return ""
    won = 0 if sides[0].get("winner") else (1 if sides[1].get("winner") else None)
    if won is None:
        return ""

    favourite = 0 if counts[0] >= counts[1] else 1
    share = round(counts[favourite] * 100 / total)
    # Имя ставим после двоеточия, а не в середину фразы: «ставили на
    # Рублёв» — то, что выходит при подстановке, склонять фамилии
    # автоматически нельзя.
    if counts[0] == counts[1]:
        return f"<i>Прогноз читателей: голоса разделились поровну ({total}).</i>"
    verdict = "Угадали." if favourite == won else "Не угадали."
    return (f"<i>Прогноз читателей: {html.escape(names[favourite])} — "
            f"{share}% из {total}. {verdict}</i>")


# =====================================================================
# ГРОМКИЕ СОБЫТИЯ ДНЯ
# =====================================================================
#
# Расписание говорит, что будет. Итоги — что было вчера. Между ними
# пропадало главное: Медведева сняли, Соболенко проиграла той, о ком
# никто не слышал. Это новость в ту минуту, когда случилась, а наутро —
# строка в таблице среди сорока других.
#
# Берём два события, и оба распознаются без рейтингов, которых у нас
# нет: снятие по состоянию матча, неожиданность — когда известный
# проиграл неизвестному.

EVENTS_KEY = "tennis_events_seen"   # что уже объявляли, чтобы не дважды
EVENTS_MEMORY = 120                 # сколько номеров помним
# Сколько событий за один обход. Лента новостей обновляется пачкой, и
# без потолка канал однажды получит восемь сообщений подряд.
MAX_EVENTS = 3

RETIRED = ("retired", "withdrew", "withdrawn", "default", "walkover")

EVENT_HEADS = {
    "retired": "🚑 <b>Снятие</b>",
    "upset": "⚡️ <b>Неожиданность</b>",
}


def _side_name(side) -> str:
    return ((side.get("athlete") or {}).get("displayName") or "").strip()


def _seed(side) -> str:
    """Посев или место в рейтинге — «(5)» в табличке источника"""
    rank = (side.get("curatedRank") or {}).get("current")
    try:
        rank = int(rank)
    except (TypeError, ValueError):
        return ""
    # ESPN ставит 99 тем, у кого места нет: это не 99-я ракетка.
    return str(rank) if 0 < rank < 99 else ""


def _moment(match) -> str:
    """Счёт на минуту снятия.

    Причины снятия в табличке нет, а вот до какого места доиграли —
    есть. «Снялся при 4:6, 2:3» говорит больше, чем «снялся»: видно,
    началось ли это в первом же гейме или человек тянул два сета.
    """
    sides = (match.get("sides") or [])[:2]
    if len(sides) < 2:
        return ""
    rows = [[x.get("value") for x in (s.get("linescores") or [])]
            for s in sides]
    pairs = []
    for a, b in zip(rows[0], rows[1]):
        if a is None or b is None:
            continue
        pairs.append(f"{int(a)}:{int(b)}")
    return ", ".join(pairs)


# Новости источника — единственное место, где написано, из-за чего
# именно снялся игрок: в самом табло этого нет, там только «Retired».
#
# Выдумывать причину нельзя, и случай Медведева показывает почему: его
# не сняли по травме, его дисквалифицировали за мяч, улетевший в лицо
# зрителю. Фраза «снялся из-за травмы» была бы не домыслом даже, а
# прямой неправдой о живом человеке.
NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/news"
NEWS_TTL = 900
_news_cache = {"atp": {"at": 0, "items": []}, "wta": {"at": 0, "items": []}}


async def _news(tour: str) -> list:
    """[(заголовок, описание, ссылка)] свежих новостей тура"""
    import time
    cache = _news_cache.setdefault(tour, {"at": 0, "items": []})
    if time.time() - cache["at"] < NEWS_TTL and cache["items"]:
        return cache["items"]
    try:
        import httpx
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            answer = await client.get(NEWS_URL.format(tour=tour),
                                      headers=tennis_live.API_HEADERS)
            answer.raise_for_status()
            data = answer.json()
    except Exception as e:
        logging.warning(f"Новости {tour} не пришли: {e}")
        return cache["items"]

    items = []
    for article in (data.get("articles") or [])[:20]:
        items.append((
            (article.get("headline") or "").strip(),
            (article.get("description") or "").strip(),
            (((article.get("links") or {}).get("web") or {}).get("href") or ""),
            str(article.get("id") or ""),
        ))
    cache.update(at=time.time(), items=items)
    return items


def _surname(name: str) -> str:
    parts = [p for p in (name or "").replace("-", " ").split() if len(p) > 2]
    return parts[-1] if parts else ""


# Полный текст заметки лежит отдельно от ленты: в списке только
# заголовок и подводка. А подробности — в тексте: там и слова самого
# игрока, и счёт на момент происшествия, и что было дальше.
STORY_URL = "https://now.core.api.espn.com/v1/sports/news/{id}"
_stories = {}


async def _story(article_id: str) -> str:
    """Текст заметки без разметки. Пусто — значит, не достали."""
    if not article_id:
        return ""
    if article_id in _stories:
        return _stories[article_id]
    try:
        import httpx
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            answer = await client.get(STORY_URL.format(id=article_id),
                                      headers=tennis_live.API_HEADERS)
            answer.raise_for_status()
            data = answer.json()
        raw = ((data.get("headlines") or [{}])[0].get("story") or "")
    except Exception as e:
        logging.warning(f"Заметка {article_id} не пришла: {e}")
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    _stories[article_id] = text
    if len(_stories) > 80:
        _stories.pop(next(iter(_stories)))
    return text


async def _why_gone(tour: str, name: str):
    """(текст для пересказа, ссылка) — либо (пусто, пусто).

    Берём все заметки про этого игрока, а не первую попавшуюся: про
    громкое пишут дважды — коротко и подробно, — и подробности лежат во
    второй. К заголовкам добавляем полный текст: там слова самого
    игрока и то, что было дальше.
    """
    surname = _surname(name).lower()
    if not surname:
        return "", ""

    found, link = [], ""
    for headline, description, article_link, article_id in await _news(tour):
        if surname not in f"{headline} {description}".lower():
            continue
        link = link or article_link
        found.append(f"{headline}. {description}")
        body = await _story(article_id)
        if body:
            found.append(body[:3000])
        if len(found) >= 4:
            break
    return "\n\n".join(found)[:6000], link


REASON_PROMPT = (
    "Ты пересказываешь спортивную заметку по-русски для телеграм-канала "
    "об одном эпизоде: игрок не доиграл матч, снялся, был "
    "дисквалифицирован или пропускает турнир.\n\n"
    "Верни от двух до четырёх коротких строк, каждая с новой строки, "
    "каждая — законченное предложение. Порядок: что произошло; как это "
    "сказалось на самом игроке и на других; слова самого игрока, если "
    "они в тексте есть.\n\n"
    "Пиши только то, что сказано в тексте. Это главное правило, и оно "
    "важнее полноты.\n\n"
    "Запрещено:\n"
    "— называть причину, которой в тексте нет;\n"
    "— ставить диагнозы и уточнять характер травмы сверх сказанного;\n"
    "— дописывать последствия по здравому смыслу. Если про штраф, "
    "потерянные очки, призовые или отстранение в тексте не сказано — "
    "молчи о них, даже если так обычно бывает;\n"
    "— оценки: «сенсация», «скандал», «позор», «шок»;\n"
    "— вступления, заголовки, кавычки вокруг всего ответа, списки "
    "с цифрами и маркерами.\n\n"
    "Различай снятие по ходу матча, отказ до начала, дисквалификацию и "
    "пропуск турнира: это разные вещи, и путать их нельзя.\n\n"
    "Если в тексте нет ничего про этот эпизод — верни пустую строку."
)

# Строки длиннее этого в канал не пускаем: пересказ на абзац перестаёт
# быть пометкой к событию и начинает соперничать с самой новостью.
REASON_LIMIT = 600


async def _reason_ru(english: str) -> str:
    """Пересказ по-русски. Пусто — значит, сказать нечего."""
    if not english.strip():
        return ""
    try:
        import block4_claude
        client = block4_claude.claude_client
    except Exception:
        return ""
    if client is None:
        return ""
    try:
        answer = await client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=400,
            system=REASON_PROMPT,
            messages=[{"role": "user", "content": english[:6000]}])
        text = (answer.content[0].text or "").strip().strip('"«»')
    except Exception as e:
        logging.warning(f"Пересказ не собрался: {e}")
        return ""

    # Маркеры списка модель иногда ставит вопреки запрету: убираем их
    # здесь, а не ещё одной просьбой в промпте.
    lines = [re.sub(r"^\s*[-–—•*\d.)]+\s*", "", x).strip()
             for x in text.splitlines() if x.strip()]
    return "\n".join(lines)[:REASON_LIMIT]


def _event_kind(match) -> str:
    """Чем этот матч примечателен: «retired», «upset» или ничем.

    Известность считаем по тому же списку, что и для расписания: свои и
    верхушка рейтинга. Матч двух неизвестных громким событием не станет,
    как бы он ни кончился.
    """
    sides = (match.get("sides") or [])[:2]
    if len(sides) < 2:
        return ""
    if not any(players_ru.notable(_side_name(s)) for s in sides):
        return ""

    state = (match.get("state") or "").lower()
    if any(word in state for word in RETIRED):
        return "retired"

    if not match.get("completed"):
        return ""

    win = next((s for s in sides if s.get("winner")), None)
    lose = next((s for s in sides if not s.get("winner")), None)
    if not win or not lose:
        return ""
    # Неожиданность — это поражение известного от неизвестного. Победа
    # одного известного над другим неожиданностью не является, как бы
    # ни удивлял счёт.
    if players_ru.notable(_side_name(lose)) \
            and not players_ru.notable(_side_name(win)):
        return "upset"
    return ""


async def _event_text(kind: str, match, tour: str) -> str:
    """Сообщение о событии — с подробностями, но без оценок.

    Оценки лишние: «сенсация» и «разгром» читатель поставит сам, а
    ошибётся в них бот, а не он. Подробности — наоборот, главное: «снят»
    без «из-за чего» оставляет читателя с тем же вопросом, с которым он
    пришёл.
    """
    sides = (match.get("sides") or [])[:2]
    win = next((s for s in sides if s.get("winner")), None)
    lose = next((s for s in sides if not s.get("winner")), None)

    lines = [EVENT_HEADS.get(kind, EVENT_HEADS["upset"])]
    event = _event(match)
    rnd = players_ru.rnd(match.get("round") or "")
    where = " · ".join(x for x in (event, rnd) if x)
    if where:
        lines.append(f"<i>{html.escape(where)}</i>")
    lines.append("")

    if kind == "retired":
        # Снялся тот, кто не победил: у снятия в табличке есть победитель.
        who = lose or sides[0]
        gone = "снялась" if tour == "wta" else "снялся"
        lines.append(f"<b>{html.escape(tennis_live._named(who))}</b> {gone}.")

        moment = _moment(match)
        if moment:
            lines.append(f"Доиграли до <code>{html.escape(moment)}</code>.")

        reason, link = await _why_gone(tour, _side_name(who))
        russian = await _reason_ru(reason)
        if russian:
            lines.append("")
            lines.append(html.escape(russian))
        if link:
            lines.append(f'<a href="{html.escape(link)}">Подробнее у источника</a>')

        if win:
            seed = _seed(win)
            mark = f" ({seed})" if seed else ""
            lines.append("")
            lines.append(f"Дальше проходит "
                         f"{html.escape(tennis_live._named(win))}{mark}.")
        return "\n".join(lines)

    line = _result_line(match)
    if line:
        lines.append(line)

    # Разрыв в рейтинге и есть то, что делает поражение неожиданным:
    # «34-я обыграла первую» объясняет само себя.
    if win and lose:
        high, low = _seed(lose), _seed(win)
        if high and low:
            lines.append(f"{html.escape(_side_name_ru(lose))} — {high}-я ракетка, "
                         f"{html.escape(_side_name_ru(win))} — {low}-я.")
    if lose:
        lines.append("")
        lines.append(f"{html.escape(tennis_live._named(lose))} вылетает.")

    reason, link = await _why_gone(tour, _side_name(lose) if lose else "")
    russian = await _reason_ru(reason) if reason else ""
    if russian:
        lines.append("")
        lines.append(html.escape(russian))
    if link:
        lines.append(f'<a href="{html.escape(link)}">Подробнее у источника</a>')
    return "\n".join(lines)


def _side_name_ru(side) -> str:
    return players_ru.short(_side_name(side)) or _side_name(side)


async def _to_subscribers(kind: str, bot: Bot, text: str) -> None:
    """Копию — тем, кто выбрал именно этот вид теннисных постов.

    Копию, а не «смотрите в канале»: человек уже в переписке с ботом, и
    на лишнем нажатии теряется половина. Так устроены и остальные
    подписки, и расходиться с ними здесь незачем.

    Ошибка рассылки не должна ронять публикацию: пост в канале уже
    вышел, и это важнее.
    """
    if not (text or "").strip():
        return
    try:
        import subs
        await subs.deliver(bot, kind, text)
    except Exception as e:
        logging.warning(f"Личная рассылка «{kind}» не прошла: {e}")


async def _seen() -> set:
    raw = await database.get_setting(EVENTS_KEY) or ""
    return {x for x in raw.split(",") if x}


async def _remember(ids) -> None:
    """Помним последние номера: без этого событие уходило бы в канал
    каждые несколько минут, пока матч висит в табличке."""
    kept = list(await _seen() | set(ids))[-EVENTS_MEMORY:]
    await database.set_setting(EVENTS_KEY, ",".join(kept))


async def find_events(tour: str):
    """[(вид, матч)] громких событий сегодняшнего дня"""
    shift = await _shift()
    today = (datetime.now(timezone.utc) + shift).date()
    try:
        data = await tennis_live.fetch_scoreboard(tour)
    except Exception as e:
        logging.warning(f"События {tour}: табличка не пришла ({e})")
        return []

    out = []
    for match in tennis_live._singles(data, tour, big_only=True):
        if not match.get("id") or not _ready(match):
            continue
        when = _starts(match)
        if not when or (when + shift).date() != today:
            continue
        kind = _event_kind(match)
        if kind:
            out.append((kind, match))
    return out


# Не всё громкое видно в табло. Дисквалификация Медведева в Пекине
# пришла туда обычным поражением: счёт, победитель, ничего особенного.
# В ленте новостей это заголовок из восьми слов.
#
# Поэтому третий вид событий берётся не из табло, а из новостей: игрок,
# которого читатель знает, плюс слово, означающее происшествие.
# Снятия по ходу матча сюда не входят: их видно в табло, и там о них
# известно больше. Здесь то, чего в табло нет совсем.
LOUD = ("disqualif", "dq'd", "dq’d", "default", "withdraw", "withdrew",
        "pulls out", "pulled out", "miss rest", "miss the rest", "will miss",
        "ruled out", "out of the", "out of china", "out of", "suspend",
        "banned", "fined", "forfeit")

# Заголовок о победе — не происшествие, даже когда в нём есть «injured»:
# «Alcaraz retains title following injury layoff» рассказывает о
# возвращении, а не о том, что кто-то снялся.
WINS = ("wins", "win ", "beats", "beat ", "retains", "reach", "reaches",
        "advances", "defeats", "overcomes", "rallies", "улучш")

NEWS_HEAD = "📣 <b>Вне корта</b>"


def _loud_about(headline: str, description: str) -> str:
    """Имя известного игрока, если заметка о происшествии. Иначе пусто.

    Игрока ищем в заголовке, а не во всей заметке: в подводке назван и
    соперник, и получалось «отказался Легечка», когда отказался другой.
    """
    head = (headline or "").lower()
    if not any(word in head for word in LOUD):
        return ""
    if any(word in head for word in WINS):
        return ""
    return players_ru.first_known(head)


async def find_news_events(tour: str):
    """[(id заметки, имя, заголовок, подводка, ссылка)] громкого вне табло"""
    out = []
    for headline, description, link, article_id in await _news(tour):
        who = _loud_about(headline, description)
        if who and article_id:
            out.append((article_id, who, headline, description, link))
    return out


async def _news_event_text(tour: str, who: str, headline: str,
                           description: str, link: str,
                           article_id: str) -> str:
    """Сообщение о событии вне корта — пересказом, а не заголовком.

    Материал собираем по всем заметкам об этом игроке, а не по той
    одной, что попалась первой: про громкое ESPN ставит и видео, и
    текст, а видео приходит без текста вовсе. Взяв первую, можно
    получить восемь слов заголовка там, где рядом лежат три тысячи
    знаков с его собственными словами.
    """
    gathered, _ = await _why_gone(tour, who)
    source = gathered or f"{headline}. {description}\n\n{await _story(article_id)}"
    recap = await _reason_ru(source)
    if not recap:
        # Без пересказа остаётся английский заголовок — это не публикация
        # для русского канала, лучше промолчать.
        return ""

    lines = [NEWS_HEAD, ""]
    russian = players_ru.ru(who)
    if russian:
        lines.append(f"<b>{html.escape(russian)}</b>")
    lines.append(html.escape(recap).replace("\n", "\n"))
    if link:
        lines.append("")
        lines.append(f'<a href="{html.escape(link)}">Подробнее у источника</a>')
    return "\n".join(lines)


async def publish_events(bot: Bot, chat: int, thread=None) -> str:
    """Объявить то, что случилось только что. Каждое событие — один раз."""
    seen = await _seen()
    posted, fresh = 0, []

    for tour in ("wta", "atp"):
        for kind, match in await find_events(tour):
            key = f"{match['id']}:{kind}"
            if key in seen:
                continue
            try:
                await bot.send_message(
                    chat, await _event_text(kind, match, tour),
                    message_thread_id=thread,
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(
                            text=f"🗓 Сетка {tennis_live.TOURS[tour]['title']}",
                            url=tennis_live.TOURS[tour]["draws"])]]))
            except Exception as e:
                logging.error(f"Событие {key} не вышло: {e}")
                continue
            fresh.append(key)
            posted += 1
            await _to_subscribers("tennis_loud", bot,
                                  await _event_text(kind, match, tour))
            await asyncio.sleep(3.2)

        # Вне корта: дисквалификация, отказ от турнира, травма на
        # месяц. В табло этого нет — дисквалификация приходит туда
        # обычным поражением.
        for article_id, who, headline, description, link in \
                await find_news_events(tour):
            key = f"n{article_id}"
            # О громком пишут дважды — коротко и подробно. Для читателя
            # это одно событие, поэтому помним ещё и игрока: вторая
            # заметка про того же человека в канал не пойдёт.
            same = f"p{tour}:{who}"
            if key in seen or same in seen or same in fresh \
                    or len(fresh) >= MAX_EVENTS:
                continue
            text = await _news_event_text(tour, who, headline, description,
                                          link, article_id)
            if not text:
                # Пересказ не собрался — заголовок по-английски в русский
                # канал не ставим. Запомним, чтобы не дёргать снова.
                fresh.append(key)
                continue
            try:
                await bot.send_message(chat, text, message_thread_id=thread,
                                       disable_web_page_preview=True)
            except Exception as e:
                logging.error(f"Событие {key} не вышло: {e}")
                continue
            fresh.extend((key, same))
            posted += 1
            await _to_subscribers("tennis_loud", bot, text)
            await asyncio.sleep(3.2)

    if fresh:
        await _remember(fresh)
    return f"событий в канал: {posted}" if posted else "громких событий нет"


@router.message(F.text.startswith("/tennis_events"))
async def events_command(message: Message, bot: Bot):
    """Проверить вручную — и увидеть, что бот считает громким"""
    if not config.is_admin(message.from_user.id):
        return
    import digest
    chat, thread = await digest._target()
    if not chat:
        await message.answer("❌ Канал не задан: <code>/digest chat -100…</code>")
        return
    await message.answer(f"🎾 {await publish_events(bot, chat, thread)}")


async def publish_results(bot: Bot, chat: int, thread=None) -> str:
    """Итоги вчерашнего дня — утром, пока результаты ещё новость"""
    shift = await _shift()
    yesterday = (datetime.now(timezone.utc) + shift - timedelta(days=1)).date()

    blocks, total = [], 0
    for tour in ("wta", "atp"):
        played = await _finished(tour, yesterday)
        if not played:
            continue
        total += len(played)
        lines = [f"<b>{tennis_live.TOURS[tour]['title']}</b>"]
        current = None
        # Все матчи, без «и ещё пять»: итог дня, из которого вырезали
        # половину, — это не итог.
        for m in played:
            event = _event(m)
            if event != current:
                current = event
                lines.append(f"<i>{html.escape(event)}</i>")
            line = _result_line(m)
            if line:
                lines.append(line)
                verdict = await _pick_verdict(m)
                if verdict:
                    lines.append(verdict)
        blocks.append("\n".join(lines))

    if not blocks:
        return "вчера крупных матчей не было"

    head = f"🎾 <b>Вчера на кортах — {yesterday.strftime('%d.%m')}</b>"
    rows = [[InlineKeyboardButton(
        text=f"🗓 Сетка {tennis_live.TOURS[tour]['title']}",
        url=tennis_live.TOURS[tour]["draws"])] for tour in ("wta", "atp")]

    # День «Шлема» — это полсотни матчей, в одно сообщение они не влезают.
    # Режем по строкам, кнопки вешаем на последнее.
    parts = _split(head + "\n\n" + "\n\n".join(blocks))
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        try:
            await bot.send_message(
                chat, part, message_thread_id=thread,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if last else None)
        except Exception as e:
            logging.error(f"Сводка результатов не вышла: {e}")
            return f"ошибка: {e}"
        if not last:
            await asyncio.sleep(3.2)

    await _to_subscribers("tennis_results", bot, parts[0])
    return f"итоги вчерашнего дня: матчей {total}, сообщений {len(parts)}"


@router.message(F.text.startswith("/tennis_paid"))
async def paid_command(message: Message):
    """Платные напоминания или свободные"""
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) > 1:
        value = "да" if parts[1].lower() in ("да", "yes", "on") else ""
        await database.set_setting(PAID_KEY, value)
        await message.answer(
            "✅ Напоминания только по подписке." if value else
            "✅ Напоминания открыты всем.")
        return
    await message.answer(
        ("Сейчас: только по подписке." if await _paid() else
         "Сейчас: открыты всем.")
        + "\n\nЗакрыть подпиской: <code>/tennis_paid да</code>\n"
          "Открыть всем: <code>/tennis_paid нет</code>")


@router.message(F.text.startswith("/tennis_lead"))
async def lead_command(message: Message):
    """За сколько минут предупреждать: 0 — ровно в момент начала"""
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) > 1:
        try:
            value = max(0, min(60, int(parts[1])))
        except ValueError:
            await message.answer("Нужно число минут: <code>/tennis_lead 0</code>")
            return
        await database.set_setting(LEAD_KEY, str(value))
        await message.answer(f"✅ {_lead_phrase(value)}")
        return
    await message.answer(
        f"Сейчас: {_lead_phrase(await _lead())}\n\n"
        "Изменить: <code>/tennis_lead 0</code> — в момент начала, "
        "<code>/tennis_lead 15</code> — за четверть часа.")


@router.message(F.text.regexp(r"^/start\s+tm-"))
async def start_with_match(message: Message, bot: Bot):
    """Пришёл из канала по кнопке напоминания: дооформляем подписку на матч.

    Этот роутер зарегистрирован раньше общего /start, поэтому в конце
    обязательно передаём ход дальше — иначе новый человек не увидит ни
    приветствия, ни выбора языка, а он тут первый раз.
    """
    done = await _handle_match_start(message, bot)
    if done:
        # Дальше общий /start не зовём: человек пришёл за напоминанием,
        # а не за выбором языка и обзором разделов.
        # Подтверждение человек уже получил — больше ему ничего не
        # присылаем. Язык запоминаем молча, чтобы следующее сообщение
        # пришло на нужном.
        import personal
        await personal.quiet(message, message.from_user)
        return
    raise SkipHandler


async def _handle_match_start(message: Message, bot: Bot) -> bool:
    """Оформить подписку на матч. True — человеку уже всё сказано.

    Возвращаемое значение решает, показывать ли ему дальше общий вход с
    выбором языка и меню. Пришедшему за напоминанием он не нужен: своё
    он получил, а меню из восьми разделов на этом месте только отпугнёт.
    """
    payload = message.text.split(maxsplit=1)[1].strip()
    try:
        _, tour, match_id = payload.split("-", 2)
    except ValueError:
        return False
    if tour not in tennis_live.TOURS:
        return False

    if not await _allowed(message.from_user.id):
        await message.answer(NO_SUB)
        return True

    matches = await _today(tour)
    match = next((m for m in matches if m["id"] == match_id), None)
    if not match:
        await message.answer("Этот матч уже начался или завершился.")
        return True

    ok = await database.ensure_alert(
        message.from_user.id, match_id, tour, _full_title(match), _starts(match))
    if ok is None:
        await message.answer("Не получилось сохранить напоминание. "
                             "Попробуйте ещё раз через минуту.")
        return True
    await _confirm(bot, message.from_user.id, tour, match_id,
                   _full_title(match), _starts(match))
    return True


@router.message(F.text.startswith("/tennis_alerts"))
async def alerts_status(message: Message):
    """Что с напоминаниями прямо сейчас — по записям, а не по ощущениям.

    Показывает и часы базы: выборка идёт сравнением с NOW() базы, и
    расхождение часов выглядит как «подписка не сработала», хотя записи
    на месте.
    """
    if not config.is_admin(message.from_user.id):
        return

    state = await database.health()
    rows, db_now, waiting = await database.alerts_overview(12)
    shift = await _shift()
    lead = await _lead()
    now_utc = datetime.now(timezone.utc)

    lines = ["🔔 <b>Напоминания о матчах</b>", ""]

    # База — первое, что надо знать: без неё не работает вообще ничего,
    # а выглядит это как «кнопка не сработала».
    if not state["ok"]:
        lines.append("❌ <b>База не отвечает</b>")
        # Показываем каждый способ отдельно: наружу летит ошибка последнего,
        # а виновата обычно первая — и без неё чинят не то.
        for how, why in state.get("attempts") or []:
            lines.append(f"• {how}: <code>{html.escape(why)}</code>")
        if not state.get("attempts"):
            lines.append(f"<code>{html.escape(state['error'])}</code>")
        if state.get("target"):
            lines.append(f"Адрес: <code>{html.escape(state['target'])}</code>")
        if state.get("driver"):
            lines.append(f"Драйвер asyncpg: <code>{html.escape(str(state['driver']))}</code>")
        import admin
        verdict = admin.db_verdict(state.get("attempts") or [])
        if verdict:
            lines.append("")
            lines.append(verdict)
        lines.append("")
    else:
        missing = [n for n, there in state["tables"].items() if not there]
        if missing:
            lines.append("❌ <b>Нет таблиц:</b> " + ", ".join(missing)
                         + "\nОни создаются при запуске — значит, запуск "
                           "оборвался на полпути.\n")

    if database.LAST_ERROR["what"]:
        when = database.LAST_ERROR["when"]
        lines.append(f"⚠️ <b>Последняя ошибка базы</b>"
                     + (f" ({when.strftime('%d.%m %H:%M')} UTC)" if when else "")
                     + f"\n<code>{html.escape(database.LAST_ERROR['what'])}</code>\n")

    lines.append(f"Связь с базой: {database.POOL_MODE['how']}")
    lines.append(f"Сейчас по UTC: <code>{now_utc.strftime('%d.%m %H:%M')}</code>")
    lines.append(f"По часам канала: <code>{(now_utc + shift).strftime('%d.%m %H:%M')}</code>")
    if db_now is not None:
        lines.append(f"По часам базы: <code>{db_now.strftime('%d.%m %H:%M')}</code>")
        # Записи сравниваются с часами базы: разошлись — рассылка молчит.
        drift = abs((db_now.replace(tzinfo=None)
                     - now_utc.replace(tzinfo=None)).total_seconds())
        if drift > 300:
            lines.append("⚠️ <b>Часы базы не совпадают с UTC</b> — из-за этого "
                         "напоминания уходят не вовремя или не уходят вовсе.")
    lines.append(f"Шлю за {lead} {_minutes_word(lead)} до начала.")
    lines.append(f"Ждут отправки: <b>{waiting}</b>")

    # Главная причина «подписка есть, а ссылки нет»: запись без времени
    # начала. Планировщик выбирает по времени и такую запись не видит.
    stuck = await database.timeless_alerts()
    if stuck:
        lines.append(f"⚠️ <b>Без времени начала: {stuck}</b> — эти не уйдут "
                     f"никогда. Время проставится само, как только матч "
                     f"появится в табличке с датой; безнадёжные снимаются "
                     f"через двое суток.")
    lines.append("")

    if not rows:
        lines.append("Записей нет вообще. Значит, ни одна кнопка «напомнить» "
                     "не сохранилась — нажмите матч в канале и посмотрите снова.")
    else:
        lines.append("<b>Последние записи</b>")
        for r in rows:
            when = r.get("starts_at")
            clock = ((when + shift).strftime("%d.%m %H:%M")
                     if when else "время неизвестно")
            mark = "✅" if r.get("sent") else "⏳"
            lines.append(f"{mark} {clock} · {html.escape((r.get('title') or '—')[:40])}")
        lines.append("")
        lines.append("⏳ — ждёт отправки, ✅ — ушло либо закрыто.")
        lines.append("«Время неизвестно» — матча не было в расписании в момент "
                     "нажатия, такую запись планировщик не возьмёт.")

    lines.append("")
    lines.append("Проверить весь путь целиком: <code>/tennis_test</code>")
    await message.answer("\n".join(lines))


@router.message(F.text.startswith("/tennis_test"))
async def test_command(message: Message, bot: Bot):
    """Проверка напоминаний целиком, а не на словах.

    Сначала присылает образец сразу — видно, как выглядит. Затем кладёт в
    базу настоящую запись на ближайшую минуту: её подберёт тот же
    планировщик, что и боевые. Если сломается запись — команда скажет об
    этом сразу, а не промолчит, как было.
    """
    if not config.is_admin(message.from_user.id):
        return

    # /tennis_test wta — проверить женский вариант: подписи и ссылки
    # у туров разные, и смотреть надо оба.
    parts = message.text.split()
    tour = parts[1].lower() if len(parts) > 1 and parts[1].lower() in tennis_live.TOURS else "atp"

    lead = await _lead()
    title = f"Проверка · {tennis_live.TOURS[tour]['title']} — тестовый матч"

    # 1. Образец прямо сейчас
    head = "Начинается" if lead <= 0 else f"Начнётся через {lead} {_minutes_word(lead)}"
    try:
        await bot.send_message(
            message.from_user.id,
            f"🎾 <b>{html.escape(title)}</b>\n\n{head}. Где смотреть:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=_watch_rows(tour)),
            disable_web_page_preview=True)
    except TelegramForbiddenError:
        await message.answer("❌ Бот не может вам писать. Нажмите «Старт» в личке.")
        return

    # 2. Настоящая запись — через минуту её должен взять планировщик
    match_id = f"test-{int(datetime.now(timezone.utc).timestamp())}"
    starts = datetime.now(timezone.utc) + timedelta(minutes=lead + 1)
    added, _ = await database.toggle_alert(
        message.from_user.id, match_id, tour, title, starts)

    if added is None:
        why = database.LAST_ERROR.get("what") or "причина не записалась"
        await message.answer(
            "☝️ Образец пришёл, но <b>запись в базу не удалась</b> — "
            "значит, боевые напоминания тоже не сохранятся.\n\n"
            f"<code>{html.escape(why)}</code>\n\n"
            "Подробности о базе: <code>/tennis_alerts</code>")
        return
    await message.answer(
        "✅ Образец отправлен.\n"
        f"И поставлено настоящее напоминание: планировщик должен прислать "
        f"его в течение минуты. Придёт — значит, весь путь рабочий.")


@router.message(F.text == "/tennis_results")
async def results_command(message: Message, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return
    import digest
    chat, thread = await digest._target()
    if not chat:
        await message.answer("❌ Канал не задан: <code>/digest chat -100…</code>")
        return
    await message.answer(f"🎾 {await publish_results(bot, chat, thread)}")


# =====================================================================
# ЛИЧНАЯ ОТМЕТКА
# =====================================================================

NO_SUB = ("🎾 Напоминания о матчах — часть теннисной подписки.\n\n"
          "Оформить: откройте бота → Спорт → Большой теннис.")

# Брать ли за напоминания деньги. По умолчанию нет: читатель канала,
# нажавший колокольчик и не получивший ничего, больше не нажмёт — а это
# единственная кнопка, которая уводит из канала в бота.
PAID_KEY = "tennis_alerts_paid"


async def _paid() -> bool:
    return (await database.get_setting(PAID_KEY) or "").strip() == "да"


async def _allowed(user_id: int) -> bool:
    if config.is_admin(user_id) or not await _paid():
        return True
    return await database.check_subscription(user_id)
NO_CHAT = ("Чтобы получать напоминания, откройте бота и нажмите «Старт» — "
           "иначе я не смогу вам написать.")


async def _deep_link(payload: str) -> str:
    """Ссылка, открывающая бота с параметром. Пусто — имя бота не задано."""
    username = await database.get_setting("bot_username")
    if not username:
        return ""
    return f"https://t.me/{username.lstrip('@')}?start={payload}"


async def _open_bot(call: CallbackQuery, payload: str, fallback: str) -> None:
    """Открыть бота у нажавшего.

    Читатель «Акцента» пришёл из репоста или поиска и о существовании бота
    не знает — предложение «нажмите Старт» для него бессмысленно. Telegram
    разрешает ответить на нажатие ссылкой на самого себя: человек одним
    касанием попадает в бота, и /start приходит уже с параметром.
    """
    url = await _deep_link(payload)
    if url:
        await call.answer(url=url)
    else:
        await call.answer(fallback, show_alert=True)


def _name_on(button) -> str:
    """Имя с кнопки прогноза без доли — доля на ней могла уже устареть"""
    return (button.text or "").split(" · ")[0]


@router.callback_query(F.data.startswith("tpick_"))
async def take_pick(call: CallbackQuery):
    """Прогноз читателя под постом канала.

    Кнопка общая, ответ личный: в окошке человек видит своё мнение и
    расклад, на самой кнопке проценты обновляются для всех.
    """
    try:
        match_id, raw = call.data[len("tpick_"):].rsplit("_", 1)
        side = int(raw)
    except ValueError:
        await call.answer()
        return

    counts = await database.save_pick(match_id, call.from_user.id, side)
    if counts is None:
        await call.answer("Не получилось сохранить голос, попробуйте ещё раз.",
                          show_alert=True)
        return

    # Имена берём с самих кнопок: матч мог уже уйти из сегодняшнего
    # расписания, а пост остаётся, и голосовать по нему продолжают.
    row = next((r for r in (call.message.reply_markup.inline_keyboard if
                            call.message and call.message.reply_markup else [])
                if r and (r[0].callback_data or "").startswith("tpick_")), None)
    names = [_name_on(b) for b in row] if row and len(row) == 2 else None

    total = sum(counts)
    mine = names[side] if names else "этого игрока"
    # «Ваш выбор: Рублёв», а не «вы за Рублёва»: фамилию в винительном
    # падеже автоматически не поставить — Швёнтек и Медведев склоняются
    # по-разному, а часть имён вообще не склоняется.
    if total < PICK_MIN:
        await call.answer(
            f"Ваш выбор: {mine}.\n\nПока голосов: {total}. Покажу расклад, "
            f"когда наберётся {PICK_MIN}.", show_alert=True)
    else:
        share = round(counts[side] * 100 / total)
        await call.answer(
            f"Ваш выбор: {mine}.\n\nТак же думают {share}% — из {total} "
            f"{_votes_word(total)}.", show_alert=True)

    if not names:
        return
    fresh = _pick_labels(match_id, names, counts)
    keyboard = [fresh if r is row else r
                for r in call.message.reply_markup.inline_keyboard]
    try:
        await call.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    except Exception:
        pass          # разметка могла не измениться — это не ошибка


def _votes_word(n: int) -> str:
    if 11 <= n % 100 <= 14:
        return "проголосовавших"
    return {1: "проголосовавшего"}.get(n % 10, "проголосовавших")


@router.callback_query(F.data.startswith("tmatch_"))
async def toggle_match(call: CallbackQuery):
    try:
        _, tour, match_id = call.data.split("_", 2)
    except ValueError:
        await call.answer()
        return

    # Подписка проверяется здесь, а не при показе: расписание видят все,
    # платят только за напоминание. Так пост работает и как витрина.
    if not await _allowed(call.from_user.id):
        # Не «у вас нет подписки», а сразу экран, где её оформляют.
        await _open_bot(call, "sport_tennis", NO_SUB)
        return

    matches = await _today(tour)
    match = next((m for m in matches if m["id"] == match_id), None)
    if match is None:
        # Пост мог пролежать до завтра, матч — переехать в другой день
        # или выпасть из крупных турниров. Ищем шире, прежде чем сдаться:
        # подписка без времени начала не сработает никогда.
        match = await _find_match(tour, match_id)

    starts = _starts(match) if match else None
    # Подписка без времени начала не сработает никогда: due_alerts
    # выбирает по времени, а его нет. Раньше такая запись молча ложилась
    # в базу — человек видел «напоминание включено» и не получал ничего.
    #
    # Снять старую подписку при этом можно всегда: кнопка, которая
    # перестала отжиматься, хуже кнопки, которая не нажимается.
    if starts is None and not await database.alert_exists(call.from_user.id,
                                                          match_id):
        logging.warning(
            f"Теннис: подписка без времени начала — {tour}/{match_id}, "
            f"матч {'не найден' if match is None else 'без даты'}")
        await call.answer(
            "Время этого матча ещё не назначено — напомнить не получится.\n\n"
            "Загляните в сетку: как только корт и час известны, матч "
            "появится в расписании дня.", show_alert=True)
        return

    title = _title(match) if match else "матч"

    # В базу — с турниром (это уйдёт в личку), на кнопку — короткое имя.
    full = _full_title(match) if match else title
    added, total = await database.toggle_alert(
        call.from_user.id, match_id, tour, full, starts)

    if added is None:
        await call.answer("Не получилось сохранить. Нажмите ещё раз.",
                          show_alert=True)
        return

    try:
        await call.message.edit_reply_markup(
            reply_markup=_with_count(call.message.reply_markup,
                                     f"tmatch_{tour}_{match_id}", title, total))
    except Exception:
        pass

    # Кнопка в канале одна на всех: Telegram не умеет показывать разным
    # читателям разные подписи. Личный переключатель поэтому уезжает в
    # личку — там клавиатура своя у каждого, и колокольчик честно
    # показывает состояние.
    if added:
        sent = await _confirm(call.bot, call.from_user.id, tour, match_id, full, starts)
        if sent:
            lead = await _lead()
            await call.answer("🔔 " + _lead_phrase(lead))
        else:
            # Бот не может написать первым: открываем его нажатием, а матч
            # передаём параметром — подписка доедет сама.
            await _open_bot(call, f"tm-{tour}-{match_id}", NO_CHAT)
    else:
        await call.answer("🔕 Напоминание снято")


async def _confirm(bot: Bot, user_id: int, tour: str, match_id: str,
                   title: str, starts) -> bool:
    """Личное подтверждение с кнопкой «выключить». False — бот не пишет."""
    shift = await _shift()
    when = (starts + shift).strftime("%H:%M") if starts else "по расписанию"
    lead = await _lead()
    text = (f"🔔 <b>Напоминание включено</b>\n\n{html.escape(title)}\n"
            f"Начало в {when}. {_lead_phrase(lead)}\n\n"
            f"<i>Придёт только вам. На кнопке в канале видно лишь число — "
            f"сколько человек собирается смотреть.</i>")
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="🔕 Выключить напоминание",
        callback_data=f"tmute_{tour}_{match_id}")]])
    try:
        await bot.send_message(user_id, text, reply_markup=markup)
        return True
    except TelegramForbiddenError:
        return False
    except Exception as e:
        logging.warning(f"Подтверждение {user_id} не ушло: {e}")
        return False


@router.callback_query(F.data.startswith("tmute_"))
async def mute_match(call: CallbackQuery):
    """Выключение из личного сообщения — колокольчик меняется на месте"""
    try:
        _, tour, match_id = call.data.split("_", 2)
    except ValueError:
        await call.answer()
        return
    off = await database.drop_alert(call.from_user.id, match_id)
    try:
        await call.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🔔 Включить обратно",
                    callback_data=f"tback_{tour}_{match_id}")]]))
    except Exception:
        pass
    await call.answer("🔕 Выключено" if off else "Уже было выключено")


@router.callback_query(F.data.startswith("tback_"))
async def unmute_match(call: CallbackQuery):
    try:
        _, tour, match_id = call.data.split("_", 2)
    except ValueError:
        await call.answer()
        return
    matches = await _today(tour)
    match = next((m for m in matches if m["id"] == match_id), None)
    added = await database.ensure_alert(
        call.from_user.id, match_id, tour,
        _full_title(match) if match else "матч",
        _starts(match) if match else None)
    if added is None:
        await call.answer("Не получилось. Нажмите ещё раз.", show_alert=True)
        return
    try:
        await call.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🔕 Выключить напоминание",
                    callback_data=f"tmute_{tour}_{match_id}")]]))
    except Exception:
        pass
    await call.answer("🔔 Включено")


def _with_count(markup, data: str, title: str, total: int):
    """Обновляет только свою кнопку: соседние матчи не трогаем"""
    rows = []
    for row in (markup.inline_keyboard if markup else []):
        rows.append([
            InlineKeyboardButton(
                text=f"🔔 {title[:34]}" + (f" · {total}" if total else ""),
                callback_data=b.callback_data)
            if b.callback_data == data else b
            for b in row])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# =====================================================================
# ДОСТАВКА
# =====================================================================

# Слова, которыми источник помечает несостоявшийся матч. Проверяем по ним,
# а не по исчезновению из расписания: пропасть матч может и потому, что его
# перенесли на другой день, — а это не отмена.
CANCELLED = ("cancel", "postponed", "walkover", "abandoned", "suspended")

# Источник пишет по-английски, а сообщение уходит читателю.
# Фразы целиком, а не одним словом: «матч» + «соперник снялся» в одну
# строку не склеивается.
WHY = {
    "cancel": "Матч отменён.",
    "postponed": "Матч перенесли на другой день.",
    "walkover": "Соперник снялся — матча не будет.",
    "abandoned": "Матч прервали и не доиграли.",
    "suspended": "Матч остановлен.",
}


def _why(state: str) -> str:
    low = (state or "").lower()
    for word, russian in WHY.items():
        if word in low:
            return russian
    return "Матч отменён."


def _cancelled(match) -> bool:
    state = (match.get("state") or "").lower()
    return any(word in state for word in CANCELLED)


async def _tell_cancelled(bot: Bot, match_id: str, state: str):
    """Сказать подписчикам, что матча не будет, и закрыть напоминания"""
    people = await database.alert_subscribers(match_id)
    if not people:
        return 0
    for user_id, title, tour in people:
        text = (f"🚫 <b>{html.escape(title or 'Матч')}</b>\n\n"
                f"{_why(state)} Напоминание снимаю — когда матч поставят "
                f"заново, он снова появится в расписании.")
        try:
            await bot.send_message(
                user_id, text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text=f"🗓 Сетка {tennis_live.TOURS.get(tour, {}).get('title', '')}".strip(),
                        url=tennis_live.TOURS.get(tour, {}).get(
                            "draws", tennis_live.TOURS["atp"]["draws"]))]]))
        except TelegramForbiddenError:
            logging.info(f"Отмена: {user_id} заблокировал бота")
        except Exception as e:
            logging.warning(f"Отмена {user_id} не ушла: {e}")
        await asyncio.sleep(0.1)
    await database.close_alerts(match_id)
    return len(people)


async def refresh_times(bot: Bot = None) -> int:
    """Сверить время начала у матчей, о которых ещё не напомнили.

    Теннисное расписание плавает: корт освобождается, когда доиграет
    предыдущая пара, и матч сдвигается на час-другой. Время мы запомнили в
    момент подписки, и без сверки напоминание пришло бы к тому времени,
    которого уже нет. Источник время пересматривает — берём оттуда.
    """
    waiting = await database.pending_matches()
    if not waiting:
        return 0

    fresh, dead = {}, {}
    for tour in {t for _, t in waiting}:
        try:
            data = await tennis_live.fetch_scoreboard(tour)
            # Без big_only: отбор по величине турнира нужен ленте канала,
            # а здесь он терял матчи, на которые уже подписались. Время у
            # них не обновлялось, отмена не замечалась — напоминание
            # молчало, хотя запись в базе была.
            for match in tennis_live._singles(data, tour, big_only=False):
                if not match.get("id"):
                    continue
                if _cancelled(match):
                    dead[match["id"]] = match.get("state") or ""
                    continue
                when = _starts(match)
                if when:
                    fresh[match["id"]] = when
        except Exception as e:
            logging.warning(f"Расписание {tour} не сверилось: {e}")

    moved = 0
    for match_id, _ in waiting:
        if match_id in dead:
            if bot:
                await _tell_cancelled(bot, match_id, dead[match_id])
            continue
        when = fresh.get(match_id)
        if when and await database.update_alert_time(match_id, when):
            moved += 1
    if moved:
        logging.info(f"Теннис: перенесено матчей {moved}")

    # Подписка без времени — это молчание на стороне читателя. Пока матч
    # в табличке, сверка выше проставит ему время. Если он не появился
    # вторые сутки, сетка ушла вперёд: запись не сработает уже никогда и
    # только прячет настоящие проблемы за своим числом.
    stuck = await database.timeless_alerts()
    if stuck:
        logging.warning(f"Теннис: подписок без времени начала — {stuck}")
        gone = await database.drop_timeless_alerts()
        if gone:
            logging.info(f"Теннис: убрано безнадёжных подписок {gone}")
    return moved


async def _find_match(tour: str, match_id: str):
    """Матч по номеру в свежей табличке. None — если его там уже нет."""
    data = await tennis_live.fetch_scoreboard(tour)
    for match in tennis_live._singles(data, tour, big_only=False):
        if str(match.get("id")) == str(match_id):
            return match
    return None


async def send_results(bot: Bot) -> int:
    """Третье уведомление: матч закончился, вот кто выиграл и с каким счётом.

    Без него подписка обрывается на полуслове: человеку сказали, что
    матч начинается, и замолчали. Итог — то, ради чего он и подписывался.

    Шлём только тем, кто получил напоминание о начале: кто не ждал матча,
    тому и результат не новость.
    """
    sent = 0
    waiting = await database.awaiting_result()
    if not waiting:
        return 0

    # Табличку тянем по одному разу на турнир, а не на каждого человека:
    # на одном матче подписчиков бывает десяток.
    cache = {}
    for user_id, match_id, tour, title in waiting:
        key = (tour, match_id)
        if key not in cache:
            cache[key] = await _find_match(tour, match_id)
        match = cache[key]
        if not match:
            continue

        if _cancelled(match):
            await database.mark_result_sent(user_id, match_id)
            continue
        if not match.get("completed"):
            continue

        line = _result_line(match)
        if not line:
            await database.mark_result_sent(user_id, match_id)
            continue

        try:
            await bot.send_message(
                user_id,
                f"🏁 <b>Матч завершён</b>\n\n{line}",
                disable_web_page_preview=True)
            sent += 1
        except TelegramForbiddenError:
            logging.info(f"Итог: {user_id} заблокировал бота")
        except Exception as e:
            logging.warning(f"Итог {user_id} не ушёл: {e}")
            continue
        await database.mark_result_sent(user_id, match_id)
        await asyncio.sleep(0.1)
    return sent


async def _events_to_channel(bot: Bot) -> None:
    """Громкие события в канал, если канал задан.

    Отдельной функцией, потому что в расписании планировщика ошибка не
    должна ронять напоминания: канал может быть не настроен, а ссылки
    людям уходить обязаны.
    """
    try:
        import digest
        chat, thread = await digest._target()
        if chat:
            await publish_events(bot, chat, thread)
    except Exception as e:
        logging.warning(f"События в канал не ушли: {e}")


async def _champion_to_channel(bot: Bot) -> None:
    """Пост о победителе турнира, если канал задан"""
    try:
        import digest
        import tennis_champion
        chat, thread = await digest._target()
        if chat:
            await tennis_champion.publish(bot, chat, thread)
    except Exception as e:
        logging.warning(f"Чемпион в канал не ушёл: {e}")


async def alerts_scheduler(bot: Bot):
    """Раз в две минуты смотрит, кому пора слать ссылку.

    Заблокировавший бота помечается доставленным: повторять некому, а
    вечно висящее напоминание засоряет очередь.
    """
    await asyncio.sleep(90)
    ticks = 0
    while True:
        try:
            # Сверяем время раз в десять минут: чаще незачем, а реже можно
            # не успеть заметить перенос.
            if ticks % 10 == 0:
                await refresh_times(bot)
            # Итоги реже, чем напоминания: матч не заканчивается в ту же
            # минуту, а лишний запрос к табличке стоит денег и лимитов.
            if ticks % 5 == 0:
                await send_results(bot)
            # Громкие события — в канал, пока они ещё события. Снятие,
            # о котором читатель узнаёт наутро из таблицы, новостью
            # быть перестало.
            if ticks % 5 == 2:
                await _events_to_channel(bot)
            # Чемпион — реже всех: финалы идут раз в неделю на турнир,
            # а пост о них тянет рейтинг и карточку из Википедии.
            if ticks % 15 == 7:
                await _champion_to_channel(bot)
            ticks += 1

            lead = await _lead()
            for user_id, match_id, tour, title in await database.due_alerts(lead):
                head = ("Начинается" if lead <= 0
                        else f"Начнётся через {lead} {_minutes_word(lead)}")
                text = (f"🎾 <b>{html.escape(title or 'Матч')}</b>\n\n"
                        f"{head}. Где смотреть:")
                markup = InlineKeyboardMarkup(inline_keyboard=_watch_rows(tour))
                try:
                    await bot.send_message(user_id, text,
                                           reply_markup=markup,
                                           disable_web_page_preview=True)
                except TelegramForbiddenError:
                    logging.info(f"Напоминание: {user_id} заблокировал бота")
                except Exception as e:
                    logging.warning(f"Напоминание {user_id} не ушло: {e}")
                    continue
                await database.mark_alert_sent(user_id, match_id)
                await asyncio.sleep(0.1)
        except Exception as e:
            logging.error(f"Ошибка рассылки напоминаний: {e}")
        await asyncio.sleep(CHECK_EVERY)
