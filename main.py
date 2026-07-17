import asyncio
import logging
import sys
import os
import json
import secrets
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update

import config
import database
import news_fetcher
import common, block1_sport, block2_creative, block3_intellect, block4_claude, profiles, block5_game, block6_vpn, block7_analytics

# Секрет для проверки, что запрос на /webhook пришёл именно от Telegram, а не от кого попало
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET") or secrets.token_urlsafe(32)


def make_handle_ping(bot: Bot, dp: Dispatcher):
    """Фабрика создаёт обработчик HTTP-запросов с доступом к bot и dp (для приёма вебхука)"""

    async def handle_ping(reader, writer):
        method, path, query_params, body = "GET", "", {}, b""
        try:
            raw = b""
            while b"\r\n\r\n" not in raw:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                raw += chunk
                if len(raw) > 65536:
                    break

            header_part, _, rest = raw.partition(b"\r\n\r\n")
            header_text = header_part.decode('utf-8', errors='ignore')
            header_lines = header_text.split('\r\n')
            first_line = header_lines[0] if header_lines else ""

            headers = {}
            for line in header_lines[1:]:
                if ':' in line:
                    k, v = line.split(':', 1)
                    headers[k.strip().lower()] = v.strip()

            parts = first_line.split(' ')
            method = parts[0] if len(parts) > 0 else "GET"
            path_full = parts[1] if len(parts) > 1 else ""
            path, _, query = path_full.partition('?')
            query_params = dict(p.split('=', 1) for p in query.split('&') if '=' in p) if query else {}

            body = rest
            content_length = int(headers.get('content-length', 0) or 0)
            while len(body) < content_length:
                chunk = await reader.read(content_length - len(body))
                if not chunk:
                    break
                body += chunk
        except Exception as e:
            logging.error(f"Ошибка парсинга HTTP-запроса: {e}")

        cors_headers = "Access-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: GET, POST, OPTIONS\r\nAccess-Control-Allow-Headers: Content-Type\r\n"

        if method == "OPTIONS":
            response = (
                f"HTTP/1.1 204 No Content\r\n{cors_headers}Content-Length: 0\r\nConnection: close\r\n\r\n"
            ).encode('utf-8')

        elif path == "/webhook" and method == "POST":
            secret_header = headers.get("x-telegram-bot-api-secret-token", "")
            if secret_header != WEBHOOK_SECRET:
                response = b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            else:
                try:
                    update_data = json.loads(body.decode('utf-8'))
                    update = Update.model_validate(update_data)
                    await dp.feed_update(bot=bot, update=update)
                except Exception as e:
                    logging.error(f"Ошибка обработки webhook-обновления: {e}")
                response = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"

        elif path == "/api/metrics" and method == "GET":
            dau, mau, total_clicks = 0, 0, 0
            sections_data, langs_data = {}, {}
            try:
                dau, mau, total_clicks, sections_data, langs_data = await database.get_metrics_summary()
            except Exception as e:
                logging.error(f"API Analytics Error: {e}")

            payload = json.dumps({
                "dau": dau, "mau": mau, "total": total_clicks,
                "sections": sections_data, "languages": langs_data
            }, ensure_ascii=False)

            response = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: application/json\r\n"
                f"{cors_headers}"
                f"Content-Length: {len(payload.encode('utf-8'))}\r\n"
                f"Connection: close\r\n\r\n{payload}"
            ).encode('utf-8')

        elif path == "/api/partners" and method == "GET":
            sport = query_params.get("sport", "")
            try:
                partners = await database.get_game_partners(sport)
                payload = json.dumps(partners, ensure_ascii=False)
                response = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: application/json\r\n"
                    f"{cors_headers}"
                    f"Content-Length: {len(payload.encode('utf-8'))}\r\n"
                    f"Connection: close\r\n\r\n{payload}"
                ).encode('utf-8')
            except Exception as e:
                logging.error(f"Ошибка получения анкет партнёров: {e}")
                payload = json.dumps({"status": "error"})
                response = (
                    f"HTTP/1.1 500 Internal Server Error\r\n"
                    f"Content-Type: application/json\r\n"
                    f"{cors_headers}"
                    f"Content-Length: {len(payload.encode('utf-8'))}\r\n"
                    f"Connection: close\r\n\r\n{payload}"
                ).encode('utf-8')

        elif path == "/api/partners" and method == "POST":
            try:
                data = json.loads(body.decode('utf-8')) if body else {}
                sport = str(data.get("sport", "")).strip()[:50]
                city = str(data.get("city", "")).strip()[:100]
                level = str(data.get("level", "")).strip()[:50]
                available_time = str(data.get("available_time", "")).strip()[:200]
                username = str(data.get("username", "")).strip().lstrip("@")[:100]

                if sport and city and username:
                    await database.add_game_partner(sport, city, level, available_time, username)
                    payload = json.dumps({"status": "ok"})
                    status_line = "HTTP/1.1 200 OK"
                else:
                    payload = json.dumps({"status": "error", "message": "missing required fields"})
                    status_line = "HTTP/1.1 400 Bad Request"

                response = (
                    f"{status_line}\r\n"
                    f"Content-Type: application/json\r\n"
                    f"{cors_headers}"
                    f"Content-Length: {len(payload.encode('utf-8'))}\r\n"
                    f"Connection: close\r\n\r\n{payload}"
                ).encode('utf-8')
            except Exception as e:
                logging.error(f"Ошибка сохранения анкеты партнёра: {e}")
                payload = json.dumps({"status": "error"})
                response = (
                    f"HTTP/1.1 500 Internal Server Error\r\n"
                    f"Content-Type: application/json\r\n"
                    f"{cors_headers}"
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

    return handle_ping

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

async def main():
    await database.init_db()

    # Фоновая задача: подтягивает свежие заголовки при старте, затем каждые 24 часа
    asyncio.create_task(news_fetcher.news_scheduler(database))

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
    server = await asyncio.start_server(make_handle_ping(bot, dp), "0.0.0.0", port)
    logging.info(f"Ping & API & Webhook server started on port {port}")

    render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
    if render_url:
        webhook_url = f"{render_url}/webhook"
        await bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=True
        )
        logging.info(f"Webhook установлен: {webhook_url}")
    else:
        logging.warning(
            "RENDER_EXTERNAL_URL не найден — webhook не установлен, "
            "бот не будет получать обновления от Telegram!"
        )

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
