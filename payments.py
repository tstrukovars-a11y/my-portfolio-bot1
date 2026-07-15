from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, LabeledPrice, PreCheckoutQuery, Message
import database

router = Router()

@router.callback_query(F.data.startswith("buy_premium_"))
async def process_buy_premium(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    tier = call.data.split("_")[2] # Получаем 1, 3 или 12 месяцев
    
    # Конфигурация тарифов: (Дни подписки, Цена в Telegram Stars)
    prices = {
        "1": (30, 200),
        "3": (90, 500),
        "12": (365, 1500)
    }
    
    days, stars_amount = prices.get(tier, (30, 200))
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
    await bot.send_invoice(
        chat_id=user_id,
        title=titles.get(lang, titles["en"]),
        description=descriptions.get(lang, descriptions["en"]),
        payload=f"premium_{days}", # Передаем количество дней в payload
        provider_token="",         # Для Telegram Stars токен провайдера ВСЕГДА пустой
        currency="XTR",            # Валюта Telegram Stars
        prices=[LabeledPrice(label="Stars", amount=stars_amount)]
    )
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
