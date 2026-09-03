# planner.py — общее расписание на несколько человек
"""Календарь, в который пишут все участники сразу.

Событие заводится одной фразой («завтра в 14:30 на час тренировка»), а
чего в ней не хватило — бот спрашивает. Занятое время не молчит: бот
показывает, чем оно занято, и предлагает отменить или перенести — прежнее
событие или новое.

Повторяющееся событие хранится ОДНОЙ строкой вместе с правилом повтора и
датой окончания; отдельные вхождения разворачиваются при показе. Поэтому
перенести можно и одно занятие серии (запись в plan_overrides), и всю
серию целиком (сдвиг самой строки события).
"""
import html
import logging
import re
from calendar import monthrange
from datetime import datetime, date, time, timedelta, timezone

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery,
                           InlineKeyboardMarkup, InlineKeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest

import config
import database

router = Router()

SECTION = "planner"

# Часовой пояс берём тот же, по которому выходит утренний дайджест: сервер
# живёт по UTC, а «сегодня» и «завтра» участники считают по своим часам.
TZ_KEY = "digest_tz"
TZ_DEFAULT = 3

MEMBERS_KEY = "plan_users"      # список id через запятую; пусто — можно всем

WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
WD_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS_IN = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]
MONTHS_NOM = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
              "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
MONTHS_SHORT = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
                "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]

REPEAT_TITLES = {
    "daily": "каждый день",
    "weekly": "каждую неделю",
    "biweekly": "раз в две недели",
    "monthly": "каждый месяц",
}

# Насколько далеко разворачивать серию при проверке занятости. Год вперёд
# покрывает любую разумную серию, а верхний предел на число вхождений не даёт
# опечатке вроде «каждый день до 2099» превратить проверку в перебор тысяч дат.
CHECK_HORIZON_DAYS = 366
MAX_OCCURRENCES = 400

# Уровень подробности дашборда у каждого свой: одному нужен список дел,
# другому — с описанием и автором. Держим в памяти процесса: настройка
# сиюминутная, ради неё не стоит ходить в базу на каждое нажатие.
_detail: dict = {}


# --- ВРЕМЯ ---

async def _shift() -> timedelta:
    try:
        offset = int(await database.get_setting(TZ_KEY) or TZ_DEFAULT)
    except (TypeError, ValueError):
        offset = TZ_DEFAULT
    return timedelta(hours=offset)


async def _now() -> datetime:
    """Местное время участников, наивное — в таком же виде лежит в базе"""
    return (datetime.now(timezone.utc) + await _shift()).replace(tzinfo=None)


async def _today() -> date:
    return (await _now()).date()


def _fmt_dur(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h} ч {m} мин"
    if h:
        return f"{h} ч"
    return f"{m} мин"


def _fmt_day(d: date, weekday: bool = True) -> str:
    head = f"{d.day} {MONTHS_IN[d.month - 1]}"
    return f"{WEEKDAYS[d.weekday()]}, {head} {d.year}" if weekday else head


def _key(d: date) -> str:
    return d.strftime("%Y%m%d")


def _unkey(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


# --- ДОСТУП ---

async def _members() -> set:
    raw = (await database.get_setting(MEMBERS_KEY) or "").strip()
    return {int(x) for x in re.findall(r"-?\d+", raw)}


async def _may_edit(user_id: int) -> bool:
    """Пока список участников пуст, календарь открыт всем — иначе первый же
    запуск запер бы владельца снаружи. Как только список задан командой
    /plan_users, писать могут только он и владелец бота."""
    allowed = await _members()
    return (not allowed) or user_id in allowed or config.is_admin(user_id)


def _who(user) -> str:
    return (user.full_name or user.username or str(user.id))[:64]


# --- РАЗБОР ФРАЗЫ ---

WD_WORDS = {
    "пн": 0, "понедельник": 0, "понедельника": 0,
    "вт": 1, "вторник": 1, "вторника": 1,
    "ср": 2, "среда": 2, "среду": 2, "среды": 2,
    "чт": 3, "четверг": 3, "четверга": 3,
    "пт": 4, "пятница": 4, "пятницу": 4, "пятницы": 4,
    "сб": 5, "суббота": 5, "субботу": 5, "субботы": 5,
    "вс": 6, "воскресенье": 6, "воскресенья": 6,
}
WD_RE = "|".join(sorted(WD_WORDS, key=len, reverse=True))

MONTH_STEMS = ["январ", "феврал", "март", "апрел", "ма", "июн",
               "июл", "август", "сентябр", "октябр", "ноябр", "декабр"]
MONTH_RE = (r"январ\w*|феврал\w*|март\w*|апрел\w*|мая|май|июн\w*|июл\w*|"
            r"август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*")


def _month_num(word: str):
    w = word.lower()
    if w.startswith("ма") and not w.startswith("март"):
        return 5
    for i, stem in enumerate(MONTH_STEMS):
        if stem != "ма" and w.startswith(stem):
            return i + 1
    return None


def _cut(text: str, m) -> str:
    return (text[:m.start()] + " " + text[m.end():])


def _next_weekday(base: date, wd: int) -> date:
    """Ближайший такой день недели, считая сегодняшний"""
    return base + timedelta(days=(wd - base.weekday()) % 7)


def _pick_date(text: str, base: date):
    """Достаёт дату из фразы. Возвращает (дата или None, остаток фразы)"""
    low = text.lower()

    m = re.search(r"\bпослезавтра\b", low)
    if m:
        return base + timedelta(days=2), _cut(text, m)
    m = re.search(r"\bзавтра\b", low)
    if m:
        return base + timedelta(days=1), _cut(text, m)
    m = re.search(r"\bсегодня\b", low)
    if m:
        return base, _cut(text, m)

    # 12.09, 12.09.2026, 12/09
    m = re.search(r"\b(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\b", low)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else base.year
        if year < 100:
            year += 2000
        try:
            got = date(year, month, day)
        except ValueError:
            got = None
        if got:
            # Год не назвали, а число уже прошло — значит, речь о следующем годе
            if not m.group(3) and got < base:
                got = got.replace(year=year + 1)
            return got, _cut(text, m)

    # 12 сентября (2026)
    m = re.search(rf"\b(\d{{1,2}})\s+({MONTH_RE})(?:\s+(\d{{4}}))?", low)
    if m:
        month = _month_num(m.group(2))
        year = int(m.group(3)) if m.group(3) else base.year
        try:
            got = date(year, month, int(m.group(1)))
        except (ValueError, TypeError):
            got = None
        if got:
            if not m.group(3) and got < base:
                got = got.replace(year=year + 1)
            return got, _cut(text, m)

    m = re.search(rf"\b({WD_RE})\b", low)
    if m:
        return _next_weekday(base, WD_WORDS[m.group(1)]), _cut(text, m)

    return None, text


def _pick_time(text: str):
    """Достаёт время. Возвращает (время или None, остаток фразы)"""
    low = text.lower()

    m = re.search(r"\b([01]?\d|2[0-3])[:.\-]([0-5]\d)\b", low)
    if m:
        return time(int(m.group(1)), int(m.group(2))), _cut(text, m)

    # «в 9», «в 19 часов» — голый час опознаём только с предлогом: без него
    # «на 2 часа» читалось бы как время начала, а не как длительность.
    m = re.search(r"\bв\s+([01]?\d|2[0-3])\s*(?:ч|час\w*)?\b(?!\s*[:.\d])", low)
    if m:
        return time(int(m.group(1)), 0), _cut(text, m)

    return None, text


def _pick_duration(text: str):
    """Достаёт длительность в минутах. Возвращает (минуты или None, остаток)"""
    low = text.lower()

    m = re.search(r"\bполчаса\b", low)
    if m:
        return 30, _cut(text, m)
    m = re.search(r"\bполтора\s+часа\b", low)
    if m:
        return 90, _cut(text, m)
    m = re.search(r"\b(\d{1,3})\s*(?:мин\w*|м)\b", low)
    if m:
        return int(m.group(1)), _cut(text, m)
    m = re.search(r"\b(\d{1,2})(?:[.,](\d))?\s*(?:ч|час\w*)\b", low)
    if m:
        minutes = int(m.group(1)) * 60
        if m.group(2):
            minutes += int(int(m.group(2)) * 6)
        return minutes, _cut(text, m)
    m = re.search(r"\bна\s+час\b", low)
    if m:
        return 60, _cut(text, m)

    return None, text


def _pick_repeat(text: str, base: date):
    """Достаёт правило повтора и дату окончания.

    Разбирается ПЕРВЫМ: во фразе «каждый вторник» слово «вторник» — это
    правило, а не дата ближайшего занятия, и порядок здесь решает.
    """
    low = text.lower()
    rule, until = None, None

    m = re.search(r"\bдо\s+(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\b", low)
    if not m:
        m = re.search(rf"\bдо\s+(\d{{1,2}})\s+({MONTH_RE})(?:\s+(\d{{4}}))?", low)
        if m:
            month = _month_num(m.group(2))
        else:
            month = None
    else:
        month = int(m.group(2))
    if m and month:
        year_raw = m.group(3)
        year = int(year_raw) if year_raw else base.year
        if year < 100:
            year += 2000
        try:
            until = date(year, month, int(m.group(1)))
            if not year_raw and until < base:
                until = until.replace(year=year + 1)
            text = _cut(text, m)
            low = text.lower()
        except ValueError:
            until = None

    for pattern, name in (
        (r"\bраз\s+в\s+две\s+недел\w*|\bчерез\s+недел\w*", "biweekly"),
        (r"\bкажд\w*\s+день\b|\bежедневн\w*", "daily"),
        (r"\bкажд\w*\s+недел\w*|\bеженедельн\w*", "weekly"),
        (r"\bкажд\w*\s+месяц\w*|\bежемесячн\w*", "monthly"),
    ):
        m = re.search(pattern, low)
        if m:
            return name, until, _cut(text, m)

    # «каждый вторник» — недельная серия, день недели оставляем в тексте:
    # его подберёт разбор даты и назначит первое занятие.
    m = re.search(rf"\bкажд\w*\s+(?={WD_RE})", low)
    if m:
        return "weekly", until, _cut(text, m)

    return rule, until, text


def _clean(text: str) -> str:
    """Остаток фразы после вырезанных даты и времени — это тема события"""
    text = re.sub(r"\s+", " ", text).strip(" ,.;–—-")
    text = re.sub(r"^(?:в|во|на|с|до|к)\s+", "", text, flags=re.I).strip()
    return text[:120]


def parse_phrase(text: str, base: date) -> dict:
    """Разбирает фразу в черновик события. Чего в ней не было — того в
    словаре нет: недостающее спросит диалог."""
    draft = {}
    body, _, tail = text.partition("\n")
    if tail.strip():
        draft["desc"] = tail.strip()[:1000]

    rule, until, body = _pick_repeat(body, base)
    if rule:
        draft["rule"] = rule
    if until:
        draft["until"] = until.isoformat()

    when, body = _pick_date(body, base)
    if when:
        draft["date"] = when.isoformat()

    at, body = _pick_time(body)
    if at:
        draft["time"] = at.strftime("%H:%M")

    dur, body = _pick_duration(body)
    if dur:
        draft["dur"] = dur

    title = _clean(body)
    if title:
        draft["title"] = title
    return draft


# --- РАЗВОРАЧИВАНИЕ СЕРИЙ ---

def _add_month(y: int, m: int, anchor: int) -> date:
    """Следующий месяц с тем же числом; 31-е в коротком месяце садится на
    последний день, но якорь не теряется — в марте занятие снова 31-го."""
    m += 1
    if m == 13:
        y, m = y + 1, 1
    return date(y, m, min(anchor, monthrange(y, m)[1]))


def _series_dates(ev, d_from: date, d_to: date) -> list:
    """Даты вхождений по исходному расписанию, без учёта переносов"""
    start = ev["starts_at"].date()
    rule = ev["repeat_rule"]
    if not rule:
        return [start] if d_from <= start <= d_to else []

    last = min(ev["repeat_until"] or d_to, d_to)
    out = []
    if rule in ("daily", "weekly", "biweekly"):
        step = {"daily": 1, "weekly": 7, "biweekly": 14}[rule]
        cur = start
        if start < d_from:
            # Сразу прыгаем к первому вхождению внутри окна: ежедневная серия
            # двухлетней давности иначе перебиралась бы по дню.
            skip = ((d_from - start).days + step - 1) // step
            cur = start + timedelta(days=skip * step)
        while cur <= last and len(out) < MAX_OCCURRENCES:
            out.append(cur)
            cur += timedelta(days=step)
    elif rule == "monthly":
        anchor = start.day
        y, m = start.year, start.month
        cur = start
        while cur <= last and len(out) < MAX_OCCURRENCES:
            if cur >= d_from:
                out.append(cur)
            cur = _add_month(y, m, anchor)
            y, m = cur.year, cur.month
    return out


def _expand(events, overrides, d_from: date, d_to: date) -> list:
    """Вхождения в окне: серии развёрнуты, отмены и переносы учтены.

    Считаем с запасом по краям: занятие, перенесённое с прошлой недели на
    эту, обязано появиться в этой — а по исходной дате оно в окно не попадает.
    """
    ov = {(o["event_id"], o["occur_date"]): o for o in overrides}
    wide_from, wide_to = d_from - timedelta(days=45), d_to + timedelta(days=45)

    out = []
    for ev in events:
        for d in _series_dates(ev, wide_from, wide_to):
            o = ov.get((ev["id"], d))
            if o is not None and o["moved_to"] is None:
                continue                       # это вхождение отменили
            start = o["moved_to"] if o else datetime.combine(d, ev["starts_at"].time())
            if not (d_from <= start.date() <= d_to):
                continue
            out.append({
                "event": ev,
                "origin": d,
                "start": start,
                "duration": (o["duration_min"] if o and o["duration_min"] else ev["duration_min"]),
                "moved": bool(o),
            })
    out.sort(key=lambda x: (x["start"], x["event"]["title"]))
    return out


async def _load(d_from: date, d_to: date) -> list:
    wide_from, wide_to = d_from - timedelta(days=45), d_to + timedelta(days=45)
    events = await database.plan_range(wide_from, wide_to)
    overrides = await database.plan_overrides([e["id"] for e in events])
    return _expand(events, overrides, d_from, d_to)


def _overlap(a_start: datetime, a_dur: int, b_start: datetime, b_dur: int) -> bool:
    return (a_start < b_start + timedelta(minutes=b_dur)
            and b_start < a_start + timedelta(minutes=a_dur))


def _draft_row(draft: dict) -> dict:
    """Черновик в том же виде, что строка события: так его вхождения считает
    та же функция, что и для сохранённых, — без второй копии правил."""
    start = datetime.combine(date.fromisoformat(draft["date"]),
                             datetime.strptime(draft["time"], "%H:%M").time())
    return {
        "id": 0,
        "title": draft.get("title", ""),
        "description": draft.get("desc", ""),
        "starts_at": start,
        "duration_min": draft.get("dur", 60),
        "repeat_rule": draft.get("rule"),
        "repeat_until": date.fromisoformat(draft["until"]) if draft.get("until") else None,
        "created_by": 0,
        "created_by_name": "",
        "cancelled": False,
    }


async def _find_conflicts(row: dict, ignore_event: int = 0) -> list:
    """Чем занято время нового события. Отдаёт пары (вхождение нового,
    занятое вхождение), первым — самое раннее пересечение."""
    start_date = row["starts_at"].date()
    end_date = min(row["repeat_until"] or start_date,
                   start_date + timedelta(days=CHECK_HORIZON_DAYS))
    mine = _expand([row], [], start_date, max(end_date, start_date))
    if not mine:
        return []

    busy = await _load(mine[0]["start"].date(), mine[-1]["start"].date())
    clashes = []
    for a in mine:
        for b in busy:
            if b["event"]["id"] == ignore_event or b["event"]["id"] == row["id"]:
                continue
            if _overlap(a["start"], a["duration"], b["start"], b["duration"]):
                clashes.append((a, b))
    clashes.sort(key=lambda pair: pair[0]["start"])
    return clashes


# --- ТЕКСТЫ ---

def _esc(s) -> str:
    return html.escape(str(s or ""))


def _repeat_line(ev) -> str:
    rule = ev["repeat_rule"]
    if not rule:
        return ""
    text = REPEAT_TITLES.get(rule, rule)
    until = ev["repeat_until"]
    if until:
        text += f" до {_fmt_day(until, weekday=False)} {until.year}"
    return text


def _occ_line(occ, detail: bool, bullet: str = "•") -> str:
    ev = occ["event"]
    start = occ["start"]
    end = start + timedelta(minutes=occ["duration"])
    mark = " ↷" if occ["moved"] else ""
    line = f"{bullet} {start:%H:%M}–{end:%H:%M} <b>{_esc(ev['title'])}</b>{mark}"
    if not detail:
        return line
    extra = []
    if ev["description"]:
        extra.append(f"   {_esc(ev['description'])[:200]}")
    tags = [f"👤 {_esc(ev['created_by_name'] or 'аноним')}"]
    if ev["repeat_rule"]:
        tags.append("🔁 " + _repeat_line(ev))
    extra.append("   " + " · ".join(tags))
    return line + "\n" + "\n".join(extra)


def _card_text(occ) -> str:
    ev = occ["event"]
    start = occ["start"]
    end = start + timedelta(minutes=occ["duration"])
    lines = [
        f"📌 <b>{_esc(ev['title'])}</b>",
        f"🗓 {_fmt_day(start.date())}",
        f"⏰ {start:%H:%M}–{end:%H:%M} ({_fmt_dur(occ['duration'])})",
    ]
    if ev["repeat_rule"]:
        lines.append(f"🔁 {_repeat_line(ev)}")
    if occ["moved"]:
        lines.append(f"↷ перенесено с {_fmt_day(occ['origin'], weekday=False)}")
    lines.append(f"👤 добавил {_esc(ev['created_by_name'] or 'аноним')}")
    if ev["description"]:
        lines.append("")
        lines.append(f"📝 {_esc(ev['description'])}")
    return "\n".join(lines)


# --- КЛАВИАТУРЫ ---

def _nav_row(mode: str, anchor: date) -> list:
    step = {"w": timedelta(days=7), "m": None, "y": None}[mode]
    if mode == "w":
        prev, nxt = anchor - step, anchor + step
    elif mode == "m":
        first = anchor.replace(day=1)
        prev = (first - timedelta(days=1)).replace(day=1)
        nxt = _add_month(first.year, first.month, 1)
    else:
        prev, nxt = anchor.replace(year=anchor.year - 1), anchor.replace(year=anchor.year + 1)
    titles = {"w": "Неделя", "m": "Месяц", "y": "Год"}
    return [
        InlineKeyboardButton(text="◀", callback_data=f"plan:v:{mode}:{_key(prev)}"),
        InlineKeyboardButton(text=titles[mode], callback_data="plan:noop"),
        InlineKeyboardButton(text="▶", callback_data=f"plan:v:{mode}:{_key(nxt)}"),
    ]


def _mode_row(mode: str, anchor: date) -> list:
    row = []
    for code, title in (("w", "Неделя"), ("m", "Месяц"), ("y", "Год")):
        if code == mode:
            continue
        row.append(InlineKeyboardButton(text=title, callback_data=f"plan:v:{code}:{_key(anchor)}"))
    return row


def _tail_rows(detail: bool, anchor: date) -> list:
    return [
        [InlineKeyboardButton(text="➕ Добавить", callback_data=f"plan:add:{_key(anchor)}"),
         InlineKeyboardButton(text="🔎 Кратко" if detail else "🔎 Подробно",
                              callback_data="plan:det")],
        [InlineKeyboardButton(text="⇦ В главное меню", callback_data="go_home")],
    ]


def _duration_kb() -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text=f"{m} мин", callback_data=f"plan:dur:{m}")
           for m in (30, 60, 90)]
    row2 = [InlineKeyboardButton(text="2 ч", callback_data="plan:dur:120"),
            InlineKeyboardButton(text="3 ч", callback_data="plan:dur:180")]
    return InlineKeyboardMarkup(inline_keyboard=[row, row2])


def _repeat_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Один раз", callback_data="plan:rep:once")],
        [InlineKeyboardButton(text="Каждый день", callback_data="plan:rep:daily"),
         InlineKeyboardButton(text="Каждую неделю", callback_data="plan:rep:weekly")],
        [InlineKeyboardButton(text="Раз в 2 недели", callback_data="plan:rep:biweekly"),
         InlineKeyboardButton(text="Каждый месяц", callback_data="plan:rep:monthly")],
    ])


def _until_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Месяц", callback_data="plan:until:30"),
         InlineKeyboardButton(text="3 месяца", callback_data="plan:until:90")],
        [InlineKeyboardButton(text="Полгода", callback_data="plan:until:182"),
         InlineKeyboardButton(text="Год", callback_data="plan:until:365")],
    ])


# --- ЭКРАНЫ ДАШБОРДА ---

async def _week_view(anchor: date, user_id: int):
    monday = anchor - timedelta(days=anchor.weekday())
    sunday = monday + timedelta(days=6)
    occs = await _load(monday, sunday)
    detail = _detail.get(user_id, False)

    head = f"📅 <b>Неделя {monday.day} {MONTHS_IN[monday.month - 1]} — {sunday.day} {MONTHS_IN[sunday.month - 1]} {sunday.year}</b>"
    lines, day_buttons = [head, ""], []
    today = await _today()
    for i in range(7):
        d = monday + timedelta(days=i)
        mine = [o for o in occs if o["start"].date() == d]
        mark = " ← сегодня" if d == today else ""
        lines.append(f"<b>{WD_SHORT[i]} {d.day} {MONTHS_IN[d.month - 1]}</b>{mark}")
        if mine:
            lines += [_occ_line(o, detail) for o in mine]
        else:
            lines.append("   — свободно")
        lines.append("")
        label = f"{WD_SHORT[i]} {d.day}" + (f" ·{len(mine)}" if mine else "")
        day_buttons.append(InlineKeyboardButton(text=label, callback_data=f"plan:d:{_key(d)}"))

    rows = [_nav_row("w", monday), _mode_row("w", monday),
            day_buttons[:4], day_buttons[4:]] + _tail_rows(detail, monday)
    return "\n".join(lines).strip(), InlineKeyboardMarkup(inline_keyboard=rows)


async def _month_view(anchor: date, user_id: int):
    first = anchor.replace(day=1)
    last = date(first.year, first.month, monthrange(first.year, first.month)[1])
    occs = await _load(first, last)
    detail = _detail.get(user_id, False)

    lines = [f"📅 <b>{MONTHS_NOM[first.month - 1]} {first.year}</b> — "
             f"{len(occs)} событий" if occs else
             f"📅 <b>{MONTHS_NOM[first.month - 1]} {first.year}</b> — пока пусто", ""]
    by_day = {}
    for o in occs:
        by_day.setdefault(o["start"].date(), []).append(o)
    for d in sorted(by_day):
        lines.append(f"<b>{d.day} {WD_SHORT[d.weekday()]}</b>")
        lines += [_occ_line(o, detail) for o in by_day[d]]
        if len("\n".join(lines)) > 3200:
            lines.append("…дальше — по кнопкам дней ниже")
            break

    # Сетка месяца: точка у дня, в котором что-то есть. Пустые клетки в начале
    # и в конце нужны, чтобы числа стояли под своими днями недели.
    grid, week = [], []
    for _ in range(first.weekday()):
        week.append(InlineKeyboardButton(text=" ", callback_data="plan:noop"))
    for day in range(1, last.day + 1):
        d = date(first.year, first.month, day)
        week.append(InlineKeyboardButton(
            text=f"{day}•" if d in by_day else str(day),
            callback_data=f"plan:d:{_key(d)}"))
        if len(week) == 7:
            grid.append(week)
            week = []
    if week:
        while len(week) < 7:
            week.append(InlineKeyboardButton(text=" ", callback_data="plan:noop"))
        grid.append(week)

    rows = [_nav_row("m", first), _mode_row("m", first)] + grid + _tail_rows(detail, first)
    return "\n".join(lines).strip(), InlineKeyboardMarkup(inline_keyboard=rows)


async def _year_view(anchor: date, user_id: int):
    year = anchor.year
    occs = await _load(date(year, 1, 1), date(year, 12, 31))
    detail = _detail.get(user_id, False)

    counts = [0] * 12
    for o in occs:
        counts[o["start"].month - 1] += 1

    lines = [f"📅 <b>{year} год</b> — {len(occs)} событий", ""]
    for i, n in enumerate(counts):
        if n:
            lines.append(f"{MONTHS_NOM[i]}: {n}")
    if not occs:
        lines.append("Пока ничего не запланировано.")

    grid, row = [], []
    for i in range(12):
        label = MONTHS_SHORT[i] + (f" {counts[i]}" if counts[i] else "")
        row.append(InlineKeyboardButton(
            text=label, callback_data=f"plan:v:m:{_key(date(year, i + 1, 1))}"))
        if len(row) == 3:
            grid.append(row)
            row = []

    rows = [_nav_row("y", date(year, 1, 1)), _mode_row("y", date(year, 1, 1))] \
        + grid + _tail_rows(detail, date(year, 1, 1))
    return "\n".join(lines).strip(), InlineKeyboardMarkup(inline_keyboard=rows)


async def _day_view(d: date, user_id: int):
    occs = await _load(d, d)
    detail = _detail.get(user_id, True)

    lines = [f"📅 <b>{_fmt_day(d)}</b>", ""]
    if not occs:
        lines.append("Свободно весь день.")
    for i, o in enumerate(occs, 1):
        lines.append(_occ_line(o, detail, bullet=f"{i}."))

    rows = []
    for o in occs:
        ev = o["event"]
        rows.append([InlineKeyboardButton(
            text=f"{o['start']:%H:%M} {ev['title'][:28]}",
            callback_data=f"plan:e:{ev['id']}:{_key(o['origin'])}")])
    rows.append([
        InlineKeyboardButton(text="◀", callback_data=f"plan:d:{_key(d - timedelta(days=1))}"),
        InlineKeyboardButton(text="➕ Добавить", callback_data=f"plan:add:{_key(d)}"),
        InlineKeyboardButton(text="▶", callback_data=f"plan:d:{_key(d + timedelta(days=1))}"),
    ])
    rows.append([
        InlineKeyboardButton(text="🔙 Неделя", callback_data=f"plan:v:w:{_key(d)}"),
        InlineKeyboardButton(text="Месяц", callback_data=f"plan:v:m:{_key(d)}"),
        InlineKeyboardButton(text="🔎 Кратко" if detail else "🔎 Подробно",
                             callback_data="plan:det"),
    ])
    rows.append([InlineKeyboardButton(text="⇦ В главное меню", callback_data="go_home")])
    return "\n".join(lines).strip(), InlineKeyboardMarkup(inline_keyboard=rows)


async def _occurrence(event_id: int, origin: date):
    """Одно вхождение серии со всеми поправками — то, что показывает карточка"""
    ev = await database.plan_event(event_id)
    if not ev or ev["cancelled"]:
        return None
    o = next((x for x in await database.plan_overrides([event_id])
              if x["occur_date"] == origin), None)
    if o is not None and o["moved_to"] is None:
        return None
    start = o["moved_to"] if o else datetime.combine(origin, ev["starts_at"].time())
    return {"event": ev, "origin": origin, "start": start,
            "duration": (o["duration_min"] if o and o["duration_min"] else ev["duration_min"]),
            "moved": bool(o)}


def _card_kb(occ) -> InlineKeyboardMarkup:
    ev = occ["event"]
    eid, key = ev["id"], _key(occ["origin"])
    day_key = _key(occ["start"].date())
    rows = []
    if ev["repeat_rule"]:
        # У серии два разных действия с одной кнопкой не помещаются: перенести
        # одно занятие и перенести всё расписание — это разные решения.
        rows.append([
            InlineKeyboardButton(text="↷ Перенести это", callback_data=f"plan:mv:{eid}:{key}:one"),
            InlineKeyboardButton(text="↷ Перенести серию", callback_data=f"plan:mv:{eid}:{key}:all"),
        ])
        rows.append([
            InlineKeyboardButton(text="❌ Отменить это", callback_data=f"plan:del:{eid}:{key}:one"),
            InlineKeyboardButton(text="❌ Отменить серию", callback_data=f"plan:del:{eid}:{key}:all"),
        ])
    else:
        rows.append([
            InlineKeyboardButton(text="↷ Перенести", callback_data=f"plan:mv:{eid}:{key}:all"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"plan:del:{eid}:{key}:all"),
        ])
    rows.append([InlineKeyboardButton(text="✏️ Описание", callback_data=f"plan:desc:{eid}:{key}")])
    rows.append([InlineKeyboardButton(text="🔙 К дню", callback_data=f"plan:d:{day_key}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render(mode: str, anchor: date, user_id: int):
    if mode == "m":
        return await _month_view(anchor, user_id)
    if mode == "y":
        return await _year_view(anchor, user_id)
    if mode == "d":
        return await _day_view(anchor, user_id)
    return await _week_view(anchor, user_id)


async def _show(call: CallbackQuery, text: str, kb: InlineKeyboardMarkup):
    """Перерисовывает экран. Главное меню приходит картинкой с подписью —
    заменить её текстом нельзя, поэтому в этом случае шлём новое сообщение."""
    try:
        await call.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        try:
            await call.message.delete()
        except TelegramBadRequest:
            pass
        await call.message.answer(text, reply_markup=kb, disable_web_page_preview=True)


# --- ДИАЛОГ ДОБАВЛЕНИЯ ---

class Add(StatesGroup):
    date = State()
    time = State()
    dur = State()
    rule = State()
    until = State()
    title = State()
    desc = State()
    conflict = State()
    move = State()
    edit_desc = State()


async def _say(target, text: str, kb: InlineKeyboardMarkup = None):
    """Отвечает и на нажатие кнопки, и на сообщение — диалог идёт вперемешку"""
    where = target.message if isinstance(target, CallbackQuery) else target
    await where.answer(text, reply_markup=kb, disable_web_page_preview=True)


def _draft_summary(draft: dict) -> str:
    row = _draft_row(draft)
    end = row["starts_at"] + timedelta(minutes=row["duration_min"])
    out = (f"<b>{_esc(row['title'] or 'без темы')}</b>\n"
           f"{_fmt_day(row['starts_at'].date())}, {row['starts_at']:%H:%M}–{end:%H:%M}")
    if row["repeat_rule"]:
        out += f"\n🔁 {_repeat_line(row)}"
    return out


async def _ask_next(target, state: FSMContext, user):
    """Спрашивает первое, чего в черновике не хватает; когда всё есть — сохраняет"""
    draft = (await state.get_data()).get("draft") or {}

    if "date" not in draft:
        await state.set_state(Add.date)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Сегодня", callback_data="plan:day:0"),
            InlineKeyboardButton(text="Завтра", callback_data="plan:day:1"),
            InlineKeyboardButton(text="Послезавтра", callback_data="plan:day:2"),
        ]])
        return await _say(target, "🗓 Какая дата?\nМожно написать «вторник», «12.09» или «5 октября».", kb)

    if "time" not in draft:
        await state.set_state(Add.time)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t, callback_data=f"plan:tm:{t}")
             for t in ("09:00", "12:00", "15:00")],
            [InlineKeyboardButton(text=t, callback_data=f"plan:tm:{t}")
             for t in ("18:00", "19:30", "21:00")],
        ])
        return await _say(target, "⏰ Во сколько начинаем?\nИли напишите своё время, например 14:30.", kb)

    if "dur" not in draft:
        await state.set_state(Add.dur)
        return await _say(target, "⏳ Сколько это займёт?", _duration_kb())

    if "rule" not in draft:
        await state.set_state(Add.rule)
        return await _say(target, "🔁 Событие разовое или повторяется?", _repeat_kb())

    if draft.get("rule") and "until" not in draft:
        await state.set_state(Add.until)
        return await _say(target, "📆 До какого числа повторять?\nМожно написать дату — «до 31.12».",
                          _until_kb())

    if "title" not in draft:
        await state.set_state(Add.title)
        return await _say(target, "📌 Как назовём событие? (одной строкой)")

    if "desc" not in draft:
        await state.set_state(Add.desc)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Пропустить", callback_data="plan:skip")]])
        return await _say(target, "📝 Добавьте описание — что именно и для кого.", kb)

    await _try_save(target, state, user)


def _clash_text(draft: dict, clashes: list) -> str:
    mine, busy = clashes[0]
    b_ev = busy["event"]
    b_end = busy["start"] + timedelta(minutes=busy["duration"])
    m_end = mine["start"] + timedelta(minutes=mine["duration"])

    lines = ["⚠️ <b>Это время уже занято</b>", "",
             f"Новое: {_fmt_day(mine['start'].date())}, "
             f"{mine['start']:%H:%M}–{m_end:%H:%M} — <b>{_esc(draft.get('title', ''))}</b>",
             f"Занято: {busy['start']:%H:%M}–{b_end:%H:%M} — <b>{_esc(b_ev['title'])}</b> "
             f"(добавил {_esc(b_ev['created_by_name'] or 'аноним')})"]
    if b_ev["repeat_rule"]:
        lines.append(f"          🔁 {_repeat_line(b_ev)}")
    others = len(clashes) - 1
    if others:
        lines.append(f"\nВ серии пересечений ещё {others} — разберём их по одному.")
    lines.append("\nЧто делаем?")
    return "\n".join(lines)


def _clash_kb(busy_is_series: bool, title: str) -> InlineKeyboardMarkup:
    short = title[:16]
    rows = []
    if busy_is_series:
        rows.append([InlineKeyboardButton(text="❌ Отменить это занятие", callback_data="plan:cf:oldx:one"),
                     InlineKeyboardButton(text="❌ Отменить всю серию", callback_data="plan:cf:oldx:all")])
        rows.append([InlineKeyboardButton(text="↷ Перенести это занятие", callback_data="plan:cf:oldm:one"),
                     InlineKeyboardButton(text="↷ Перенести всю серию", callback_data="plan:cf:oldm:all")])
    else:
        rows.append([InlineKeyboardButton(text=f"❌ Отменить «{short}»", callback_data="plan:cf:oldx:all"),
                     InlineKeyboardButton(text=f"↷ Перенести «{short}»", callback_data="plan:cf:oldm:all")])
    rows.append([InlineKeyboardButton(text="↷ Перенести новое", callback_data="plan:cf:newm")])
    rows.append([InlineKeyboardButton(text="✅ Оставить оба", callback_data="plan:cf:both"),
                 InlineKeyboardButton(text="🚫 Не добавлять", callback_data="plan:cf:drop")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _try_save(target, state: FSMContext, user, force: bool = False):
    """Проверяет занятость и либо сохраняет событие, либо предлагает выход"""
    data = await state.get_data()
    draft = data.get("draft") or {}
    row = _draft_row(draft)

    clashes = [] if force else await _find_conflicts(row)
    if clashes:
        mine, busy = clashes[0]
        b_ev = busy["event"]
        await state.update_data(clash={
            "eid": b_ev["id"],
            "date": _key(busy["origin"]),
            "series": bool(b_ev["repeat_rule"]),
            "title": b_ev["title"],
            "start": busy["start"].isoformat(),
            "end": (busy["start"] + timedelta(minutes=busy["duration"])).isoformat(),
            "dur": busy["duration"],
        })
        await state.set_state(Add.conflict)
        return await _say(target, _clash_text(draft, clashes),
                          _clash_kb(bool(b_ev["repeat_rule"]), b_ev["title"]))

    event_id = await database.plan_add(
        row["title"], row["description"], row["starts_at"], row["duration_min"],
        row["repeat_rule"], row["repeat_until"], user.id, _who(user))
    await state.clear()

    if not event_id:
        return await _say(target, "😔 База не ответила, событие не сохранилось. Попробуйте ещё раз.")

    day = row["starts_at"].date()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Открыть этот день", callback_data=f"plan:d:{_key(day)}")],
        [InlineKeyboardButton(text="➕ Ещё одно", callback_data=f"plan:addd:{_key(day)}"),
         InlineKeyboardButton(text="🗓 Неделя", callback_data=f"plan:v:w:{_key(day)}")],
    ])
    await _say(target, "✅ Записал:\n\n" + _draft_summary(draft), kb)


# --- ПЕРЕНОС ---

async def _ask_move(target, state: FSMContext, mv: dict):
    """Спрашивает, куда двигать. mv: что двигаем и зачем — см. _apply_move"""
    await state.update_data(mv=mv)
    await state.set_state(Add.move)

    rows = [[InlineKeyboardButton(text="+30 мин", callback_data="plan:mq:30"),
             InlineKeyboardButton(text="+1 час", callback_data="plan:mq:60"),
             InlineKeyboardButton(text="+1 день", callback_data="plan:mq:1440"),
             InlineKeyboardButton(text="+1 неделя", callback_data="plan:mq:10080")]]
    if mv.get("after"):
        rows.insert(0, [InlineKeyboardButton(text="⏭ Сразу после занятого",
                                             callback_data="plan:mq:after")])
    rows.append([InlineKeyboardButton(text="🚫 Отмена", callback_data="plan:cf:drop")])

    await _say(target,
               f"↷ Куда перенести «{_esc(mv['title'])}»?\n"
               "Напишите дату и время — «завтра 15:00», «12.09 18:30» — "
               "или сдвиньте кнопкой.",
               InlineKeyboardMarkup(inline_keyboard=rows))


async def _apply_move(target, state: FSMContext, user, new_start: datetime):
    data = await state.get_data()
    mv = data.get("mv") or {}
    purpose = mv.get("purpose")

    if purpose == "new":
        draft = data.get("draft") or {}
        draft["date"] = new_start.date().isoformat()
        draft["time"] = new_start.strftime("%H:%M")
        await state.update_data(draft=draft, mv=None)
        return await _try_save(target, state, user)

    event_id = mv["eid"]
    origin = _unkey(mv["date"])
    ev = await database.plan_event(event_id)
    if not ev:
        await state.clear()
        return await _say(target, "Событие уже удалено — переносить нечего.")

    single = mv.get("scope") == "one" and ev["repeat_rule"]
    if single:
        ok = await database.plan_set_override(event_id, origin, new_start, None, user.id)
    else:
        ok = await database.plan_reschedule(event_id, new_start)
    if not ok:
        return await _say(target, "😔 Не удалось перенести — база не ответила.")

    # На новом месте тоже может быть занято. Не запрещаем — участники сами
    # решают, накладки бывают осознанными, — но молчать об этом нельзя.
    probe = {"id": event_id, "title": ev["title"], "description": "",
             "starts_at": new_start, "duration_min": ev["duration_min"],
             "repeat_rule": None if single else ev["repeat_rule"],
             "repeat_until": ev["repeat_until"], "created_by": 0,
             "created_by_name": "", "cancelled": False}
    warn = ""
    for _, busy in (await _find_conflicts(probe))[:1]:
        b_end = busy["start"] + timedelta(minutes=busy["duration"])
        warn = (f"\n\n⚠️ На новом месте пересечение: {busy['start']:%d.%m} "
                f"{busy['start']:%H:%M}–{b_end:%H:%M} «{_esc(busy['event']['title'])}»")

    scope_word = "занятие" if single else ("серия" if ev["repeat_rule"] else "событие")
    moved = (f"↷ «{_esc(ev['title'])}»: {scope_word} перенесено на "
             f"{_fmt_day(new_start.date())}, {new_start:%H:%M}." + warn)

    if purpose == "old":
        # Прежнее подвинули — возвращаемся к тому, ради чего всё затевалось
        await state.update_data(mv=None, clash=None)
        await _say(target, moved)
        return await _try_save(target, state, user)

    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📅 Открыть день",
                             callback_data=f"plan:d:{_key(new_start.date())}")]])
    await _say(target, moved, kb)


# --- ХЕНДЛЕРЫ: ПОКАЗ ---

# Последний экран каждого участника: переключатель «кратко/подробно» обязан
# перерисовать ровно то, на что человек смотрит, а в нажатии кнопки этого нет.
_last_view: dict = {}


async def _open(call: CallbackQuery, mode: str, anchor: date):
    _last_view[call.from_user.id] = (mode, _key(anchor))
    text, kb = await _render(mode, anchor, call.from_user.id)
    await _show(call, text, kb)


@router.callback_query(F.data == "plan:open")
async def dash_open(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await _open(call, "w", await _today())
    await call.answer()


@router.callback_query(F.data.startswith("plan:v:"))
async def dash_view(call: CallbackQuery):
    _, _, mode, key = call.data.split(":")
    await _open(call, mode, _unkey(key))
    await call.answer()


@router.callback_query(F.data.startswith("plan:d:"))
async def dash_day(call: CallbackQuery):
    await _open(call, "d", _unkey(call.data.split(":")[2]))
    await call.answer()


@router.callback_query(F.data == "plan:det")
async def dash_detail(call: CallbackQuery):
    user_id = call.from_user.id
    _detail[user_id] = not _detail.get(user_id, False)
    mode, key = _last_view.get(user_id, ("w", _key(await _today())))
    await _open(call, mode, _unkey(key))
    await call.answer("Подробно" if _detail[user_id] else "Кратко")


@router.callback_query(F.data == "plan:noop")
async def dash_noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data.startswith("plan:e:"))
async def dash_card(call: CallbackQuery):
    _, _, eid, key = call.data.split(":")
    occ = await _occurrence(int(eid), _unkey(key))
    if not occ:
        await call.answer("Это событие уже отменили", show_alert=True)
        return await dash_day_key(call, _unkey(key))
    await _show(call, _card_text(occ), _card_kb(occ))
    await call.answer()


async def dash_day_key(call: CallbackQuery, d: date):
    await _open(call, "d", d)


# --- ХЕНДЛЕРЫ: ДОБАВЛЕНИЕ ---

async def _guard(call: CallbackQuery) -> bool:
    if await _may_edit(call.from_user.id):
        return True
    await call.answer("Календарь ведут участники команды — у вас только просмотр.",
                      show_alert=True)
    return False


@router.callback_query(F.data.startswith("plan:add:") | F.data.startswith("plan:addd:"))
async def add_start(call: CallbackQuery, state: FSMContext):
    if not await _guard(call):
        return
    parts = call.data.split(":")
    draft = {}
    if parts[1] == "addd":
        # Кнопка со страницы дня: дату человек уже выбрал, спрашивать её снова незачем
        draft["date"] = _unkey(parts[2]).isoformat()
    await state.clear()
    await state.update_data(draft=draft)
    await call.answer()
    await _ask_next(call, state, call.from_user)


@router.callback_query(F.data.startswith("plan:day:"))
async def add_pick_day(call: CallbackQuery, state: FSMContext):
    draft = (await state.get_data()).get("draft") or {}
    draft["date"] = ((await _today()) + timedelta(days=int(call.data.split(":")[2]))).isoformat()
    await state.update_data(draft=draft)
    await call.answer()
    await _ask_next(call, state, call.from_user)


@router.callback_query(F.data.startswith("plan:tm:"))
async def add_pick_time(call: CallbackQuery, state: FSMContext):
    draft = (await state.get_data()).get("draft") or {}
    draft["time"] = call.data.split(":", 2)[2]
    await state.update_data(draft=draft)
    await call.answer()
    await _ask_next(call, state, call.from_user)


@router.callback_query(F.data.startswith("plan:dur:"))
async def add_pick_dur(call: CallbackQuery, state: FSMContext):
    draft = (await state.get_data()).get("draft") or {}
    draft["dur"] = int(call.data.split(":")[2])
    await state.update_data(draft=draft)
    await call.answer()
    await _ask_next(call, state, call.from_user)


@router.callback_query(F.data.startswith("plan:rep:"))
async def add_pick_repeat(call: CallbackQuery, state: FSMContext):
    draft = (await state.get_data()).get("draft") or {}
    rule = call.data.split(":")[2]
    draft["rule"] = None if rule == "once" else rule
    await state.update_data(draft=draft)
    await call.answer()
    await _ask_next(call, state, call.from_user)


@router.callback_query(F.data.startswith("plan:until:"))
async def add_pick_until(call: CallbackQuery, state: FSMContext):
    draft = (await state.get_data()).get("draft") or {}
    start = date.fromisoformat(draft.get("date") or (await _today()).isoformat())
    draft["until"] = (start + timedelta(days=int(call.data.split(":")[2]))).isoformat()
    await state.update_data(draft=draft)
    await call.answer()
    await _ask_next(call, state, call.from_user)


@router.callback_query(F.data == "plan:skip")
async def add_skip_desc(call: CallbackQuery, state: FSMContext):
    draft = (await state.get_data()).get("draft") or {}
    draft["desc"] = ""
    await state.update_data(draft=draft)
    await call.answer()
    await _ask_next(call, state, call.from_user)


@router.message(StateFilter(Add.date, Add.time, Add.dur, Add.rule))
async def add_free_text(message: Message, state: FSMContext):
    """Любой ответ разбирается как целая фраза: человек может дописать сразу
    и время, и длительность, и тему — переспрашивать это потом незачем."""
    raw = (message.text or "").strip()
    if not raw:
        return
    current = await state.get_state()
    draft = (await state.get_data()).get("draft") or {}

    # Голое число в ответе на «во сколько» и «сколько длится» — это час и
    # минуты соответственно, а не название события.
    if current == Add.time.state and re.fullmatch(r"([01]?\d|2[0-3])", raw):
        parsed = {"time": f"{int(raw):02d}:00"}
    elif current == Add.dur.state and re.fullmatch(r"\d{1,3}", raw):
        parsed = {"dur": int(raw)}
    else:
        parsed = parse_phrase(raw, await _today())

    for key, value in parsed.items():
        draft.setdefault(key, value)
    await state.update_data(draft=draft)

    missing = {Add.date.state: "date", Add.time.state: "time",
               Add.dur.state: "dur", Add.rule.state: "rule"}.get(current)
    if missing and missing not in draft:
        await message.answer("🤔 Не разобрал — попробуйте иначе или нажмите кнопку.")
    await _ask_next(message, state, message.from_user)


@router.message(Add.until)
async def add_until_text(message: Message, state: FSMContext):
    when, _ = _pick_date(message.text or "", await _today())
    if not when:
        return await message.answer("🤔 Не понял дату. Напишите, например, «31.12».")
    draft = (await state.get_data()).get("draft") or {}
    draft["until"] = when.isoformat()
    await state.update_data(draft=draft)
    await _ask_next(message, state, message.from_user)


@router.message(Add.title)
async def add_title_text(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    if not raw:
        return
    body, _, tail = raw.partition("\n")
    draft = (await state.get_data()).get("draft") or {}
    draft["title"] = re.sub(r"\s+", " ", body).strip()[:120]
    if tail.strip():
        draft["desc"] = tail.strip()[:1000]
    await state.update_data(draft=draft)
    await _ask_next(message, state, message.from_user)


@router.message(Add.desc)
async def add_desc_text(message: Message, state: FSMContext):
    draft = (await state.get_data()).get("draft") or {}
    draft["desc"] = (message.text or "").strip()[:1000]
    await state.update_data(draft=draft)
    await _ask_next(message, state, message.from_user)


@router.message(Add.conflict)
async def add_conflict_text(message: Message):
    await message.answer("Выберите кнопкой, что делать с занятым временем.")


# --- ХЕНДЛЕРЫ: КОНФЛИКТ ---

@router.callback_query(F.data.startswith("plan:cf:"))
async def conflict_choice(call: CallbackQuery, state: FSMContext):
    if not await _guard(call):
        return
    parts = call.data.split(":")
    action = parts[2]
    scope = parts[3] if len(parts) > 3 else "all"

    data = await state.get_data()
    draft = data.get("draft") or {}
    clash = data.get("clash") or {}
    user = call.from_user
    await call.answer()

    if action == "drop":
        await state.clear()
        return await _say(call, "Хорошо, ничего не меняю.")

    if action == "both":
        return await _try_save(call, state, user, force=True)

    if not clash:
        await state.clear()
        return await _say(call, "Диалог устарел — начните заново кнопкой «➕ Добавить».")

    if action == "oldx":
        event_id, origin = clash["eid"], _unkey(clash["date"])
        if scope == "one" and clash["series"]:
            ok = await database.plan_set_override(event_id, origin, None, None, user.id)
            what = f"занятие {_fmt_day(origin, weekday=False)}"
        else:
            ok = await database.plan_cancel(event_id)
            what = "серия целиком" if clash["series"] else "событие"
        if not ok:
            return await _say(call, "😔 База не ответила, прежнее событие осталось на месте.")
        await _say(call, f"❌ «{_esc(clash['title'])}»: {what} отменено.")
        return await _try_save(call, state, user)

    if action == "oldm":
        return await _ask_move(call, state, {
            "purpose": "old", "eid": clash["eid"], "date": clash["date"],
            "scope": scope, "title": clash["title"], "base": clash["start"],
        })

    if action == "newm":
        row = _draft_row(draft)
        return await _ask_move(call, state, {
            "purpose": "new", "eid": 0, "date": _key(row["starts_at"].date()),
            "scope": "all", "title": draft.get("title", "новое событие"),
            "base": row["starts_at"].isoformat(), "after": clash.get("end"),
        })


@router.callback_query(F.data.startswith("plan:mq:"))
async def move_quick(call: CallbackQuery, state: FSMContext):
    mv = (await state.get_data()).get("mv") or {}
    if not mv:
        await call.answer("Диалог устарел", show_alert=True)
        return await state.clear()
    code = call.data.split(":")[2]
    if code == "after" and mv.get("after"):
        new_start = datetime.fromisoformat(mv["after"])
    else:
        new_start = datetime.fromisoformat(mv["base"]) + timedelta(minutes=int(code))
    await call.answer()
    await _apply_move(call, state, call.from_user, new_start)


@router.message(Add.move)
async def move_text(message: Message, state: FSMContext):
    mv = (await state.get_data()).get("mv") or {}
    if not mv:
        await state.clear()
        return await message.answer("Диалог устарел — откройте событие заново.")

    base = datetime.fromisoformat(mv["base"])
    when, rest = _pick_date(message.text or "", await _today())
    at, _ = _pick_time(rest)
    if not when and not at:
        return await message.answer("🤔 Не понял. Напишите «завтра 15:00» или «12.09 18:30».")

    new_start = datetime.combine(when or base.date(), at or base.time())
    await _apply_move(message, state, message.from_user, new_start)


# --- ХЕНДЛЕРЫ: КАРТОЧКА СОБЫТИЯ ---

@router.callback_query(F.data.startswith("plan:mv:"))
async def card_move(call: CallbackQuery, state: FSMContext):
    if not await _guard(call):
        return
    _, _, eid, key, scope = call.data.split(":")
    occ = await _occurrence(int(eid), _unkey(key))
    if not occ:
        return await call.answer("Событие уже отменили", show_alert=True)
    await state.clear()
    await call.answer()
    await _ask_move(call, state, {
        "purpose": "card", "eid": int(eid), "date": key, "scope": scope,
        "title": occ["event"]["title"], "base": occ["start"].isoformat(),
    })


@router.callback_query(F.data.startswith("plan:del:"))
async def card_delete(call: CallbackQuery):
    if not await _guard(call):
        return
    _, _, eid, key, scope = call.data.split(":")
    occ = await _occurrence(int(eid), _unkey(key))
    if not occ:
        return await call.answer("Событие уже отменили", show_alert=True)

    if scope == "all" and occ["event"]["repeat_rule"]:
        # Отмена всей серии стирает и будущие занятия — такое лучше переспросить
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Да, отменить всю серию",
                                  callback_data=f"plan:delok:{eid}:{key}:all")],
            [InlineKeyboardButton(text="🔙 Нет, вернуться",
                                  callback_data=f"plan:e:{eid}:{key}")],
        ])
        await _show(call, _card_text(occ) + "\n\n⚠️ Отменить <b>всю серию</b>, включая будущие занятия?", kb)
        return await call.answer()

    await _do_delete(call, int(eid), _unkey(key), scope)


@router.callback_query(F.data.startswith("plan:delok:"))
async def card_delete_ok(call: CallbackQuery):
    if not await _guard(call):
        return
    _, _, eid, key, scope = call.data.split(":")
    await _do_delete(call, int(eid), _unkey(key), scope)


async def _do_delete(call: CallbackQuery, event_id: int, origin: date, scope: str):
    ev = await database.plan_event(event_id)
    day = origin
    if scope == "one" and ev and ev["repeat_rule"]:
        ok = await database.plan_set_override(event_id, origin, None, None, call.from_user.id)
        note = "Занятие отменено, остальные в серии остались"
    else:
        ok = await database.plan_cancel(event_id)
        note = "Событие отменено"
    await call.answer(note if ok else "База не ответила", show_alert=not ok)
    await _open(call, "d", day)


@router.callback_query(F.data.startswith("plan:desc:"))
async def card_desc(call: CallbackQuery, state: FSMContext):
    if not await _guard(call):
        return
    _, _, eid, key = call.data.split(":")
    await state.clear()
    await state.set_state(Add.edit_desc)
    await state.update_data(ed={"eid": int(eid), "key": key})
    await call.answer()
    await _say(call, "✏️ Пришлите новое описание одним сообщением.")


@router.message(Add.edit_desc)
async def card_desc_text(message: Message, state: FSMContext):
    ed = (await state.get_data()).get("ed") or {}
    await state.clear()
    if not ed:
        return await message.answer("Диалог устарел — откройте событие заново.")
    ok = await database.plan_set_description(ed["eid"], (message.text or "").strip()[:1000])
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📌 К событию",
                             callback_data=f"plan:e:{ed['eid']}:{ed['key']}")]])
    await message.answer("✅ Описание обновлено." if ok else "😔 Не сохранилось.", reply_markup=kb)


# --- КОМАНДЫ ---

HELP = (
    "📅 <b>Общее расписание</b>\n\n"
    "• <code>/plan</code> — календарь: неделя, месяц, год\n"
    "• <code>/plan_add завтра в 14:30 на час тренировка</code> — добавить одной фразой\n"
    "• Повтор: «каждую неделю до 31.12», «каждый день», «раз в две недели»\n"
    "• Чего в фразе не хватит — спрошу\n"
    "• Если время занято, предложу отменить или перенести — прежнее событие или новое\n"
    "• В карточке события видно тему, описание и кто его добавил"
)


@router.message(F.text.regexp(r"^/plan(@\w+)?$"))
async def cmd_plan(message: Message, state: FSMContext):
    await state.clear()
    today = await _today()
    _last_view[message.from_user.id] = ("w", _key(today))
    text, kb = await _week_view(today, message.from_user.id)
    await message.answer(text, reply_markup=kb, disable_web_page_preview=True)


@router.message(F.text.regexp(r"^/plan_help(@\w+)?$"))
async def cmd_plan_help(message: Message):
    await message.answer(HELP)


@router.message(F.text.regexp(r"^/plan_add(@\w+)?(\s|$)"))
async def cmd_plan_add(message: Message, state: FSMContext):
    if not await _may_edit(message.from_user.id):
        return await message.answer("Календарь ведут участники команды — у вас только просмотр.")
    phrase = re.sub(r"^/plan_add(@\w+)?\s*", "", message.text or "", flags=re.I)
    await state.clear()
    await state.update_data(draft=parse_phrase(phrase, await _today()) if phrase.strip() else {})
    await _ask_next(message, state, message.from_user)


@router.message(F.text.regexp(r"^/plan_users(@\w+)?(\s|$)"))
async def cmd_plan_users(message: Message):
    """Кто может писать в общий календарь. Без списка — можно всем."""
    if not config.is_admin(message.from_user.id):
        return
    arg = re.sub(r"^/plan_users(@\w+)?\s*", "", message.text or "", flags=re.I).strip()
    if not arg:
        current = sorted(await _members())
        return await message.answer(
            f"Участники календаря: {', '.join(map(str, current)) if current else 'все подряд'}\n"
            "Задать: <code>/plan_users 111,222</code>, снять ограничение: <code>/plan_users -</code>")
    ids = re.findall(r"\d{5,}", arg)
    await database.set_setting(MEMBERS_KEY, ",".join(ids))
    await message.answer(f"Готово. Пишут в календарь: {', '.join(ids) if ids else 'все подряд'}")
