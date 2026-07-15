import asyncio
import logging
import sys
import os
import json
import sqlite3
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
import database
import common, block1_sport, block2_creative, block3_intellect, block4_claude, profiles, block5_game, block6_vpn, block7_analytics

async def handle_ping(reader, writer):
    try:
        data = await reader.read(1024)
        request_text = data.decode('utf-8', errors='ignore')
        first_line = request_text.split('\r\n')[0] if request_text else ""
    except Exception:
        first_line = ""

    # Если это запрос к нашему API аналитики для будущих графиков
    if "GET /api/metrics" in first_line:
        dau, mau, total_clicks = 0, 0, 0
        sections_data, langs_data = {}, {}
        try:
            # Делаем быстрые синхронные запросы для API-ответа сервера
            conn = sqlite3.connect(database.DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(DISTINCT user_id) FROM user_logs WHERE timestamp >= datetime('now', '-1 day')")
            dau = c.fetchone()[0] or 0
            c.execute("SELECT COUNT(DISTINCT user_id) FROM user_logs WHERE timestamp >= datetime('now', '-30 days')")
            mau = c.fetchone()[0] or 0
            c.execute("SELECT COUNT(*) FROM user_logs")
            total_clicks = c.fetchone()[0] or 0
            
            if total_clicks > 0:
                c.execute("SELECT section, COUNT(*) FROM user_logs GROUP BY section")
                for sec, cnt in c.fetchall():
                    sections_data[sec] = cnt
                c.execute("SELECT lang, COUNT(*) FROM user_logs GROUP BY lang")
                for ln, cnt in c.fetchall():
                    langs_data[ln] = cnt
            conn.close()
        except Exception as e:
            logging.error(f"API Analytics Error: {e}")

        payload = json.dumps({
            "dau": dau, "mau": mau, "total": total_clicks,
            "sections": sections_data, "languages": langs_data
        }, ensure_ascii=False)
        
        response = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: application/json\r\n"
            f"Access-Control-Allow-Origin: *\r\n" # Разрешаем внешние запросы от GitHub Pages
            f"Content-Length: {len(payload.encode('utf-8'))}\r\n"
            f"Connection: close\r\n\r\n{payload}"
        ).encode('utf-8')
    else:
        # Стандартный ответ для cron-job.org (Защита от сна)
        response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK"

    try:
        writer.write(response)
        await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

async def main():
    await database.init_db()

    bot = Bot(
        token=config.TOKEN, 
        default_properties=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Приоритеты регистрации роутеров
    dp.include_router(block7_analytics.router)
    dp.include_router(block6_vpn.router)
    dp.include_router(block5_game.router)
    dp.include_router(common.router)
    dp.include_router(block1_sport.router)
    dp.include_router(block2_creative.router)
    dp.include_router(block3_intellect.router)
    dp.include_router(block4_claude.router)
    dp.include_router(profiles.router)

    port = int(os.environ.get("PORT", 10000))
    server = await asyncio.start_server(handle_ping, "0.0.0.0", port)
    logging.info(f"Ping & API server started on port {port}")

    await bot.delete_webhook(drop_pending_updates=True)
    
    async with server:
        await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
