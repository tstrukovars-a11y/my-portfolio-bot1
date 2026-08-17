# block7_analytics.py
import logging
import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import config
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
        "🎯 **Как зарабатывать на канале и боте**\n\n"
        "Три способа монетизации — от простого к сложному.\n\n"
        "**1. Реклама от самого Telegram**\n"
        "Telegram показывает объявления в канале и делится выручкой с владельцем. "
        "Включается внутри канала: «Управление каналом» → «Монетизация». "
        "Нужен кошелёк TON, выплаты идут туда. Ничего продавать не надо — "
        "площадка делает всё сама.\n\n"
        "**2. Прямые размещения**\n"
        "Рекламодатель платит за пост в вашем канале. Даёт больше, чем первый способ, "
        "но клиентов надо находить самому.\n\n"
        "**3. Спонсорская ссылка внутри бота**\n"
        "Самое недооценённое. У бота аудитория теплее, чем у канала: человек уже "
        "нажимает кнопки и чего-то ищет. Спонсор получает кнопку или блок в нужном "
        "разделе — например, магазин экипировки в теннисе или сервис в разделе "
        "путешествий. Платят за размещение или за переходы.\n\n"
        "**Где искать спонсоров**\n"
        "• *Бренды из вашей же темы* — те, чьи товары уместны в разделе. Писать "
        "напрямую в отдел маркетинга; в нишевых компаниях это работает лучше, чем кажется.\n"
        "• *Партнёрские программы* — магазины и сервисы дают ссылку с вашей меткой "
        "и процент с покупок. Подключение обычно бесплатное и без порога.\n"
        "• *Биржи размещений* — каталоги, где рекламодатели сами ищут площадки. "
        "Берут комиссию, но дают поток заявок и защиту сделки.\n"
        "• *Соседние каналы* — взаимный обмен упоминаниями. Денег не приносит, "
        "но растит аудиторию, а с ней и ценность площадки.\n\n"
        "**Мини-инструкция**\n"
        "1. Опишите площадку: тема, размер аудитории, чем она занимается.\n"
        "2. Выберите места под рекламу — конкретные разделы, а не «где-нибудь».\n"
        "3. Сделайте размётку ссылок: `t.me/ваш_бот?start=партнёр1`. Метка приходит "
        "в /start, и вы видите, кто сколько привёл.\n"
        "4. Напишите трём-пяти брендам из своей темы с конкретным предложением.\n"
        "5. Первое размещение сделайте тестовым и коротким — так проще договориться "
        "и понятнее, что считать успехом.\n\n"
        "**Что показывать рекламодателю**\n"
        "Не охват, а действия: сколько людей дошло до нужного раздела и нажало кнопку. "
        "Такие цифры бот уже собирает — они в разделе выше.\n\n"
        "_Хотите разместиться у меня или собрать такой же инструмент под свою задачу — "
        "нажмите «Оставить заявку»._"
    ),
    "en": (
        "🎯 **How to earn from a channel and a bot**\n\n"
        "Three routes, from simplest to hardest.\n\n"
        "**1. Ads served by Telegram itself**\n"
        "Telegram places ads in the channel and shares the revenue with the owner. "
        "Enable it inside the channel: Manage Channel → Monetization. A TON wallet is "
        "required and payouts go there. Nothing to sell — the platform does the work.\n\n"
        "**2. Direct placements**\n"
        "An advertiser pays for a post in your channel. Pays more than the first route, "
        "but you find the clients yourself.\n\n"
        "**3. A sponsor link inside the bot**\n"
        "The most underrated one. A bot audience is warmer than a channel's: the person "
        "is already tapping buttons and looking for something. The sponsor gets a button "
        "or a block in a relevant section — a gear store in the tennis part, a service in "
        "the travel part. Paid per placement or per click.\n\n"
        "**Where to find sponsors**\n"
        "• *Brands from your own topic* — the ones whose products fit the section. Write "
        "to their marketing team directly; in niche companies this works better than expected.\n"
        "• *Affiliate programmes* — shops and services give you a tagged link and a cut of "
        "purchases. Joining is usually free and has no threshold.\n"
        "• *Placement marketplaces* — catalogues where advertisers look for venues. They "
        "take a commission but bring a flow of requests and deal protection.\n"
        "• *Neighbouring channels* — swap mentions. No money, but it grows the audience, "
        "and with it the value of the venue.\n\n"
        "**Mini guide**\n"
        "1. Describe the venue: topic, audience size, what it does.\n"
        "2. Pick the ad slots — specific sections, not «somewhere».\n"
        "3. Tag your links: `t.me/your_bot?start=partner1`. The tag arrives with /start, "
        "so you see who brought whom.\n"
        "4. Write to three to five brands in your topic with a concrete offer.\n"
        "5. Make the first placement short and experimental — easier to agree on and "
        "clearer about what counts as success.\n\n"
        "**What to show an advertiser**\n"
        "Not reach, but actions: how many people reached the section and pressed the button. "
        "The bot already collects that — see the section above.\n\n"
        "_Want to advertise with me, or to have a tool like this built for you — "
        "tap «Send a request»._"
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

    rows = [
        [InlineKeyboardButton(text="📢 Telegram Ad Platform", url="https://ads.telegram.org")],
        [InlineKeyboardButton(
            text="💰 Монетизация каналов" if is_ru else "💰 Channel monetization",
            url="https://telegram.org/blog/ad-revenue-sharing")],
    ]
    # Кнопку заявки показываем, только если заявке есть куда прийти
    if config.ADMIN_ID:
        rows.append([InlineKeyboardButton(
            text="✉️ Оставить заявку" if is_ru else "✉️ Send a request",
            callback_data="ads_order")])
    rows.append([InlineKeyboardButton(
        text="⇦ К аналитике" if is_ru else "⇦ Back to analytics",
        callback_data="menu_analytics")])

    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        await call.message.edit_caption(caption=text, reply_markup=markup, parse_mode="Markdown")
    except Exception:
        await call.message.answer(text=text, reply_markup=markup,
                                  parse_mode="Markdown", disable_web_page_preview=True)
