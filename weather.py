# weather.py — погода по просьбе, а не по расписанию.
#
# Пост в канале один на всех, и погода в нём может быть только для одного
# города: половине читателей она будет враньём. Поэтому никакой погоды в
# канале нет — там стоит кнопка. Нажавший попадает в бота, один раз
# показывает, где он, и получает прогноз лично.
#
# Тем же путём ходят напоминания о матчах: канал зовёт, личка отвечает.
# Разница только в том, что погоду человек просит сам, — и рассылки,
# которая надоедает, здесь не возникает.
#
# Координаты храним округлёнными до сотой доли градуса: это около
# километра, для прогноза точнее не нужно, а точка на карте — уже адрес
# человека, и хранить его незачем.
import logging
import time

import httpx
from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, ReplyKeyboardMarkup,
                           KeyboardButton, ReplyKeyboardRemove)
from aiogram.dispatcher.event.bases import SkipHandler

import database

router = Router()

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

PLACE_KEY = "wx_place_"      # + id пользователя: "широта,долгота,название"
ASK_KEY = "wx_waiting"       # кто сейчас называет город
ASK_MINUTES = 20

# Коды погоды ВМО. Словарь короткий намеренно: «слабый ливневый дождь» и
# «умеренный ливневый дождь» человеку одно и то же — ему решать, брать ли
# зонт, а не сдавать метеорологию.
CODES = {
    0: ("☀️", "ясно"),
    1: ("🌤", "малооблачно"),
    2: ("⛅️", "переменная облачность"),
    3: ("☁️", "пасмурно"),
    45: ("🌫", "туман"),
    48: ("🌫", "изморозь"),
    51: ("🌦", "морось"),
    53: ("🌦", "морось"),
    55: ("🌦", "морось"),
    61: ("🌧", "дождь"),
    63: ("🌧", "дождь"),
    65: ("🌧", "сильный дождь"),
    66: ("🌧", "ледяной дождь"),
    67: ("🌧", "ледяной дождь"),
    71: ("🌨", "снег"),
    73: ("🌨", "снег"),
    75: ("🌨", "сильный снег"),
    77: ("🌨", "снежная крупа"),
    80: ("🌦", "ливень"),
    81: ("🌦", "ливень"),
    82: ("⛈", "сильный ливень"),
    85: ("🌨", "снегопад"),
    86: ("🌨", "снегопад"),
    95: ("⛈", "гроза"),
    96: ("⛈", "гроза с градом"),
    99: ("⛈", "гроза с градом"),
}

WET = set(range(51, 68)) | set(range(80, 83)) | {95, 96, 99}
SNOWY = set(range(71, 78)) | {85, 86}


def _describe(code) -> tuple:
    return CODES.get(int(code or 0), ("🌡", ""))


def _degrees(value) -> str:
    """+18° — со знаком: без него ноль и минус читаются одинаково"""
    try:
        return f"{round(float(value)):+d}°"
    except (TypeError, ValueError):
        return "—"


# ---------------------------------------------------------------------
# ГДЕ ЧЕЛОВЕК
# ---------------------------------------------------------------------

async def _save_place(user_id: int, lat: float, lon: float, name: str = ""):
    await database.set_setting(PLACE_KEY + str(user_id),
                               f"{round(lat, 2)},{round(lon, 2)},{name[:40]}")


async def _place(user_id: int):
    raw = await database.get_setting(PLACE_KEY + str(user_id)) or ""
    parts = raw.split(",", 2)
    if len(parts) < 2:
        return None
    try:
        return float(parts[0]), float(parts[1]), (parts[2] if len(parts) > 2 else "")
    except ValueError:
        return None


async def _ask_on(user_id: int):
    await database.set_setting(ASK_KEY, f"{user_id}:{int(time.time()) + ASK_MINUTES * 60}")


async def _ask_off():
    await database.set_setting(ASK_KEY, "")


async def _ask_active(user_id: int) -> bool:
    raw = await database.get_setting(ASK_KEY) or ""
    try:
        who, until = raw.split(":")
        return int(who) == user_id and int(until) > time.time()
    except ValueError:
        return False


async def _find_city(name: str):
    """Координаты по названию города. None — не нашли."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(GEOCODE_URL, params={
                "name": name[:60], "count": 1, "language": "ru", "format": "json"})
            response.raise_for_status()
            found = (response.json() or {}).get("results") or []
    except Exception as e:
        logging.warning(f"Город «{name}» не нашёлся: {e}")
        return None
    if not found:
        return None
    top = found[0]
    label = top.get("name") or name
    country = top.get("country") or ""
    if country and country not in label:
        label = f"{label}, {country}"
    return top.get("latitude"), top.get("longitude"), label


# ---------------------------------------------------------------------
# ПРОГНОЗ
# ---------------------------------------------------------------------

# Прогноз меняется не чаще, чем раз в час, а кнопку «Обновить» жмут
# подряд. Держим ответ четверть часа: у бесплатной службы есть предел
# запросов, и упереться в него из-за нетерпения было бы обидно.
_cache = {}
CACHE_TTL = 900


async def forecast(lat: float, lon: float) -> dict:
    key = (round(lat, 2), round(lon, 2))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(FORECAST_URL, params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,weather_code",
            "hourly": "temperature_2m,precipitation_probability,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code",
            "timezone": "auto", "forecast_days": 1})
        response.raise_for_status()
        data = response.json() or {}
    _cache[key] = (time.time(), data)
    return data


def _evening(data: dict) -> str:
    """Строка про вечер — та, ради которой всё и затевалось.

    Смотрим часы с 16 до 22 по местному времени человека: утренний дождь
    к вечеру уже неинтересен, а именно вечером люди выходят из дома без
    зонта.
    """
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    codes = hourly.get("weather_code") or []
    chance = hourly.get("precipitation_probability") or []

    worst_code, worst_chance = None, 0
    for i, stamp in enumerate(times):
        try:
            hour = int(str(stamp)[11:13])
        except ValueError:
            continue
        if not 16 <= hour <= 22:
            continue
        probability = chance[i] if i < len(chance) and chance[i] is not None else 0
        code = codes[i] if i < len(codes) else 0
        if probability > worst_chance:
            worst_chance, worst_code = probability, code

    if worst_chance < 40 or worst_code is None:
        return ""
    if int(worst_code) in SNOWY:
        return f"К вечеру снег ({worst_chance}%) — одевайтесь теплее."
    if int(worst_code) in WET:
        return f"К вечеру дождь ({worst_chance}%) — возьмите зонт."
    return ""


def _text(data: dict, place: str) -> str:
    current = data.get("current") or {}
    daily = data.get("daily") or {}
    icon, words = _describe(current.get("weather_code"))

    where = f" · {place}" if place else ""
    lines = [f"{icon} <b>Погода{where}</b>", ""]
    lines.append(f"Сейчас: {_degrees(current.get('temperature_2m'))}"
                 + (f", {words}" if words else ""))

    highs = (daily.get("temperature_2m_max") or [None])[0]
    lows = (daily.get("temperature_2m_min") or [None])[0]
    if highs is not None and lows is not None:
        lines.append(f"Днём до {_degrees(highs)}, ночью {_degrees(lows)}")

    evening = _evening(data)
    if evening:
        lines += ["", evening]
    return "\n".join(lines)


def _again_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔄 Обновить", callback_data="wx_again"),
        InlineKeyboardButton(text="📍 Сменить место", callback_data="wx_change")]])


async def _send(target, user_id: int) -> bool:
    """Прогноз для сохранённого места. False — места ещё нет."""
    place = await _place(user_id)
    if not place:
        return False
    lat, lon, name = place
    try:
        data = await forecast(lat, lon)
    except Exception as e:
        logging.error(f"Погода не пришла: {type(e).__name__}: {e}")
        await target.answer("Служба погоды сейчас не отвечает. "
                            "Попробуйте через несколько минут.")
        return True
    await target.answer(_text(data, name), reply_markup=_again_kb())
    return True


# ---------------------------------------------------------------------
# РАЗГОВОР
# ---------------------------------------------------------------------

WHERE_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📍 Отправить местоположение",
                              request_location=True)]],
    resize_keyboard=True, one_time_keyboard=True)

ASK_TEXT = ("🌦 <b>Какая у вас погода</b>\n\n"
            "Скажите, где вы, — и я пришлю прогноз на сегодня.\n\n"
            "Нажмите кнопку внизу или просто напишите город: "
            "<i>Москва</i>, <i>Тель-Авив</i>, <i>Алматы</i>.\n\n"
            "Точку на карте не храню — только город с точностью до "
            "километра, чтобы не спрашивать каждый раз.")


async def _ask_where(message: Message):
    await _ask_on(message.from_user.id)
    await message.answer(ASK_TEXT, reply_markup=WHERE_KB)


@router.message(F.text.regexp(r"^/start\s+weather"))
async def start_weather(message: Message):
    """Пришёл из канала по кнопке погоды.

    Роутер стоит раньше общего /start, поэтому в конце передаём ход
    дальше: человек мог оказаться здесь впервые, и приветствие с выбором
    языка ему всё равно нужно.
    """
    if not await _send(message, message.from_user.id):
        await _ask_where(message)
    raise SkipHandler


@router.message(F.text.regexp(r"^/(погода|weather)\b"))
async def weather_command(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        await _set_city(message, parts[1].strip())
        return
    if not await _send(message, message.from_user.id):
        await _ask_where(message)


@router.callback_query(F.data == "wx_again")
async def again(call: CallbackQuery):
    await call.answer("Смотрю…")
    if not await _send(call.message, call.from_user.id):
        await _ask_where(call.message)


@router.callback_query(F.data == "wx_change")
async def change(call: CallbackQuery):
    await call.answer()
    await database.set_setting(PLACE_KEY + str(call.from_user.id), "")
    await _ask_on(call.from_user.id)
    await call.message.answer(ASK_TEXT, reply_markup=WHERE_KB)


@router.message(F.location)
async def got_location(message: Message):
    """Координаты с кнопки. Работают только в личке — так Telegram и задуман."""
    await _ask_off()
    await _save_place(message.from_user.id,
                      message.location.latitude, message.location.longitude)
    await message.answer("Запомнила, где вы.", reply_markup=ReplyKeyboardRemove())
    await _send(message, message.from_user.id)


async def _set_city(message: Message, name: str):
    found = await _find_city(name)
    if not found:
        await message.answer(
            f"Не нашла «{name[:40]}». Попробуйте написать иначе — "
            f"например, «Нижний Новгород» вместо «НН».")
        return
    lat, lon, label = found
    await _ask_off()
    await _save_place(message.from_user.id, lat, lon, label)
    await message.answer(f"Запомнила: {label}.", reply_markup=ReplyKeyboardRemove())
    await _send(message, message.from_user.id)


@router.message(F.text & ~F.text.startswith("/"))
async def maybe_city(message: Message):
    """Название города — но только когда мы его сами спросили.

    Иначе обработчик перехватывал бы любую фразу в боте: тут ходят и
    ссылки на книги, и ответы на головоломки.
    """
    if not await _ask_active(message.from_user.id):
        raise SkipHandler
    text = (message.text or "").strip()
    if len(text) > 60:
        raise SkipHandler
    await _set_city(message, text)
