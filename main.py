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
import translator
import common, block1_sport, block2_creative, block3_intellect, block4_claude, profiles, block5_game, block6_vpn, block7_analytics, puzzles, shop, orders, genetics, admin, tennis_live, travel, payments, fx_rates
import finance
import digest
import growth
import race
import cartoon
import characters
import travel_import
import travel_channel
import travel_spots
import books_seed
import tennis_alerts
import banners
import avatars
import puzzle_daily
import tennis_rank
import art_shop
import checklist
import advcake
import inline_kb
import planner


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


# Номера недавно обработанных апдейтов. Telegram (или прокси перед ботом) может
# доставить один и тот же апдейт дважды — тогда на одну команду /start приходило
# два меню. Номер апдейта уникален, поэтому повтор видно сразу.
_seen_updates: set = set()
_seen_order: list = []


def _already_processed(update_id: int) -> bool:
    if update_id in _seen_updates:
        return True
    _seen_updates.add(update_id)
    _seen_order.append(update_id)
    if len(_seen_order) > 1000:
        _seen_updates.discard(_seen_order.pop(0))
    return False


async def _process_update(bot: Bot, dp: Dispatcher, update: Update):
    """Прогоняет апдейт через роутеры, не давая исключению потеряться молча"""
    if _already_processed(update.update_id):
        logging.warning(f"Апдейт {update.update_id} пришёл повторно — пропускаю")
        return
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

        elif path == "/go" and method == "GET":
            # Счётчик переходов: записываем клик и отправляем в магазин.
            # Подпись обязательна — иначе наш адрес стал бы открытым
            # редиректом, которым уводят куда угодно.
            import links
            code, target = await links.handle(
                {k: (v[0] if isinstance(v, list) else v)
                 for k, v in query_params.items()})
            if code == 302:
                response = (
                    "HTTP/1.1 302 Found\r\n"
                    f"Location: {target}\r\n"
                    "Cache-Control: no-store\r\n"
                    "Content-Length: 0\r\nConnection: close\r\n\r\n"
                ).encode("utf-8")
            else:
                payload = target.encode("utf-8")
                response = (
                    f"HTTP/1.1 {code} \r\n"
                    "Content-Type: text/plain; charset=utf-8\r\n"
                    f"Content-Length: {len(payload)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("utf-8") + payload

        elif path == "/game" and method == "GET":
            body_bytes = race.page()
            response = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: text/html; charset=utf-8\r\n"
                f"Cache-Control: no-cache\r\n"
                f"Content-Length: {len(body_bytes)}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode('utf-8') + body_bytes

        elif path == "/game/score" and method == "POST":
            try:
                code, result = await race.handle_score(body, config.TOKEN)
            except Exception as e:
                logging.error(f"Гонка: ошибка приёма счёта: {e}")
                code, result = 500, {"status": "error"}
            payload = json.dumps(result, ensure_ascii=False)
            response = (
                f"HTTP/1.1 {code} {'OK' if code == 200 else 'Error'}\r\n"
                f"Content-Type: application/json\r\n"
                f"{cors_headers}"
                f"Content-Length: {len(payload.encode('utf-8'))}\r\n"
                f"Connection: close\r\n\r\n{payload}"
            ).encode('utf-8')

        elif path == "/cartoon" and method == "GET":
            body_bytes = cartoon.page()
            response = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: text/html; charset=utf-8\r\n"
                f"Cache-Control: no-cache\r\n"
                f"Content-Length: {len(body_bytes)}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode('utf-8') + body_bytes

        elif path == "/cartoon/example" and method == "GET":
            body_bytes = cartoon.example_page()
            response = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: text/html; charset=utf-8\r\n"
                f"Cache-Control: public, max-age=3600\r\n"
                f"Content-Length: {len(body_bytes)}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode('utf-8') + body_bytes

        elif path == "/cartoon/data" and method == "GET":
            try:
                board = await database.get_cartoon(int(query_params.get("id", "0")))
            except ValueError:
                board = None
            if board:
                try:
                    frames = await database.cartoon_frame_list(
                        int(query_params.get("id", "0")))
                except ValueError:
                    frames = []
                payload = ('{"status":"ok","frames":' + json.dumps(frames)
                           + ',"film":' + board + '}')
                status_line = "HTTP/1.1 200 OK"
            else:
                payload = json.dumps({"status": "error", "message": "not found"})
                status_line = "HTTP/1.1 404 Not Found"
            response = (
                f"{status_line}\r\n"
                f"Content-Type: application/json; charset=utf-8\r\n"
                f"{cors_headers}"
                f"Content-Length: {len(payload.encode('utf-8'))}\r\n"
                f"Connection: close\r\n\r\n{payload}"
            ).encode('utf-8')

        elif path == "/cartoon/char" and method == "GET":
            # Адрес персонажа случаен, поэтому подписи не требуется: угадать
            # его нельзя, а ссылка живёт только внутри мультика автора.
            drawing = await database.own_character_by_token(
                query_params.get("t", "")[:64])
            if drawing:
                data, mime = drawing
                response = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: {mime}\r\n"
                    f"Cache-Control: private, max-age=86400\r\n"
                    f"{cors_headers}"
                    f"Content-Length: {len(data)}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode('utf-8') + bytes(data)
            else:
                response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"

        elif path == "/cartoon/img" and method == "GET":
            frame = None
            try:
                frame = await database.cartoon_frame(
                    int(query_params.get("id", "0")), int(query_params.get("scene", "0")))
            except ValueError:
                pass
            if frame:
                data, mime = frame
                response = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: {mime}\r\n"
                    # Кадр неизменен: он нарисован один раз и навсегда,
                    # поэтому пусть браузер держит его у себя.
                    f"Cache-Control: public, max-age=31536000, immutable\r\n"
                    f"{cors_headers}"
                    f"Content-Length: {len(data)}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode('utf-8') + bytes(data)
            else:
                response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"

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

    # Свои картинки разделов — до первого показа меню.
    await banners.load()

    # Рейтинг и свои написания имён — из базы в память процесса.
    try:
        logging.info(f"Теннис: {await tennis_rank.apply()}")
    except Exception as e:
        logging.warning(f"Рейтинг не поднялся: {e}")

    logging.info(await translator.check_key())

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

    async def _log(user, section: str):
        try:
            lang = await database.get_user_language(user.id)
            await database.log_action(user.id, section, lang)
            await database.record_visitor(
                user.id, user.username, user.full_name, user.language_code)
        except Exception as e:
            logging.error(f"Не удалось записать действие в аналитику: {e}")

    @dp.callback_query.outer_middleware()
    async def track_clicks(handler, event, data):
        """Продуктовая аналитика пишется здесь, а не в хендлерах: раньше вызов
        log_action стоял ровно в одном месте, поэтому DAU и MAU всегда были нулевыми.
        Пишем в фоне, чтобы запись в базу не задерживала ответ на нажатие."""
        if event.data and event.from_user:
            asyncio.create_task(_log(event.from_user, _section_of(event.data)))
        return await handler(event, data)

    # Шлюз стоит после аналитики: заход в закрытый раздел — тоже интерес,
    # и учитывать его надо независимо от того, пустили пользователя или нет.
    dp.callback_query.outer_middleware(growth.gate_middleware)

    @dp.message.outer_middleware()
    async def track_commands(handler, event, data):
        if event.text and event.text.startswith("/") and event.from_user:
            asyncio.create_task(_log(event.from_user, event.text.split()[0][:50]))
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
    dp.include_router(planner.router)
    dp.include_router(banners.router)
    dp.include_router(avatars.router)
    dp.include_router(puzzle_daily.router)
    dp.include_router(tennis_rank.router)
    dp.include_router(art_shop.router)
    dp.include_router(checklist.router)
    dp.include_router(advcake.router)
    dp.include_router(puzzles.router)
    dp.include_router(shop.router)
    dp.include_router(orders.router)
    dp.include_router(genetics.router)
    dp.include_router(admin.router)
    dp.include_router(payments.router)
    dp.include_router(fx_rates.router)
    dp.include_router(digest.router)
    dp.include_router(growth.router)
    dp.include_router(race.router)
    dp.include_router(cartoon.router)
    dp.include_router(characters.router)
    dp.include_router(travel_import.router)
    dp.include_router(travel_channel.router)
    dp.include_router(travel_spots.router)
    dp.include_router(books_seed.router)
    dp.include_router(tennis_alerts.router)

    dp.include_router(tennis_live.router)
    dp.include_router(travel.router)
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

    # Публикация в канал: запускаем после создания бота — раньше объекта ещё нет
    asyncio.create_task(digest.scheduler(bot))
    asyncio.create_task(tennis_alerts.alerts_scheduler(bot))
    asyncio.create_task(tennis_rank.scheduler())
    asyncio.create_task(checklist.scheduler(bot))

    # Своё имя бот спрашивает у Telegram, а не ждёт, пока его впишут руками:
    # на нём держатся глубокие ссылки из канала, и опечатка в нём означала бы
    # кнопки, ведущие в никуда.
    try:
        me = await bot.get_me()
        if me.username:
            await database.set_setting("bot_username", me.username)
            logging.info(f"Глубокие ссылки ведут на @{me.username}")
    except Exception as e:
        logging.warning(f"Имя бота не определилось: {e}")

    # Меню собирается синхронно и в базу сходить не может, поэтому ссылку на
    # канал подкладываем один раз при старте.
    try:
        inline_kb.CHANNEL_URL = await database.get_setting(growth.LINK_KEY) or ""
    except Exception as e:
        logging.warning(f"Ссылку на канал прочитать не вышло: {e}")

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
