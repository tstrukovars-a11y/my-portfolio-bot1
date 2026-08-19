# tennis_live.py — живые данные WTA: сетка турнира, итоги дня и ссылки на матчи.
#
# Источник — открытый scoreboard ESPN. Важная тонкость: этот адрес отдаёт 403 на
# браузерный User-Agent и отвечает нормально без него. Это ровно наоборот к
# RSS-лентам новостей, где браузерный заголовок обязателен.
import html
import logging
import re
from datetime import datetime
import time

import httpx

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from aiogram.exceptions import TelegramBadRequest

import config
import database

router = Router()

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard"
API_HEADERS = {"Accept": "application/json"}

CACHE_TTL = 600          # секунд: счёт меняется не ежесекундно, а ходить в сеть на каждое нажатие незачем
MAX_MATCHES = 12         # длиннее списка сообщение становится нечитаемым

_cache = {"at": 0.0, "data": None}


# =====================================================================
# ДАННЫЕ
# =====================================================================

async def fetch_scoreboard(force: bool = False):
    """Табло WTA. Держим короткий кэш, чтобы раздел открывался мгновенно."""
    now = time.time()
    if not force and _cache["data"] is not None and now - _cache["at"] < CACHE_TTL:
        return _cache["data"]

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(SCOREBOARD_URL, headers=API_HEADERS)
            response.raise_for_status()
            data = response.json()
        _cache.update(at=now, data=data)
        return data
    except Exception as e:
        logging.error(f"Табло WTA недоступно: {e}")
        return _cache["data"]          # лучше показать вчерашнее, чем пустой экран


def _player(side) -> str:
    athlete = side.get("athlete") or {}
    name = athlete.get("displayName")
    if not name:
        roster = side.get("roster") or []
        name = roster[0].get("displayName") if roster else None
    return name or "—"


def _sets(side) -> list:
    """Геймы по сетам: ESPN отдаёт 6.0, приводим к «6»"""
    out = []
    for entry in side.get("linescores") or []:
        value = entry.get("value")
        if value is None:
            continue
        out.append(str(int(value)) if float(value).is_integer() else str(value))
    return out


def _score(left, right) -> str:
    """Счёт парами по сетам: «6-3 7-5», а не «6 7 : 3 5» — так его читают."""
    a, b = _sets(left), _sets(right)
    return " ".join(f"{x}-{y}" for x, y in zip(a, b))


def _women_links(event, women_id):
    """Ссылки на ЖЕНСКУЮ сетку.

    ESPN отдаёт ссылки турнира всегда с type=1 — это мужской разряд. Номер
    разряда берём из самой группировки («Women's Singles» = 2) и подставляем,
    иначе кнопка «Сетка» уводила на мужскую таблицу.
    """
    if not women_id:
        return event.get("links") or []
    fixed = []
    for link in event.get("links") or []:
        href = link.get("href") or ""
        href = re.sub(r"/type/\d+", f"/type/{women_id}", href)
        href = re.sub(r"competitionType/\d+", f"competitionType/{women_id}", href)
        fixed.append({**link, "href": href})
    return fixed


def _women_matches(data):
    """Матчи женского одиночного разряда с названием турнира и раундом"""
    result = []
    for event in (data or {}).get("events", []):
        tournament = event.get("name") or ""
        for grouping in event.get("groupings", []):
            name = ((grouping.get("grouping") or {}).get("displayName") or "")
            if "women" not in name.lower() or "double" in name.lower():
                continue
            for match in grouping.get("competitions", []):
                status = ((match.get("status") or {}).get("type") or {})
                state = status.get("state")
                sides = match.get("competitors") or []
                if len(sides) < 2:
                    continue
                result.append({
                    "tournament": tournament,
                    "links": _women_links(event, (grouping.get("grouping") or {}).get("id")),
                    "round": (match.get("grouping") or {}).get("displayName") or name,
                    "sides": sides,
                    "completed": bool(status.get("completed")),
                    "live": state == "in",
                    "date": match.get("date"),
                    "state": status.get("description") or "",
                })
    return result


def _when(match) -> str:
    """Время начала в UTC: часовой пояс читателя Telegram боту неизвестен,
    поэтому подписываем явно, а не показываем «как есть» неизвестно чей час.

    В теннисе точное время есть только у первого матча сессии. Остальные идут
    «не ранее»: корт освобождается, когда закончится предыдущий матч, а он может
    затянуться на три сета. Поэтому время помечается как ориентир.
    """
    raw = match.get("date") or ""
    try:
        moment = datetime.strptime(raw.replace("Z", "+0000"), "%Y-%m-%dT%H:%M%z")
    except ValueError:
        return ""
    return moment.strftime("%d.%m %H:%M UTC")


def _format(match) -> str:
    """Матч одной строкой: состояние, участники, счёт или время начала"""
    sides = sorted(match["sides"], key=lambda s: not s.get("winner"))
    left, right = sides[0], sides[1]
    names = f"{html.escape(_player(left))} — {html.escape(_player(right))}"

    if match["completed"]:
        score = _score(left, right)
        tail = f"  <code>{html.escape(score)}</code>" if score else ""
        return f"🏆 {names}{tail}"

    if match["live"]:
        score = _score(left, right)
        tail = f"  <code>{html.escape(score)}</code>" if score else ""
        return f"🔴 <b>идёт</b>  {names}{tail}"

    when = _when(match)
    tail = f"  <code>не ранее {when}</code>" if when else ""
    return f"🕐 {names}{tail}"


def _tournament_links(matches, lang: str):
    """ESPN не даёт ссылок на отдельные матчи, зато даёт на турнир: сводное
    табло и настоящую сетку. Их и предлагаем — это полезнее ссылки на матч."""
    rows = []
    for link in (matches[0]["links"] if matches else []):
        text, href = link.get("text"), link.get("href")
        if not href:
            continue
        if text == "Bracket":
            rows.append([InlineKeyboardButton(
                text="🔗 Сетка турнира" if lang == "ru" else "🔗 Full bracket", url=href)])
        elif text == "Summary":
            rows.append([InlineKeyboardButton(
                text="🔗 Табло матчей" if lang == "ru" else "🔗 Scoreboard", url=href)])
    return rows


# =====================================================================
# ЭКРАНЫ
# =====================================================================

HUB = {
    "ru": "🎾 **WTA: живые данные**\n\nСетка турнира, итоги дня и ссылки на матчи. Выберите:",
    "en": "🎾 **WTA live**\n\nDraw, daily results and match links. Choose:",
    "fr": "🎾 **WTA en direct**\n\nTableau, résultats du jour et liens. Choisissez :",
    "he": "🎾 **WTA בזמן אמת**\n\nהמערכת, תוצאות היום וקישורים. בחרו:"
}

UNAVAILABLE = {
    "ru": "🎾 Данные турнира сейчас недоступны — источник не отвечает. Попробуйте позже.",
    "en": "🎾 Tournament data is unavailable right now. Please try later.",
    "fr": "🎾 Données indisponibles pour le moment.",
    "he": "🎾 הנתונים אינם זמינים כרגע."
}

NO_MATCHES = {
    "ru": "Сейчас нет матчей женского одиночного разряда — между турнирами такое бывает.",
    "en": "No women's singles matches right now — that happens between tournaments.",
    "fr": "Aucun match en simple dames actuellement.",
    "he": "אין כרגע משחקי יחידות נשים."
}

BTN_RESULTS = {"ru": "🏆 Итоги дня", "en": "🏆 Today's results",
               "fr": "🏆 Résultats du jour", "he": "🏆 תוצאות היום"}
BTN_DRAW = {"ru": "🗓 Расписание и сетка", "en": "🗓 Schedule & draw",
            "fr": "🗓 Programme", "he": "🗓 לוח משחקים"}
BACK = {"ru": "🔙 Назад", "en": "🔙 Back", "fr": "🔙 Retour", "he": "🔙 חזרה"}


def _t(mapping: dict, lang: str) -> str:
    return mapping.get(lang, mapping["en"])


@router.callback_query(F.data == "tennis_wta")
async def open_hub(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_t(BTN_RESULTS, lang), callback_data="wta_results")],
        [InlineKeyboardButton(text=_t(BTN_DRAW, lang), callback_data="wta_draw")],
        [InlineKeyboardButton(text=_t(BTN_WATCH, lang), callback_data="wta_watch")],
        [InlineKeyboardButton(text=_t(BACK, lang), callback_data="sport_tennis")],
    ])
    try:
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.TENNIS_BANNER, caption=_t(HUB, lang),
                                  parse_mode="Markdown"),
            reply_markup=markup
        )
    except TelegramBadRequest:
        await call.message.answer(_t(HUB, lang), parse_mode="Markdown", reply_markup=markup)


SCHEDULE_NOTE = {
    "ru": ("\n\n<i>Время — ориентир, а не расписание. Точное начало есть только у "
           "первого матча сессии: следующий выходит на корт, когда закончится "
           "предыдущий. Сдвиг на час-два — обычное дело.</i>"),
    "en": ("\n\n<i>Times are estimates. Only the first match of a session has a fixed "
           "start; the next one begins when the previous ends. An hour or two of drift "
           "is normal.</i>"),
    "fr": "\n\n<i>Les horaires sont indicatifs : seul le premier match a une heure fixe.</i>",
    "he": "\n\n<i>הזמנים הם הערכה בלבד — רק המשחק הראשון מתחיל בשעה קבועה.</i>"
}


async def _send(call: CallbackQuery, lang: str, heading: str, matches, note: str = "",
                refresh: str = None):
    rows = _tournament_links(matches, lang)
    if refresh:
        rows.insert(0, [InlineKeyboardButton(
            text="🔄 Обновить" if lang == "ru" else "🔄 Refresh", callback_data=refresh)])
    rows.append([InlineKeyboardButton(text=_t(BACK, lang), callback_data="tennis_wta")])
    back = InlineKeyboardMarkup(inline_keyboard=rows)

    if not matches:
        await call.message.answer(_t(NO_MATCHES, lang), reply_markup=back)
        return

    lines = [heading, ""]
    for match in matches[:MAX_MATCHES]:
        lines.append(_format(match))

    if len(matches) > MAX_MATCHES:
        lines.append(f"\n<i>…и ещё {len(matches) - MAX_MATCHES}</i>")

    await call.message.answer("\n".join(lines) + note, parse_mode="HTML",
                              disable_web_page_preview=True, reply_markup=back)


@router.callback_query(F.data == "wta_results")
async def show_results(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)

    data = await fetch_scoreboard()
    if data is None:
        await call.message.answer(_t(UNAVAILABLE, lang))
        return

    matches = [m for m in _women_matches(data) if m["completed"]]
    matches.reverse()          # свежие сверху
    tournament = matches[0]["tournament"] if matches else ""
    heading = (f"🏆 <b>Итоги дня — {html.escape(tournament)}</b>" if lang == "ru"
               else f"🏆 <b>Results — {html.escape(tournament)}</b>")
    await _send(call, lang, heading, matches, refresh="wta_results")


@router.callback_query(F.data == "wta_draw")
async def show_draw(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)

    data = await fetch_scoreboard()
    if data is None:
        await call.message.answer(_t(UNAVAILABLE, lang))
        return

    # Расписание: сначала то, что идёт прямо сейчас, затем ближайшие по времени
    matches = [m for m in _women_matches(data) if not m["completed"]]
    matches.sort(key=lambda m: (not m["live"], m.get("date") or ""))
    tournament = matches[0]["tournament"] if matches else ""
    heading = (f"🗓 <b>Расписание — {html.escape(tournament)}</b>" if lang == "ru"
               else f"🗓 <b>Schedule — {html.escape(tournament)}</b>")
    await _send(call, lang, heading, matches,
                note=_t(SCHEDULE_NOTE, lang), refresh="wta_draw")


# =====================================================================
# 📺 ГДЕ СМОТРЕТЬ
# =====================================================================
# Вещателей в ленте ESPN нет — поля broadcasts приходят пустыми, поэтому раздел
# содержательный, а не сгенерированный. Конкретных цен и стран умышленно нет:
# права на показ пересматриваются каждый сезон, и устаревшая цифра хуже её
# отсутствия.

WHERE_TO_WATCH = {
    "ru": (
        "📺 <b>Где смотреть WTA</b>\n\n"
        "<b>WTA TV</b> — официальный сервис тура. Показывает большинство турниров WTA, "
        "включая ранние круги, которые не берут телеканалы. Нужен аккаунт и подписка.\n"
        "⚠️ Матчи, права на которые куплены местным вещателем, в вашей стране будут "
        "закрыты даже при активной подписке — это обычное условие таких сервисов.\n\n"
        "<b>Tennis Channel</b> — сильное покрытие тенниса, но привязан к США.\n\n"
        "<b>Местный вещатель</b> — у крупных турниров права обычно выкупает "
        "спортивный канал вашей страны, и это чаще всего самый дешёвый и стабильный путь.\n\n"
        "❗️ <b>Частая путаница:</b> Tennis TV — это <b>ATP</b>, мужской тур. "
        "Женских матчей там нет, подписка на него для WTA бесполезна.\n\n"
        "<b>Что нужно</b>\n"
        "• аккаунт и активная подписка сервиса;\n"
        "• проверить, доступен ли конкретный турнир в вашей стране — это видно "
        "на странице турнира до оплаты;\n"
        "• для больших турниров сперва посмотреть, не показывает ли его местный "
        "канал: часто дешевле и без ограничений.\n\n"
        "<i>Права на трансляции пересматриваются каждый сезон, поэтому проверяйте "
        "актуальность на странице самого турнира.</i>"
    ),
    "en": (
        "📺 <b>Where to watch WTA</b>\n\n"
        "<b>WTA TV</b> — the tour's official service, covering most WTA events including "
        "early rounds that television skips. Requires an account and a subscription.\n"
        "⚠️ Matches licensed to a local broadcaster stay blocked in your country even "
        "with an active subscription — that is standard for such services.\n\n"
        "<b>Tennis Channel</b> — strong tennis coverage, tied to the US.\n\n"
        "<b>Your local broadcaster</b> — for big events the rights usually go to a "
        "national sports channel, which is often the cheapest and most reliable route.\n\n"
        "❗️ <b>Common mix-up:</b> Tennis TV is <b>ATP</b>, the men's tour. It carries no "
        "women's matches, so it is useless for WTA.\n\n"
        "<b>What you need</b>\n"
        "• an account and an active subscription;\n"
        "• a check that the specific tournament is available in your country — shown on "
        "the tournament page before you pay;\n"
        "• for major events, check the national channel first.\n\n"
        "<i>Broadcast rights are renegotiated every season, so verify on the "
        "tournament's own page.</i>"
    )
}

BTN_WATCH = {"ru": "📺 Где смотреть", "en": "📺 Where to watch",
             "fr": "📺 Où regarder", "he": "📺 איפה לצפות"}


@router.callback_query(F.data == "wta_watch")
async def where_to_watch(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    text = WHERE_TO_WATCH.get(lang, WHERE_TO_WATCH["en"])

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 WTA TV", url="https://www.wtatv.com")],
        [InlineKeyboardButton(text="🔗 Календарь WTA" if lang == "ru" else "🔗 WTA calendar",
                              url="https://www.wtatennis.com/tournaments")],
        [InlineKeyboardButton(text=_t(BACK, lang), callback_data="tennis_wta")],
    ])
    await call.message.answer(text, parse_mode="HTML",
                              disable_web_page_preview=True, reply_markup=markup)
