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
import time

from aiogram import Router, F, Bot
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
    "course_mba": "🎓 MBA и «Лидеры России»",
    "course_ai": "🤖 ИИ в работе и CI/CD для LLM",
}

# Цена в звёздах Telegram: (дней, звёзд). Сотня звёзд — около двух
# долларов; это цена чашки кофе, а не курса, и спорить с ней не хочется.
TARIFFS = {
    "1": (30, 100),
    "3": (90, 250),
    "12": (365, 800),
}

TARIFF_NAMES = {"1": "месяц", "3": "три месяца", "12": "год"}

# Цена переводом, в рублях. Отдельно от звёзд: у звезды свой курс, и
# пересчитывать его на лету — значит показывать человеку каждый раз
# новое число. Правится здесь.
PRICE_RUB = {"1": 199, "3": 499, "12": 1490}

# Заявка «я оплатил»: кто, что и когда. Живёт в настройках, чтобы
# пережить перезапуск, — человек ждёт ответа, а не деплоя.
CLAIM_KEY = "pay_claim_"         # + id: «навык|тариф|время»
CLAIM_PAUSE = 300                # секунд между заявками одного человека

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
    """Чем платить.

    Звёзды работают всегда и открывают доступ мгновенно. Перевод даёт
    деньги на счёт, но подтверждение приходит не в бот, а в банк —
    поэтому рядом с ним кнопка «я оплатил»: она зовёт владельца, а не
    просит человека писать в личку и объясняться.
    """
    rows = [[InlineKeyboardButton(
        text=f"⭐ {TARIFF_NAMES[code]} — {stars}",
        callback_data=f"buy_skill_{skill}_{code}")]
        for code, (_, stars) in TARIFFS.items()]

    card = await pay_url(skill)
    if card:
        rows.append([InlineKeyboardButton(
            text=f"💳 Перевод — {PRICE_RUB['1']} ₽ за месяц", url=card)])
        rows.append([InlineKeyboardButton(
            text="✅ Я оплатил переводом",
            callback_data=f"pay_claim_{skill}_1")])
    rows.append([InlineKeyboardButton(text="⇦", callback_data="go_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def wall_text(skill: str, done: str = "") -> str:
    """Экран «продолжить». Говорим, что человек уже прошёл, а не чего
    лишён: первое — его результат, второе — упрёк."""
    name = SKILLS.get(skill, "этот раздел")
    return (f"{done}\n\n" if done else "") + (
        f"<b>{html.escape(name)}</b>\n\n"
        "Дальше — остальные темы и разбор ошибок. Доступ открывается "
        "на месяц, три или год, и только к этому разделу: платить за то, "
        "чем не пользуетесь, незачем.")


# ---------------------------------------------------------------------
# «Я ОПЛАТИЛ»
# ---------------------------------------------------------------------
#
# Перевод приходит в банк, а не в бот: узнать о нём бот не может никак.
# Просить человека «напишите мне в личку» — потерять половину: он уже
# заплатил и не обязан ничего доказывать.
#
# Поэтому он нажимает кнопку, а владелица получает карточку с одной
# кнопкой «открыть». Сверить с выпиской — её работа, но на неё уходит
# секунда, а не переписка.

async def _claim_seen(user_id: int) -> bool:
    """Повторное нажатие в ближайшие минуты — не новая заявка"""
    raw = await database.get_setting(CLAIM_KEY + str(user_id)) or ""
    parts = raw.split("|")
    if len(parts) < 3:
        return False
    try:
        return time.time() - float(parts[2]) < CLAIM_PAUSE
    except ValueError:
        return False


@router.callback_query(F.data.startswith("pay_claim_"))
async def claim(call: CallbackQuery, bot: Bot):
    body = call.data[len("pay_claim_"):]
    skill, _, tier = body.rpartition("_")
    if skill not in SKILLS or tier not in TARIFFS:
        await call.answer()
        return

    if await _claim_seen(call.from_user.id):
        await call.answer("Заявка уже отправлена, жду ответа", show_alert=True)
        return

    await database.set_setting(CLAIM_KEY + str(call.from_user.id),
                               f"{skill}|{tier}|{time.time()}")
    await call.answer()
    await call.message.answer(
        "Спасибо! Сказала владелице — она сверит перевод и откроет доступ. "
        "Обычно это занимает несколько часов; бот напишет вам сам, "
        "отвечать не нужно.")

    who = call.from_user
    name = " ".join(x for x in [who.first_name, who.last_name] if x) or "—"
    tag = f"@{who.username}" if who.username else "без @"
    days = TARIFFS[tier][0]
    if not config.ADMIN_ID:
        return
    try:
        await bot.send_message(
            config.ADMIN_ID,
            f"💳 <b>Говорит, что оплатил переводом</b>\n\n"
            f"{html.escape(name)} · {html.escape(tag)} · <code>{who.id}</code>\n"
            f"{SKILLS[skill]} — {TARIFF_NAMES[tier]}, {PRICE_RUB[tier]} ₽\n\n"
            f"Сверьте с выпиской и откройте:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=f"✅ Открыть на {days} дней",
                    callback_data=f"pay_ok_{who.id}_{skill}_{tier}")]]))
    except Exception as e:
        logging.error(f"Заявка об оплате не дошла до владельца: {e}")


@router.callback_query(F.data.startswith("pay_ok_"))
async def approve(call: CallbackQuery, bot: Bot):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return

    body = call.data[len("pay_ok_"):]
    head, _, tier = body.rpartition("_")
    buyer, _, skill = head.partition("_")
    if skill not in SKILLS or tier not in TARIFFS:
        await call.answer()
        return

    days = TARIFFS[tier][0]
    if not await database.grant_skill(int(buyer), skill, days, "перевод"):
        await call.answer("Не записалось — проверьте /db", show_alert=True)
        return

    await database.set_setting(CLAIM_KEY + buyer, "")

    # В журнал операций — туда же, где звёзды. Иначе половина выручки
    # живёт только в банковской выписке, и сверять её с «Моим налогом»
    # приходится по памяти.
    try:
        import finance
        await finance.record(
            kind="income", asset="RUB", amount=PRICE_RUB[tier],
            category="subscription",
            note=f"{skill}: {days} дней, перевод, user {buyer}",
            external_id=f"transfer_{buyer}_{int(time.time())}")
    except Exception as e:
        logging.error(f"Продажа не записана в журнал: {e}")

    await call.answer("Открыла")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(f"✅ {SKILLS[skill]} — открыт на {days} дней.")
    try:
        await bot.send_message(
            int(buyer), f"{SKILLS[skill]}\n\nДоступ открыт на {days} дней. "
                        f"Спасибо!")
    except Exception as e:
        logging.info(f"Купившему не написать: {e}")
        await call.message.answer("Сообщить ему не вышло — бот ему не писал раньше.")


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


@router.message(F.text.regexp(r"^/касса"))
async def till_command(message: Message):
    """Ссылка на оплату картой: общая или для одного навыка.

        /касса https://…              — на все навыки
        /касса lang_he https://…      — только на иврит
        /касса lang_he -              — убрать
    """
    if not config.is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        lines = ["<b>Ссылка на оплату картой</b>", ""]
        common = await database.get_setting("pay_url")
        lines.append(f"Общая: {html.escape(common) if common else '—'}")
        for skill, name in SKILLS.items():
            own = await database.get_setting(PAY_URL_KEY + skill)
            if own:
                lines.append(f"{name}: {html.escape(own)}")
        lines += ["", "<code>/касса https://ссылка</code> — на все навыки",
                  "<code>/касса lang_he https://ссылка</code> — на один",
                  "<code>/касса lang_he -</code> — убрать",
                  "",
                  "Пока ссылки нет, кнопки «оплатить картой» не будет: "
                  "вести в никуда хуже, чем не предлагать."]
        await message.answer("\n".join(lines), disable_web_page_preview=True)
        return

    if parts[1] in SKILLS:
        key, value = PAY_URL_KEY + parts[1], " ".join(parts[2:]).strip()
    else:
        key, value = "pay_url", " ".join(parts[1:]).strip()

    if value in ("-", "—", ""):
        await database.set_setting(key, "")
        await message.answer("Убрала. Кнопки картой больше нет.")
        return

    if not value.startswith("https://"):
        # Telegram не примет кнопку с другой схемой, и человек увидит
        # ошибку вместо оплаты.
        await message.answer("Ссылка должна начинаться с https://")
        return

    await database.set_setting(key, value)
    await message.answer(f"✅ Записала.\n{html.escape(value)}",
                         disable_web_page_preview=True)


@router.message(F.text.regexp(r"^/продажи"))
async def sales_command(message: Message):
    """Что продано — по месяцам, в той валюте, в которой пришло.

    Экран нужен для сверки: в «Моём налоге» чек выбивается на каждую
    оплату, и без списка их легко пропустить. Звёзды и рубли не
    складываем: это разные деньги, и в налог идут по-разному.
    """
    if not config.is_admin(message.from_user.id):
        return

    rows = await database.sales(90)
    if not rows:
        await message.answer(
            "Продаж пока нет.\n\nЗдесь появятся оплаты звёздами и "
            "переводом — с датой и суммой, чтобы сверять с «Моим налогом».")
        return

    by_month = {}
    for row in rows:
        key = row["occurred_at"].strftime("%Y-%m")
        by_month.setdefault(key, {}).setdefault(row["asset"], 0)
        by_month[key][row["asset"]] += float(row["amount"])

    lines = ["💳 <b>Продажи доступа</b>", ""]
    for month in sorted(by_month, reverse=True):
        year, mon = month.split("-")
        totals = ", ".join(
            f"{amount:.0f} {'⭐' if asset == 'XTR' else '₽'}"
            for asset, amount in sorted(by_month[month].items()))
        lines.append(f"<b>{MONTHS[int(mon)]} {year}</b> — {totals}")

    lines += ["", "<b>Последние:</b>"]
    for row in rows[:12]:
        mark = "⭐" if row["asset"] == "XTR" else "₽"
        lines.append(f"{row['occurred_at']:%d.%m} · {float(row['amount']):.0f} {mark} "
                     f"· {html.escape((row['note'] or '')[:40])}")

    lines += ["", "<i>Чек на каждую рублёвую оплату выбивается в «Моём "
              "налоге» — этот список для сверки.</i>"]
    await message.answer("\n".join(lines))


MONTHS = ["", "январь", "февраль", "март", "апрель", "май", "июнь", "июль",
          "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


@router.message(F.text.regexp(r"^/мои_навыки"))
async def my_skills(message: Message):
    rows = await database.skills_of(message.from_user.id)
    if not rows:
        await message.answer("Открытых навыков пока нет.")
        return
    lines = [f"• {SKILLS.get(skill, skill)} — до {until:%d.%m.%Y}"
             for skill, until in rows.items()]
    await message.answer("<b>Открыто:</b>\n" + "\n".join(lines))
