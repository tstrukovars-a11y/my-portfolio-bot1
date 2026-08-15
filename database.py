import json
import os
import logging
from datetime import datetime, timedelta

import asyncpg

# Render даёт строку вида postgres://..., приводим к схеме postgresql:// для совместимости
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

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
    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(
                DATABASE_URL, min_size=1, max_size=5, init=_init_connection
            )
            _pool_failure_logged = False
            logging.info(f"Подключение к базе установлено: {describe_db_target()}")
        except Exception:
            # Пишем адрес только при первом сбое: иначе каждая кнопка засыпает
            # логи одной и той же строкой, а найти причину всё равно нельзя.
            if not _pool_failure_logged:
                logging.error(
                    f"Не удалось подключиться к базе. Адрес из DATABASE_URL: "
                    f"{describe_db_target()}"
                )
                _pool_failure_logged = True
            raise
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

        # 12. Анкеты поиска партнёра для игры
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
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT lang FROM {SCHEMA}.users WHERE user_id = $1", user_id)
        if row:
            _lang_cache[user_id] = row["lang"]
            return row["lang"]
    except Exception as e:
        logging.error(f"БД недоступна при чтении языка, работаем из памяти: {e}")

    return _lang_cache.get(user_id, "en")


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

async def add_recipe(category: str, title: str, text_content: str, video_file_id: str, link_url: str):
    """Сохраняет новый рецепт (добавляется автоматически при публикации в канале)"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.recipes (category, title, text_content, video_file_id, link_url) "
                "VALUES ($1, $2, $3, $4, $5)",
                category, title, text_content, video_file_id, link_url
            )
    except Exception as e:
        logging.error(f"БД недоступна, рецепт из канала не сохранён: {e}")

async def get_recipe_titles(category: str, limit: int = 15):
    """Возвращает список (id, title) для отображения кликабельного списка рецептов"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, title FROM {SCHEMA}.recipes "
                "WHERE category = $1 ORDER BY id DESC LIMIT $2",
                category, limit
            )
        return [(r["id"], r["title"]) for r in rows]
    except Exception as e:
        logging.error(f"БД недоступна при чтении списка рецептов: {e}")
        return []

async def get_recipe_by_id(recipe_id: int):
    """Возвращает (text_content, video_file_id, link_url) конкретного рецепта по id"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT text_content, video_file_id, link_url FROM {SCHEMA}.recipes WHERE id = $1",
                recipe_id
            )
        return (row["text_content"], row["video_file_id"], row["link_url"]) if row else None
    except Exception as e:
        logging.error(f"БД недоступна при чтении рецепта: {e}")
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
