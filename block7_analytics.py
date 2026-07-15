# block7_analytics.py
import logging
import os
import aiosqlite
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
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute("SELECT COUNT(DISTINCT user_id) FROM user_logs WHERE timestamp >= datetime('now', '-1 day')") as c:
                row = await c.fetchone()
                dau = row[0] if row else 0
            async with db.execute("SELECT COUNT(DISTINCT user_id) FROM user_logs WHERE timestamp >= datetime('now', '-30 days')") as c:
                row = await c.fetchone()
                mau = row[0] if row else 0
            async with db.execute("SELECT COUNT(*) FROM user_logs") as c:
                row = await c.fetchone()
                total_clicks = row[0] if row else 0
                
            if total_clicks > 0:
                async with db.execute("SELECT section, COUNT(*) as cnt FROM user_logs GROUP BY section ORDER BY cnt DESC LIMIT 4") as cursor:
                    async for section_name, count in cursor:
                        pct = (count / total_clicks) * 100
                        bar = generate_progress_bar(pct)
                        sections_list.append(f"• `{section_name}`:\n  `{bar}` {pct:.1f}% ({count} кликов)")
                async with db.execute("SELECT lang, COUNT(*) as cnt FROM user_logs GROUP BY lang ORDER BY cnt DESC") as cursor:
                    async for l_code, count in cursor:
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
        [InlineKeyboardButton(text="⇦ В главное меню" if user_lang == "ru" else "⇦ Main Menu", callback_data="go_home")]
    ])
    
    try:
        await call.message.edit_caption(caption=final_caption, reply_markup=back_markup, parse_mode="Markdown")
    except Exception:
        await call.message.answer(text=final_caption, reply_markup=back_markup, parse_mode="Markdown")
