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
from aiogram.types import (
    CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

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
# 1% — типично для безналичного обмена, 2% — для наличного.
SPREADS = (1.0, 2.0)

RETRO = {
    "ru": ("\n\n📐 **Что дали эти {days} дней**\n"
           "_100 единиц валюты, переложенные в доллар в начале периода и обменянные "
           "обратно сегодня — по биржевому курсу и со спредом обменника. "
           "В скобках изменение к исходной сотне._\n"),
    "en": ("\n\n📐 **What these {days} days did**\n"
           "_100 units moved into dollars at the start of the period and back today — "
           "At the market rate and with an exchange spread; the change against the "
           "starting 100 is in brackets._\n"),
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
        # 100 единиц валюты → доллары по курсу начала → обратно по курсу конца.
        # Спред платится дважды: доллары покупаем дороже, продаём дешевле.
        cells = [100 * end / start]
        cells += [100 / (start * (1 + sp / 100)) * (end * (1 - sp / 100))
                  for sp in SPREADS]
        retro.append(f"{meta['flag']} " + "  ".join(
            f"{v:5.1f} ({v - 100:+.1f})" for v in cells))

    if retro:
        lines.append(_t(RETRO, lang).format(days=DAYS))
        head = ("биржа" if lang == "ru" else "market")
        header = ("   " + f"{head:^13}" +
                  "".join(f"{f'спред {sp:.0f}%' if lang == 'ru' else f'spread {sp:.0f}%':^15}"
                          for sp in SPREADS))
        lines.append("`" + header + "`\n" + "\n".join(f"`{row}`" for row in retro))

    return "".join(lines)


@router.callback_query(F.data == "fx_rates")
async def show_rates(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    await call.message.answer(
        await render(lang), parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=_t(BTN_CALC, lang), callback_data="fx_calc")],
            [InlineKeyboardButton(text=_t(BACK, lang), callback_data="sport_news")],
        ])
    )


# =====================================================================
# 🧮 КАЛЬКУЛЯТОР
# =====================================================================
# Доллар — база, курсы хранятся как «сколько валюты за один доллар», поэтому
# любая пара считается через него: сумма → доллары → нужная валюта.

CALC_ORDER = ["USD", "EUR", "ILS", "RUB"]
# «in» — предложный падеж для фразы «сумму в рублях»: именительный из кнопки
# в неё не подставить.
CALC_META = {
    "USD": {"flag": "🇺🇸", "ru": "Доллар", "en": "Dollar", "sign": "$", "in": "долларах"},
    "EUR": {"flag": "🇪🇺", "ru": "Евро", "en": "Euro", "sign": "€", "in": "евро"},
    "ILS": {"flag": "🇮🇱", "ru": "Шекель", "en": "Shekel", "sign": "₪", "in": "шекелях"},
    "RUB": {"flag": "🇷🇺", "ru": "Рубль", "en": "Rouble", "sign": "₽", "in": "рублях"},
}


class CalcState(StatesGroup):
    waiting_amount = State()


CALC_PICK = {
    "ru": "🧮 **Калькулятор валют**\n\nВыберите, в какой валюте вводите сумму:",
    "en": "🧮 **Currency calculator**\n\nPick the currency you will enter:",
}
CALC_ASK = {
    "ru": "Введите сумму в {name} ({sign}). Можно присылать числа подряд — "
          "каждое пересчитаю.",
    "en": "Enter the amount in {name} ({sign}). Send numbers one after another — "
          "each will be converted.",
}
CALC_BAD = {
    "ru": "Не похоже на число. Пришлите, например: 1000",
    "en": "That is not a number. Send something like: 1000",
}
CALC_NO_RATES = {
    "ru": "Курсы сейчас недоступны — пересчитать не могу.",
    "en": "Rates are unavailable right now.",
}
BTN_CALC = {"ru": "🧮 Калькулятор", "en": "🧮 Calculator",
            "fr": "🧮 Calculatrice", "he": "🧮 מחשבון"}
BTN_OTHER = {"ru": "🔄 Другая валюта", "en": "🔄 Another currency"}
BTN_DONE = {"ru": "✅ Готово", "en": "✅ Done"}


async def latest_rates() -> dict:
    """{валюта: сколько её дают за $1}. Доллар к себе — единица."""
    series = await fetch_series()
    rates = {"USD": 1.0}
    for code, points in series.items():
        if points:
            rates[code] = points[-1][1]
    return rates if len(rates) > 1 else {}


def _amount(text: str):
    """Число из сообщения: принимаем запятую и пробелы между разрядами"""
    cleaned = text.replace(",", ".").replace(" ", "").replace(" ", "")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if 0 < value < 1e12 else None


def _pick_markup(lang: str) -> InlineKeyboardMarkup:
    rows, pair = [], []
    for code in CALC_ORDER:
        meta = CALC_META[code]
        pair.append(InlineKeyboardButton(
            text=f"{meta['flag']} {meta['ru' if lang == 'ru' else 'en']}",
            callback_data=f"fxcalc_{code}"))
        if len(pair) == 2:
            rows.append(pair); pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton(text=_t(BACK, lang), callback_data="fx_rates")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "fx_calc")
async def calc_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    await state.clear()
    await call.message.answer(_t(CALC_PICK, lang), parse_mode="Markdown",
                              reply_markup=_pick_markup(lang))


@router.callback_query(F.data.startswith("fxcalc_"))
async def calc_pick(call: CallbackQuery, state: FSMContext):
    await call.answer()
    code = call.data.removeprefix("fxcalc_")
    if code not in CALC_META:
        return

    lang = await database.get_user_language(call.from_user.id)
    await state.set_state(CalcState.waiting_amount)
    await state.update_data(calc_code=code, calc_lang=lang)

    meta = CALC_META[code]
    name = meta["in"] if lang == "ru" else meta["en"].lower() + "s"
    await call.message.answer(_t(CALC_ASK, lang).format(name=name, sign=meta["sign"]))


@router.message(CalcState.waiting_amount, F.text, ~F.text.startswith("/"))
async def calc_convert(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("calc_lang", "ru")
    code = data.get("calc_code", "USD")

    value = _amount(message.text)
    if value is None:
        await message.answer(_t(CALC_BAD, lang))
        return

    rates = await latest_rates()
    if code not in rates:
        await message.answer(_t(CALC_NO_RATES, lang))
        return

    in_usd = value / rates[code]
    lines = []
    for other in CALC_ORDER:
        if other not in rates:
            continue
        meta = CALC_META[other]
        amount = in_usd * rates[other]
        mark = "▪" if other == code else " "
        lines.append(f"{mark} {meta['flag']} `{amount:>12,.2f}` {meta['sign']}"
                     .replace(",", " "))

    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=_t(BTN_OTHER, lang), callback_data="fx_calc"),
        InlineKeyboardButton(text=_t(BTN_DONE, lang), callback_data="fx_rates"),
    ]])
    await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=markup)
