import logging

from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery, LabeledPrice, PreCheckoutQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton
)
import access
import database
import finance

router = Router()

# Тарифы: код → (дней доступа, цена в звёздах Telegram).
# Оплата идёт звёздами, а не картой: Telegram требует продавать цифровые товары
# именно так, и это единственный способ без торгового счёта и токена провайдера.
TARIFFS = {
    "1": (30, 200),
    "3": (90, 500),
    "12": (365, 1500),
}

TARIFF_LABELS = {
    "ru": {"1": "⭐ Месяц — {stars}", "3": "⭐ 3 месяца — {stars}", "12": "⭐ Год — {stars}"},
    "en": {"1": "⭐ 1 month — {stars}", "3": "⭐ 3 months — {stars}", "12": "⭐ 1 year — {stars}"},
    "fr": {"1": "⭐ 1 mois — {stars}", "3": "⭐ 3 mois — {stars}", "12": "⭐ 1 an — {stars}"},
    "he": {"1": "⭐ חודש — {stars}", "3": "⭐ 3 חודשים — {stars}", "12": "⭐ שנה — {stars}"},
}


def tariff_rows(lang: str) -> list:
    """Кнопки тарифов — их показывают и лимит ИИ, и премиум-разделы"""
    labels = TARIFF_LABELS.get(lang, TARIFF_LABELS["en"])
    return [
        [InlineKeyboardButton(text=labels[code].format(stars=stars),
                              callback_data=f"buy_premium_{code}")]
        for code, (_, stars) in TARIFFS.items()
    ]

@router.callback_query(F.data.startswith("buy_skill_"))
async def buy_skill(call: CallbackQuery, bot: Bot):
    """Один навык, а не всё сразу: за иврит платят, за ИИ — нет."""
    body = call.data[len("buy_skill_"):]
    skill, _, tier = body.rpartition("_")
    if skill not in access.SKILLS or tier not in access.TARIFFS:
        await call.answer()
        return

    days, stars = access.TARIFFS[tier]
    name = access.SKILLS[skill]
    try:
        await bot.send_invoice(
            chat_id=call.from_user.id,
            title=name,
            description=f"Доступ на {days} дней. Только этот раздел.",
            payload=f"skill_{skill}_{days}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Stars", amount=stars)])
    except Exception as e:
        logging.error(f"Счёт за навык не выставлен: {type(e).__name__}: {e}")
        await call.message.answer("⚠️ Не удалось открыть оплату. Попробуйте позже.")
    await call.answer()


@router.callback_query(F.data.startswith("buy_premium_"))
async def process_buy_premium(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    tier = call.data.split("_")[2] # Получаем 1, 3 или 12 месяцев
    
    days, stars_amount = TARIFFS.get(tier, TARIFFS["1"])
    lang = await database.get_user_language(user_id)
    
    # Тексты инвойсов под разные языки
    titles = {
        "ru": "Claude AI Premium подписка",
        "en": "Claude AI Premium Subscription",
        "fr": "Abonnement Claude AI Premium",
        "he": "מנוי Claude AI Premium"
    }
    
    descriptions = {
        "ru": f"Доступ к нейросети Claude без дневных ограничений на {days} дней.",
        "en": f"Access to Claude AI without daily limits for {days} days.",
        "fr": f"Accès à Claude AI без лимитов pour {days} jours.",
        "he": f"גישה ל-Claude AI ללא הגבלה למשך {days} ימים."
    }

    # Выставляем инвойс на оплату звездами (XTR)
    try:
        await bot.send_invoice(
            chat_id=user_id,
            title=titles.get(lang, titles["en"]),
            description=descriptions.get(lang, descriptions["en"]),
            payload=f"premium_{days}",   # дни доступа возвращаются в successful_payment
            provider_token="",           # для звёзд токен провайдера всегда пустой
            currency="XTR",
            prices=[LabeledPrice(label="Stars", amount=stars_amount)]
        )
    except Exception as e:
        logging.error(f"Не удалось выставить счёт: {type(e).__name__}: {e}")
        fail = {"ru": "⚠️ Не удалось открыть оплату. Попробуйте позже.",
                "en": "⚠️ Could not open the payment. Please try later."}
        await call.message.answer(fail.get(lang, fail["en"]))
    await call.answer()

# Шаг 1 подтверждения платежа (Telegram запрашивает у бота, всё ли в порядке перед списанием)
@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

# Шаг 2: Успешная оплата. Начисляем дни в БД
@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    user_id = message.from_user.id
    payload = message.successful_payment.invoice_payload

    # В payload лежит либо «premium_30», либо «skill_lang_he_30»: общая
    # подписка открывает всё, покупка навыка — только его.
    skill = ""
    if payload.startswith("skill_"):
        skill, _, tail = payload[len("skill_"):].rpartition("_")
        days = int(tail)
        await database.grant_skill(user_id, skill, days, "stars")
    else:
        days = int(payload.split("_")[1])
        await database.add_or_extend_subscription(user_id, days)

    # И в общий журнал операций: charge_id уникален, поэтому повторная
    # доставка того же апдейта запись не задвоит.
    payment = message.successful_payment
    # Telegram отдаёт сумму в минимальных единицах валюты: для карт это копейки,
    # а для звёзд — целые звёзды. Без этой развилки карточный платёж записался бы
    # в сто раз больше.
    amount = (payment.total_amount if payment.currency == "XTR"
              else payment.total_amount / 100)
    await finance.record(
        kind="income", asset=payment.currency, amount=amount,
        category="subscription", note=f"{skill or 'premium'}: {days} дней, user {user_id}",
        external_id=payment.telegram_payment_charge_id,
    )
    
    lang = await database.get_user_language(user_id)

    if skill:
        await message.answer(
            f"🎉 {access.SKILLS.get(skill, skill)}\n\n"
            f"Доступ открыт на {days} дней. Спасибо!")
        return

    success_texts = {
        "ru": f"🎉 **Оплата успешно завершена!** Подписка активирована на {days} дней. Спасибо!",
        "en": f"🎉 **Payment successful!** Your subscription is active for {days} days. Thank you!",
        "fr": f"🎉 **Paiement réussi !** Votre abonnement est actif pour {days} jours. Merci !",
        "he": f"🎉 **התשלום בוצע בהצלחה!** המנוי שלך הופעל למשך {days} ימים. תודה!"
    }
    
    await message.answer(success_texts.get(lang, success_texts["en"]), parse_mode="Markdown")
