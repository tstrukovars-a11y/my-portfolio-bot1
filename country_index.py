# country_index.py — сравнительный индекс четырёх стран.
#
# Что это НЕ: не рейтинг экономик и не прогноз. Из четырёх заголовков в день
# такого вывести нельзя.
#
# Что это: композит из трёх понятных составляющих, формула которого показана
# пользователю прямо в боте, чтобы результат можно было проверить:
#   • тон деловых заголовков за сегодня — оценивает Claude по шкале -5…+5;
#   • инфляция и рост ВВП — фактические данные Всемирного банка.
# Значения копятся по дням, поэтому рядом с баллом видно изменение.
import asyncio
import json
import logging
from datetime import date

import httpx

import config
import database

COUNTRIES = {
    "ru": {"iso": "RUS", "cur": "RUB", "flag": "🇷🇺", "ru": "Россия", "en": "Russia"},
    "il": {"iso": "ISR", "cur": "ILS", "flag": "🇮🇱", "ru": "Израиль", "en": "Israel"},
    "fr": {"iso": "FRA", "cur": "EUR", "flag": "🇫🇷", "ru": "Франция", "en": "France"},
    "us": {"iso": "USA", "cur": "USD", "flag": "🇺🇸", "ru": "США", "en": "USA"},
}

# Веса составляющих. Сумма — единица; показываются пользователю вместе с баллом.
WEIGHT_TONE = 0.4
WEIGHT_INFLATION = 0.3
WEIGHT_GDP = 0.3

FX_URL = "https://open.er-api.com/v6/latest/USD"
WB_URL = "https://api.worldbank.org/v2/country/{iso}/indicator/{ind}?format=json&mrnev=1"
IND_INFLATION = "FP.CPI.TOTL.ZG"
IND_GDP = "NY.GDP.MKTP.KD.ZG"


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def tone_to_score(tone) -> float:
    """-5…+5 → 0…100"""
    return _clamp((tone + 5) * 10) if tone is not None else 50.0


def inflation_to_score(inflation) -> float:
    """0% → 100 баллов, 20% и выше → 0. Дефляция тоже наказывается."""
    if inflation is None:
        return 50.0
    if inflation < 0:
        return _clamp(100 + inflation * 10)
    return _clamp(100 - inflation * 5)


def gdp_to_score(gdp) -> float:
    """0% → 50 баллов, +5% → 100, -5% → 0"""
    return _clamp(50 + gdp * 10) if gdp is not None else 50.0


def composite(tone, inflation, gdp) -> float:
    return round(
        WEIGHT_TONE * tone_to_score(tone)
        + WEIGHT_INFLATION * inflation_to_score(inflation)
        + WEIGHT_GDP * gdp_to_score(gdp),
        1
    )


# =====================================================================
# СБОР ДАННЫХ
# =====================================================================

async def fetch_fx(client: httpx.AsyncClient) -> dict:
    """Курс валюты каждой страны к доллару. Для США это всегда 1."""
    try:
        response = await client.get(FX_URL, timeout=20)
        response.raise_for_status()
        rates = response.json().get("rates", {})
        return {key: rates.get(meta["cur"]) for key, meta in COUNTRIES.items()}
    except Exception as e:
        logging.warning(f"Курсы валют недоступны: {e}")
        return {}


async def fetch_worldbank(client: httpx.AsyncClient, iso: str, indicator: str):
    """Одно значение показателя. API отвечает нестабильно, поэтому три попытки,
    и запросы идут по одной стране: многострановый запрос он отвергает."""
    for attempt in range(3):
        try:
            response = await client.get(WB_URL.format(iso=iso, ind=indicator), timeout=25)
            body = response.text.strip()
            if response.status_code == 200 and body.startswith("["):
                payload = json.loads(body)
                if len(payload) > 1 and payload[1] and payload[1][0]["value"] is not None:
                    return round(float(payload[1][0]["value"]), 2)
            return None
        except Exception:
            if attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))
    logging.warning(f"Всемирный банк не ответил: {iso}/{indicator}")
    return None


async def fetch_macro(client: httpx.AsyncClient) -> dict:
    """Инфляция и рост ВВП по странам. Пропуски заполняются последним известным
    значением из базы: показатели годовые, устареть за сутки они не могут."""
    result = {}
    for key, meta in COUNTRIES.items():
        inflation = await fetch_worldbank(client, meta["iso"], IND_INFLATION)
        gdp = await fetch_worldbank(client, meta["iso"], IND_GDP)

        if inflation is None or gdp is None:
            stored_inflation, stored_gdp = await database.get_last_known_macro(key)
            inflation = inflation if inflation is not None else stored_inflation
            gdp = gdp if gdp is not None else stored_gdp

        result[key] = {"inflation": inflation, "gdp_growth": gdp}
    return result


TONE_PROMPT = (
    "You are a macroeconomic analyst. For each country below you get today's business "
    "headlines. Rate the economic tone of the news flow for each country on a scale from "
    "-5 (sharply negative) to +5 (sharply positive). Judge only the economic signal in "
    "these headlines, not your prior knowledge of the country.\n\n"
    "Reply with raw JSON only, no explanations, exactly in this shape:\n"
    '{"ru": 0, "il": 0, "fr": 0, "us": 0}\n\n'
)


async def fetch_tone(claude_client) -> dict:
    """Оценка тона заголовков. Без ключа Claude составляющая просто выключается."""
    if claude_client is None:
        return {}

    blocks = []
    for key, meta in COUNTRIES.items():
        content, _ = await database.get_daily_news(key)
        if content:
            blocks.append(f"### {key} ({meta['en']})\n{content}")

    if not blocks:
        return {}

    try:
        response = await claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=TONE_PROMPT,
            messages=[{"role": "user", "content": "\n\n".join(blocks)}]
        )
        raw = response.content[0].text.strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return {}
        parsed = json.loads(raw[start:end + 1])
        return {k: float(v) for k, v in parsed.items() if k in COUNTRIES}
    except Exception as e:
        logging.warning(f"Не удалось оценить тон новостей: {e}")
        return {}


async def refresh_index(claude_client=None):
    """Считает срез за сегодня и складывает его в базу"""
    today = date.today()
    async with httpx.AsyncClient(follow_redirects=True) as client:
        fx = await fetch_fx(client)
        macro = await fetch_macro(client)
    tone = await fetch_tone(claude_client)

    for key in COUNTRIES:
        country_tone = tone.get(key)
        inflation = macro.get(key, {}).get("inflation")
        gdp = macro.get(key, {}).get("gdp_growth")
        score = composite(country_tone, inflation, gdp)
        await database.save_country_index(
            today, key, country_tone, fx.get(key), inflation, gdp, score
        )

    logging.info(f"Индекс стран пересчитан за {today}")


# =====================================================================
# ОТОБРАЖЕНИЕ
# =====================================================================

HEADER = {
    "ru": "📊 **Сравнительный индекс стран — {date}**\n",
    "en": "📊 **Comparative country index — {date}**\n",
}

EMPTY = {
    "ru": ("📊 Индекс ещё не рассчитан.\n\nОн считается фоновой задачей раз в сутки — "
           "загляните позже."),
    "en": ("📊 The index has not been calculated yet.\n\nIt is computed by a daily "
           "background job — check back later."),
}

FOOTER = {
    "ru": ("\n\n_Формула: {t:.0%} тон деловых заголовков за сегодня (оценка Claude, шкала −5…+5) "
           "+ {i:.0%} инфляция + {g:.0%} рост ВВП. Инфляция и ВВП — данные Всемирного банка, "
           "годовые. Стрелка — изменение балла за неделю._\n"
           "_Это оценка новостного фона и макропоказателей, а не рейтинг экономик._"),
    "en": ("\n\n_Formula: {t:.0%} tone of today's business headlines (Claude, −5…+5 scale) "
           "+ {i:.0%} inflation + {g:.0%} GDP growth. Inflation and GDP come from the World "
           "Bank and are annual. The arrow is the weekly change in score._\n"
           "_This measures news tone and macro indicators, not the economies themselves._"),
}

MEDALS = ["🥇", "🥈", "🥉", "4️⃣"]


def _arrow(current, previous) -> str:
    """Стрелка изменения. Точка — сравнивать не с чем: это первый срез."""
    if previous is None or current is None:
        return "·"
    delta = current - previous
    if delta >= 0.05:
        return f"▲ +{delta:.1f}"
    if delta <= -0.05:
        return f"▼ {delta:.1f}"
    return "→ 0.0"


async def render_index(lang: str) -> str:
    day, snapshot = await database.get_latest_index()
    if not snapshot:
        return EMPTY.get(lang, EMPTY["en"])

    base_day, previous = await database.get_scores_before(day, 7)

    ranked = sorted(snapshot.items(), key=lambda kv: kv[1]["score"] or 0, reverse=True)
    name_key = "ru" if lang == "ru" else "en"

    lines = [HEADER.get(lang, HEADER["en"]).format(date=day.strftime("%d.%m.%Y"))]
    for place, (key, row) in enumerate(ranked):
        meta = COUNTRIES[key]
        medal = MEDALS[place] if place < len(MEDALS) else f"{place + 1}."
        arrow = _arrow(row["score"], previous.get(key))

        lines.append(f"\n{medal} {meta['flag']} **{meta[name_key]}** — `{row['score']:.1f}`  {arrow}")

        parts = []
        if row["tone"] is not None:
            parts.append(f"тон {row['tone']:+.1f}" if lang == "ru" else f"tone {row['tone']:+.1f}")
        if row["inflation"] is not None:
            parts.append(f"инфл. {row['inflation']:.1f}%" if lang == "ru" else f"infl. {row['inflation']:.1f}%")
        if row["gdp_growth"] is not None:
            parts.append(f"ВВП {row['gdp_growth']:+.1f}%" if lang == "ru" else f"GDP {row['gdp_growth']:+.1f}%")
        if row["fx"] and key != "us":
            parts.append(f"{COUNTRIES[key]['cur']}/USD {row['fx']:.2f}")
        if parts:
            lines.append(f"\n   `{' · '.join(parts)}`")

    footer = FOOTER.get(lang, FOOTER["en"]).format(
        t=WEIGHT_TONE, i=WEIGHT_INFLATION, g=WEIGHT_GDP)

    # Честно говорим, с чем сравниваем: пока истории нет недели, стрелка
    # показывает изменение к ближайшему прошлому срезу, а не к неделе назад.
    if base_day:
        days = (day - base_day).days
        if lang == "ru":
            period = ("со вчера" if days == 1 else
                      "за неделю" if days >= 7 else f"за {days} дн.")
            footer = footer.replace("Стрелка — изменение балла за неделю.",
                                    f"Стрелка — изменение балла {period} (с {base_day.strftime('%d.%m')}).")
        else:
            period = ("since yesterday" if days == 1 else
                      "over a week" if days >= 7 else f"over {days} days")
            footer = footer.replace("The arrow is the weekly change in score.",
                                    f"The arrow is the change in score {period}.")
    elif lang == "ru":
        footer = footer.replace("Стрелка — изменение балла за неделю.",
                                "Стрелка появится со второго дня: сравнивать пока не с чем.")
    else:
        footer = footer.replace("The arrow is the weekly change in score.",
                                "Arrows appear from the second day — there is nothing to compare yet.")

    lines.append(footer)
    return "".join(lines)
