import os
import logging
from datetime import datetime, timedelta

import asyncpg

# Render даёт строку вида postgres://..., приводим к схеме postgresql:// для совместимости
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_pool = None

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


async def get_pool():
    """Возвращает пул соединений, создаёт при первом обращении"""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=1, max_size=5, init=_init_connection
        )
    return _pool


async def init_db():
    """Инициализация базы данных и создание всех необходимых таблиц"""
    pool = await get_pool()
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

        # 9. Анкеты поиска партнёра для игры
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
    """Сохраняет выбранный язык пользователя в базу данных"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"INSERT INTO {SCHEMA}.users (user_id, lang) VALUES ($1, $2) "
            "ON CONFLICT (user_id) DO UPDATE SET lang = EXCLUDED.lang",
            user_id, lang
        )

async def get_user_language(user_id: int) -> str:
    """Получает сохраненный язык пользователя (по умолчанию английский)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(f"SELECT lang FROM {SCHEMA}.users WHERE user_id = $1", user_id)
        return row["lang"] if row else "en"


# --- ФУНКЦИИ ДЛЯ РАБОТЫ С ПОДПИСКАМИ ---

async def check_subscription(user_id: int) -> bool:
    """Проверяет, активна ли платная подписка у пользователя"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(f"SELECT expires_at FROM {SCHEMA}.subscriptions WHERE user_id = $1", user_id)
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
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT requests_count, last_request_date FROM {SCHEMA}.ai_limits WHERE user_id = $1", user_id
        )
        if row and row["last_request_date"] == today:
            return row["requests_count"]
        return 0

async def increment_ai_requests(user_id: int):
    """Увеличивает счетчик запросов к Claude на 1"""
    today = datetime.now().date().isoformat()
    current_count = await get_ai_requests_count(user_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"INSERT INTO {SCHEMA}.ai_limits (user_id, requests_count, last_request_date) VALUES ($1, $2, $3) "
            "ON CONFLICT (user_id) DO UPDATE SET requests_count = EXCLUDED.requests_count, "
            "last_request_date = EXCLUDED.last_request_date",
            user_id, current_count + 1, today
        )


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
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(f"SELECT content, fetched_at FROM {SCHEMA}.daily_news WHERE country = $1", country)
        return (row["content"], row["fetched_at"]) if row else (None, None)


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

async def add_recipe(category: str, title: str, text_content: str, video_file_id: str, link_url: str):
    """Сохраняет новый рецепт (добавляется автоматически при публикации в канале)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"INSERT INTO {SCHEMA}.recipes (category, title, text_content, video_file_id, link_url) "
            "VALUES ($1, $2, $3, $4, $5)",
            category, title, text_content, video_file_id, link_url
        )

async def get_recipe_titles(category: str, limit: int = 15):
    """Возвращает список (id, title) для отображения кликабельного списка рецептов"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT id, title FROM {SCHEMA}.recipes "
            "WHERE category = $1 ORDER BY id DESC LIMIT $2",
            category, limit
        )
        return [(r["id"], r["title"]) for r in rows]

async def get_recipe_by_id(recipe_id: int):
    """Возвращает (text_content, video_file_id, link_url) конкретного рецепта по id"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT text_content, video_file_id, link_url FROM {SCHEMA}.recipes WHERE id = $1",
            recipe_id
        )
        return (row["text_content"], row["video_file_id"], row["link_url"]) if row else None


# --- ФУНКЦИИ ДЛЯ КНИГ (блок интеллекта) ---

async def get_books(category: str, limit: int = 3):
    """Возвращает последние книги по категории"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT text_content, cover_file_id FROM {SCHEMA}.books "
            "WHERE category = $1 ORDER BY id DESC LIMIT $2",
            category, limit
        )
        return [(r["text_content"], r["cover_file_id"]) for r in rows]

async def add_book(category: str, text_content: str, cover_file_id: str):
    """Сохраняет новую книгу (добавляется автоматически при публикации в канале)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"INSERT INTO {SCHEMA}.books (category, text_content, cover_file_id) VALUES ($1, $2, $3)",
            category, text_content, cover_file_id
        )


# --- ФУНКЦИИ ДЛЯ КВИЗОВ-ГОЛОВОЛОМОК ---

async def get_next_unsolved_quiz(user_id: int):
    """Возвращает (poll_id, message_id) следующей нерешённой пользователем головоломки, либо None"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT poll_id, message_id FROM {SCHEMA}.quizzes "
            f"WHERE poll_id NOT IN (SELECT poll_id FROM {SCHEMA}.user_answers WHERE user_id = $1) "
            "ORDER BY message_id ASC LIMIT 1",
            user_id
        )
        return (row["poll_id"], row["message_id"]) if row else None
