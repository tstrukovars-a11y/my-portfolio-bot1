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

USD_LABEL = {"flag": "🇺🇸", "ru": "Доллар", "en": "Dollar"}

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


def dollar_index(series: dict) -> list:
    """Сила доллара к корзине из трёх валют, начало периода = 100.

    Отдельной строкой курс доллара показать нельзя — он здесь база, и к самому
    себе всегда равен единице. Зато видно, как он двигался против остальных:
    берём даты, которые есть у всех трёх рядов, и усредняем изменение к старту.
    """
    maps = {code: dict(points) for code, points in series.items() if points}
    if len(maps) < 2:
        return []

    common = sorted(set.intersection(*(set(m) for m in maps.values())))
    if len(common) < 2:
        return []

    base = {code: maps[code][common[0]] for code in maps}
    index = []
    for day in common:
        ratios = [maps[code][day] / base[code] for code in maps if base[code]]
        index.append(sum(ratios) / len(ratios) * 100)
    return index


def strength(values: list) -> list:
    """Ряд силы валюты к доллару: старт = 100, рост = валюта крепнет.

    Исходный ряд — сколько валюты дают за доллар, и он растёт, когда валюта
    СЛАБЕЕТ. Показывать такой график под названием валюты значит вводить
    в заблуждение: строка «Евро ▼» читалась как падение евро, хотя падал
    доллар. Поэтому переворачиваем: теперь и стрелка, и столбики говорят
    об одном и том же — о названной валюте.
    """
    base = values[0]
    return [base / v * 100 for v in values if v] if base else []


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


def _verdict(last_strength: float, name: str, lang: str, versus: str = None) -> str:
    """Словами: кто именно укрепился и к чему. Проценты без этого читают наугад.

    Ориентир передаётся отдельно: у доллара он не «к доллару», а к корзине.
    """
    if lang == "ru":
        against = versus or "к доллару"
        if last_strength >= 100.05:
            return f"{name.lower()} укрепился {against}"
        if last_strength <= 99.95:
            return f"{name.lower()} ослаб {against}"
        return f"без изменений {against}"

    against = versus or "against the dollar"
    if last_strength >= 100.05:
        return f"stronger {against}"
    if last_strength <= 99.95:
        return f"weaker {against}"
    return f"unchanged {against}"


# Спред обменника: курс покупки и продажи хуже биржевого, и платится он дважды.
# Один процент в каждую сторону — типичная величина для безналичного обмена.
SPREAD = 1.0

RETRO = {
    "ru": ("\n\n📐 **Что дали эти {days} дней**\n"
           "_100 единиц валюты, переложенные в доллар в начале периода и обменянные "
           "обратно сегодня. Вторая колонка — то же со спредом {spread:.0f}% "
           "в каждую сторону._\n"),
    "en": ("\n\n📐 **What these {days} days did**\n"
           "_100 units moved into dollars at the start of the period and back today. "
           "The second column is the same with a {spread:.0f}% spread each way._\n"),
}

HEADER = {
    "ru": "💱 **Курсы к доллару — {days} дней**\n",
    "en": "💱 **Rates against the dollar — {days} days**\n",
}

EMPTY = {
    "ru": "💱 Курсы сейчас недоступны — источники не отвечают. Попробуйте позже.",
    "en": "💱 Rates are unavailable right now. Please try later.",
}

FOOTER = {
    "ru": ("\n_Каждая строка — о своей валюте: столбики и процент показывают её силу "
           "к доллару, начало периода принято за 100. Растёт — валюта крепнет._\n"
           "_Евро и шекель — данные ЕЦБ, рубль — Банка России: ЕЦБ рубль больше "
           "не публикует._"),
    "en": ("\n_Each line is about its own currency: the bars and the percentage show its "
           "strength against the dollar, with the start of the period set to 100. Rising "
           "means the currency is gaining._\n"
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
        own = strength(values)
        if not own:
            continue
        verdict = _verdict(own[-1], meta[name_key], lang)
        rate = (f"за $1 дают {values[-1]:.2f}" if lang == "ru"
                else f"{values[-1]:.2f} per $1")
        lines.append(
            f"\n{meta['flag']} **{meta[name_key]}** · `{rate}`"
            f"\n{_trend(own, lang)} — {verdict}"
            f"\n`{sparkline(own)}`"
        )

    # Доллар идёт последним: он не курс, а сводный индекс, и логично читается
    # после валют, из которых собран.
    index = dollar_index(series)
    if index:
        verdict = _verdict(index[-1], USD_LABEL[name_key], lang,
                           versus="к корзине" if lang == "ru" else "against the basket")
        basket = ("к корзине из евро, шекеля и рубля" if lang == "ru"
                  else "against a basket of euro, shekel and rouble")
        lines.append(
            f"\n{USD_LABEL['flag']} **{USD_LABEL[name_key]}** · `{basket}`"
            f"\n{_trend(index, lang)} — {verdict}"
            f"\n`{sparkline(index)}`"
        )

    lines.append(_t(FOOTER, lang))

    # Ретроспектива: показываем результат вложения задним числом. Это факт о
    # прошлом, а не совет — оговорка идёт следом и не выносится в мелкий шрифт.
    retro = []
    for code, meta in CURRENCIES.items():
        points = series.get(code)
        if not points or len(points) < 2:
            continue
        start, end = points[0][1], points[-1][1]
        if not start:
            continue
        # 100 единиц валюты → доллары по курсу начала → обратно по курсу конца
        result = 100 * end / start
        # Спред платится дважды: доллары покупаем дороже, продаём дешевле
        net = 100 / (start * (1 + SPREAD / 100)) * (end * (1 - SPREAD / 100))
        delta, net_delta = result - 100, net - 100
        retro.append(
            f"{meta['flag']} `{result:6.1f}` ({delta:+.1f})"
            f"   `{net:6.1f}` ({net_delta:+.1f})"
        )

    if retro:
        lines.append(_t(RETRO, lang).format(days=DAYS, spread=SPREAD))
        lines.append("\n".join(retro))

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
