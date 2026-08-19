import json
import os
import logging
from datetime import datetime, timedelta

import asyncpg

# Render даёт строку вида postgres://..., приводим к схеме postgresql:// для совместимости
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


def _dsn_candidates() -> list:
    """Строки подключения в порядке проверки.

    Внешний адрес базы (External Database URL у Render, Neon и прочие облака)
    принимает только SSL, а asyncpg сам его не включает и падает с
    «SSL/TLS required». Внутренний адрес Render, наоборот, может SSL не
    предлагать вовсе. sslmode=prefer не спасает: он молча откатывается на
    открытое соединение и упирается в отказ сервера. Поэтому пробуем сначала с
    SSL, затем без — что сработает, то и запомним.
    """
    if not DATABASE_URL:
        return []
    if "sslmode=" in DATABASE_URL:
        return [DATABASE_URL]
    sep = "&" if "?" in DATABASE_URL else "?"
    return [f"{DATABASE_URL}{sep}sslmode=require", DATABASE_URL]

_pool = None

# Язык пользователя дублируется в памяти процесса. Это страховка: если база
# недоступна (истёк бесплатный Postgres на Render, не резолвится хост,
# сменился DATABASE_URL), навигация по боту обязана продолжать работать —
# раньше любая ошибка БД убивала хендлер, и кнопки просто «не нажимались».
_lang_cache: dict[int, str] = {}

# Отдельная "схема" (namespace) внутри общей базы — изолирует таблицы этого бота
# от таблиц других ботов, использующих ту же самую бесплатную базу Postgres на Render.
# Указывается явно в каждом запросе (а не через SET search_path), потому что
# бесплатный Postgres на Render обычно работает через PgBouncer в режиме
# transaction pooling, где session-level настройки вроде search_path могут
# не сохраняться между запросами.
SCHEMA = "vizitka_bot"


async def _init_connection(conn):
    """Выполняется при каждом новом соединении: гарантирует существование схемы"""
    await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")


def describe_db_target() -> str:
    """Хост и имя базы из DATABASE_URL без пароля — чтобы безопасно писать в логи"""
    if not DATABASE_URL:
        return "DATABASE_URL не задан"
    try:
        from urllib.parse import urlparse
        parsed = urlparse(DATABASE_URL)
        return f"{parsed.hostname}:{parsed.port or 5432}{parsed.path}"
    except Exception:
        return "не удалось разобрать DATABASE_URL"


_pool_failure_logged = False


async def get_pool():
    """Возвращает пул соединений, создаёт при первом обращении"""
    global _pool, _pool_failure_logged
    if _pool is not None:
        return _pool

    candidates = _dsn_candidates()
    if not candidates:
        raise RuntimeError("DATABASE_URL не задан")

    last_error = None
    for dsn in candidates:
        ssl_note = "с SSL" if "sslmode=require" in dsn else "без SSL"
        try:
            _pool = await asyncpg.create_pool(
                dsn, min_size=1, max_size=5, init=_init_connection
            )
            _pool_failure_logged = False
            logging.info(f"Подключение к базе установлено ({ssl_note}): {describe_db_target()}")
            return _pool
        except Exception as e:
            last_error = e
            logging.warning(f"Подключение {ssl_note} не удалось: {e}")

    # Адрес пишем только при первом сбое: иначе каждая кнопка засыпает логи
    # одной и той же строкой, а найти причину всё равно нельзя.
    if not _pool_failure_logged:
        logging.error(
            f"Не удалось подключиться к базе ни с SSL, ни без него. "
            f"Адрес из DATABASE_URL: {describe_db_target()}"
        )
        _pool_failure_logged = True
    raise last_error


async def measure_latency() -> float:
    """Время простейшего запроса к базе, в миллисекундах.

    Один этот замер отвечает на вопрос «тормозит сеть или код»: внутренний адрес
    Render в том же регионе даёт единицы миллисекунд, внешний — сотни, и тогда
    каждое обращение к базе видно на глаз.
    """
    import time
    pool = await get_pool()
    started = time.perf_counter()
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    return (time.perf_counter() - started) * 1000


async def init_db():
    """Инициализация базы данных и создание всех необходимых таблиц"""
    pool = await get_pool()

    try:
        latency = await measure_latency()
        verdict = ("внутренний адрес, быстро" if latency < 20 else
                   "терпимо" if latency < 80 else
                   "МЕДЛЕННО — похоже на внешний адрес базы, отклик бота будет вязким")
        logging.info(f"Задержка до базы: {latency:.0f} мс ({verdict})")
    except Exception as e:
        logging.warning(f"Не удалось измерить задержку до базы: {e}")

    async with pool.acquire() as conn:
        # Одноразовая очистка "недоделанных" таблиц от прошлых прерванных попыток
        # деплоя. Срабатывает только один раз благодаря маркеру _schema_version —
        # при всех следующих запусках эта проверка пропускается, и данные между
        # деплоями сохраняются как положено.
        marker_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables "
            f"WHERE table_schema = '{SCHEMA}' AND table_name = '_schema_version')"
        )
        if not marker_exists:
            for table_name in [
                "quizzes", "user_answers", "subscriptions", "recipes", "books",
                "payments", "ai_limits", "users", "user_logs", "daily_news", "game_partners"
            ]:
                await conn.execute(f"DROP TABLE IF EXISTS {SCHEMA}.{table_name} CASCADE")
            await conn.execute(f"CREATE TABLE {SCHEMA}._schema_version (version INTEGER)")
            await conn.execute(f"INSERT INTO {SCHEMA}._schema_version (version) VALUES (1)")
            logging.info("Выполнена одноразовая очистка испорченных таблиц")

        # 1. Таблицы для квизов
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.quizzes (
            poll_id TEXT PRIMARY KEY,
            message_id BIGINT,
            question TEXT,
            correct_option_id INTEGER
        )""")
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.user_answers (
            user_id BIGINT,
            poll_id TEXT,
            is_correct INTEGER,
            PRIMARY KEY (user_id, poll_id)
        )""")

        # 2. Таблица для подписок
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.subscriptions (
            user_id BIGINT PRIMARY KEY,
            expires_at TEXT
        )""")

        # 3. Таблицы для контента (рецепты и книги)
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.recipes (
            id SERIAL PRIMARY KEY,
            category TEXT,
            title TEXT,
            text_content TEXT,
            video_file_id TEXT,
            link_url TEXT
        )""")
        # Фото добавлено позже: у таблиц, созданных раньше, колонки нет,
        # а CREATE TABLE IF NOT EXISTS её не дорисует.
        await conn.execute(
            f"ALTER TABLE {SCHEMA}.recipes ADD COLUMN IF NOT EXISTS photo_file_id TEXT"
        )
        # Один и тот же пост не должен попасть в банк дважды — ни из канала,
        # ни при импорте пересылкой.
        await conn.execute(
            f"ALTER TABLE {SCHEMA}.recipes ADD COLUMN IF NOT EXISTS source_key TEXT"
        )
        # Индекс обязан быть ОБЫЧНЫМ, а не частичным. Postgres не выводит
        # частичный индекс из «ON CONFLICT (source_key)» — предикат пришлось бы
        # дословно повторять в каждом запросе, иначе он падает с «no unique or
        # exclusion constraint matching the ON CONFLICT specification».
        # Отдельный WHERE тут и не нужен: NULL-значения уникальный индекс
        # считает различными, так что старые записи без source_key не мешают.
        await conn.execute(
            f"DROP INDEX IF EXISTS {SCHEMA}.recipes_source_key_idx"
        )
        await conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS recipes_source_key_uniq "
            f"ON {SCHEMA}.recipes (source_key)"
        )
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.books (
            id SERIAL PRIMARY KEY,
            category TEXT,
            text_content TEXT,
            cover_file_id TEXT
        )""")

        # 4. Таблица для логов платежей
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.payments (
            invoice_id TEXT PRIMARY KEY,
            user_id BIGINT,
            amount REAL,
            currency TEXT,
            status TEXT,
            created_at TEXT
        )""")

        # 5. Таблица для лимитов ИИ
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.ai_limits (
            user_id BIGINT PRIMARY KEY,
            requests_count INTEGER DEFAULT 0,
            last_request_date TEXT
        )""")

        # 6. Таблица языка пользователя
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.users (
            user_id BIGINT PRIMARY KEY,
            lang TEXT
        )""")

        # 7. Продуктовые логи для DAU/MAU и долей трафика
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.user_logs (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            section TEXT,
            lang TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        # 8. Ежедневные новости по странам
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.daily_news (
            country TEXT PRIMARY KEY,
            content TEXT,
            fetched_at TEXT
        )""")

        # 9. Головоломки: банк задач, импортированных из quiz-опросов канала
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.puzzles (
            id SERIAL PRIMARY KEY,
            source_poll_id TEXT UNIQUE,
            question TEXT NOT NULL,
            options TEXT NOT NULL,
            correct_option_id INTEGER NOT NULL,
            explanation TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        # 10. Завершённые прохождения (для итогового балла и статистики)
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.puzzle_rounds (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            total INTEGER,
            correct INTEGER,
            finished_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        # 11. Каждый отдельный ответ — нужен для точности по конкретным задачам
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.puzzle_answers (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            puzzle_id INTEGER,
            is_correct BOOLEAN,
            answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        # 12. Товары Pro-Shop: пол + тип вещи, карточка со ссылкой на пост-источник
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.shop_items (
            id SERIAL PRIMARY KEY,
            gender TEXT,
            item_type TEXT,
            title TEXT,
            description TEXT,
            photo_file_id TEXT,
            link_url TEXT,
            source_key TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        # Индекс обычный, а не частичный: см. историю с recipes_source_key —
        # ON CONFLICT не умеет выводить частичный индекс без повтора предиката.
        await conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS shop_items_source_uniq "
            f"ON {SCHEMA}.shop_items (source_key)"
        )

        # 13. Ежедневный индекс по странам: тон новостей + макропоказатели.
        # Копится по дням, чтобы считать динамику относительно вчера и недели.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.country_index (
            country TEXT,
            day DATE,
            tone REAL,
            fx REAL,
            inflation REAL,
            gdp_growth REAL,
            score REAL,
            PRIMARY KEY (country, day)
        )""")

        # 14. Посты из тематических каналов, разложенные по разделам бота.
        # Сейчас это генетика; таблица общая, чтобы так же подключить другие темы.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.articles (
            id SERIAL PRIMARY KEY,
            section TEXT,
            title TEXT,
            text_content TEXT,
            photo_file_id TEXT,
            video_file_id TEXT,
            link_url TEXT,
            source_key TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        await conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS articles_source_uniq "
            f"ON {SCHEMA}.articles (source_key)"
        )

        # 15. Анкеты поиска партнёра для игры
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.game_partners (
            id SERIAL PRIMARY KEY,
            sport TEXT,
            city TEXT,
            level TEXT,
            available_time TEXT,
            username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

    logging.info("PostgreSQL: таблицы инициализированы")


# --- ФУНКЦИИ ДЛЯ РАБОТЫ С ЯЗЫКАМИ ПОЛЬЗОВАТЕЛЕЙ ---

async def set_user_language(user_id: int, lang: str):
    """Сохраняет выбранный язык пользователя. Недоступность БД не должна ломать бота."""
    _lang_cache[user_id] = lang
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.users (user_id, lang) VALUES ($1, $2) "
                "ON CONFLICT (user_id) DO UPDATE SET lang = EXCLUDED.lang",
                user_id, lang
            )
    except Exception as e:
        logging.error(f"БД недоступна, язык сохранён только в памяти процесса: {e}")

async def get_user_language(user_id: int) -> str:
    """Получает сохранённый язык пользователя.

    Порядок: база → кэш в памяти → английский по умолчанию. Ошибка БД здесь
    НЕ пробрасывается наружу: этот вызов стоит первой строкой почти в каждом
    хендлере, и исключение делало неработающим всё меню целиком.
    """
    # Кэш проверяем ПЕРВЫМ. Эта функция стоит в начале почти каждого хендлера и
    # ещё раз в middleware аналитики: без кэша получалось по два обращения к базе
    # на каждое нажатие, а по внешнему адресу это заметная задержка отклика.
    cached = _lang_cache.get(user_id)
    if cached:
        return cached

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT lang FROM {SCHEMA}.users WHERE user_id = $1", user_id)
        if row:
            _lang_cache[user_id] = row["lang"]
            return row["lang"]
    except Exception as e:
        logging.error(f"БД недоступна при чтении языка, работаем из памяти: {e}")

    return "en"


# --- ФУНКЦИИ ДЛЯ РАБОТЫ С ПОДПИСКАМИ ---

async def check_subscription(user_id: int) -> bool:
    """Проверяет, активна ли платная подписка. При недоступной БД считаем, что подписки нет."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT expires_at FROM {SCHEMA}.subscriptions WHERE user_id = $1", user_id)
    except Exception as e:
        logging.error(f"БД недоступна при проверке подписки: {e}")
        return False

    if not row or not row["expires_at"]:
        return False
    try:
        expires_at = datetime.fromisoformat(row["expires_at"])
        return expires_at > datetime.now()
    except ValueError:
        return False

async def add_or_extend_subscription(user_id: int, days: int):
    """Создает или продлевает платную подписку на N дней"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(f"SELECT expires_at FROM {SCHEMA}.subscriptions WHERE user_id = $1", user_id)

        now = datetime.now()
        if row and row["expires_at"]:
            try:
                current_expires = datetime.fromisoformat(row["expires_at"])
                start_date = current_expires if current_expires > now else now
            except ValueError:
                start_date = now
        else:
            start_date = now

        new_expires = start_date + timedelta(days=days)
        await conn.execute(
            f"INSERT INTO {SCHEMA}.subscriptions (user_id, expires_at) VALUES ($1, $2) "
            "ON CONFLICT (user_id) DO UPDATE SET expires_at = EXCLUDED.expires_at",
            user_id, new_expires.isoformat()
        )


# --- ФУНКЦИИ ДЛЯ РАБОТЫ С ЛИМИТАМИ ИИ ---

async def get_ai_requests_count(user_id: int) -> int:
    """Получает количество запросов пользователя к Claude за сегодня"""
    today = datetime.now().date().isoformat()
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT requests_count, last_request_date FROM {SCHEMA}.ai_limits WHERE user_id = $1", user_id
            )
    except Exception as e:
        logging.error(f"БД недоступна при чтении лимитов ИИ: {e}")
        return 0

    if row and row["last_request_date"] == today:
        return row["requests_count"]
    return 0

async def increment_ai_requests(user_id: int):
    """Увеличивает счетчик запросов к Claude на 1"""
    today = datetime.now().date().isoformat()
    current_count = await get_ai_requests_count(user_id)
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.ai_limits (user_id, requests_count, last_request_date) VALUES ($1, $2, $3) "
                "ON CONFLICT (user_id) DO UPDATE SET requests_count = EXCLUDED.requests_count, "
                "last_request_date = EXCLUDED.last_request_date",
                user_id, current_count + 1, today
            )
    except Exception as e:
        logging.error(f"БД недоступна при записи лимитов ИИ: {e}")


# --- ЛОГИРОВАНИЕ ПРОДУКТОВОЙ АНАЛИТИКИ ---

async def log_action(user_id: int, section: str, lang: str):
    """Фиксирует клик пользователя для подсчета DAU/MAU и долей трафика"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.user_logs (user_id, section, lang) VALUES ($1, $2, $3)",
                user_id, section, lang
            )
    except Exception as e:
        logging.error(f"Ошибка логирования продуктовой аналитики: {e}")

async def get_metrics_summary():
    """Возвращает (dau, mau, total_clicks, sections_data, langs_data) для дашборда аналитики"""
    dau, mau, total_clicks = 0, 0, 0
    sections_data, langs_data = {}, {}
    pool = await get_pool()
    async with pool.acquire() as conn:
        dau = await conn.fetchval(
            f"SELECT COUNT(DISTINCT user_id) FROM {SCHEMA}.user_logs WHERE timestamp >= NOW() - INTERVAL '1 day'"
        ) or 0
        mau = await conn.fetchval(
            f"SELECT COUNT(DISTINCT user_id) FROM {SCHEMA}.user_logs WHERE timestamp >= NOW() - INTERVAL '30 days'"
        ) or 0
        total_clicks = await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA}.user_logs") or 0

        if total_clicks > 0:
            rows = await conn.fetch(f"SELECT section, COUNT(*) as cnt FROM {SCHEMA}.user_logs GROUP BY section")
            for r in rows:
                sections_data[r["section"]] = r["cnt"]
            rows = await conn.fetch(f"SELECT lang, COUNT(*) as cnt FROM {SCHEMA}.user_logs GROUP BY lang")
            for r in rows:
                langs_data[r["lang"]] = r["cnt"]

    return dau, mau, total_clicks, sections_data, langs_data


# --- ФУНКЦИИ ДЛЯ ЕЖЕДНЕВНЫХ НОВОСТЕЙ ---

async def save_daily_news(country: str, content: str):
    """Сохраняет свежую подборку заголовков по стране (перезаписывает предыдущую)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"INSERT INTO {SCHEMA}.daily_news (country, content, fetched_at) VALUES ($1, $2, $3) "
            "ON CONFLICT (country) DO UPDATE SET content = EXCLUDED.content, fetched_at = EXCLUDED.fetched_at",
            country, content, datetime.now().isoformat()
        )

async def get_daily_news(country: str):
    """Возвращает (content, fetched_at) для страны или (None, None), если новостей ещё нет"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT content, fetched_at FROM {SCHEMA}.daily_news WHERE country = $1", country)
        return (row["content"], row["fetched_at"]) if row else (None, None)
    except Exception as e:
        logging.error(f"БД недоступна при чтении новостей: {e}")
        return (None, None)


# --- ФУНКЦИИ ДЛЯ ПОИСКА ПАРТНЁРА ПО ИГРЕ (падел / настольный теннис) ---

async def add_game_partner(sport: str, city: str, level: str, available_time: str, username: str):
    """Сохраняет анкету игрока, ищущего партнёра"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"INSERT INTO {SCHEMA}.game_partners (sport, city, level, available_time, username) "
            "VALUES ($1, $2, $3, $4, $5)",
            sport, city, level, available_time, username
        )

async def get_game_partners(sport: str, limit: int = 50):
    """Возвращает список анкет по конкретному виду спорта, самые новые первыми"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT city, level, available_time, username, created_at FROM {SCHEMA}.game_partners "
            "WHERE sport = $1 ORDER BY created_at DESC LIMIT $2",
            sport, limit
        )
        return [
            {
                "city": r["city"],
                "level": r["level"],
                "available_time": r["available_time"],
                "username": r["username"],
                "created_at": str(r["created_at"])
            }
            for r in rows
        ]


# --- ФУНКЦИИ ДЛЯ РЕЦЕПТОВ (блок кулинарии) ---

async def add_recipe(category: str, title: str, text_content: str, video_file_id: str,
                     link_url: str, photo_file_id: str = None, source_key: str = None) -> str:
    """Сохраняет рецепт. Возвращает 'added', 'duplicate' или 'error'.

    source_key — отпечаток исходного поста, чтобы повторная пересылка того же
    рецепта не плодила дубли.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if source_key:
                inserted = await conn.fetchval(
                    f"INSERT INTO {SCHEMA}.recipes "
                    "(category, title, text_content, video_file_id, link_url, photo_file_id, source_key) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7) "
                    "ON CONFLICT (source_key) DO NOTHING RETURNING id",
                    category, title, text_content, video_file_id, link_url,
                    photo_file_id, source_key
                )
                return "added" if inserted else "duplicate"

            await conn.execute(
                f"INSERT INTO {SCHEMA}.recipes "
                "(category, title, text_content, video_file_id, link_url, photo_file_id) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                category, title, text_content, video_file_id, link_url, photo_file_id
            )
            return "added"
    except Exception as e:
        # Точный текст возвращаем наверх, а не прячем за общим «ошибка базы»:
        # админ увидит причину сразу в чате, без похода в логи Render.
        logging.error(f"Не удалось сохранить рецепт: {type(e).__name__}: {e}")
        return f"error:{type(e).__name__}: {e}"


async def count_recipes(category: str = None) -> int:
    """Сколько рецептов в банке — всего или в одной категории"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if category:
                return await conn.fetchval(
                    f"SELECT COUNT(*) FROM {SCHEMA}.recipes WHERE category = $1", category
                ) or 0
            return await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA}.recipes") or 0
    except Exception as e:
        logging.error(f"БД недоступна при подсчёте рецептов: {e}")
        return 0

async def get_recipe_titles(category: str, limit: int = 15, offset: int = 0):
    """Страница списка рецептов: (id, title), отсортированные по названию.

    lower() нужен, чтобы «Борщ» и «борщ» стояли рядом, а не двумя группами.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, title FROM {SCHEMA}.recipes "
                "WHERE category = $1 ORDER BY lower(title), id LIMIT $2 OFFSET $3",
                category, limit, offset
            )
        return [(r["id"], r["title"]) for r in rows]
    except Exception as e:
        logging.error(f"БД недоступна при чтении списка рецептов: {e}")
        return []

async def get_recipe_by_id(recipe_id: int):
    """Возвращает (text_content, video_file_id, link_url, photo_file_id) рецепта по id"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT text_content, video_file_id, link_url, photo_file_id "
                f"FROM {SCHEMA}.recipes WHERE id = $1",
                recipe_id
            )
        if not row:
            return None
        return (row["text_content"], row["video_file_id"], row["link_url"], row["photo_file_id"])
    except Exception as e:
        logging.error(f"БД недоступна при чтении рецепта: {e}")
        return None


# --- ПОСТЫ ТЕМАТИЧЕСКИХ КАНАЛОВ (база знаний по разделам) ---

async def add_article(section: str, title: str, text_content: str, photo_file_id: str,
                      video_file_id: str, link_url: str, source_key: str) -> str:
    """Сохраняет пост в базу знаний раздела. 'added' | 'duplicate' | 'error:<причина>'"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            inserted = await conn.fetchval(
                f"INSERT INTO {SCHEMA}.articles "
                "(section, title, text_content, photo_file_id, video_file_id, link_url, source_key) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7) "
                "ON CONFLICT (source_key) DO NOTHING RETURNING id",
                section, title, text_content, photo_file_id, video_file_id, link_url, source_key
            )
        return "added" if inserted else "duplicate"
    except Exception as e:
        logging.error(f"Не удалось сохранить пост раздела: {type(e).__name__}: {e}")
        return f"error:{type(e).__name__}: {e}"


async def count_articles(section: str) -> int:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                f"SELECT COUNT(*) FROM {SCHEMA}.articles WHERE section = $1", section) or 0
    except Exception as e:
        logging.error(f"БД недоступна при подсчёте постов раздела: {e}")
        return 0


async def get_article_titles(section: str, limit: int = 15, offset: int = 0):
    """Страница списка заголовков по алфавиту"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, title FROM {SCHEMA}.articles WHERE section = $1 "
                "ORDER BY lower(title), id LIMIT $2 OFFSET $3",
                section, limit, offset
            )
        return [(r["id"], r["title"]) for r in rows]
    except Exception as e:
        logging.error(f"БД недоступна при чтении заголовков раздела: {e}")
        return []


async def update_article_title(article_id: int, title: str) -> bool:
    """Переименовывает материал — заголовки из постов не всегда читаемы"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {SCHEMA}.articles SET title = $1 WHERE id = $2", title, article_id)
        return True
    except Exception as e:
        logging.error(f"Не удалось переименовать материал: {type(e).__name__}: {e}")
        return False


async def get_articles_raw(section: str):
    """(id, title, text_content) всех материалов — для пересчёта заголовков"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, title, text_content FROM {SCHEMA}.articles WHERE section = $1 ORDER BY id",
                section)
        return [(r["id"], r["title"], r["text_content"]) for r in rows]
    except Exception as e:
        logging.error(f"БД недоступна при чтении материалов: {e}")
        return []


async def get_article(article_id: int):
    """(title, text_content, photo_file_id, video_file_id, link_url)"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT title, text_content, photo_file_id, video_file_id, link_url "
                f"FROM {SCHEMA}.articles WHERE id = $1", article_id
            )
        if not row:
            return None
        return (row["title"], row["text_content"], row["photo_file_id"],
                row["video_file_id"], row["link_url"])
    except Exception as e:
        logging.error(f"БД недоступна при чтении поста раздела: {e}")
        return None


# --- ИНДЕКС СТРАН (тон новостей + макропоказатели) ---

async def save_country_index(day, country: str, tone, fx, inflation, gdp_growth, score):
    """Кладёт значения за день; повторный расчёт в тот же день перезаписывает их"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.country_index "
                "(country, day, tone, fx, inflation, gdp_growth, score) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7) "
                "ON CONFLICT (country, day) DO UPDATE SET "
                "tone = EXCLUDED.tone, fx = EXCLUDED.fx, inflation = EXCLUDED.inflation, "
                "gdp_growth = EXCLUDED.gdp_growth, score = EXCLUDED.score",
                country, day, tone, fx, inflation, gdp_growth, score
            )
    except Exception as e:
        logging.error(f"Не удалось сохранить индекс стран: {type(e).__name__}: {e}")


async def get_latest_index():
    """Самый свежий срез: (дата, {страна: {...показатели}}) либо (None, {})"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            day = await conn.fetchval(f"SELECT MAX(day) FROM {SCHEMA}.country_index")
            if not day:
                return None, {}
            rows = await conn.fetch(
                f"SELECT country, tone, fx, inflation, gdp_growth, score "
                f"FROM {SCHEMA}.country_index WHERE day = $1", day
            )
        return day, {r["country"]: dict(r) for r in rows}
    except Exception as e:
        logging.error(f"БД недоступна при чтении индекса стран: {e}")
        return None, {}


async def get_scores_before(day, days_back: int):
    """Баллы на ближайший день не позже чем day - days_back. Для стрелок динамики."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            target = await conn.fetchval(
                f"SELECT MAX(day) FROM {SCHEMA}.country_index "
                "WHERE day <= $1::date - $2::int", day, days_back
            )
            if not target:
                return {}
            rows = await conn.fetch(
                f"SELECT country, score FROM {SCHEMA}.country_index WHERE day = $1", target
            )
        return {r["country"]: r["score"] for r in rows}
    except Exception as e:
        logging.error(f"БД недоступна при чтении истории индекса: {e}")
        return {}


async def get_last_known_macro(country: str):
    """Последние непустые инфляция и рост ВВП — API Всемирного банка часто
    отваливается, а показатели годовые, поэтому старое значение вполне годится."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT inflation, gdp_growth FROM {SCHEMA}.country_index "
                "WHERE country = $1 AND inflation IS NOT NULL AND gdp_growth IS NOT NULL "
                "ORDER BY day DESC LIMIT 1", country
            )
        return (row["inflation"], row["gdp_growth"]) if row else (None, None)
    except Exception as e:
        logging.error(f"БД недоступна при чтении макроданных: {e}")
        return (None, None)


# --- ФУНКЦИИ ДЛЯ PRO-SHOP (каталог одежды и аксессуаров) ---

async def add_shop_item(gender: str, item_type: str, title: str, description: str,
                        photo_file_id: str, link_url: str, source_key: str) -> str:
    """Сохраняет товар. Возвращает 'added', 'duplicate' или 'error:<причина>'."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            inserted = await conn.fetchval(
                f"INSERT INTO {SCHEMA}.shop_items "
                "(gender, item_type, title, description, photo_file_id, link_url, source_key) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7) "
                "ON CONFLICT (source_key) DO NOTHING RETURNING id",
                gender, item_type, title, description, photo_file_id, link_url, source_key
            )
        return f"added:{inserted}" if inserted else "duplicate"
    except Exception as e:
        logging.error(f"Не удалось сохранить товар: {type(e).__name__}: {e}")
        return f"error:{type(e).__name__}: {e}"


async def move_shop_item(item_id: int, gender: str, item_type: str) -> bool:
    """Переносит товар в другую категорию — на случай ошибки автораскладки"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {SCHEMA}.shop_items SET gender = $1, item_type = $2 WHERE id = $3",
                gender, item_type, item_id
            )
        return True
    except Exception as e:
        logging.error(f"Не удалось перенести товар: {type(e).__name__}: {e}")
        return False


async def get_shop_counts() -> dict:
    """Счётчики всех категорий одним запросом: {(пол, тип): количество}.

    Раньше витрина спрашивала количество отдельно по каждой категории — это
    полтора десятка обращений к базе на одно открытие раздела.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT gender, item_type, COUNT(*) AS n FROM {SCHEMA}.shop_items "
                "GROUP BY gender, item_type"
            )
        return {(r["gender"], r["item_type"]): r["n"] for r in rows}
    except Exception as e:
        logging.error(f"БД недоступна при подсчёте витрины: {e}")
        return {}


async def count_shop_items(gender: str = None, item_type: str = None) -> int:
    """Сколько товаров всего, в разделе пола или в конкретной категории"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if gender and item_type:
                return await conn.fetchval(
                    f"SELECT COUNT(*) FROM {SCHEMA}.shop_items "
                    "WHERE gender = $1 AND item_type = $2", gender, item_type
                ) or 0
            if gender:
                return await conn.fetchval(
                    f"SELECT COUNT(*) FROM {SCHEMA}.shop_items WHERE gender = $1", gender
                ) or 0
            return await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA}.shop_items") or 0
    except Exception as e:
        logging.error(f"БД недоступна при подсчёте товаров: {e}")
        return 0


async def get_shop_titles(gender: str, item_type: str, limit: int = 15, offset: int = 0):
    """Страница списка товаров категории, по алфавиту"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, title FROM {SCHEMA}.shop_items "
                "WHERE gender = $1 AND item_type = $2 "
                "ORDER BY lower(title), id LIMIT $3 OFFSET $4",
                gender, item_type, limit, offset
            )
        return [(r["id"], r["title"]) for r in rows]
    except Exception as e:
        logging.error(f"БД недоступна при чтении списка товаров: {e}")
        return []


async def get_shop_item(item_id: int):
    """Карточка товара: (title, description, photo_file_id, link_url)"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT title, description, photo_file_id, link_url "
                f"FROM {SCHEMA}.shop_items WHERE id = $1", item_id
            )
        if not row:
            return None
        return (row["title"], row["description"], row["photo_file_id"], row["link_url"])
    except Exception as e:
        logging.error(f"БД недоступна при чтении товара: {e}")
        return None


# --- ФУНКЦИИ ДЛЯ КНИГ (блок интеллекта) ---

async def get_books(category: str, limit: int = 3):
    """Возвращает последние книги по категории"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT text_content, cover_file_id FROM {SCHEMA}.books "
                "WHERE category = $1 ORDER BY id DESC LIMIT $2",
                category, limit
            )
        return [(r["text_content"], r["cover_file_id"]) for r in rows]
    except Exception as e:
        logging.error(f"БД недоступна при чтении книг: {e}")
        return []

async def add_book(category: str, text_content: str, cover_file_id: str):
    """Сохраняет новую книгу (добавляется автоматически при публикации в канале)"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.books (category, text_content, cover_file_id) VALUES ($1, $2, $3)",
                category, text_content, cover_file_id
            )
    except Exception as e:
        logging.error(f"БД недоступна, книга из канала не сохранена: {e}")


# --- ФУНКЦИИ ДЛЯ ГОЛОВОЛОМОК (банк задач + статистика) ---

async def add_puzzle(source_poll_id, question, options, correct_option_id, explanation=None) -> str:
    """Сохраняет задачу в банк. Возвращает 'added', 'duplicate' или 'error'.

    options — список строк с вариантами ответа, хранится как JSON.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            inserted = await conn.fetchval(
                f"INSERT INTO {SCHEMA}.puzzles "
                "(source_poll_id, question, options, correct_option_id, explanation) "
                "VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (source_poll_id) DO NOTHING RETURNING id",
                source_poll_id, question, json.dumps(options, ensure_ascii=False),
                correct_option_id, explanation
            )
        return "added" if inserted else "duplicate"
    except Exception as e:
        logging.error(f"БД недоступна при сохранении головоломки: {e}")
        return "error"


async def get_all_puzzles():
    """Весь банк задач. Перемешиванием занимается вызывающий код."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, question, options, correct_option_id, explanation "
                f"FROM {SCHEMA}.puzzles ORDER BY id"
            )
        return [
            {
                "id": r["id"],
                "question": r["question"],
                "options": json.loads(r["options"]),
                "correct_option_id": r["correct_option_id"],
                "explanation": r["explanation"],
            }
            for r in rows
        ]
    except Exception as e:
        logging.error(f"БД недоступна при чтении банка головоломок: {e}")
        return []


async def count_puzzles() -> int:
    """Сколько задач в банке — нужно админу при импорте"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA}.puzzles") or 0
    except Exception as e:
        logging.error(f"БД недоступна при подсчёте головоломок: {e}")
        return 0


async def save_puzzle_answer(user_id: int, puzzle_id: int, is_correct: bool):
    """Фиксирует один ответ пользователя"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.puzzle_answers (user_id, puzzle_id, is_correct) "
                "VALUES ($1, $2, $3)",
                user_id, puzzle_id, is_correct
            )
    except Exception as e:
        logging.error(f"БД недоступна при записи ответа на головоломку: {e}")


async def save_puzzle_round(user_id: int, total: int, correct: int):
    """Фиксирует завершённое прохождение целиком"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.puzzle_rounds (user_id, total, correct) VALUES ($1, $2, $3)",
                user_id, total, correct
            )
    except Exception as e:
        logging.error(f"БД недоступна при записи итога раунда: {e}")


async def get_puzzle_stats(user_id: int) -> dict:
    """Сводная статистика пользователя по головоломкам"""
    empty = {
        "rounds": 0, "best_correct": 0, "best_total": 0, "best_pct": 0.0,
        "avg_pct": 0.0, "answers": 0, "answers_correct": 0, "accuracy": 0.0,
        "last_correct": 0, "last_total": 0,
    }
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rounds = await conn.fetch(
                f"SELECT total, correct FROM {SCHEMA}.puzzle_rounds "
                "WHERE user_id = $1 ORDER BY finished_at DESC",
                user_id
            )
            ans = await conn.fetchrow(
                f"SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE is_correct) AS ok "
                f"FROM {SCHEMA}.puzzle_answers WHERE user_id = $1",
                user_id
            )
    except Exception as e:
        logging.error(f"БД недоступна при чтении статистики головоломок: {e}")
        return empty

    if not rounds:
        return empty

    scored = [(r["correct"], r["total"]) for r in rounds if r["total"]]
    if not scored:
        return empty

    percents = [c / t * 100 for c, t in scored]
    best_correct, best_total = max(scored, key=lambda ct: ct[0] / ct[1])
    total_answers = (ans["n"] if ans else 0) or 0
    total_ok = (ans["ok"] if ans else 0) or 0

    return {
        "rounds": len(scored),
        "best_correct": best_correct,
        "best_total": best_total,
        "best_pct": best_correct / best_total * 100,
        "avg_pct": sum(percents) / len(percents),
        "answers": total_answers,
        "answers_correct": total_ok,
        "accuracy": (total_ok / total_answers * 100) if total_answers else 0.0,
        "last_correct": scored[0][0],
        "last_total": scored[0][1],
    }


# --- ЛЕГАСИ: СТАРЫЙ ДВИЖОК КВИЗОВ ЧЕРЕЗ ПЕРЕСЫЛКУ ИЗ КАНАЛА ---

async def get_next_unsolved_quiz(user_id: int):
    """Возвращает (poll_id, message_id) следующей нерешённой пользователем головоломки, либо None"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT poll_id, message_id FROM {SCHEMA}.quizzes "
                f"WHERE poll_id NOT IN (SELECT poll_id FROM {SCHEMA}.user_answers WHERE user_id = $1) "
                "ORDER BY message_id ASC LIMIT 1",
                user_id
            )
        return (row["poll_id"], row["message_id"]) if row else None
    except Exception as e:
        logging.error(f"БД недоступна при чтении головоломок: {e}")
        return None
