import logging

from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery, LabeledPrice, PreCheckoutQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton
)
import database

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
    days = int(payload.split("_")[1]) # Достаем количество дней из payload
    
    # Записываем подписку в единую базу данных
    await database.add_or_extend_subscription(user_id, days)
    
    lang = await database.get_user_language(user_id)
    
    success_texts = {
        "ru": f"🎉 **Оплата успешно завершена!** Подписка активирована на {days} дней. Спасибо!",
        "en": f"🎉 **Payment successful!** Your subscription is active for {days} days. Thank you!",
        "fr": f"🎉 **Paiement réussi !** Votre abonnement est actif pour {days} jours. Merci !",
        "he": f"🎉 **התשלום בוצע בהצלחה!** המנוי שלך הופעל למשך {days} ימים. תודה!"
    }
    
    await message.answer(success_texts.get(lang, success_texts["en"]), parse_mode="Markdown")
