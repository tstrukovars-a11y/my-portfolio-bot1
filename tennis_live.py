# tennis_live.py — живые данные WTA: сетка турнира, итоги дня и ссылки на матчи.
#
# Источник — открытый scoreboard ESPN. Важная тонкость: этот адрес отдаёт 403 на
# браузерный User-Agent и отвечает нормально без него. Это ровно наоборот к
# RSS-лентам новостей, где браузерный заголовок обязателен.
import html
import logging
from datetime import datetime, timezone
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

API_HEADERS = {"Accept": "application/json"}

# Два тура на одном движке: отличаются лентой и разрядом внутри турнира.
TOURS = {
    "wta": {
        "url": "https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard",
        "singles": "women's singles",
        "title": "WTA",
        "ranking": "https://live-tennis.eu/ru/wta-live-ranking",
        "ranking_ru": "📈 Рейтинг теннисисток",
        "ranking_en": "📈 WTA live ranking",
        "draws": "https://live-tennis.eu/ru/wta-singles-draws",
        "schedule": "https://live-tennis.eu/ru/wta-schedule",
        "highlights": "https://youtube.com/@wta?feature=shared",
    },
    "atp": {
        "url": "https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard",
        "singles": "men's singles",
        "title": "ATP",
        "ranking": "https://live-tennis.eu/ru/atp-live-ranking",
        "ranking_ru": "📈 Рейтинг теннисистов",
        "ranking_en": "📈 ATP live ranking",
        "draws": "https://live-tennis.eu/ru/atp-singles-draws",
        "schedule": "https://live-tennis.eu/ru/atp-schedule",
        "highlights": "https://youtube.com/@atptour",
    },
}

CACHE_TTL = 60           # секунд. Время старта у источника пересматривается по ходу дня,
                         # поэтому кэш короткий — иначе бот показывает вчерашний прогноз
MAX_MATCHES = 12         # длиннее списка сообщение становится нечитаемым

_cache = {tour: {"at": 0.0, "data": None} for tour in TOURS}


# =====================================================================
# ДАННЫЕ
# =====================================================================

async def fetch_scoreboard(tour: str, force: bool = False):
    """Табло тура. Кэш свой на каждый тур, чтобы они не затирали друг друга."""
    now = time.time()
    cache = _cache[tour]
    if not force and cache["data"] is not None and now - cache["at"] < CACHE_TTL:
        return cache["data"]

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(TOURS[tour]["url"], headers=API_HEADERS)
            response.raise_for_status()
            data = response.json()
        cache.update(at=now, data=data)
        return data
    except Exception as e:
        logging.error(f"Табло {TOURS[tour]['title']} недоступно: {e}")
        return cache["data"]          # лучше показать вчерашнее, чем пустой экран


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


def _singles(data, tour: str):
    """Матчи одиночного разряда нужного тура с турниром и раундом"""
    result = []
    for event in (data or {}).get("events", []):
        tournament = event.get("name") or ""
        for grouping in event.get("groupings", []):
            name = ((grouping.get("grouping") or {}).get("displayName") or "")
            if name.lower() != TOURS[tour]["singles"]:
                continue
            for match in grouping.get("competitions", []):
                status = ((match.get("status") or {}).get("type") or {})
                state = status.get("state")
                sides = match.get("competitors") or []
                if len(sides) < 2:
                    continue
                result.append({
                    # Номер матча у источника — по нему кнопка «напомнить»
                    # связывается с матчем; без него напоминание не к чему
                    # привязать.
                    "id": str(match.get("id") or ""),
                    "tournament": tournament,
                    "round": (match.get("grouping") or {}).get("displayName") or name,
                    "sides": sides,
                    "completed": bool(status.get("completed")),
                    "live": state == "in",
                    "date": match.get("date"),
                    "state": status.get("description") or "",
                })
    return result


def _when(match, lang: str) -> str:
    """Когда начнётся — так, как это показывает поисковик: «через 5 мин».

    Абсолютное время бесполезно, пока неизвестен часовой пояс читателя, а
    относительное понятно всем. Источник пересматривает время по ходу дня, и с
    коротким кэшем бот показывает ровно то же, что видно в Google.
    """
    raw = match.get("date") or ""
    try:
        moment = datetime.strptime(raw.replace("Z", "+0000"), "%Y-%m-%dT%H:%M%z")
    except ValueError:
        return ""

    minutes = (moment - datetime.now(timezone.utc)).total_seconds() / 60
    ru = lang == "ru"

    if minutes < 1:
        return "вот-вот" if ru else "about to start"
    if minutes < 60:
        return f"через {int(minutes)} мин" if ru else f"in {int(minutes)} min"
    if minutes < 24 * 60:
        hours, rest = divmod(int(minutes), 60)
        tail = f" {rest} мин" if rest and ru else (f" {rest} min" if rest else "")
        return (f"через {hours} ч{tail}" if ru else f"in {hours} h{tail}")
    return moment.strftime("%d.%m %H:%M UTC")


def _format(match, lang: str = "ru") -> str:
    """Матч одной строкой: состояние, участники, счёт или время начала"""
    sides = sorted(match["sides"], key=lambda s: not s.get("winner"))
    left, right = sides[0], sides[1]
    names = f"{html.escape(_player(left))} — {html.escape(_player(right))}"

    if match["completed"]:
        # Победителя выделяем: в списке из десятка строк глаз должен цепляться
        # за исход, а не вычитывать счёт.
        winner = f"<b>{html.escape(_player(left))}</b>"
        pair = f"{winner} — {html.escape(_player(right))}"
        score = _score(left, right)
        tail = f"  <code>{html.escape(score)}</code>" if score else ""
        return f"🏆 {pair}{tail}"

    if match["live"]:
        score = _score(left, right)
        tail = f"  <code>{html.escape(score)}</code>" if score else ""
        return f"🔴 <b>идёт</b>  {names}{tail}"

    when = _when(match, lang)
    tail = f"  <code>{when}</code>" if when else ""
    return f"🕐 {names}{tail}"


def _tournament_links(tour: str, lang: str):
    """Полная сетка и расписание — на live-tennis.eu. Раньше вели на ESPN, но
    там страницы англоязычные и с чужой навигацией."""
    meta = TOURS[tour]
    return [
        [InlineKeyboardButton(
            text="🔗 Полная сетка" if lang == "ru" else "🔗 Full draw", url=meta["draws"])],
        [InlineKeyboardButton(
            text="🔗 Расписание всех матчей" if lang == "ru" else "🔗 Full schedule",
            url=meta["schedule"])],
    ]


# =====================================================================
# ЭКРАНЫ
# =====================================================================

HUB = {
    "ru": "🎾 **{tour}: живые данные**\n\nРасписание, итоги дня, рейтинг и трансляции. Выберите:",
    "en": "🎾 **{tour} live**\n\nSchedule, results, ranking and streams. Choose:",
    "fr": "🎾 **{tour} en direct**\n\nProgramme, résultats, classement et diffusions :",
    "he": "🎾 **{tour} בזמן אמת**\n\nלוח משחקים, תוצאות, דירוג ושידורים:"
}

UNAVAILABLE = {
    "ru": "🎾 Данные турнира сейчас недоступны — источник не отвечает. Попробуйте позже.",
    "en": "🎾 Tournament data is unavailable right now. Please try later.",
    "fr": "🎾 Données indisponibles pour le moment.",
    "he": "🎾 הנתונים אינם זמינים כרגע."
}

NO_MATCHES = {
    "ru": "Сейчас нет матчей одиночного разряда — между турнирами такое бывает.",
    "en": "No singles matches right now — that happens between tournaments.",
    "fr": "Aucun match en simple actuellement.",
    "he": "אין כרגע משחקי יחידים."
}

BTN_RESULTS = {"ru": "🏆 Итоги дня", "en": "🏆 Today's results",
               "fr": "🏆 Résultats du jour", "he": "🏆 תוצאות היום"}
BTN_DRAW = {"ru": "🗓 Расписание и сетка", "en": "🗓 Schedule & draw",
            "fr": "🗓 Programme", "he": "🗓 לוח משחקים"}
BACK = {"ru": "🔙 Назад", "en": "🔙 Back", "fr": "🔙 Retour", "he": "🔙 חזרה"}

# Проверенные площадки, которые ведёт владелец бота
PRIME_SPORT_URL = "https://vk.com/tennisprimesport"
BOLSHE_URL = "https://vk.com/tennis_bolshe"

BTN_WATCH = {"ru": "📺 Где смотреть", "en": "📺 Where to watch",
             "fr": "📺 Où regarder", "he": "📺 איפה לצפות"}
BTN_HIGHLIGHTS = {"ru": "🎬 Хайлайты игр", "en": "🎬 Match highlights",
                  "fr": "🎬 Résumés des matchs", "he": "🎬 תקצירי משחקים"}


def _t(mapping: dict, lang: str) -> str:
    return mapping.get(lang, mapping["en"])


def _tour_of(data: str) -> str:
    """Тур зашит первым словом callback: «wta_results», «atp_draw»"""
    prefix = data.split("_", 1)[0]
    return prefix if prefix in TOURS else "wta"


@router.callback_query(F.data.in_({"tennis_wta", "tennis_atp"}))
async def open_hub(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    tour = "atp" if call.data.endswith("atp") else "wta"
    meta = TOURS[tour]

    caption = _t(HUB, lang).format(tour=meta["title"])
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_t(BTN_RESULTS, lang), callback_data=f"{tour}_results")],
        [InlineKeyboardButton(text=_t(BTN_DRAW, lang), callback_data=f"{tour}_draw")],
        [InlineKeyboardButton(text=_t(BTN_WATCH, lang), callback_data=f"{tour}_watch")],
        # Подпись рейтинга своя у каждого тура: «участниц» на мужском туре — ляп
        [InlineKeyboardButton(
            text=meta["ranking_ru"] if lang == "ru" else meta["ranking_en"],
            url=meta["ranking"])],
        [InlineKeyboardButton(text=_t(BTN_HIGHLIGHTS, lang), url=meta["highlights"])],
        [InlineKeyboardButton(text=_t(BACK, lang), callback_data="sport_tennis")],
    ])
    try:
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.TENNIS_BANNER, caption=caption,
                                  parse_mode="Markdown"),
            reply_markup=markup
        )
    except TelegramBadRequest:
        await call.message.answer(caption, parse_mode="Markdown", reply_markup=markup)


def _fallback_markup(tour: str, lang: str) -> InlineKeyboardMarkup:
    """Когда источник молчит, экран всё равно должен вести дальше: ссылки на
    сетку и расписание плюс возврат. Иначе получается тупик."""
    rows = _tournament_links(tour, lang)
    rows.append([InlineKeyboardButton(text=_t(BACK, lang), callback_data=f"tennis_{tour}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


SCHEDULE_NOTE = {
    "ru": "\n\n<i>Обновляется вместе с источником — жмите «Обновить» перед началом матча.</i>",
    "en": "\n\n<i>Updates with the source — tap Refresh right before a match.</i>",
    "fr": "\n\n<i>Mis à jour avec la source.</i>",
    "he": "\n\n<i>מתעדכן יחד עם המקור.</i>"
}


async def _send(call: CallbackQuery, lang: str, tour: str, heading: str, matches,
                note: str = "", refresh: str = None):
    rows = _tournament_links(tour, lang)
    if refresh:
        rows.insert(0, [InlineKeyboardButton(
            text="🔄 Обновить" if lang == "ru" else "🔄 Refresh", callback_data=refresh)])
    rows.append([InlineKeyboardButton(text=_t(BACK, lang), callback_data=f"tennis_{tour}")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)

    if not matches:
        await call.message.answer(_t(NO_MATCHES, lang), reply_markup=markup)
        return

    lines = [heading, ""]
    for match in matches[:MAX_MATCHES]:
        lines.append(_format(match, lang))

    if len(matches) > MAX_MATCHES:
        lines.append(f"\n<i>…и ещё {len(matches) - MAX_MATCHES}</i>")

    await call.message.answer("\n".join(lines) + note, parse_mode="HTML",
                              disable_web_page_preview=True, reply_markup=markup)


@router.callback_query(F.data.in_({"wta_results", "atp_results"}))
async def show_results(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    tour = _tour_of(call.data)

    data = await fetch_scoreboard(tour)
    if data is None:
        await call.message.answer(_t(UNAVAILABLE, lang), reply_markup=_fallback_markup(tour, lang))
        return

    matches = [m for m in _singles(data, tour) if m["completed"]]
    matches.reverse()          # свежие сверху
    tournament = matches[0]["tournament"] if matches else TOURS[tour]["title"]
    heading = (f"🏆 <b>Итоги дня — {html.escape(tournament)}</b>" if lang == "ru"
               else f"🏆 <b>Results — {html.escape(tournament)}</b>")
    await _send(call, lang, tour, heading, matches, refresh=f"{tour}_results")


@router.callback_query(F.data.in_({"wta_draw", "atp_draw"}))
async def show_draw(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    tour = _tour_of(call.data)

    # Расписание всегда свежее: время старта пересматривается по ходу дня
    data = await fetch_scoreboard(tour, force=True)
    if data is None:
        await call.message.answer(_t(UNAVAILABLE, lang), reply_markup=_fallback_markup(tour, lang))
        return

    matches = [m for m in _singles(data, tour) if not m["completed"]]
    matches.sort(key=lambda m: (not m["live"], m.get("date") or ""))
    tournament = matches[0]["tournament"] if matches else TOURS[tour]["title"]
    heading = (f"🗓 <b>Расписание — {html.escape(tournament)}</b>" if lang == "ru"
               else f"🗓 <b>Schedule — {html.escape(tournament)}</b>")
    await _send(call, lang, tour, heading, matches,
                note=_t(SCHEDULE_NOTE, lang), refresh=f"{tour}_draw")


# =====================================================================
# 📺 ГДЕ СМОТРЕТЬ
# =====================================================================
# Вещателей в ленте ESPN нет — поля broadcasts приходят пустыми, поэтому раздел
# написан, а не сгенерирован. Цен и стран нет намеренно: права пересматриваются
# каждый сезон, и устаревшая цифра хуже её отсутствия.

OFFICIAL = {
    "wta": {"name": "WTA TV", "url": "https://www.wtatv.com",
            "calendar": "https://www.wtatennis.com/tournaments",
            "wrong": "Tennis TV", "wrong_tour": "ATP, мужской тур"},
    "atp": {"name": "Tennis TV", "url": "https://www.tennistv.com",
            "calendar": "https://www.atptour.com/en/tournaments",
            "wrong": "WTA TV", "wrong_tour": "WTA, женский тур"},
}

WATCH_RU = (
    "📺 <b>Видеотрансляции {tour}</b>\n\n"
    "<b>Прайм спорт</b> и канал <b>«Больше»</b> — трансляции и разборы на русском. "
    "Начинать проще с них: без подписки и без региональных ограничений.\n\n"
    "<b>{official}</b> — официальный сервис тура, показывает его целиком, "
    "включая ранние круги. Нужны аккаунт и подписка.\n\n"
    "<b>Турниры Большого шлема идут не там.</b> У Australian Open, Roland Garros, "
    "Wimbledon и US Open свои правообладатели — смотреть у местного спортивного "
    "канала. У самих турниров часто есть бесплатные трансляции отдельных кортов "
    "на их сайте.\n\n"
    "❗️ <b>{wrong} — это {wrong_tour}.</b> Матчей нужного вам тура там нет, "
    "подписка не поможет. Путают постоянно.\n\n"
    "<b>Что сделать</b>\n"
    "1. Открыть турнир в календаре — там указан вещатель для вашей страны.\n"
    "2. Проверить доступность: матчи, права на которые куплены локально, "
    "закрыты даже для платных подписчиков.\n"
    "3. Для Большого шлема сразу искать местного вещателя."
)

WATCH_EN = (
    "📺 <b>{tour} video streaming</b>\n\n"
    "<b>{official}</b> is the tour's official service, carrying it in full including "
    "early rounds. Account and subscription required.\n\n"
    "<b>The Grand Slams are not on it</b> — they have their own rights holders and go "
    "to a national broadcaster; the tournaments often stream selected courts free on "
    "their own sites.\n\n"
    "❗️ <b>{wrong} is the other tour.</b> It carries none of these matches.\n\n"
    "<b>What to do</b>\n"
    "1. Open the tournament in the calendar — it names your country's broadcaster.\n"
    "2. Check availability: locally licensed matches stay blocked even for subscribers.\n"
    "3. For a Grand Slam, go straight to the national broadcaster."
)


@router.callback_query(F.data.in_({"wta_watch", "atp_watch"}))
async def where_to_watch(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    tour = _tour_of(call.data)
    meta, official = TOURS[tour], OFFICIAL[tour]

    template = WATCH_RU if lang == "ru" else WATCH_EN
    text = template.format(tour=meta["title"], official=official["name"],
                           wrong=official["wrong"], wrong_tour=official["wrong_tour"])

    rows = [
        [InlineKeyboardButton(text="📡 Прайм спорт", url=PRIME_SPORT_URL)],
        [InlineKeyboardButton(text="📡 Канал «Больше»", url=BOLSHE_URL)],
        [InlineKeyboardButton(text=f"🔗 {official['name']}", url=official["url"])],
        [InlineKeyboardButton(text=f"🔗 Календарь {meta['title']}" if lang == "ru"
                              else f"🔗 {meta['title']} calendar", url=official["calendar"])],
        [InlineKeyboardButton(text=_t(BACK, lang), callback_data=f"tennis_{tour}")],
    ]
    await call.message.answer(text, parse_mode="HTML",
                              disable_web_page_preview=True,
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
