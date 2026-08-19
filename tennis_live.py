# tennis_live.py — живые данные WTA: сетка турнира, итоги дня и ссылки на матчи.
#
# Источник — открытый scoreboard ESPN. Важная тонкость: этот адрес отдаёт 403 на
# браузерный User-Agent и отвечает нормально без него. Это ровно наоборот к
# RSS-лентам новостей, где браузерный заголовок обязателен.
import html
import logging
import re
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

async def fetch_scoreboard():
    """Табло WTA. Держим короткий кэш, чтобы раздел открывался мгновенно."""
    now = time.time()
    if _cache["data"] is not None and now - _cache["at"] < CACHE_TTL:
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
                sides = match.get("competitors") or []
                if len(sides) < 2:
                    continue
                result.append({
                    "tournament": tournament,
                    "links": _women_links(event, (grouping.get("grouping") or {}).get("id")),
                    "round": (match.get("grouping") or {}).get("displayName") or name,
                    "sides": sides,
                    "completed": bool(status.get("completed")),
                    "state": status.get("description") or "",
                })
    return result


def _format(match) -> str:
    """Строка матча: победитель первым, счёт, ссылка на матч"""
    sides = sorted(match["sides"], key=lambda s: not s.get("winner"))
    left, right = sides[0], sides[1]

    names = f"{html.escape(_player(left))} — {html.escape(_player(right))}"
    score = _score(left, right)
    tail = f"  <code>{html.escape(score)}</code>" if score else ""
    mark = "🏆 " if match["completed"] else "▶️ "
    return f"{mark}{names}{tail}"


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
BTN_DRAW = {"ru": "🗓 Сетка турнира", "en": "🗓 Tournament draw",
            "fr": "🗓 Tableau", "he": "🗓 המערכת"}
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


async def _send(call: CallbackQuery, lang: str, heading: str, matches):
    rows = _tournament_links(matches, lang)
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

    await call.message.answer("\n".join(lines), parse_mode="HTML",
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
    await _send(call, lang, heading, matches)


@router.callback_query(F.data == "wta_draw")
async def show_draw(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)

    data = await fetch_scoreboard()
    if data is None:
        await call.message.answer(_t(UNAVAILABLE, lang))
        return

    # В сетке интересны те, кто ещё играет: незавершённые матчи текущего круга
    matches = [m for m in _women_matches(data) if not m["completed"]]
    tournament = matches[0]["tournament"] if matches else ""
    heading = (f"🗓 <b>Сетка — {html.escape(tournament)}</b>" if lang == "ru"
               else f"🗓 <b>Draw — {html.escape(tournament)}</b>")
    await _send(call, lang, heading, matches)
