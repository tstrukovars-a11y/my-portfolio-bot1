# block7_analytics.py
import logging
import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import database

router = Router()

DASHBOARD_TEXTS = {
    "ru": (
        "📊 **Executive Product Analytics (Real-Time)**\n\n"
        "• **DAU** (Активность за 24ч): `{dau}` уникальных сессий\n"
        "• **MAU** (Активность за 30д): `{mau}` уникальных сессий\n"
        "• **Всего кликов в системе**: `{total}`\n\n"
        "📈 **Распределение трафика (Share of Traffic):**\n"
        "{sections_data}\n"
        "🌐 **Языковое расслоение аудитории:**\n"
        "{langs_data}\n"
        "*(Метрики генерируются динамически на базе SQL-логов базы данных)*"
    ),
    "en": (
        "📊 **Executive Product Analytics (Real-Time)**\n\n"
        "• **DAU** (24h Activity): `{dau}` unique sessions\n"
        "• **MAU** (30d Activity): `{mau}` unique sessions\n"
        "• **Total Logged Clicks**: `{total}`\n\n"
        "📈 **Traffic Share Vectors:**\n"
        "{sections_data}\n"
        "🌐 **Audience Language Breakdown:**\n"
        "{langs_data}\n"
        "*(Metrics generated dynamically via core db log arrays)*"
    )
}

def generate_progress_bar(percentage: float, total_blocks: int = 10) -> str:
    filled_blocks = int(round((percentage / 100) * total_blocks))
    return "█" * filled_blocks + "░" * (total_blocks - filled_blocks)

@router.callback_query(F.data == "menu_analytics")
async def show_analytics_dashboard(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    
    try:
        user_lang = await database.get_user_language(user_id)
    except Exception:
        user_lang = "ru"
        
    t = DASHBOARD_TEXTS.get(user_lang, DASHBOARD_TEXTS["en"])
    dau, mau, total_clicks = 0, 0, 0
    sections_list, langs_list = [], []
    
    try:
        dau, mau, total_clicks, sections_data, langs_data = await database.get_metrics_summary()

        if total_clicks > 0:
            top_sections = sorted(sections_data.items(), key=lambda x: x[1], reverse=True)[:4]
            for section_name, count in top_sections:
                pct = (count / total_clicks) * 100
                bar = generate_progress_bar(pct)
                sections_list.append(f"• `{section_name}`:\n  `{bar}` {pct:.1f}% ({count} кликов)")

            top_langs = sorted(langs_data.items(), key=lambda x: x[1], reverse=True)
            for l_code, count in top_langs:
                pct = (count / total_clicks) * 100
                langs_list.append(f"• `{l_code.upper()}`: {pct:.1f}%")
    except Exception as e:
        logging.error(f"Ошибка вычисления дашборда: {e}")

    sections_str = "\n".join(sections_list) if sections_list else "• `Нет данных` (собираем логи...)"
    langs_str = " | ".join(langs_list) if langs_list else "`Нет данных`"
    
    final_caption = t.format(dau=dau, mau=mau, total=total_clicks, sections_data=sections_str, langs_data=langs_str)
    
    # Финальная чистая и стабильная ссылка на веб-графики GitHub Pages
    # RENDER_EXTERNAL_URL создаётся автоматически на Render, вручную задавать не нужно
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
    web_app_url = "https://tstrukovars-a11y.github.io/my-portfolio-bot1/analytics.html"
    if render_url:
        web_app_url = f"{web_app_url}?api={render_url}/api/metrics"
    
    back_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Web App: Графики (Mini App)" if user_lang == "ru" else "📊 Open Mini App Charts", web_app=WebAppInfo(url=web_app_url))],
        [InlineKeyboardButton(text="🎯 Реклама в каналах" if user_lang == "ru" else "🎯 Channel advertising", callback_data="analytics_ads")],
        [InlineKeyboardButton(text="⇦ В главное меню" if user_lang == "ru" else "⇦ Main Menu", callback_data="go_home")]
    ])
    
    try:
        await call.message.edit_caption(caption=final_caption, reply_markup=back_markup, parse_mode="Markdown")
    except Exception:
        await call.message.answer(text=final_caption, reply_markup=back_markup, parse_mode="Markdown")


# =====================================================================
# 🎯 ПОДКЛЮЧЕНИЕ РЕКЛАМЫ К КАНАЛАМ
# =====================================================================
# Намеренно без конкретных сумм и процентов: пороги входа, минимальные бюджеты
# и доля выплат у Telegram менялись уже не раз. Даём маршрут и официальные
# ссылки, где условия всегда актуальны, — цифры пусть читаются там.

ADS_TEXTS = {
    "ru": (
        "🎯 **Реклама в Telegram-каналах: как подключить**\n\n"
        "Два принципиально разных сценария — их часто путают.\n\n"
        "**1. Зарабатывать на своём канале**\n"
        "Официальный путь — Ad Revenue Sharing: Telegram сам показывает рекламу "
        "в канале, владелец получает долю. Подключается в самом канале: "
        "«Управление каналом» → «Монетизация». Нужен порог по числу подписчиков "
        "и кошелёк TON — выплаты идут в нём.\n\n"
        "**2. Покупать рекламу для продвижения**\n"
        "• *Официальная площадка* — Telegram Ad Platform. Объявление до 160 знаков, "
        "без картинок, ведёт на канал или бота. Таргет по темам каналов и языку, "
        "не по интересам пользователя: Telegram не строит профиль читателя.\n"
        "• *Прямые закупки у каналов* — договорённость с владельцем о посте. "
        "Дешевле на старте и позволяет нативный формат, но проверять статистику "
        "придётся самостоятельно.\n"
        "• *Биржи размещений* — посредники между рекламодателем и каналами, "
        "берут комиссию, зато дают отчётность и защиту сделки.\n\n"
        "**Что считать до запуска**\n"
        "Ключевая метрика — не охват, а стоимость целевого действия. "
        "Для бота это подписка или первый диалог. "
        "CPM без конверсии в подписку ничего не говорит: канал на 100 тысяч "
        "с вовлечённостью 2% проигрывает каналу на 10 тысяч с 15%.\n\n"
        "**Как мерить**\n"
        "Deep link вида `t.me/ваш_бот?start=канал1` — параметр приходит в /start, "
        "и источник видно поимённо. Разные метки на разные размещения — "
        "и вы сравниваете их не на глаз, а по цифрам.\n\n"
        "_Пороги, минимальные бюджеты и доля выплат периодически меняются — "
        "актуальные смотрите по ссылкам ниже._"
    ),
    "en": (
        "🎯 **Advertising in Telegram channels: how to set it up**\n\n"
        "Two different scenarios, often confused.\n\n"
        "**1. Earning from your own channel**\n"
        "The official route is Ad Revenue Sharing: Telegram places ads in the "
        "channel and the owner gets a share. Enable it in the channel itself: "
        "Manage Channel → Monetization. A subscriber threshold and a TON wallet "
        "are required — payouts are made in TON.\n\n"
        "**2. Buying ads to promote something**\n"
        "• *Official platform* — Telegram Ad Platform. Up to 160 characters, no "
        "images, linking to a channel or bot. Targeting is by channel topic and "
        "language, not by user interests: Telegram does not profile readers.\n"
        "• *Direct deals with channels* — arrange a post with the owner. Cheaper "
        "to start and allows native formats, but you verify the stats yourself.\n"
        "• *Placement marketplaces* — intermediaries that take a commission and "
        "provide reporting and deal protection in return.\n\n"
        "**What to calculate first**\n"
        "The metric that matters is cost per action, not reach. For a bot that "
        "means a subscription or a first dialogue. CPM without conversion says "
        "nothing: a 100k channel at 2% engagement loses to a 10k channel at 15%.\n\n"
        "**How to measure**\n"
        "A deep link like `t.me/your_bot?start=channel1` passes the tag into "
        "/start, so each source is identified by name. Different tags per "
        "placement turn guesswork into numbers.\n\n"
        "_Thresholds, minimum budgets and revenue shares change periodically — "
        "check the current terms via the links below._"
    )
}


@router.callback_query(F.data == "analytics_ads")
async def show_ads_guide(call: CallbackQuery):
    await call.answer()
    try:
        user_lang = await database.get_user_language(call.from_user.id)
    except Exception:
        user_lang = "ru"

    text = ADS_TEXTS.get(user_lang, ADS_TEXTS["en"])
    is_ru = user_lang == "ru"

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📢 Telegram Ad Platform" if is_ru else "📢 Telegram Ad Platform",
            url="https://ads.telegram.org")],
        [InlineKeyboardButton(
            text="💰 Монетизация каналов" if is_ru else "💰 Channel monetization",
            url="https://telegram.org/blog/ad-revenue-sharing")],
        [InlineKeyboardButton(
            text="⇦ К аналитике" if is_ru else "⇦ Back to analytics",
            callback_data="menu_analytics")]
    ])

    try:
        await call.message.edit_caption(caption=text, reply_markup=markup, parse_mode="Markdown")
    except Exception:
        await call.message.answer(text=text, reply_markup=markup,
                                  parse_mode="Markdown", disable_web_page_preview=True)
