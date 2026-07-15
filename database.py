import os
import aiosqlite
from datetime import datetime, timedelta

# Определяем путь к БД в зависимости от среды (локально или Amvera/Render)
DB_PATH = "/data/quiz_bot_v2.db" if os.path.exists("/data") else "quiz_bot_v2.db"

async def init_db():
    """Инициализация базы данных и создание всех необходимых таблиц"""
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Таблицы для квизов
        await db.execute("""
        CREATE TABLE IF NOT EXISTS quizzes (
            poll_id TEXT PRIMARY KEY,
            message_id INTEGER,
            question TEXT,
            correct_option_id INTEGER
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_answers (
            user_id INTEGER,
            poll_id TEXT,
            is_correct INTEGER,
            PRIMARY KEY (user_id, poll_id)
        )""")
        
        # 2. Таблица для подписок
        await db.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            expires_at TEXT
        )""")
        
        # 3. Таблицы для контента (рецепты и книги)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            text_content TEXT,
            video_file_id TEXT,
            link_url TEXT
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            text_content TEXT,
            cover_file_id TEXT
        )""")
        
        # 4. Таблица для логов платежей (CryptoBot, ЮKassa и т.д.)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            invoice_id TEXT PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            currency TEXT,
            status TEXT,
            created_at TEXT
        )""")
        
        # 5. Таблица для надежного хранения лимитов ИИ
        await db.execute("""
        CREATE TABLE IF NOT EXISTS ai_limits (
            user_id INTEGER PRIMARY KEY,
            requests_count INTEGER DEFAULT 0,
            last_request_date TEXT
        )""")
        
        # 6. Таблица для сохранения выбранного языка пользователя
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            lang TEXT
        )""")
        
        # 7. НОВАЯ ТАБЛИЦА: Продуктовые логи для DAU/MAU и долей трафика по разделам
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            section TEXT,
            lang TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        
        await db.commit()

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С ЯЗЫКАМИ ПОЛЬЗОВАТЕЛЕЙ ---

async def set_user_language(user_id: int, lang: str):
    """Сохраняет выбранный язык пользователя в базу данных"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO users (user_id, lang) VALUES (?, ?)", 
            (user_id, lang)
        )
        await db.commit()

async def get_user_language(user_id: int) -> str:
    """Получает сохраненный язык пользователя (по умолчанию английский)"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else "en"

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С ПОДПИСКАМИ ---

async def check_subscription(user_id: int) -> bool:
    """Проверяет, активна ли платная подписка у пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT expires_at FROM subscriptions WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or not row[0]:
                return False
            
            try:
                expires_at = datetime.fromisoformat(row[0])
                return expires_at > datetime.now()
            except ValueError:
                return False

async def add_or_extend_subscription(user_id: int, days: int):
    """Создает или продлевает платную подписку на N дней"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT expires_at FROM subscriptions WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            
        now = datetime.now()
        if row and row[0]:
            try:
                current_expires = datetime.fromisoformat(row[0])
                start_date = current_expires if current_expires > now else now
            except ValueError:
                start_date = now
        else:
            start_date = now
            
        new_expires = start_date + timedelta(days=days)
        await db.execute(
            "INSERT OR REPLACE INTO subscriptions (user_id, expires_at) VALUES (?, ?)",
            (user_id, new_expires.isoformat())
        )
        await db.commit()

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С ЛИМИТАМИ ИИ ---

async def get_ai_requests_count(user_id: int) -> int:
    """Получает количество запросов пользователя к Claude за сегодня"""
    today = datetime.now().date().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT requests_count, last_request_date FROM ai_limits WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                requests_count, last_date = row
                if last_date == today:
                    return requests_count
            return 0

async def increment_ai_requests(user_id: int):
    """Увеличивает счетчик запросов к Claude на 1"""
    today = datetime.now().date().isoformat()
    current_count = await get_ai_requests_count(user_id)
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO ai_limits (user_id, requests_count, last_request_date) VALUES (?, ?, ?)",
            (user_id, current_count + 1, today)
        )
        await db.commit()

# --- НОВАЯ ФУНКЦИЯ: Сбор сырых метрик для сквозного Data-Driven дашборда ---
async def log_action(user_id: int, section: str, lang: str):
    """Фиксирует клик пользователя для подсчета DAU/MAU и долей трафика"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO user_logs (user_id, section, lang) VALUES (?, ?, ?)",
                (user_id, section, lang)
            )
            await db.commit()
    except Exception as e:
        import logging
        logging.error(f"Ошибка логирования продуктовой аналитики: {e}")
