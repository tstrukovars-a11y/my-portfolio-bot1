# exchange.py — сколько дойдёт, если переводить из России в Израиль.
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

router = Router()

SERVICES_KEY = "transfer_services"
DEFAULT_AMOUNT = 50000          # с чего начинается разговор о переводе

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


def parse_service(text: str):
    """«Название | ссылка | 1.5% | 100 | 0.8%» → словарь либо None.

    Проценты и рубли различаем по знаку, а не по порядку: перепутать их
    местами легко, а ошибка в комиссии врёт в деньгах.
    """
    parts = [p.strip() for p in text.split("|")]
    if not parts or not parts[0]:
        return None

    item = {"name": parts[0][:40], "url": "", "percent": 0.0,
            "fixed": 0.0, "markup": 0.0}
    seen_percent = 0
    for part in parts[1:]:
        if part.startswith("http"):
            item["url"] = part[:200]
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
    return item


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


async def cross_rate():
    """Сколько шекелей за рубль. None — если курсов нет."""
    try:
        import fx_rates
        rates = await fx_rates.latest_rates()
    except Exception as e:
        logging.warning(f"Курсы для перевода недоступны: {e}")
        return None
    rub, ils = rates.get("RUB"), rates.get("ILS")
    if not rub or not ils:
        return None
    return ils / rub


def _money(value: float, mark: str) -> str:
    return f"{value:,.0f}".replace(",", " ") + " " + mark


async def report(amount: float) -> str:
    items = await services()
    if not items:
        return ("💱 <b>Перевод в Израиль</b>\n\nСписок сервисов пока пуст.\n\n"
                + DISCLAIMER)

    rate = await cross_rate()
    if not rate:
        return ("💱 <b>Перевод в Израиль</b>\n\nКурс сейчас недоступен — "
                "посчитать не могу. Загляните позже.\n\n" + DISCLAIMER)

    rows = compare(amount, items, rate)
    best = rows[0]["out"] if rows else 0
    lines = [f"💱 <b>Перевод в Израиль</b>",
             f"Отправляем <b>{_money(amount, '₽')}</b>. "
             f"Биржевой курс: 1 ₽ = {rate:.4f} ₪.", ""]

    for row in rows:
        name = html.escape(row["name"])
        title = f'<a href="{html.escape(row["url"])}">{name}</a>' if row["url"] else name
        # Разницу с лучшим показываем деньгами: «на 300 ₪ меньше» понятнее
        # любых процентов, потому что это те самые шекели.
        behind = best - row["out"]
        tail = f" · <i>−{_money(behind, '₪')}</i>" if behind >= 1 else " · 👍"
        lines.append(f"{title} — <b>{_money(row['out'], '₪')}</b>{tail}")
        lines.append(f"    <i>комиссия {_money(row['fee'], '₽')}, "
                     f"курс {row['rate']:.4f}</i>")

    lines += ["", DISCLAIMER]
    return "\n".join(lines)


# ---------------------------------------------------------------------
# ЭКРАНЫ
# ---------------------------------------------------------------------

AMOUNTS = (10000, 50000, 100000)


def _amounts_kb(current: float) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=("• " if abs(value - current) < 1 else "") + _money(value, "₽"),
        callback_data=f"xch_{value}") for value in AMOUNTS]]
    rows.append([InlineKeyboardButton(text="⇦", callback_data="sport_travel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text.regexp(r"^/(перевод|transfer)\b"))
async def transfer_command(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    amount = DEFAULT_AMOUNT
    if len(parts) > 1:
        cleaned = parts[1].replace(" ", "").replace(",", ".").replace(" ", "")
        try:
            amount = max(1.0, min(float(cleaned), 1e9))
        except ValueError:
            pass
    await message.answer(await report(amount), reply_markup=_amounts_kb(amount),
                         disable_web_page_preview=True)


@router.callback_query(F.data == "xch_open")
async def open_screen(call: CallbackQuery):
    await call.answer()
    await call.message.answer(await report(DEFAULT_AMOUNT),
                              reply_markup=_amounts_kb(DEFAULT_AMOUNT),
                              disable_web_page_preview=True)


@router.callback_query(F.data.regexp(r"^xch_\d+$"))
async def pick_amount(call: CallbackQuery):
    amount = float(call.data.split("_")[1])
    await call.answer()
    await call.message.answer(await report(amount),
                              reply_markup=_amounts_kb(amount),
                              disable_web_page_preview=True)


# ---------------------------------------------------------------------
# ВЕДЕНИЕ СПИСКА
# ---------------------------------------------------------------------

HELP = (
    "💱 <b>Сервисы перевода</b>\n\n"
    "Добавить:\n"
    "<code>/сервисы + Название | https://ссылка | 1.5% | 100 | 0.8%</code>\n\n"
    "По порядку: комиссия в процентах, фиксированная часть в рублях, "
    "наценка к биржевому курсу в процентах. Лишнее можно не писать.\n\n"
    "Удалить: <code>/сервисы -2</code>\n\n"
    "<i>Цифры берите из своего перевода, а не с сайта: там пишут курс, "
    "а не итог.</i>")


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
            lines.append(
                f"{i}. <b>{html.escape(item['name'])}</b> — "
                f"{item.get('percent', 0)}% + {item.get('fixed', 0):.0f} ₽, "
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
            f"✅ <b>{html.escape(item['name'])}</b>: "
            f"{item['percent']}% + {item['fixed']:.0f} ₽, "
            f"курс −{item['markup']}%.\n\nВсего сервисов: {len(items)}.")
        return

    await message.answer(HELP)
