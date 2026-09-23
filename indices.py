# indices.py — индексы как термометр событий.
#
# Зачем они в канале для предпринимателей: индекс — это не про то, что
# покупать, а про то, что случилось. Ставка, отчёт, война, разрешение на
# лекарство — всё это видно цифрой в тот же день, и цифра объясняет
# новость лучше, чем пересказ новости.
#
# Отсюда граница, и она жёстче, чем в остальных разделах. Мы показываем
# индексы, а не отдельные бумаги: подборка акций, которые «пошли», в
# глазах читателя — подсказка, что покупать, даже без слова «покупайте».
# Рекомендации по вложениям требуют лицензии, которой нет, и здесь этой
# черты не переходим ни ради интереса, ни ради заработка.
#
# Данные — Yahoo: без ключа, история за месяц одним запросом. Кэш на час:
# индекс за минуту не меняет картину дня, а лимиты у чужого сервиса свои.
import logging
from datetime import date

import httpx

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0"}          # без него Yahoo молчит

# Три индекса, которые объясняют три разные вещи: широкий рынок,
# промышленность старой школы и технологии.
INDICES = {
    "^GSPC": {"ru": "S&P 500", "note": "широкий рынок США"},
    "^DJI": {"ru": "Dow Jones", "note": "тридцать крупнейших"},
    "^IXIC": {"ru": "NASDAQ", "note": "технологии"},
}

BARS = "▁▂▃▄▅▆▇█"
_cache = {"at": None, "series": {}}


async def fetch_series(days: str = "1mo") -> dict:
    """{символ: [цены закрытия]}. Пусто — значит источник недоступен."""
    if _cache["at"] == date.today() and _cache["series"]:
        return _cache["series"]

    series = {}
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        for symbol in INDICES:
            try:
                answer = await client.get(URL.format(symbol=symbol),
                                          params={"range": days,
                                                  "interval": "1d"},
                                          headers=HEADERS)
                data = answer.json()["chart"]["result"][0]
                closes = [x for x in data["indicators"]["quote"][0]["close"]
                          if x is not None]
            except Exception as e:
                logging.warning(f"Индекс {symbol} не прочитался: {e}")
                continue
            if len(closes) >= 2:
                series[symbol] = closes

    if series:
        _cache.update(at=date.today(), series=series)
    return series or _cache["series"]


def sparkline(values: list, width: int = 20) -> str:
    """Мини-график столбиками — он читается прямо в сообщении.

    Картинку Telegram показал бы крупнее, но её надо рисовать, хранить и
    ждать; столбики приходят вместе с текстом.
    """
    if len(values) > width:
        step = len(values) / width
        values = [values[int(i * step)] for i in range(width)]
    low, high = min(values), max(values)
    if high - low < 1e-12:
        return BARS[0] * len(values)
    scale = len(BARS) - 1
    return "".join(BARS[round((v - low) / (high - low) * scale)] for v in values)


def moves(closes: list) -> tuple:
    """(за сутки %, за месяц %). Считаем от предыдущего закрытия."""
    if len(closes) < 2:
        return 0.0, 0.0
    day = (closes[-1] - closes[-2]) / closes[-2] * 100 if closes[-2] else 0.0
    month = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] else 0.0
    return day, month


def arrow(value: float) -> str:
    return "▲" if value > 0.05 else ("▼" if value < -0.05 else "=")


def chart_url(series: dict) -> str:
    """Общий график трёх индексов в процентах от начала месяца.

    В абсолютных числах их не совместить: у Dow пятизначные значения, у
    S&P четырёхзначные, и на одной оси меньший превращается в прямую.
    Приведённые к старту, они сравнимы — видно, кто шёл быстрее.
    """
    import json
    from urllib.parse import quote

    datasets = []
    for symbol, closes in series.items():
        base = closes[0]
        if not base:
            continue
        datasets.append({
            "label": INDICES[symbol]["ru"],
            "data": [round((x - base) / base * 100, 2) for x in closes],
            "fill": False,
            "borderWidth": 2,
        })
    if not datasets:
        return ""

    longest = max(len(d["data"]) for d in datasets)
    config = {
        "type": "line",
        "data": {"labels": [""] * longest, "datasets": datasets},
        "options": {
            "title": {"display": True, "text": "Месяц, % от начала"},
            "legend": {"position": "bottom"},
            "elements": {"point": {"radius": 0}},
        },
    }
    return ("https://quickchart.io/chart?w=700&h=400&c="
            + quote(json.dumps(config, ensure_ascii=False)))


def morning_block(series: dict) -> str:
    """Три строки для утреннего выпуска, в разметке Markdown.

    Разметка та же, что у новостей и курсов: выпуск собирается одним
    сообщением, и смешивать HTML с Markdown в нём нельзя.
    """
    if not series:
        return ""
    lines = []
    for symbol, meta in INDICES.items():
        closes = series.get(symbol)
        if not closes:
            continue
        day, month = moves(closes)
        lines.append(
            f"*{meta['ru']}*: {closes[-1]:,.0f}".replace(",", " ")
            + f" {arrow(day)} {abs(day):.2f}% за сутки, {month:+.1f}% за месяц\n"
            + sparkline(closes))
    return "📈 *Индексы*\n\n" + "\n\n".join(lines) if lines else ""


# ---------------------------------------------------------------------
# ЭКРАН
# ---------------------------------------------------------------------
#
# Индексы объясняют новости, поэтому живут рядом с ними — в боте, а не
# отдельным разделом, куда надо специально заходить.

from aiogram import Router, F                                  # noqa: E402
from aiogram.types import (Message, CallbackQuery,             # noqa: E402
                           InlineKeyboardMarkup, InlineKeyboardButton)

router = Router()

INTRO = (
    "📈 <b>Индексы</b>\n\n"
    "Это не про то, что покупать, а про то, что случилось. Ставка, "
    "отчёт, решение регулятора — всё видно цифрой в тот же день, и "
    "цифра объясняет новость лучше пересказа.\n\n"
    "{body}\n\n"
    "<i>График — месяц в процентах от начала: в абсолютных числах их не "
    "совместить, у индексов разный масштаб.</i>"
)


def _screen_text(series: dict) -> str:
    rows = []
    for symbol, meta in INDICES.items():
        closes = series.get(symbol)
        if not closes:
            continue
        day, month = moves(closes)
        rows.append(f"<b>{meta['ru']}</b> — {meta['note']}\n"
                    f"{closes[-1]:,.0f}".replace(",", " ")
                    + f"  {arrow(day)} {abs(day):.2f}% за сутки, "
                      f"{month:+.1f}% за месяц\n{sparkline(closes)}")
    return "\n\n".join(rows)


def _kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="idx_open")],
        [InlineKeyboardButton(text="⇦", callback_data="go_home")]])


async def _send(message: Message):
    series = await fetch_series()
    if not series:
        await message.answer("Биржевые данные сейчас недоступны — "
                             "источник не отвечает. Загляните позже.")
        return

    text = INTRO.format(body=_screen_text(series))
    url = chart_url(series)
    if url:
        try:
            # Картинку отдаёт внешний сервис по ссылке: рисовать её у
            # себя значило бы тащить библиотеку графиков ради трёх линий.
            await message.answer_photo(url, caption=text[:1024],
                                       reply_markup=_kb())
            return
        except Exception as e:
            logging.warning(f"График индексов не нарисовался: {e}")
    await message.answer(text, reply_markup=_kb())


@router.message(F.text.regexp(r"^/(индексы|indices)\b"))
async def indices_command(message: Message):
    await _send(message)


@router.callback_query(F.data == "idx_open")
async def open_screen(call: CallbackQuery):
    await call.answer()
    await _send(call.message)
