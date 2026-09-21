# access.py — что человек уже купил.
#
# Навыки продаются поштучно. Общая подписка выглядит выгоднее для
# продавца, но покупают её хуже: за иврит человек платить готов, за ИИ,
# который ему не нужен, — нет. Дешёвый и понятный доступ к одной вещи
# продаётся сам, а сложный тариф приходится объяснять.
#
# Пробное — не «демо-режим», а настоящий первый урок целиком. Показать
# огрызок значит показать, что продукт плохой: человек должен успеть
# понять на себе, что слух без перевода работает, — и только тогда
# вопрос о деньгах становится честным.
#
# Способ оплаты здесь намеренно не один. Звёзды Telegram работают сразу
# и без реквизитов, но приходят криптовалютой через Fragment. Карта даёт
# деньги на счёт, но требует кассы, сайта и ИНН. Поэтому модуль знает
# только одно — открыт доступ или нет, — а чем именно заплатили, его не
# касается: оплата любым способом заканчивается одним и тем же вызовом
# database.grant_skill.
import html
import logging

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)

import config
import database

router = Router()

# Навык → как он называется человеку. Ключ уходит в базу и в платёж,
# поэтому меняться не должен.
SKILLS = {
    "lang_he": "🎧 Иврит на слух",
    "lang_fr": "🎧 Французский на слух",
    "lang_en": "🎧 Английский на слух",
}

# Цена в звёздах Telegram: (дней, звёзд). Сотня звёзд — около двух
# долларов; это цена чашки кофе, а не курса, и спорить с ней не хочется.
TARIFFS = {
    "1": (30, 100),
    "3": (90, 250),
    "12": (365, 800),
}

TARIFF_NAMES = {"1": "месяц", "3": "три месяца", "12": "год"}

# Ссылка на оплату картой, если она заведена: настройка pay_url_<навык>
# или общая pay_url. Пока её нет, кнопки просто не будет.
PAY_URL_KEY = "pay_url_"


async def has(user_id: int, skill: str) -> bool:
    if config.is_admin(user_id):
        return True
    return await database.skill_until(user_id, skill) is not None


async def pay_url(skill: str) -> str:
    return (await database.get_setting(PAY_URL_KEY + skill)
            or await database.get_setting("pay_url") or "")


async def buy_kb(skill: str) -> InlineKeyboardMarkup:
    """Чем платить. Звёзды всегда, карта — если заведена касса."""
    rows = [[InlineKeyboardButton(
        text=f"⭐ {TARIFF_NAMES[code]} — {stars}",
        callback_data=f"buy_skill_{skill}_{code}")]
        for code, (_, stars) in TARIFFS.items()]

    card = await pay_url(skill)
    if card:
        rows.append([InlineKeyboardButton(text="💳 Оплатить картой", url=card)])
    rows.append([InlineKeyboardButton(text="⇦", callback_data="go_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def wall_text(skill: str, done: str = "") -> str:
    """Экран «продолжить». Говорим, что человек уже прошёл, а не чего
    лишён: первое — его результат, второе — упрёк."""
    name = SKILLS.get(skill, "этот раздел")
    return (f"{done}\n\n" if done else "") + (
        f"<b>{html.escape(name)}</b>\n\n"
        "Дальше — остальные темы и разбор ошибок. Доступ открывается "
        "на месяц, три или год, и только к этому языку: платить за то, "
        "чем не пользуетесь, незачем.")


# ---------------------------------------------------------------------
# РУЧНАЯ ВЫДАЧА
# ---------------------------------------------------------------------
#
# Карта приносит деньги на счёт, но подтверждение приходит не в бот, а в
# кассу. Пока касса не связана с ботом, доступ открывается руками — это
# полминуты и не стоит того, чтобы ждать интеграцию.

@router.message(F.text.regexp(r"^/доступ"))
async def grant_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer(
            "<b>Открыть доступ вручную</b>\n\n"
            "<code>/доступ 123456789 lang_he 30</code>\n\n"
            "Навыки: " + ", ".join(f"<code>{k}</code>" for k in SKILLS) +
            "\nДней можно не писать — по умолчанию 30.")
        return

    try:
        user_id = int(parts[1])
        skill = parts[2]
        days = int(parts[3]) if len(parts) > 3 else 30
    except ValueError:
        await message.answer("Не разобрала. Нужно: /доступ id навык дней")
        return

    if skill not in SKILLS:
        await message.answer(f"Нет такого навыка: {html.escape(skill)}")
        return

    if await database.grant_skill(user_id, skill, days, "вручную"):
        await message.answer(
            f"✅ {SKILLS[skill]} — открыт для {user_id} на {days} дней.")
        try:
            await message.bot.send_message(
                user_id, f"{SKILLS[skill]}\n\nДоступ открыт. Приятных уроков!")
        except Exception as e:
            logging.info(f"Купившему не написать: {e}")
            await message.answer("Сообщить ему не вышло — бот ему не писал раньше.")
        return
    await message.answer("⚠️ Не записалось. Проверьте базу: /db")


@router.message(F.text.regexp(r"^/мои_навыки"))
async def my_skills(message: Message):
    rows = await database.skills_of(message.from_user.id)
    if not rows:
        await message.answer("Открытых навыков пока нет.")
        return
    lines = [f"• {SKILLS.get(skill, skill)} — до {until:%d.%m.%Y}"
             for skill, until in rows.items()]
    await message.answer("<b>Открыто:</b>\n" + "\n".join(lines))
