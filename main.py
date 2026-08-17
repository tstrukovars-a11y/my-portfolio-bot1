import asyncio
import hashlib
import logging
import sys
import os
import json
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update

import config
import database
import news_fetcher
import country_index
import common, block1_sport, block2_creative, block3_intellect, block4_claude, profiles, block5_game, block6_vpn, block7_analytics, puzzles, shop, orders, genetics


def _make_webhook_secret() -> str:
    """Секрет для проверки, что запрос на /webhook пришёл именно от Telegram.

    Важно: секрет обязан быть ОДИНАКОВЫМ при каждом старте процесса. На бесплатном
    тарифе Render сервис засыпает и перезапускается; если генерировать секрет
    случайно, то апдейты, которые Telegram шлёт со старым секретом (пока новый
    процесс ещё не успел вызвать setWebhook), получают 403 и молча теряются.
    Поэтому берём значение из переменной окружения, а если её нет — детерминированно
    выводим его из токена бота.
    """
    env_secret = os.environ.get("WEBHOOK_SECRET")
    if env_secret:
        return env_secret
    return hashlib.sha256(f"webhook-secret::{config.TOKEN}".encode()).hexdigest()[:48]


WEBHOOK_SECRET = _make_webhook_secret()


async def _process_update(bot: Bot, dp: Dispatcher, update: Update):
    """Прогоняет апдейт через роутеры, не давая исключению потеряться молча"""
    try:
        await dp.feed_update(bot=bot, update=update)
    except Exception as e:
        logging.exception(f"Необработанная ошибка в хендлере (апдейт {update.update_id}): {e}")


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
                logging.warning("Webhook: отклонён запрос с неверным секретом")
                response = b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            else:
                try:
                    update_data = json.loads(body.decode('utf-8'))
                    update = Update.model_validate(update_data)
                    logging.info(f"Webhook: получен апдейт {update.update_id} типа {update.event_type}")
                    # Обрабатываем в фоне и сразу отвечаем 200: иначе медленный хендлер
                    # (запрос к Claude, к БД) заставит Telegram считать доставку неудачной
                    # и слать тот же апдейт повторно.
                    asyncio.create_task(_process_update(bot, dp, update))
                except Exception as e:
                    logging.exception(f"Ошибка разбора webhook-обновления: {e}")
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
    # Бот обязан подниматься даже с недоступной базой: язык и навигация работают
    # из памяти процесса, а в логах остаётся явная причина сбоя.
    try:
        await database.init_db()
    except Exception as e:
        logging.error(
            f"НЕ УДАЛОСЬ ПОДКЛЮЧИТЬСЯ К БАЗЕ: {e}\n"
            f"    Хост из DATABASE_URL: {database.describe_db_target()}\n"
            f"    Бот запустится, но данные (язык, рецепты, книги, аналитика) не сохраняются.\n"
            f"    Проверьте, жива ли база Postgres на Render и совпадает ли DATABASE_URL."
        )

    # Фоновая задача: подтягивает свежие заголовки при старте, затем каждые 24 часа
    # Индексу нужен Claude для оценки тона; без ключа составляющая просто отключится
    asyncio.create_task(news_fetcher.news_scheduler(
        database, country_index, block2_creative.claude_client))

    # ВАЖНО: параметр называется `default`, а не `default_properties`.
    # Неизвестные аргументы aiogram молча проглатывает в **kwargs, из-за чего
    # раньше режим разметки по умолчанию вообще не применялся.
    bot = Bot(
        token=config.TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    def _section_of(data: str) -> str:
        """Схлопывает callback до узнаваемого раздела: из «shopitem_women_sneakers_0_12»
        получается «shopitem_women». Иначе в аналитике была бы каша из id."""
        parts = [p for p in data.split("_") if not p.isdigit()]
        return "_".join(parts[:2])[:50] or "unknown"

    async def _log(user_id: int, section: str):
        try:
            lang = await database.get_user_language(user_id)
            await database.log_action(user_id, section, lang)
        except Exception as e:
            logging.error(f"Не удалось записать действие в аналитику: {e}")

    @dp.callback_query.outer_middleware()
    async def track_clicks(handler, event, data):
        """Продуктовая аналитика пишется здесь, а не в хендлерах: раньше вызов
        log_action стоял ровно в одном месте, поэтому DAU и MAU всегда были нулевыми.
        Пишем в фоне, чтобы запись в базу не задерживала ответ на нажатие."""
        if event.data and event.from_user:
            asyncio.create_task(_log(event.from_user.id, _section_of(event.data)))
        return await handler(event, data)

    @dp.message.outer_middleware()
    async def track_commands(handler, event, data):
        if event.text and event.text.startswith("/") and event.from_user:
            asyncio.create_task(_log(event.from_user.id, event.text.split()[0][:50]))
        return await handler(event, data)

    seen_channels = set()

    @dp.channel_post.outer_middleware()
    async def log_channel_id(handler, event, data):
        """Подсказывает id каналов: узнать его иначе неоткуда, а он нужен для
        переменных CULINARY_CHANNEL, BOOKS_CHANNEL и QUIZ_CHANNEL. Пишем один
        раз на канал, чтобы не засорять логи."""
        if event.chat.id not in seen_channels:
            seen_channels.add(event.chat.id)
            logging.info(f"Канал «{event.chat.title}» -> id {event.chat.id}")
        return await handler(event, data)

    @dp.errors()
    async def on_error(event):
        """Глобальный перехватчик: без него ошибка в хендлере не видна в логах Render,
        а пользователь просто видит кнопку, которая «ничего не делает»."""
        logging.exception(f"Ошибка при обработке апдейта: {event.exception}")
        return True

    # Приоритеты регистрации роутеров
    dp.include_router(puzzles.router)
    dp.include_router(shop.router)
    dp.include_router(orders.router)
    dp.include_router(genetics.router)
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
        # allowed_updates задаём ЯВНО. Если его не передать, Telegram сохраняет
        # список типов апдейтов от предыдущей настройки — и если там когда-то
        # остался только "message", то нажатия на инлайн-кнопки (callback_query)
        # просто не доставляются: меню показывается, а кнопки не работают.
        allowed = dp.resolve_used_update_types()
        await bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            allowed_updates=allowed,
            drop_pending_updates=True
        )
        logging.info(f"Webhook установлен: {webhook_url} | allowed_updates={allowed}")

        info = await bot.get_webhook_info()
        logging.info(
            f"getWebhookInfo -> url={info.url} pending={info.pending_update_count} "
            f"allowed_updates={info.allowed_updates} last_error={info.last_error_message}"
        )
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
