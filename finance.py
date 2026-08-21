# finance.py — запись операций в общий журнал и пересчёт в шекели.
#
# Журнал общий для всех ботов (схема finance в той же базе), поэтому здесь
# только запись и пересчёт: отчёты будет строить отдельный учётный бот.
#
# Три вида активов пересчитываются по-разному, и это не деталь реализации,
# а суть дела:
#   • фиат   — курс известен, берём из модуля курсов;
#   • крипта — стейблкоины считаем как доллар, остальное без курса;
#   • звёзды — курс вывода плавает и задаётся вручную настройкой.
import logging
from datetime import date

import database

SOURCE = "vizitka_bot"          # какой бот записал операцию

FIAT = {"ILS", "USD", "EUR", "RUB"}
STABLE = {"USDT", "USDC"}       # к доллару один к одному с достаточной точностью
CRYPTO = STABLE | {"TON", "BTC", "ETH"}

# Сколько шекелей приносит одна звезда после комиссии Telegram. Значение
# плавает и зависит от магазина приложения, поэтому не зашито в код: владелец
# ставит его в настройках, увидев реальную сумму первого вывода.
STARS_RATE_KEY = "stars_ils_rate"


def asset_kind(asset: str) -> str:
    if asset == "XTR":
        return "stars"
    if asset in CRYPTO:
        return "crypto"
    return "fiat"


async def to_ils(amount: float, asset: str):
    """(сумма в шекелях, курс) либо (None, None), если курс неизвестен.

    Пустой результат честнее выдуманного: непересчитанные операции видны
    в отчёте отдельной строкой, а не растворяются в обороте.
    """
    if asset == "ILS":
        return round(amount, 2), 1.0

    if asset == "XTR":
        raw = await database.get_setting(STARS_RATE_KEY)
        try:
            rate = float(raw)
        except (TypeError, ValueError):
            return None, None
        return round(amount * rate, 2), rate

    # Курсы модуля хранятся как «сколько валюты за один доллар», поэтому
    # всё считается через доллар.
    import fx_rates
    rates = await fx_rates.latest_rates()
    ils = rates.get("ILS")
    if not ils:
        return None, None

    if asset in STABLE:
        return round(amount * ils, 2), ils

    per_usd = rates.get(asset)
    if not per_usd:
        return None, None            # TON, BTC и прочее — курса у нас нет
    rate = ils / per_usd
    return round(amount * rate, 2), rate


async def record(kind: str, asset: str, amount: float, category: str = None,
                 note: str = None, external_id: str = None,
                 source: str = SOURCE) -> str:
    """Записывает операцию, пересчитав её в шекели, если курс известен"""
    amount_ils, rate = await to_ils(amount, asset)
    result = await database.add_transaction(
        source=source, kind=kind, asset=asset, asset_kind=asset_kind(asset),
        amount=amount, amount_ils=amount_ils, rate_ils=rate,
        rate_at=date.today() if rate else None,
        category=category, note=note, external_id=external_id,
    )
    if result.startswith("error"):
        logging.error(f"Операция не записана: {kind} {amount} {asset} — {result}")
    return result
