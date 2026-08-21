# fx_rates.py — курсы четырёх валют с графиком за месяц.
#
# Источников два, и это вынужденно: ЕЦБ перестал публиковать рубль, поэтому
# евро и шекель берутся у него, а рубль — у Банка России. Оба открытые и без
# ключей. Доллар здесь база, его курс к самому себе равен единице.
import logging
import re
from datetime import date, timedelta

import httpx

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import database

router = Router()

DAYS = 30
CACHE_TTL_SECONDS = 3600      # курсы обновляются раз в день, чаще ходить незачем

ECB_URL = "https://api.frankfurter.app/{start}..?from=USD&to=EUR,ILS"
CBR_URL = ("https://www.cbr.ru/scripts/XML_dynamic.asp"
           "?date_req1={start}&date_req2={end}&VAL_NM_RQ=R01235")

CURRENCIES = {
    "EUR": {"flag": "🇪🇺", "ru": "Евро", "en": "Euro"},
    "ILS": {"flag": "🇮🇱", "ru": "Шекель", "en": "Shekel"},
    "RUB": {"flag": "🇷🇺", "ru": "Рубль", "en": "Rouble"},
}

# Столбики для мини-графика в тексте: картинку Telegram показал бы крупнее,
# но её пришлось бы рисовать и хранить, а так график читается прямо в сообщении.
BARS = "▁▂▃▄▅▆▇█"

_cache = {"at": None, "series": {}}


# =====================================================================
# ДАННЫЕ
# =====================================================================

async def _fetch_ecb(client: httpx.AsyncClient, start: str) -> dict:
    """{валюта: [(дата, курс), …]} по данным ЕЦБ — евро и шекель"""
    try:
        response = await client.get(ECB_URL.format(start=start), timeout=20)
        response.raise_for_status()
        rates = response.json().get("rates", {})
    except Exception as e:
        logging.warning(f"ЕЦБ не отдал курсы: {e}")
        return {}

    series = {"EUR": [], "ILS": []}
    for day in sorted(rates):
        for code in series:
            value = rates[day].get(code)
            if value is not None:
                series[code].append((day, float(value)))
    return {k: v for k, v in series.items() if v}


async def _fetch_cbr(client: httpx.AsyncClient, start: date, end: date) -> dict:
    """Рубль за доллар по данным Банка России.

    ЦБ отдаёт XML с запятой как разделителем дробной части и датами в
    формате ДД.ММ.ГГГГ — приводим к тому же виду, что у ЕЦБ.
    """
    try:
        response = await client.get(
            CBR_URL.format(start=start.strftime("%d/%m/%Y"), end=end.strftime("%d/%m/%Y")),
            timeout=20)
        response.raise_for_status()
        body = response.text
    except Exception as e:
        logging.warning(f"Банк России не отдал курсы: {e}")
        return {}

    points = []
    for raw_day, raw_value in re.findall(
            r'Date="([\d.]+)".*?<Value>([\d,]+)</Value>', body, re.S):
        d, m, y = raw_day.split(".")
        points.append((f"{y}-{m}-{d}", float(raw_value.replace(",", "."))))
    return {"RUB": sorted(points)} if points else {}


async def fetch_series() -> dict:
    """Ряды за месяц по всем валютам. Кэш на час — курс меняется раз в сутки."""
    today = date.today()
    if _cache["at"] == today and _cache["series"]:
        return _cache["series"]

    start = today - timedelta(days=DAYS)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        series = await _fetch_ecb(client, start.isoformat())
        series.update(await _fetch_cbr(client, start, today))

    if series:
        _cache.update(at=today, series=series)
    return series or _cache["series"]


# =====================================================================
# ГРАФИК
# =====================================================================

def sparkline(values: list, width: int = 24) -> str:
    """Мини-график столбиками. Ряд прореживаем до ширины сообщения."""
    if len(values) > width:
        step = len(values) / width
        values = [values[int(i * step)] for i in range(width)]

    low, high = min(values), max(values)
    if high - low < 1e-12:
        return BARS[0] * len(values)
    scale = len(BARS) - 1
    return "".join(BARS[round((v - low) / (high - low) * scale)] for v in values)


def _trend(values: list, lang: str) -> str:
    """Изменение за период в процентах — знак важнее точности"""
    first, last = values[0], values[-1]
    if not first:
        return ""
    change = (last - first) / first * 100
    if change >= 0.05:
        return f"▲ +{change:.1f}%"
    if change <= -0.05:
        return f"▼ {change:.1f}%"
    return "→ 0.0%"


HEADER = {
    "ru": "💱 **Курсы к доллару — {days} дней**\n",
    "en": "💱 **Rates against the dollar — {days} days**\n",
}

EMPTY = {
    "ru": "💱 Курсы сейчас недоступны — источники не отвечают. Попробуйте позже.",
    "en": "💱 Rates are unavailable right now. Please try later.",
}

FOOTER = {
    "ru": ("\n_Сколько валюты дают за один доллар: рост столбиков — доллар дорожает, "
           "валюта слабеет._\n"
           "_Евро и шекель — данные ЕЦБ, рубль — Банка России: ЕЦБ рубль больше "
           "не публикует._"),
    "en": ("\n_How much currency one dollar buys: rising bars mean a stronger dollar._\n"
           "_Euro and shekel from the ECB, rouble from the Bank of Russia, which the "
           "ECB no longer publishes._"),
}

BACK = {"ru": "🔙 Назад", "en": "🔙 Back", "fr": "🔙 Retour", "he": "🔙 חזרה"}
BTN_RATES = {"ru": "💱 Курсы валют", "en": "💱 Exchange rates",
             "fr": "💱 Taux de change", "he": "💱 שערי מטבע"}


def _t(mapping: dict, lang: str) -> str:
    return mapping.get(lang, mapping["en"])


async def render(lang: str) -> str:
    series = await fetch_series()
    if not series:
        return _t(EMPTY, lang)

    name_key = "ru" if lang == "ru" else "en"
    lines = [_t(HEADER, lang).format(days=DAYS)]

    for code, meta in CURRENCIES.items():
        points = series.get(code)
        if not points:
            continue
        values = [v for _, v in points]
        lines.append(
            f"\n{meta['flag']} **{meta[name_key]}** — `{values[-1]:.2f}`  {_trend(values, lang)}"
            f"\n`{sparkline(values)}`"
            f"\n`мин {min(values):.2f} · макс {max(values):.2f} · точек {len(values)}`"
            if lang == "ru" else
            f"\n{meta['flag']} **{meta[name_key]}** — `{values[-1]:.2f}`  {_trend(values, lang)}"
            f"\n`{sparkline(values)}`"
            f"\n`min {min(values):.2f} · max {max(values):.2f} · points {len(values)}`"
        )

    lines.append(_t(FOOTER, lang))
    return "".join(lines)


@router.callback_query(F.data == "fx_rates")
async def show_rates(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    await call.message.answer(
        await render(lang), parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text=_t(BACK, lang), callback_data="sport_news")]])
    )
