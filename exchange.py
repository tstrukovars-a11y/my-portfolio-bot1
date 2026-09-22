# exchange.py — сколько дойдёт при переводе между своими странами.
#
# Люди сравнивают курсы, а теряют на другом: комиссия отправителя, спред
# к курсу и комиссия получателя. Рекламируют всегда курс, а узнаётся
# итог — постфактум, когда деньги уже ушли. Здесь считается только итог.
#
# Чего этот модуль не делает и делать не должен:
#
#   • не принимает деньги и заявки;
#   • не сводит людей для обмена между собой;
#   • не обещает курс и не гарантирует условия.
#
# Всё это превратило бы справочник в посредника — а посредничество в
# переводах лицензируется и в России, и в Израиле, независимо от того,
# берёт ли посредник вознаграждение. Здесь только арифметика и ссылка на
# того, кто переводит на самом деле.
#
# Список сервисов зашивать в код нельзя: условия меняются месяцами, а
# неверная подсказка в деньгах хуже её отсутствия. Владелица ведёт его
# сама и правит после каждого своего перевода.
import html
import json
import logging

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)

import config
import database
import freshness

router = Router()

SERVICES_KEY = "transfer_services"
LOG_KEY = "transfer_log"        # свои переводы: что обещали и что дошло
LOG_MAX = 100                   # больше в настройку класть незачем

# Четыре страны, между которыми ходят деньги. Доллар и евро считаются
# через биржевой курс так же, как рубль с шекелем: разницы в арифметике
# нет, разница — в комиссиях сервисов, а их ведёт человек.
MONEY = {
    "RUB": {"mark": "₽", "flag": "🇷🇺", "steps": (10000, 50000, 100000)},
    "USD": {"mark": "$", "flag": "🇺🇸", "steps": (100, 500, 2000)},
    "EUR": {"mark": "€", "flag": "🇫🇷", "steps": (100, 500, 2000)},
    "ILS": {"mark": "₪", "flag": "🇮🇱", "steps": (500, 2000, 5000)},
}

# Направление по умолчанию: с него начинался модуль, и оно же самое
# частое — пока карты есть не везде.
DEFAULT_PAIR = ("RUB", "ILS")
DEFAULT_AMOUNT = 50000

DISCLAIMER = ("<i>Бот не переводит деньги и не принимает заявки. Это "
              "калькулятор: условия уточняйте у сервиса — они меняются.</i>")


# ---------------------------------------------------------------------
# СПРАВОЧНИК
# ---------------------------------------------------------------------

async def services() -> list:
    raw = await database.get_setting(SERVICES_KEY)
    if not raw:
        return []
    try:
        items = json.loads(raw)
        return items if isinstance(items, list) else []
    except (ValueError, TypeError):
        logging.error("Список сервисов перевода не читается")
        return []


async def save_services(items: list):
    await database.set_setting(SERVICES_KEY, json.dumps(items, ensure_ascii=False))


def parse_pair(text: str):
    """«RUB→ILS», «rub-ils», «₽→₪» → ("RUB", "ILS") либо None"""
    cleaned = text.upper().replace("→", " ").replace("->", " ") \
                  .replace("-", " ").replace(">", " ")
    for mark, code in (("₽", "RUB"), ("$", "USD"), ("€", "EUR"), ("₪", "ILS")):
        cleaned = cleaned.replace(mark, " " + code + " ")
    found = [word for word in cleaned.split() if word in MONEY]
    return (found[0], found[1]) if len(found) == 2 and found[0] != found[1] else None


def parse_service(text: str):
    """«Название | RUB→ILS | ссылка | 1.5% | 100 | 0.8%» → словарь.

    Проценты и рубли различаем по знаку, а не по порядку: перепутать их
    местами легко, а ошибка в комиссии врёт в деньгах.
    """
    parts = [p.strip() for p in text.split("|")]
    if not parts or not parts[0]:
        return None

    item = {"name": parts[0][:40], "url": "", "percent": 0.0,
            "fixed": 0.0, "markup": 0.0,
            "from": DEFAULT_PAIR[0], "to": DEFAULT_PAIR[1]}
    seen_percent = 0
    for part in parts[1:]:
        if part.startswith("http"):
            item["url"] = part[:200]
            continue
        pair = parse_pair(part)
        if pair:
            item["from"], item["to"] = pair
            continue
        value = part.replace(",", ".").replace("%", "").replace(" ", "")
        try:
            number = float(value)
        except ValueError:
            continue
        if "%" in part:
            # Первый процент — комиссия, второй — наценка к курсу.
            if seen_percent == 0:
                item["percent"] = number
            else:
                item["markup"] = number
            seen_percent += 1
        else:
            item["fixed"] = number
    return freshness.stamp(item)


# ---------------------------------------------------------------------
# СВОИ ПЕРЕВОДЫ
# ---------------------------------------------------------------------
#
# Витрина сервиса показывает курс, а не итог, и почти всегда лучше
# правды. Единственный источник настоящих цифр — собственная выписка.
#
# Поэтому каждый свой перевод записывается фактом: отправлено столько,
# дошло столько. Из этого считается действительная потеря в процентах —
# та самая, которую нигде не публикуют, — и она же поправляет карточку
# сервиса. Через полгода получается сравнение, проверенное деньгами.

async def log() -> list:
    raw = await database.get_setting(LOG_KEY)
    if not raw:
        return []
    try:
        items = json.loads(raw)
        return items if isinstance(items, list) else []
    except (ValueError, TypeError):
        return []


async def save_log(items: list):
    await database.set_setting(LOG_KEY, json.dumps(items[-LOG_MAX:],
                                                   ensure_ascii=False))


def real_loss(sent: float, got: float, rate: float) -> float:
    """Сколько процентов съел перевод целиком.

    Считаем от того, что дошло бы по биржевому курсу: это единственная
    честная точка отсчёта. Комиссия и спред здесь уже не разделяются —
    человеку и не нужно, ему важна итоговая потеря.
    """
    perfect = sent * rate
    if perfect <= 0:
        return 0.0
    return max(0.0, (perfect - got) / perfect * 100)


def loss_by_service(items: list) -> dict:
    """Средняя потеря по каждому сервису, по своим переводам"""
    sums = {}
    for row in items:
        key = (row.get("name", "—"), row.get("from"), row.get("to"))
        sums.setdefault(key, []).append(row.get("loss", 0))
    return {key: sum(values) / len(values) for key, values in sums.items()}


# ---------------------------------------------------------------------
# СЧЁТ
# ---------------------------------------------------------------------

def arrives(amount: float, service: dict, rate: float) -> dict:
    """Сколько шекелей дойдёт. rate — сколько ₪ за рубль по бирже.

    Считаем в том же порядке, в каком деньги тают: сначала комиссия с
    отправляемой суммы, потом обмен по курсу сервиса, который хуже
    биржевого на величину наценки.
    """
    fee = amount * float(service.get("percent", 0)) / 100 + float(service.get("fixed", 0))
    left = max(0.0, amount - fee)
    own_rate = rate * (1 - float(service.get("markup", 0)) / 100)
    return {"name": service.get("name", "—"), "url": service.get("url", ""),
            "fee": fee, "rate": own_rate, "out": left * own_rate}


def compare(amount: float, items: list, rate: float) -> list:
    """Сервисы по тому, сколько дойдёт, — а не по рекламному курсу"""
    return sorted((arrives(amount, item, rate) for item in items),
                  key=lambda row: row["out"], reverse=True)


async def cross_rate(src: str = None, dst: str = None):
    """Сколько единиц dst за одну src. None — если курсов нет.

    Курсы приходят к доллару, поэтому любая пара считается через него:
    отдельных рядов на каждое направление не нужно.
    """
    src = src or DEFAULT_PAIR[0]
    dst = dst or DEFAULT_PAIR[1]
    try:
        import fx_rates
        rates = await fx_rates.latest_rates()
    except Exception as e:
        logging.warning(f"Курсы для перевода недоступны: {e}")
        return None
    one, two = rates.get(src), rates.get(dst)
    if not one or not two:
        return None
    return two / one


def _money(value: float, code: str) -> str:
    mark = MONEY.get(code, {}).get("mark", code)
    # Мелкие валюты без копеек выглядят грубо: сто долларов и сто
    # десять — разные деньги, а «100» и «110» после округления рубля нет.
    digits = 0 if code == "RUB" or value >= 1000 else 2
    return f"{value:,.{digits}f}".replace(",", " ") + " " + mark


def pairs_with_services(items: list) -> list:
    """Направления, по которым есть что показать.

    Рисовать все двенадцать пар нельзя: одиннадцать из них пусты, и
    человек тыкает наугад.
    """
    seen = []
    for item in items:
        pair = (item.get("from", DEFAULT_PAIR[0]), item.get("to", DEFAULT_PAIR[1]))
        if pair not in seen:
            seen.append(pair)
    return seen


def _title(src: str, dst: str) -> str:
    return (f"💱 <b>Перевод {MONEY[src]['flag']} → {MONEY[dst]['flag']}</b>")


async def report(amount: float, src: str = None, dst: str = None) -> str:
    src = src or DEFAULT_PAIR[0]
    dst = dst or DEFAULT_PAIR[1]
    head = _title(src, dst)

    items = [item for item in await services()
             if item.get("from", DEFAULT_PAIR[0]) == src
             and item.get("to", DEFAULT_PAIR[1]) == dst]
    if not items:
        return (f"{head}\n\nПо этому направлению сервисов пока нет.\n\n"
                + DISCLAIMER)

    rate = await cross_rate(src, dst)
    if not rate:
        return (f"{head}\n\nКурс сейчас недоступен — посчитать не могу. "
                f"Загляните позже.\n\n" + DISCLAIMER)

    rows = compare(amount, items, rate)
    best = rows[0]["out"] if rows else 0
    # Что проверено своим переводом, а что переписано с витрины — разные
    # по надёжности вещи, и человек вправе это видеть.
    checked = loss_by_service(await log())
    lines = [head,
             f"Отправляем <b>{_money(amount, src)}</b>. Биржевой курс: "
             f"1 {MONEY[src]['mark']} = {rate:.4f} {MONEY[dst]['mark']}.", ""]

    for row in rows:
        name = html.escape(row["name"])
        title = f'<a href="{html.escape(row["url"])}">{name}</a>' if row["url"] else name
        # Разницу с лучшим показываем деньгами: «на 300 ₪ меньше» понятнее
        # любых процентов, потому что это те самые шекели.
        behind = best - row["out"]
        tail = (f" · <i>−{_money(behind, dst)}</i>"
                if behind >= (1 if dst == "RUB" else 0.01) else " · 👍")
        card = next((s for s in items if s.get("name") == row["name"]), {})
        seen = checked.get((row["name"], src, dst))
        mark = " ✓" if seen is not None else ""
        lines.append(f"{title}{mark} — <b>{_money(row['out'], dst)}</b>{tail}")
        note = (f"    <i>комиссия {_money(row['fee'], src)}, "
                f"курс {row['rate']:.4f}")
        note += (f" · проверено: теряли {seen:.1f}%</i>" if seen is not None
                 else f" · {freshness.label(card)}</i>")
        lines.append(note)

    if checked:
        lines.append("\n<i>✓ — цифры проверены своим переводом, "
                     "остальные взяты с витрины сервиса.</i>")
    lines.append(freshness.warning(items))
    lines += ["", DISCLAIMER]
    return "\n".join(line for line in lines if line)


# ---------------------------------------------------------------------
# ЭКРАНЫ
# ---------------------------------------------------------------------

def _kb(src: str, dst: str, amount: float, pairs: list) -> InlineKeyboardMarkup:
    rows = []
    # Суммы — в валюте отправления: предлагать сто тысяч долларов так же
    # глупо, как пятьсот рублей.
    steps = MONEY[src]["steps"]
    rows.append([InlineKeyboardButton(
        text=("• " if abs(value - amount) < 0.01 else "") + _money(value, src),
        callback_data=f"xch_{src}_{dst}_{value:g}") for value in steps])

    # Направления — только те, где есть сервисы. Двенадцать пустых кнопок
    # хуже одной: человек тыкает наугад и уходит.
    line = []
    for one, two in pairs:
        if (one, two) == (src, dst):
            continue
        line.append(InlineKeyboardButton(
            text=f"{MONEY[one]['flag']}→{MONEY[two]['flag']}",
            callback_data=f"xch_{one}_{two}_{MONEY[one]['steps'][1]:g}"))
        if len(line) == 4:
            rows.append(line)
            line = []
    if line:
        rows.append(line)

    rows.append([InlineKeyboardButton(text="⇦", callback_data="sport_travel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _screen(message: Message, src: str, dst: str, amount: float):
    pairs = pairs_with_services(await services()) or [DEFAULT_PAIR]
    await message.answer(await report(amount, src, dst),
                         reply_markup=_kb(src, dst, amount, pairs),
                         disable_web_page_preview=True)


@router.message(F.text.regexp(r"^/(перевод|transfer)\b"))
async def transfer_command(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    src, dst = DEFAULT_PAIR
    amount = DEFAULT_AMOUNT
    if len(parts) > 1:
        pair = parse_pair(parts[1])
        if pair:
            src, dst = pair
            amount = MONEY[src]["steps"][1]
        digits = "".join(c for c in parts[1] if c.isdigit() or c == ".")
        if digits:
            try:
                amount = max(1.0, min(float(digits), 1e9))
            except ValueError:
                pass
    await _screen(message, src, dst, amount)


@router.callback_query(F.data == "xch_open")
async def open_screen(call: CallbackQuery):
    await call.answer()
    pairs = pairs_with_services(await services())
    src, dst = pairs[0] if pairs else DEFAULT_PAIR
    await _screen(call.message, src, dst, MONEY[src]["steps"][1])


@router.callback_query(F.data.regexp(r"^xch_[A-Z]{3}_[A-Z]{3}_[\d.]+$"))
async def pick(call: CallbackQuery):
    _, src, dst, amount = call.data.split("_")
    await call.answer()
    if src not in MONEY or dst not in MONEY:
        return
    await _screen(call.message, src, dst, float(amount))


# ---------------------------------------------------------------------
# ВЕДЕНИЕ СПИСКА
# ---------------------------------------------------------------------

HELP = (
    "💱 <b>Сервисы перевода</b>\n\n"
    "Добавить:\n"
    "<code>/сервисы + Название | RUB→ILS | https://ссылка | 1.5% | 100 | 0.8%</code>"
    "\n\nПо порядку: направление, ссылка, комиссия в процентах, "
    "фиксированная часть в валюте отправления, наценка к биржевому курсу. "
    "Лишнее можно не писать; без направления будет ₽→₪.\n\n"
    "Валюты: <code>RUB</code>, <code>USD</code>, <code>EUR</code>, "
    "<code>ILS</code>.\n\n"
    "Удалить: <code>/сервисы -2</code>\n\n"
    "<i>Цифры берите из своего перевода, а не с сайта: там пишут курс, "
    "а не итог.</i>")


LOG_HELP = (
    "🧾 <b>Свои переводы</b>\n\n"
    "Записать факт из выписки:\n"
    "<code>/перевёл 50000 RUB→ILS Золотая корона 1736</code>\n\n"
    "То есть: отправила 50 000 ₽, дошло 1736 ₪. Название сервиса — как в "
    "справочнике.\n\n"
    "<i>Цифры берите из выписки, а не из обещаний: витрина показывает "
    "курс, а не итог, и почти всегда лучше правды.</i>")


@router.message(F.text.regexp(r"^/(перевёл|перевел|sent)\b"))
async def log_command(message: Message):
    """Записать состоявшийся перевод — и поправить им справочник"""
    if not config.is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        items = await log()
        if not items:
            await message.answer(LOG_HELP)
            return
        lines = ["🧾 <b>Свои переводы</b>", ""]
        for row in items[-10:][::-1]:
            lines.append(
                f"{MONEY[row['from']]['flag']}→{MONEY[row['to']]['flag']} "
                f"{html.escape(row['name'])}: "
                f"{_money(row['sent'], row['from'])} → "
                f"{_money(row['got'], row['to'])} "
                f"· <b>−{row['loss']:.1f}%</b>")
        average = loss_by_service(items)
        if average:
            lines += ["", "<b>В среднем теряли:</b>"]
            for (name, src, dst), value in sorted(average.items(),
                                                  key=lambda x: x[1]):
                lines.append(f"{MONEY[src]['flag']}→{MONEY[dst]['flag']} "
                             f"{html.escape(name)} — {value:.1f}%")
        lines += ["", LOG_HELP]
        await message.answer("\n".join(lines))
        return

    body = parts[1]
    pair = parse_pair(body)
    if not pair:
        await message.answer("Не поняла направление. Нужно, например, "
                             "<code>RUB→ILS</code>.\n\n" + LOG_HELP)
        return

    numbers = []
    words = []
    for word in body.split():
        cleaned = word.replace(",", ".").replace(" ", "")
        if parse_pair(word):
            continue
        try:
            numbers.append(float(cleaned))
        except ValueError:
            words.append(word)
    if len(numbers) < 2:
        await message.answer("Нужны два числа: сколько отправили и сколько "
                             "дошло.\n\n" + LOG_HELP)
        return

    src, dst = pair
    sent, got = numbers[0], numbers[-1]
    name = " ".join(words)[:40] or "—"

    rate = await cross_rate(src, dst)
    if not rate:
        await message.answer("Курс сейчас недоступен — без него потерю не "
                             "посчитать. Попробуйте позже.")
        return

    loss = real_loss(sent, got, rate)
    items = await log()
    items.append({"name": name, "from": src, "to": dst, "sent": sent,
                  "got": got, "loss": round(loss, 2)})
    await save_log(items)

    # Сразу сравниваем с тем, что записано в справочнике: расхождение
    # значит, что карточка врёт, и лучше узнать об этом сейчас.
    promised = None
    for service in await services():
        if service.get("name") == name and service.get("from") == src \
                and service.get("to") == dst:
            perfect = sent * rate
            out = arrives(sent, service, rate)["out"]
            promised = (perfect - out) / perfect * 100 if perfect else None
            break

    text = (f"✅ Записала.\n\n{MONEY[src]['flag']}→{MONEY[dst]['flag']} "
            f"{html.escape(name)}: {_money(sent, src)} → {_money(got, dst)}\n"
            f"Потеря к биржевому курсу: <b>{loss:.1f}%</b>")
    if promised is not None:
        diff = loss - promised
        if abs(diff) >= 0.3:
            text += (f"\n\n⚠️ В справочнике у него выходит {promised:.1f}% — "
                     f"расхождение {diff:+.1f}%. Стоит поправить цифры: "
                     f"<code>/сервисы</code>")
        else:
            text += f"\n\nСправочник сходится ({promised:.1f}%)."
    await message.answer(text)


@router.message(F.text.regexp(r"^/сервисы"))
async def services_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=1)
    items = await services()

    if len(parts) < 2:
        if not items:
            await message.answer(HELP)
            return
        lines = ["💱 <b>Сервисы перевода</b>", ""]
        for i, item in enumerate(items, 1):
            src = item.get("from", DEFAULT_PAIR[0])
            dst = item.get("to", DEFAULT_PAIR[1])
            lines.append(
                f"{i}. {MONEY[src]['flag']}→{MONEY[dst]['flag']} "
                f"<b>{html.escape(item['name'])}</b> — "
                f"{item.get('percent', 0)}% + "
                f"{_money(item.get('fixed', 0), src)}, "
                f"курс −{item.get('markup', 0)}%")
        lines += ["", HELP]
        await message.answer("\n".join(lines), disable_web_page_preview=True)
        return

    body = parts[1].strip()
    if body.startswith("-") and body[1:].strip().isdigit():
        number = int(body[1:].strip())
        if not 1 <= number <= len(items):
            await message.answer(f"Столько сервисов нет: их {len(items)}.")
            return
        gone = items.pop(number - 1)
        await save_services(items)
        await message.answer(f"Убрала: {html.escape(gone['name'])}")
        return

    if body.startswith("+"):
        item = parse_service(body[1:].strip())
        if not item:
            await message.answer("Не разобрала. Нужно хотя бы название.")
            return
        items.append(item)
        await save_services(items)
        await message.answer(
            f"✅ {MONEY[item['from']]['flag']}→{MONEY[item['to']]['flag']} "
            f"<b>{html.escape(item['name'])}</b>: "
            f"{item['percent']}% + {_money(item['fixed'], item['from'])}, "
            f"курс −{item['markup']}%.\n\nВсего сервисов: {len(items)}.")
        return

    await message.answer(HELP)
