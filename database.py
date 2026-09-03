import json
import os
import logging
import secrets
from datetime import datetime, timedelta, timezone

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


# Общая схема для учёта: сюда пишут ВСЕ боты, а не только этот. Собственные
# таблицы каждого бота лежат в своей схеме, финансы — в одной на всех, иначе
# сводный отчёт пришлось бы собирать запросами по чужим неймспейсам.
FINANCE_SCHEMA = "finance"


async def _init_connection(conn):
    """Выполняется при каждом новом соединении: гарантирует существование схемы"""
    await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {FINANCE_SCHEMA}")


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

        # Напоминания о матчах. Отметка в общем канале — личная: кто на что
        # подписался, видит только бот, а ссылка уходит в личку к началу.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.match_alerts (
            user_id BIGINT NOT NULL,
            match_id TEXT NOT NULL,
            tour TEXT NOT NULL,
            title TEXT,
            starts_at TIMESTAMP,
            sent BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, match_id)
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

        # Номер поста книги в её канале — чтобы правка не плодила копии,
        # как это уже устроено у путешествий.
        await conn.execute(
            f"ALTER TABLE {SCHEMA}.books ADD COLUMN IF NOT EXISTS channel_msg_id BIGINT")

        # Партнёрская ссылка у каждой книги своя: магазины дают ссылку на
        # страницу товара, а не шаблон с подстановкой названия.
        await conn.execute(
            f"ALTER TABLE {SCHEMA}.books ADD COLUMN IF NOT EXISTS buy_url TEXT")

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

        # 11а. Какая задача когда выходила в канал: по ней считается
        # статистика дня и отбираются ещё не публиковавшиеся.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.puzzle_posts (
            id SERIAL PRIMARY KEY,
            puzzle_id INTEGER,
            chat_id BIGINT,
            message_id BIGINT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        # Раньше хранили только «верно/неверно». Чтобы показать счётчик на
        # кнопке, нужен сам выбор.
        await conn.execute(
            f"ALTER TABLE {SCHEMA}.puzzle_answers "
            "ADD COLUMN IF NOT EXISTS choice INTEGER")

        # 11б. Рейтинг тура: кого показывать в анонсе. Тянется у ESPN раз в
        # неделю, чтобы список сильнейших не устаревал в коде.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.tennis_ranking (
            tour TEXT NOT NULL,
            place INTEGER NOT NULL,
            name TEXT NOT NULL,
            country TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tour, place)
        )""")

        # Свои написания имён: словарь в коде покрывает не всех, а
        # исправлять написание не должно требовать деплоя.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.player_names (
            name_en TEXT PRIMARY KEY,
            name_ru TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

        # 15. Настройки, меняемые из бота (пароли разделов и прочее).
        # Нужны, чтобы владелец мог сменить пароль, не трогая Render.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")

        # 16. Путешествия: страна → локация → публикация.
        # Страна хранится на двух языках, чтобы кнопки читались и по-английски.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.travel_places (
            id SERIAL PRIMARY KEY,
            country_ru TEXT,
            country_en TEXT,
            place TEXT,
            text_content TEXT,
            photo_file_id TEXT,
            video_file_id TEXT,
            link_url TEXT,
            source_key TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        # Порядок мест внутри страны. Нужен отдельным столбцом: алфавит
        # ставит Авиньон перед Ниццей, а по стране осмысленнее двигаться
        # маршрутом — с юга на север.
        await conn.execute(
            f"ALTER TABLE {SCHEMA}.travel_places "
            "ADD COLUMN IF NOT EXISTS ordering INTEGER NOT NULL DEFAULT 0")
        # Номер поста в канале путешествий. Без него повторная выкладка
        # плодит копии вместо того, чтобы поправить уже вышедшее.
        await conn.execute(
            f"ALTER TABLE {SCHEMA}.travel_places "
            "ADD COLUMN IF NOT EXISTS channel_msg_id BIGINT")
        await conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS travel_source_uniq "
            f"ON {SCHEMA}.travel_places (source_key)"
        )

        # 17. Кэш переводов. Перевод одного и того же поста не должен
        # заказываться заново при каждом открытии: это и деньги, и секунды
        # ожидания у читателя.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.translations (
            source TEXT,
            source_id INTEGER,
            field TEXT,
            lang TEXT,
            text TEXT,
            PRIMARY KEY (source, source_id, field, lang)
        )""")

        # 18. Посетители: кто заходил в бота. Telegram отдаёт имя, ник и язык
        # в каждом апдейте — храним, чтобы владелец видел аудиторию поимённо,
        # а не только обезличенные счётчики DAU/MAU.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.visitors (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            tg_language TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actions INTEGER DEFAULT 0
        )""")

        # Восстанавливаем тех, кто заходил до появления этой таблицы: клики
        # писались в user_logs с самого начала. Имя подставится при следующем
        # заходе человека, а id, счётчик и даты видны сразу. DO NOTHING делает
        # вызов безопасным при каждом старте и не воскрешает удалённых через
        # /forget — у них вычищены и логи.
        await conn.execute(f"""
        INSERT INTO {SCHEMA}.visitors (user_id, first_seen, last_seen, actions)
        SELECT user_id, MIN(timestamp), MAX(timestamp), COUNT(*)
        FROM {SCHEMA}.user_logs GROUP BY user_id
        ON CONFLICT (user_id) DO NOTHING""")

        # 19. Единый журнал операций всех ботов и каналов.
        #
        # Три вида активов ведут себя по-разному, поэтому вид хранится отдельно
        # от кода валюты:
        #   • звёзды — не деньги, пока не выведены, и курс вывода плавает;
        #   • крипта — дробные суммы и цена меняется ежеминутно;
        #   • фиат — обычные деньги с курсом на дату.
        # amount_ils заполняется, только когда курс известен: пустое поле честнее
        # выдуманного пересчёта, а порог оборота считается по заполненным.
        #
        # owner заложен заранее: пока значение одно — ваше. Появятся чужие деньги
        # в этой таблице — это уже посредничество, для которого нужна лицензия,
        # и увидеть это лучше в структуре, чем постфактум.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {FINANCE_SCHEMA}.transactions (
            id SERIAL PRIMARY KEY,
            owner TEXT NOT NULL DEFAULT 'self',
            source TEXT NOT NULL,
            kind TEXT NOT NULL,
            asset TEXT NOT NULL,
            asset_kind TEXT NOT NULL,
            amount NUMERIC(24, 8) NOT NULL,
            amount_ils NUMERIC(20, 2),
            rate_ils NUMERIC(24, 8),
            rate_at DATE,
            category TEXT,
            note TEXT,
            external_id TEXT,
            occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        # Индекс обычный, не частичный: ON CONFLICT не выводит частичный без
        # повтора предиката — на этом уже обжигались с рецептами. NULL в
        # external_id уникальность не нарушает, их Postgres считает различными.
        await conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS transactions_source_external_uniq "
            f"ON {FINANCE_SCHEMA}.transactions (source, external_id)")
        await conn.execute(
            f"CREATE INDEX IF NOT EXISTS transactions_occurred_idx "
            f"ON {FINANCE_SCHEMA}.transactions (occurred_at)")

        # 20. Что уже ушло в дайджест-канал. Без этого материалы выходили бы
        # по кругу: источники общие с разделами бота и сами о публикации
        # ничего не знают.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.digest_log (
            section TEXT,
            item_id INTEGER,
            message_id BIGINT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (section, item_id)
        )""")
        # Сколько раз материал выходил. Повтор — не сбой, а отдельный повод:
        # «приготовим лазанью? напоминаю рецепт» читается иначе, чем та же
        # публикация впервые. Счётчик нужен, чтобы отличать одно от другого.
        await conn.execute(
            f"ALTER TABLE {SCHEMA}.digest_log "
            "ADD COLUMN IF NOT EXISTS times INTEGER NOT NULL DEFAULT 1")

        # 21. Рекорды браузерной гонки. Ключ — игрок, а не заезд: в таблице
        # хранится лучший результат, а не история попыток.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.race_scores (
            user_id BIGINT PRIMARY KEY,
            name TEXT,
            best INTEGER NOT NULL DEFAULT 0,
            played INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        # 22. Мультфильмы: хранится раскадровка, а не видео — она занимает
        # килобайты и проигрывается заново на каждом устройстве.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.cartoons (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            story TEXT,
            board TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        # 23. Нарисованные кадры к сценам. Хранятся в базе, а не файлами:
        # своего файлового хранилища у сервиса нет, а кадр нужен ровно там же,
        # где раскадровка, и живёт ровно столько же.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.cartoon_frames (
            cartoon_id INTEGER NOT NULL,
            scene_index INTEGER NOT NULL,
            mime TEXT NOT NULL DEFAULT 'image/png',
            data BYTEA NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (cartoon_id, scene_index)
        )""")

        # 24. Достопримечательности внутри города. Отдельный уровень нужен
        # затем, что город — это не один рассказ: в Минске проспект,
        # Троицкое предместье и ратуша это три разных повода для поста.
        #
        # visited отделяет то, где владелец действительно был, от того, что
        # в городе просто есть: канал от первого лица и справочник — разные
        # вещи, и путать их нельзя.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.travel_spots (
            id SERIAL PRIMARY KEY,
            place_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            lower_name TEXT GENERATED ALWAYS AS (lower(name)) STORED,
            text_content TEXT,
            photo_file_id TEXT,
            art BYTEA,
            art_mime TEXT,
            visited BOOLEAN NOT NULL DEFAULT FALSE,
            ordering INTEGER NOT NULL DEFAULT 0,
            channel_msg_id BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (place_id, lower_name)
        )""")
        # Адрес и сайт добавлены позже: пост без них — заметка, с ними —
        # повод дойти. Часы работы намеренно не храним: они устаревают,
        # а ссылка на сайт остаётся верной.
        await conn.execute(
            f"ALTER TABLE {SCHEMA}.travel_spots ADD COLUMN IF NOT EXISTS address TEXT")
        await conn.execute(
            f"ALTER TABLE {SCHEMA}.travel_spots ADD COLUMN IF NOT EXISTS url TEXT")

        # 25. Персонажи, нарисованные самими пользователями. Каждый видит и
        # использует только своих: чужой рисунок в своей истории — не то, что
        # человек ожидает увидеть, и не то, на что он давал согласие.
        # lower_name — вычисляемый столбец: он и держит уникальность имени,
        # потому что ON CONFLICT по выражению Postgres вывести не может.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.own_characters (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            -- Случайный адрес вместо порядкового номера: картинку забирает
            -- тег <img> на странице, приложить к нему подпись Telegram
            -- нельзя, а номер подбирается перебором за минуту.
            token TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            lower_name TEXT GENERATED ALWAYS AS (lower(name)) STORED,
            kind TEXT NOT NULL DEFAULT 'character',
            mime TEXT NOT NULL DEFAULT 'image/jpeg',
            data BYTEA NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, lower_name)
        )""")

        # 26. Отклики читателей на посты канала. Один человек — один голос
        # на пост, поэтому ключ составной: повторное нажатие не накручивает
        # счётчик, а снимает голос.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.post_votes (
            section TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            user_id BIGINT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (section, item_id, user_id)
        )""")

        # 27. Анкеты поиска партнёра для игры
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

        # 28. Календари. Один календарь — одна семья или один человек:
        # события чужого календаря не видны никому снаружи, включая владельца
        # бота. Подписку продлевает тот, кому календарь передан, — до её конца
        # календарь пишущий, после — только для чтения.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.plan_spaces (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            owner_id BIGINT NOT NULL,
            owner_name TEXT,
            invite_code TEXT UNIQUE,
            paid_until DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed BOOLEAN DEFAULT FALSE
        )""")

        # 29. Кто состоит в календаре. Владелец тоже участник — иначе при
        # смене владельца пришлось бы чинить его собственный доступ.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.plan_members (
            space_id INTEGER NOT NULL REFERENCES {SCHEMA}.plan_spaces(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL,
            user_name TEXT,
            role TEXT DEFAULT 'member',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (space_id, user_id)
        )""")

        # 30. События календаря. Одно событие — одна строка, даже если оно
        # повторяется: правило повтора лежит рядом, а отдельные вхождения
        # разворачиваются уже при показе. Иначе годовая еженедельная серия
        # это полсотни строк, и перенос серии — полсотни правок.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.plan_events (
            id SERIAL PRIMARY KEY,
            space_id INTEGER NOT NULL DEFAULT 0,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            starts_at TIMESTAMP NOT NULL,
            duration_min INTEGER NOT NULL DEFAULT 60,
            repeat_rule TEXT,
            repeat_until DATE,
            created_by BIGINT NOT NULL,
            created_by_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            cancelled BOOLEAN DEFAULT FALSE
        )""")

        # 31. Отклонения отдельных вхождений серии: одно занятие перенесли
        # или отменили, остальные идут по расписанию. Ключ — дата вхождения
        # ПО ИСХОДНОМУ расписанию: только она не меняется, когда занятие
        # двигают повторно.
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.plan_overrides (
            event_id INTEGER NOT NULL REFERENCES {SCHEMA}.plan_events(id) ON DELETE CASCADE,
            occur_date DATE NOT NULL,
            moved_to TIMESTAMP,
            duration_min INTEGER,
            changed_by BIGINT,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (event_id, occur_date)
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

async def toggle_alert(user_id: int, match_id: str, tour: str,
                       title: str, starts_at):
    """Ставит или снимает напоминание. Возвращает (поставлено ли, всего у матча).

    Повторное нажатие снимает: кнопка, которую нельзя отжать, ловит
    случайное касание и потом присылает то, чего не просили.
    """
    # Колонка starts_at объявлена как TIMESTAMP без пояса, а сюда приходит
    # время с поясом (UTC от источника). asyncpg на этом падает изнутри —
    # ошибка глоталась, напоминание не записывалось, и кнопка отвечала
    # «снято». Приводим к наивному UTC.
    if starts_at is not None and starts_at.tzinfo is not None:
        starts_at = starts_at.astimezone(timezone.utc).replace(tzinfo=None)

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            gone = await conn.execute(
                f"DELETE FROM {SCHEMA}.match_alerts WHERE user_id = $1 AND match_id = $2",
                user_id, match_id)
            added = not gone.endswith("1")
            if added:
                await conn.execute(
                    f"INSERT INTO {SCHEMA}.match_alerts "
                    "(user_id, match_id, tour, title, starts_at) "
                    "VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING",
                    user_id, match_id, tour, title, starts_at)
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM {SCHEMA}.match_alerts WHERE match_id = $1",
                match_id)
        return added, total
    except Exception as e:
        # None, а не False: «не сохранилось» и «снято» — разные вещи, и
        # читателю надо сказать правду.
        logging.error(f"Напоминание не сохранено: {e}")
        return None, 0


async def ensure_alert(user_id: int, match_id: str, tour: str,
                       title: str, starts_at):
    """Включить напоминание, не выключая уже включённое.

    toggle_alert здесь не годится: холодный читатель нажимает кнопку в
    канале (запись создаётся), а потом открывает бота по ссылке — второй
    вызов снял бы то, ради чего он пришёл.
    """
    if starts_at is not None and starts_at.tzinfo is not None:
        starts_at = starts_at.astimezone(timezone.utc).replace(tzinfo=None)
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.match_alerts "
                "(user_id, match_id, tour, title, starts_at) "
                "VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (user_id, match_id) DO UPDATE "
                "SET starts_at = EXCLUDED.starts_at, sent = FALSE",
                user_id, match_id, tour, title, starts_at)
        return True
    except Exception as e:
        logging.error(f"Напоминание не включено: {e}")
        return None


async def drop_alert(user_id: int, match_id: str) -> bool:
    """Снять напоминание. True — оно было и снято."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            gone = await conn.execute(
                f"DELETE FROM {SCHEMA}.match_alerts "
                "WHERE user_id = $1 AND match_id = $2", user_id, match_id)
        return gone.endswith("1")
    except Exception as e:
        logging.error(f"Напоминание не снято: {e}")
        return False


async def due_alerts(within_minutes: int = 10):
    """Напоминания, которым пора уйти: матч вот-вот начнётся"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT user_id, match_id, tour, title FROM {SCHEMA}.match_alerts
                    WHERE NOT sent AND starts_at IS NOT NULL
                      AND starts_at <= NOW() + ($1 || ' minutes')::interval
                      AND starts_at > NOW() - interval '3 hours'""",
                str(within_minutes))
        return [tuple(r) for r in rows]
    except Exception as e:
        logging.error(f"Напоминания недоступны: {e}")
        return []


async def mark_alert_sent(user_id: int, match_id: str) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {SCHEMA}.match_alerts SET sent = TRUE "
                "WHERE user_id = $1 AND match_id = $2", user_id, match_id)
        return True
    except Exception as e:
        logging.error(f"Отметка о доставке не сохранена: {e}")
        return False


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


# --- КЭШ ПЕРЕВОДОВ ---

async def get_translations(source: str, ids: list, field: str, lang: str) -> dict:
    """{id: перевод} для тех записей, что уже переводились"""
    if not ids:
        return {}
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT source_id, text FROM {SCHEMA}.translations "
                "WHERE source = $1 AND field = $2 AND lang = $3 AND source_id = ANY($4::int[])",
                source, field, lang, ids
            )
        return {r["source_id"]: r["text"] for r in rows}
    except Exception as e:
        logging.error(f"БД недоступна при чтении переводов: {e}")
        return {}


async def save_translation(source: str, source_id: int, field: str, lang: str, text: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.translations (source, source_id, field, lang, text) "
                "VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (source, source_id, field, lang) DO UPDATE SET text = EXCLUDED.text",
                source, source_id, field, lang, text
            )
    except Exception as e:
        logging.error(f"Не удалось сохранить перевод: {type(e).__name__}: {e}")


# --- ПУТЕШЕСТВИЯ: СТРАНА → ЛОКАЦИЯ → ПУБЛИКАЦИЯ ---

async def add_travel_place(country_ru, country_en, place, text_content,
                           photo_file_id, video_file_id, link_url, source_key) -> str:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            inserted = await conn.fetchval(
                f"INSERT INTO {SCHEMA}.travel_places "
                "(country_ru, country_en, place, text_content, photo_file_id, "
                "video_file_id, link_url, source_key) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
                "ON CONFLICT (source_key) DO NOTHING RETURNING id",
                country_ru, country_en, place, text_content,
                photo_file_id, video_file_id, link_url, source_key
            )
        return "added" if inserted else "duplicate"
    except Exception as e:
        logging.error(f"Не удалось сохранить локацию: {type(e).__name__}: {e}")
        return f"error:{type(e).__name__}: {e}"


async def add_spot(place_id: int, name: str, text: str, ordering: int,
                   address: str = None, url: str = None) -> str:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            got = await conn.fetchval(
                f"INSERT INTO {SCHEMA}.travel_spots "
                "(place_id, name, text_content, ordering, address, url) "
                "VALUES ($1, $2, $3, $4, $5, $6) "
                "ON CONFLICT (place_id, lower_name) DO NOTHING "
                "RETURNING id", place_id, name, text, ordering, address, url)
        return "added" if got else "duplicate"
    except Exception as e:
        logging.error(f"Достопримечательность не сохранена: {e}")
        return "error"


async def spots_of(place_id: int):
    """(id, название, текст, фото, был ли, номер поста) по порядку"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, name, text_content, photo_file_id, visited, channel_msg_id, "
                f"address, url FROM {SCHEMA}.travel_spots WHERE place_id = $1 "
                "ORDER BY ordering, id",
                place_id)
        return [tuple(r) for r in rows]
    except Exception as e:
        logging.error(f"Достопримечательности недоступны: {e}")
        return []


async def set_spot_visited(spot_id: int, visited: bool) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {SCHEMA}.travel_spots SET visited = $1 WHERE id = $2",
                visited, spot_id)
        return True
    except Exception as e:
        logging.error(f"Отметка о посещении не сохранена: {e}")
        return False


async def toggle_vote(section: str, item_id: int, user_id: int):
    """Ставит или снимает голос. Возвращает (поставлен ли, сколько всего).

    Повторное нажатие снимает: кнопка-счётчик, которую нельзя отжать,
    превращается в ловушку для случайного касания.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            gone = await conn.execute(
                f"DELETE FROM {SCHEMA}.post_votes "
                "WHERE section = $1 AND item_id = $2 AND user_id = $3",
                section, item_id, user_id)
            added = not gone.endswith("1")
            if added:
                await conn.execute(
                    f"INSERT INTO {SCHEMA}.post_votes (section, item_id, user_id) "
                    "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                    section, item_id, user_id)
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM {SCHEMA}.post_votes "
                "WHERE section = $1 AND item_id = $2", section, item_id)
        return added, total
    except Exception as e:
        logging.error(f"Голос не учтён: {e}")
        return False, 0


async def vote_count(section: str, item_id: int) -> int:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                f"SELECT COUNT(*) FROM {SCHEMA}.post_votes "
                "WHERE section = $1 AND item_id = $2", section, item_id) or 0
    except Exception as e:
        logging.error(f"Счётчик голосов недоступен: {e}")
        return 0


async def spots_without_photo(limit: int = 40):
    """(id, город, страна, название) мест без снимка — по маршруту"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT s.id, p.place, p.country_ru, s.name "
                f"FROM {SCHEMA}.travel_spots s "
                f"JOIN {SCHEMA}.travel_places p ON p.id = s.place_id "
                "WHERE s.photo_file_id IS NULL OR s.photo_file_id = '' "
                "ORDER BY p.country_ru, p.ordering, s.ordering LIMIT $1", limit)
        return [tuple(r) for r in rows]
    except Exception as e:
        logging.error(f"Места без фото недоступны: {e}")
        return []


async def set_spot_photo(spot_id: int, file_id: str) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {SCHEMA}.travel_spots SET photo_file_id = $1 WHERE id = $2",
                file_id, spot_id)
        return True
    except Exception as e:
        logging.error(f"Фото места не сохранено: {e}")
        return False


async def spot_place(spot_id: int):
    """Город, которому принадлежит достопримечательность"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                f"SELECT place_id FROM {SCHEMA}.travel_spots WHERE id = $1", spot_id)
    except Exception as e:
        logging.error(f"Город достопримечательности не найден: {e}")
        return None


async def spot_counts():
    """(всего, отмечено посещёнными, с фотографией)"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT COUNT(*) AS total, "
                f"COUNT(*) FILTER (WHERE visited) AS seen, "
                f"COUNT(*) FILTER (WHERE photo_file_id IS NOT NULL AND photo_file_id <> '') "
                f"AS shot FROM {SCHEMA}.travel_spots")
        return row["total"], row["seen"], row["shot"]
    except Exception as e:
        logging.error(f"Счётчики достопримечательностей недоступны: {e}")
        return 0, 0, 0


async def travel_all_ordered():
    """Все места маршрутом: (id, страна, место, текст, фото, номер поста)"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, country_ru, place, text_content, photo_file_id, "
                f"channel_msg_id FROM {SCHEMA}.travel_places "
                "ORDER BY country_ru, ordering, id")
        return [tuple(r) for r in rows]
    except Exception as e:
        logging.error(f"Список мест недоступен: {e}")
        return []


async def set_travel_msg(place_id: int, msg_id: int) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {SCHEMA}.travel_places SET channel_msg_id = $1 WHERE id = $2",
                msg_id, place_id)
        return True
    except Exception as e:
        logging.error(f"Номер поста не сохранён: {e}")
        return False


async def travel_country_places(country_ru: str):
    """(id, место, номер поста) всех мест страны — для удаления целиком"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, place, channel_msg_id FROM {SCHEMA}.travel_places "
                "WHERE lower(country_ru) = lower($1) ORDER BY ordering, id", country_ru)
        return [(r["id"], r["place"], r["channel_msg_id"]) for r in rows]
    except Exception as e:
        logging.error(f"Места страны недоступны: {e}")
        return []


async def delete_travel_country(country_ru: str) -> int:
    """Удаляет все места страны. Возвращает, сколько удалено."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            done = await conn.execute(
                f"DELETE FROM {SCHEMA}.travel_places WHERE lower(country_ru) = lower($1)",
                country_ru)
        return int(done.rsplit(" ", 1)[-1]) if done else 0
    except Exception as e:
        logging.error(f"Страна не удалена: {e}")
        return 0


async def travel_by_msg(msg_id: int):
    """(id, место) по номеру поста — чтобы правку в канале отнести к месту"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT id, place FROM {SCHEMA}.travel_places WHERE channel_msg_id = $1",
                msg_id)
        return (row["id"], row["place"]) if row else None
    except Exception as e:
        logging.error(f"Место по номеру поста не найдено: {e}")
        return None


async def set_travel_order(source_key: str, ordering: int) -> bool:
    """Ставит место на его место в маршруте. Отдельно от вставки затем,
    что вставка существующее не трогает, а порядок поправить надо."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {SCHEMA}.travel_places SET ordering = $1 WHERE source_key = $2",
                ordering, source_key)
        return True
    except Exception as e:
        logging.error(f"Порядок места не сохранён: {e}")
        return False


async def travel_without_photo(limit: int = 40):
    """(id, страна, место) мест без фотографии — по ним и идёт дозагрузка"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, country_ru, place FROM {SCHEMA}.travel_places "
                "WHERE photo_file_id IS NULL OR photo_file_id = '' "
                "ORDER BY country_ru, ordering, place LIMIT $1", limit)
        return [(r["id"], r["country_ru"], r["place"]) for r in rows]
    except Exception as e:
        logging.error(f"Список мест без фото недоступен: {e}")
        return []


async def set_travel_photo(place_id: int, file_id: str) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            done = await conn.execute(
                f"UPDATE {SCHEMA}.travel_places SET photo_file_id = $1 WHERE id = $2",
                file_id, place_id)
        return done.endswith("1")
    except Exception as e:
        logging.error(f"Фото места не сохранено: {e}")
        return False


async def set_travel_text(place_id: int, text: str) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            done = await conn.execute(
                f"UPDATE {SCHEMA}.travel_places SET text_content = $1 WHERE id = $2",
                text, place_id)
        return done.endswith("1")
    except Exception as e:
        logging.error(f"Текст места не сохранён: {e}")
        return False


async def get_travel_countries():
    """Страны со счётчиком локаций, по алфавиту"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT country_ru, country_en, COUNT(*) AS n FROM {SCHEMA}.travel_places "
                "GROUP BY country_ru, country_en ORDER BY lower(country_ru)"
            )
        return [(r["country_ru"], r["country_en"], r["n"]) for r in rows]
    except Exception as e:
        logging.error(f"БД недоступна при чтении стран: {e}")
        return []


async def get_travel_places(country_ru: str):
    """Локации страны: (id, место)"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, place FROM {SCHEMA}.travel_places "
                "WHERE country_ru = $1 ORDER BY ordering, lower(place), id", country_ru
            )
        return [(r["id"], r["place"]) for r in rows]
    except Exception as e:
        logging.error(f"БД недоступна при чтении локаций: {e}")
        return []


async def get_travel_place(place_id: int):
    """(country_ru, place, text, photo, video, link)"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT country_ru, place, text_content, photo_file_id, video_file_id, "
                f"link_url FROM {SCHEMA}.travel_places WHERE id = $1", place_id
            )
        if not row:
            return None
        return (row["country_ru"], row["place"], row["text_content"],
                row["photo_file_id"], row["video_file_id"], row["link_url"])
    except Exception as e:
        logging.error(f"БД недоступна при чтении локации: {e}")
        return None


async def count_travel_places() -> int:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA}.travel_places") or 0
    except Exception as e:
        logging.error(f"БД недоступна при подсчёте локаций: {e}")
        return 0


async def update_travel_country(place_id: int, country_ru: str, country_en: str) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {SCHEMA}.travel_places SET country_ru = $1, country_en = $2 "
                "WHERE id = $3", country_ru, country_en, place_id)
        return True
    except Exception as e:
        logging.error(f"Не удалось сменить страну: {type(e).__name__}: {e}")
        return False


# --- ПОСЕТИТЕЛИ ---

async def record_visitor(user_id: int, username, full_name, tg_language):
    """Отмечает визит: имя обновляем при каждом заходе, счётчик растёт.

    Имя и ник в Telegram меняются, поэтому храним последнее известное, а не
    первое: иначе через полгода список будет из устаревших подписей.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"""INSERT INTO {SCHEMA}.visitors
                    (user_id, username, full_name, tg_language, actions)
                    VALUES ($1, $2, $3, $4, 1)
                    ON CONFLICT (user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        full_name = EXCLUDED.full_name,
                        tg_language = EXCLUDED.tg_language,
                        last_seen = CURRENT_TIMESTAMP,
                        actions = visitors.actions + 1""",
                user_id, username, full_name, tg_language
            )
    except Exception as e:
        logging.error(f"Не удалось записать посетителя: {type(e).__name__}: {e}")


async def count_visitors() -> int:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA}.visitors") or 0
    except Exception as e:
        logging.error(f"БД недоступна при подсчёте посетителей: {e}")
        return 0


async def get_visitors(limit: int = 10, offset: int = 0):
    """Посетители, недавние первыми"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT user_id, username, full_name, tg_language, first_seen, "
                f"last_seen, actions FROM {SCHEMA}.visitors "
                "ORDER BY last_seen DESC LIMIT $1 OFFSET $2", limit, offset)
        return [dict(r) for r in rows]
    except Exception as e:
        logging.error(f"БД недоступна при чтении посетителей: {e}")
        return []


async def get_unnamed_visitors(limit: int = 50):
    """id тех, у кого имя не заполнено — они восстановлены из журнала кликов"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT user_id FROM {SCHEMA}.visitors "
                "WHERE full_name IS NULL OR full_name = '' "
                "ORDER BY last_seen DESC LIMIT $1", limit)
        return [r["user_id"] for r in rows]
    except Exception as e:
        logging.error(f"БД недоступна при чтении безымянных посетителей: {e}")
        return []


async def update_visitor_identity(user_id: int, username, full_name) -> bool:
    """Дописывает имя, не трогая счётчик действий и даты"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {SCHEMA}.visitors SET username = $2, full_name = $3 "
                "WHERE user_id = $1", user_id, username, full_name)
        return True
    except Exception as e:
        logging.error(f"Не удалось дописать имя посетителя: {type(e).__name__}: {e}")
        return False


async def forget_visitor(user_id: int) -> bool:
    """Полное удаление посетителя — на случай, если человек попросит"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"DELETE FROM {SCHEMA}.visitors WHERE user_id = $1", user_id)
            await conn.execute(f"DELETE FROM {SCHEMA}.user_logs WHERE user_id = $1", user_id)
        return True
    except Exception as e:
        logging.error(f"Не удалось удалить посетителя: {type(e).__name__}: {e}")
        return False


# --- ДАЙДЖЕСТ-КАНАЛ ---

# Откуда брать материал для каждого раздела: таблица, поле идентификатора и
# условие отбора. Держим одним местом, чтобы добавление раздела было строкой.
DIGEST_SOURCES = {
    "genetics": ("articles", "section = 'genetics'"),
    "recipes": ("recipes", "TRUE"),
    "travel": ("travel_places", "TRUE"),
    "books": ("books", "TRUE"),
}


async def next_for_digest(section: str):
    """id самого раннего ещё не опубликованного материала раздела.

    Идём от старых к новым: канал пустой, и архив логичнее выкладывать
    по порядку, а не начинать с последнего поста.
    """
    source = DIGEST_SOURCES.get(section)
    if not source:
        return None
    table, condition = source
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                f"""SELECT id FROM {SCHEMA}.{table}
                    WHERE {condition} AND id NOT IN (
                        SELECT item_id FROM {SCHEMA}.digest_log WHERE section = $1)
                    ORDER BY id LIMIT 1""", section)
    except Exception as e:
        logging.error(f"БД недоступна при выборе материала для дайджеста: {e}")
        return None


async def oldest_published(section: str, min_days: int = 30):
    """id материала, вышедшего дольше всего назад — кандидат на напоминание.

    Порог в днях обязателен: повтор через неделю читается как сбой, а через
    месяц — как «а помните».
    """
    source = DIGEST_SOURCES.get(section)
    if not source:
        return None
    table, condition = source
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                f"""SELECT l.item_id FROM {SCHEMA}.digest_log l
                    JOIN {SCHEMA}.{table} t ON t.id = l.item_id
                    WHERE l.section = $1 AND {condition}
                      AND l.published_at < NOW() - ($2 || ' days')::interval
                    ORDER BY l.published_at LIMIT 1""", section, str(min_days))
    except Exception as e:
        logging.error(f"Кандидат на повтор не найден: {e}")
        return None


async def mark_repeated(section: str, item_id: int, message_id: int = None) -> bool:
    """Отмечает повторный выход: материал уходит в конец очереди повторов"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {SCHEMA}.digest_log SET published_at = CURRENT_TIMESTAMP, "
                "times = times + 1, message_id = COALESCE($3, message_id) "
                "WHERE section = $1 AND item_id = $2", section, item_id, message_id)
        return True
    except Exception as e:
        logging.error(f"Повтор не отмечен: {e}")
        return False


async def reset_digest(with_channels: bool = False) -> dict:
    """Забывает всё, что канал уже публиковал, и начинает с чистого листа.

    Стирается история публикаций и отметки слотов — сам материал остаётся.
    with_channels дополнительно забывает номера постов в справочниках:
    это нужно, только если их каналы тоже вычищены, иначе бот потеряет
    связь с живыми постами и выложит их заново.
    """
    out = {}
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            done = await conn.execute(f"DELETE FROM {SCHEMA}.digest_log")
            out["публикаций забыто"] = int(done.rsplit(" ", 1)[-1] or 0)

            done = await conn.execute(
                f"DELETE FROM {SCHEMA}.settings WHERE key LIKE 'digest_slot_%' "
                "OR key LIKE 'digest_fail_%' "
                "OR key IN ('digest_sport_n', 'digest_last_section', "
                "'digest_last_at', 'digest_last_error')")
            out["служебных отметок"] = int(done.rsplit(" ", 1)[-1] or 0)

            if with_channels:
                for table in ("travel_places", "books"):
                    done = await conn.execute(
                        f"UPDATE {SCHEMA}.{table} SET channel_msg_id = NULL "
                        "WHERE channel_msg_id IS NOT NULL")
                    out[f"номеров постов ({table})"] = int(done.rsplit(" ", 1)[-1] or 0)
        _settings_cache.clear()
        return out
    except Exception as e:
        logging.error(f"Сброс не выполнен: {e}")
        return {"ошибка": str(e)[:120]}


async def next_candidates(section: str, limit: int = 12):
    """Несколько ближайших неопубликованных, а не один.

    Публикатору нужен выбор: если первый не проходит проверку — длинный
    текст, нет фотографии, — он не публикуется, а очередь идёт дальше.
    С одним кандидатом раздел вставал бы на нём насмерть.
    """
    source = DIGEST_SOURCES.get(section)
    if not source:
        return []
    table, condition = source
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT id FROM {SCHEMA}.{table}
                    WHERE {condition} AND id NOT IN (
                        SELECT item_id FROM {SCHEMA}.digest_log WHERE section = $1)
                    ORDER BY id LIMIT $2""", section, limit)
        return [r["id"] for r in rows]
    except Exception as e:
        logging.error(f"Кандидаты для дайджеста недоступны: {e}")
        return []


async def mark_published(section: str, item_id: int, message_id: int = None) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.digest_log (section, item_id, message_id) "
                "VALUES ($1, $2, $3) ON CONFLICT (section, item_id) DO NOTHING",
                section, item_id, message_id)
        return True
    except Exception as e:
        logging.error(f"Не удалось отметить публикацию: {type(e).__name__}: {e}")
        return False


async def digest_stats():
    """Сколько материалов опубликовано и сколько осталось по каждому разделу"""
    out = {}
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            for section, (table, condition) in DIGEST_SOURCES.items():
                total = await conn.fetchval(
                    f"SELECT COUNT(*) FROM {SCHEMA}.{table} WHERE {condition}") or 0
                done = await conn.fetchval(
                    f"SELECT COUNT(*) FROM {SCHEMA}.digest_log WHERE section = $1",
                    section) or 0
                out[section] = {"total": total, "published": done}
    except Exception as e:
        logging.error(f"БД недоступна при сводке дайджеста: {e}")
    return out


# --- ЖУРНАЛ ОПЕРАЦИЙ (общий для всех ботов) ---

async def add_transaction(source: str, kind: str, asset: str, asset_kind: str,
                          amount, amount_ils=None, rate_ils=None, rate_at=None,
                          category: str = None, note: str = None,
                          external_id: str = None, occurred_at=None,
                          owner: str = "self") -> str:
    """Записывает операцию. 'added' | 'duplicate' | 'error:<причина>'.

    external_id — идентификатор со стороны платёжной системы (charge_id у
    Telegram, хеш у крипты). По нему повторная обработка одного и того же
    платежа не задваивает запись.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            inserted = await conn.fetchval(
                f"""INSERT INTO {FINANCE_SCHEMA}.transactions
                    (owner, source, kind, asset, asset_kind, amount, amount_ils,
                     rate_ils, rate_at, category, note, external_id, occurred_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                            COALESCE($13, CURRENT_TIMESTAMP))
                    ON CONFLICT (source, external_id) DO NOTHING RETURNING id""",
                owner, source, kind, asset, asset_kind, amount, amount_ils,
                rate_ils, rate_at, category, note, external_id, occurred_at
            )
        return "added" if inserted else "duplicate"
    except Exception as e:
        logging.error(f"Не удалось записать операцию: {type(e).__name__}: {e}")
        return f"error:{type(e).__name__}: {e}"


async def get_transactions(limit: int = 20, offset: int = 0, since=None):
    """Операции, свежие первыми"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if since:
                rows = await conn.fetch(
                    f"SELECT * FROM {FINANCE_SCHEMA}.transactions "
                    "WHERE occurred_at >= $1 ORDER BY occurred_at DESC "
                    "LIMIT $2 OFFSET $3", since, limit, offset)
            else:
                rows = await conn.fetch(
                    f"SELECT * FROM {FINANCE_SCHEMA}.transactions "
                    "ORDER BY occurred_at DESC LIMIT $1 OFFSET $2", limit, offset)
        return [dict(r) for r in rows]
    except Exception as e:
        logging.error(f"БД недоступна при чтении операций: {e}")
        return []


async def turnover(year: int) -> dict:
    """Оборот за год: сумма в шекелях, сколько операций и сколько без пересчёта.

    Непересчитанные считаем отдельно — иначе цифра оборота выглядела бы
    достоверной, будучи неполной.
    """
    empty = {"income_ils": 0.0, "expense_ils": 0.0, "count": 0, "unconverted": 0}
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""SELECT
                    COALESCE(SUM(amount_ils) FILTER (WHERE kind = 'income'), 0) AS income,
                    COALESCE(SUM(amount_ils) FILTER (WHERE kind = 'expense'), 0) AS expense,
                    COUNT(*) AS cnt,
                    COUNT(*) FILTER (WHERE amount_ils IS NULL) AS unconverted
                    FROM {FINANCE_SCHEMA}.transactions
                    WHERE EXTRACT(YEAR FROM occurred_at) = $1""", year)
    except Exception as e:
        logging.error(f"БД недоступна при подсчёте оборота: {e}")
        return empty

    if not row:
        return empty
    return {"income_ils": float(row["income"]), "expense_ils": float(row["expense"]),
            "count": row["cnt"], "unconverted": row["unconverted"]}


async def totals_by_asset(year: int):
    """Сколько накоплено в каждом активе — звёзды и крипта живут своей жизнью
    и в шекелях появляются только при выводе."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT asset, asset_kind,
                    SUM(amount) FILTER (WHERE kind = 'income') AS income,
                    SUM(amount) FILTER (WHERE kind = 'withdrawal') AS withdrawn
                    FROM {FINANCE_SCHEMA}.transactions
                    WHERE EXTRACT(YEAR FROM occurred_at) = $1
                    GROUP BY asset, asset_kind ORDER BY asset_kind, asset""", year)
        return [dict(r) for r in rows]
    except Exception as e:
        logging.error(f"БД недоступна при сводке по активам: {e}")
        return []


# --- НАСТРОЙКИ, МЕНЯЕМЫЕ ИЗ БОТА ---

async def save_cartoon(user_id: int, story: str, board_json: str):
    """Сохраняет раскадровку и возвращает её номер — он же адрес просмотра"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                f"INSERT INTO {SCHEMA}.cartoons (user_id, story, board) "
                "VALUES ($1, $2, $3) RETURNING id", user_id, story, board_json)
    except Exception as e:
        logging.error(f"Мультфильм не сохранён: {e}")
        return None


MAX_OWN_CHARACTERS = 8      # больше не помещается в подсказку раскадровщику


async def add_own_character(user_id: int, name: str, kind: str, data: bytes,
                            mime: str) -> str:
    """Сохраняет присланный рисунок. «занято», если имя уже есть у автора."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                f"SELECT COUNT(*) FROM {SCHEMA}.own_characters WHERE user_id = $1", user_id)
            if count >= MAX_OWN_CHARACTERS:
                return "лимит"
            done = await conn.execute(
                f"INSERT INTO {SCHEMA}.own_characters (user_id, token, name, kind, mime, data) "
                "VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (user_id, lower_name) DO NOTHING",
                user_id, secrets.token_urlsafe(16), name, kind, mime, data)
            return "ok" if done.endswith("1") else "занято"
    except Exception as e:
        logging.error(f"Персонаж не сохранён: {e}")
        return "ошибка"


async def own_characters(user_id: int):
    """[(id, имя, вид)] персонажей автора — без самих картинок"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, name, kind, token FROM {SCHEMA}.own_characters "
                "WHERE user_id = $1 ORDER BY id", user_id)
        return [(r["id"], r["name"], r["kind"], r["token"]) for r in rows]
    except Exception as e:
        logging.error(f"Персонажи недоступны: {e}")
        return []


async def own_character_by_token(token: str):
    """(байты, тип) по случайному адресу — так картинку отдаёт страница"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT data, mime FROM {SCHEMA}.own_characters WHERE token = $1", token)
        return (row["data"], row["mime"]) if row else None
    except Exception as e:
        logging.error(f"Рисунок персонажа не читается: {e}")
        return None


async def own_character_image(char_id: int, user_id: int = None):
    """(байты, тип) рисунка. user_id ограничивает выдачу автором."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if user_id is None:
                row = await conn.fetchrow(
                    f"SELECT data, mime FROM {SCHEMA}.own_characters WHERE id = $1", char_id)
            else:
                row = await conn.fetchrow(
                    f"SELECT data, mime FROM {SCHEMA}.own_characters "
                    "WHERE id = $1 AND user_id = $2", char_id, user_id)
        return (row["data"], row["mime"]) if row else None
    except Exception as e:
        logging.error(f"Рисунок персонажа не читается: {e}")
        return None


async def delete_own_character(char_id: int, user_id: int) -> bool:
    """Удаляет — только собственного: чужой не тронуть даже зная номер"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            done = await conn.execute(
                f"DELETE FROM {SCHEMA}.own_characters WHERE id = $1 AND user_id = $2",
                char_id, user_id)
        return done.endswith("1")
    except Exception as e:
        logging.error(f"Персонаж не удалён: {e}")
        return False


async def save_cartoon_frames(cartoon_id: int, frames) -> int:
    """Кладёт нарисованные кадры. frames — [(номер сцены, байты, тип)]"""
    if not frames:
        return 0
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.executemany(
                f"INSERT INTO {SCHEMA}.cartoon_frames (cartoon_id, scene_index, mime, data) "
                "VALUES ($1, $2, $3, $4) ON CONFLICT (cartoon_id, scene_index) DO NOTHING",
                [(cartoon_id, i, mime, data) for i, data, mime in frames])
        return len(frames)
    except Exception as e:
        logging.error(f"Кадры не сохранены: {e}")
        return 0


async def cartoon_frame(cartoon_id: int, scene_index: int):
    """(байты, тип) одного кадра либо None"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT data, mime FROM {SCHEMA}.cartoon_frames "
                "WHERE cartoon_id = $1 AND scene_index = $2", cartoon_id, scene_index)
        return (row["data"], row["mime"]) if row else None
    except Exception as e:
        logging.error(f"Кадр не читается: {e}")
        return None


async def cartoon_frame_list(cartoon_id: int):
    """Номера сцен, для которых кадр нарисован"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT scene_index FROM {SCHEMA}.cartoon_frames "
                "WHERE cartoon_id = $1 ORDER BY scene_index", cartoon_id)
        return [r["scene_index"] for r in rows]
    except Exception as e:
        logging.error(f"Список кадров недоступен: {e}")
        return []


async def get_cartoon(cartoon_id: int):
    """Раскадровка в виде строки JSON либо None"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                f"SELECT board FROM {SCHEMA}.cartoons WHERE id = $1", cartoon_id)
    except Exception as e:
        logging.error(f"Мультфильм не читается: {e}")
        return None


async def save_race_score(user_id: int, name: str, score: int):
    """Сохраняет результат и возвращает (место в таблице, личный рекорд).

    Храним лучший результат игрока, а не каждый заезд: таблица рекордов из
    двадцати строк одного упорного человека никому не интересна.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            best = await conn.fetchval(
                f"""INSERT INTO {SCHEMA}.race_scores (user_id, name, best, played)
                    VALUES ($1, $2, $3, 1)
                    ON CONFLICT (user_id) DO UPDATE
                    SET best = GREATEST(race_scores.best, EXCLUDED.best),
                        name = EXCLUDED.name,
                        played = race_scores.played + 1,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING best""",
                user_id, name, score)
            place = await conn.fetchval(
                f"SELECT COUNT(*) + 1 FROM {SCHEMA}.race_scores WHERE best > $1", best)
        return place, best
    except Exception as e:
        logging.error(f"Не удалось сохранить результат гонки: {e}")
        return None, score


async def race_top(limit: int = 10):
    """(id, имя, рекорд) лучших игроков"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT user_id, name, best FROM {SCHEMA}.race_scores "
                "ORDER BY best DESC, updated_at LIMIT $1", limit)
        return [(r["user_id"], r["name"], r["best"]) for r in rows]
    except Exception as e:
        logging.error(f"Таблица рекордов недоступна: {e}")
        return []


async def all_user_ids() -> list[tuple[int, str]]:
    """(id, язык) всех, кто когда-либо запускал бота — для разовой рассылки.

    Язык нужен вместе с id: рассылка на четырёх языках, и добирать его
    отдельным запросом на каждого адресата было бы разорительно.
    """
    pool = await get_pool()
    if not pool:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT user_id, COALESCE(lang, 'ru') FROM {SCHEMA}.users ORDER BY user_id")
        return [(r[0], r[1]) for r in rows]
    except Exception as e:
        logging.error(f"Не удалось получить список пользователей: {e}")
        return []


_settings_cache: dict[str, str] = {}


async def get_setting(key: str, default: str = None):
    """Значение из базы; при недоступности базы — последнее известное.

    Кэш обязателен: пароли спрашиваются на каждом входе в закрытый раздел,
    а лишний поход в базу на каждое нажатие бот заметно замедляет.
    """
    if key in _settings_cache:
        return _settings_cache[key]
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            value = await conn.fetchval(
                f"SELECT value FROM {SCHEMA}.settings WHERE key = $1", key)
        if value is not None:
            _settings_cache[key] = value
            return value
    except Exception as e:
        logging.error(f"БД недоступна при чтении настройки {key}: {e}")
    return default


async def set_setting(key: str, value: str) -> bool:
    _settings_cache[key] = value
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.settings (key, value) VALUES ($1, $2) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", key, value)
        return True
    except Exception as e:
        logging.error(f"Не удалось сохранить настройку {key}: {type(e).__name__}: {e}")
        return False


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
    """Страница заголовков в порядке публикации в канале.

    Сортируем по номеру исходного сообщения, зашитому в source_key
    («<чат>:<message_id>»), а не по id записи: порядок пересылки может быть
    любым, а номера сообщений в канале всегда идут по возрастанию. Материалы
    без source_key уходят в конец и упорядочиваются по id.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, title FROM {SCHEMA}.articles WHERE section = $1 "
                "ORDER BY CASE WHEN source_key ~ ':[0-9]+$' "
                "THEN split_part(source_key, ':', 2)::bigint END "
                "NULLS LAST, id LIMIT $2 OFFSET $3",
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


async def update_article_text(article_id: int, text_content: str) -> bool:
    """Заменяет текст материала — им правят главы, импортированные неполностью"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {SCHEMA}.articles SET text_content = $1 WHERE id = $2",
                text_content, article_id)
        return True
    except Exception as e:
        logging.error(f"Не удалось изменить текст материала: {type(e).__name__}: {e}")
        return False


async def clear_article_media(article_id: int) -> bool:
    """Убирает картинку и видео — глава-иллюстрация превращается в обычный пост"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {SCHEMA}.articles SET photo_file_id = NULL, video_file_id = NULL "
                "WHERE id = $1", article_id)
        return True
    except Exception as e:
        logging.error(f"Не удалось убрать медиа: {type(e).__name__}: {e}")
        return False


async def delete_article(article_id: int) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"DELETE FROM {SCHEMA}.articles WHERE id = $1", article_id)
        return True
    except Exception as e:
        logging.error(f"Не удалось удалить материал: {type(e).__name__}: {e}")
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
    """Баллы предыдущего среза и его дата: (дата, {страна: балл}).

    Сначала ищем срез недельной давности. Если истории ещё нет — берём самый
    свежий день до текущего: иначе первую неделю после запуска стрелки динамики
    не с чем сравнивать и они вообще не появляются.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            target = await conn.fetchval(
                f"SELECT MAX(day) FROM {SCHEMA}.country_index "
                "WHERE day <= $1::date - $2::int", day, days_back
            )
            if not target:
                target = await conn.fetchval(
                    f"SELECT MAX(day) FROM {SCHEMA}.country_index WHERE day < $1", day
                )
            if not target:
                return None, {}
            rows = await conn.fetch(
                f"SELECT country, score FROM {SCHEMA}.country_index WHERE day = $1", target
            )
        return target, {r["country"]: r["score"] for r in rows}
    except Exception as e:
        logging.error(f"БД недоступна при чтении истории индекса: {e}")
        return None, {}


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

async def add_book_unique(category: str, text: str) -> str:
    """Добавляет книгу, не задваивая: ключ — первая строка с автором
    и названием. Повторный запуск списка обновляет, а не плодит."""
    head = (text or "").strip().split("\n")[0][:200]
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                f"SELECT id FROM {SCHEMA}.books WHERE text_content LIKE $1", head + "%")
            if exists:
                await conn.execute(
                    f"UPDATE {SCHEMA}.books SET text_content = $1, category = $2 "
                    "WHERE id = $3", text, category, exists)
                return "updated"
            await conn.execute(
                f"INSERT INTO {SCHEMA}.books (category, text_content) VALUES ($1, $2)",
                category, text)
        return "added"
    except Exception as e:
        logging.error(f"Книга не сохранена: {e}")
        return "error"


async def book_counts() -> dict:
    """Сколько книг на каждой полке"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT category, COUNT(*) AS n FROM {SCHEMA}.books GROUP BY category")
        return {r["category"]: r["n"] for r in rows}
    except Exception as e:
        logging.error(f"Счётчики книг недоступны: {e}")
        return {}


async def set_book_link(book_id: int, url: str) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            done = await conn.execute(
                f"UPDATE {SCHEMA}.books SET buy_url = $1 WHERE id = $2",
                url or None, book_id)
        return done.endswith("1")
    except Exception as e:
        logging.error(f"Ссылка на книгу не сохранена: {e}")
        return False


async def books_with_link():
    """(id, название, ссылка) книг, у которых ссылка уже есть"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, text_content, buy_url FROM {SCHEMA}.books "
                "WHERE buy_url IS NOT NULL AND buy_url <> '' ORDER BY id")
        return [(r["id"], (r["text_content"] or "").split("\n")[0][:70], r["buy_url"])
                for r in rows]
    except Exception as e:
        logging.error(f"Книги со ссылками недоступны: {e}")
        return []


async def get_book_link_by_id(book_id: int):
    """Ссылка книги по её номеру — так её знает библиотека бота"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                f"SELECT buy_url FROM {SCHEMA}.books WHERE id = $1", book_id)
    except Exception as e:
        logging.error(f"Ссылка книги недоступна: {e}")
        return None


async def get_book_link(title: str):
    """Ссылка книги по её первой строке — так её знает публикатор"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                f"SELECT buy_url FROM {SCHEMA}.books "
                "WHERE buy_url IS NOT NULL AND text_content LIKE $1 LIMIT 1",
                f"{title[:60]}%")
    except Exception as e:
        logging.error(f"Ссылка книги недоступна: {e}")
        return None


async def books_without_link(category: str = None):
    """(id, название) книг, у которых ссылки ещё нет"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if category:
                rows = await conn.fetch(
                    f"SELECT id, text_content FROM {SCHEMA}.books "
                    "WHERE category = $1 AND (buy_url IS NULL OR buy_url = '') "
                    "ORDER BY id", category)
            else:
                rows = await conn.fetch(
                    f"SELECT id, text_content FROM {SCHEMA}.books "
                    "WHERE buy_url IS NULL OR buy_url = '' ORDER BY id")
        return [(r["id"], (r["text_content"] or "").split("\n")[0][:70]) for r in rows]
    except Exception as e:
        logging.error(f"Книги без ссылок недоступны: {e}")
        return []


async def books_link_stats() -> dict:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT COUNT(*) AS total, "
                f"COUNT(*) FILTER (WHERE buy_url IS NOT NULL AND buy_url <> '') AS done "
                f"FROM {SCHEMA}.books")
        return dict(row) if row else {"total": 0, "done": 0}
    except Exception as e:
        logging.error(f"Счёт ссылок недоступен: {e}")
        return {"total": 0, "done": 0}


# ---------------------------------------------------------------------
# ТЕННИС: РЕЙТИНГ И ИМЕНА
# ---------------------------------------------------------------------

async def save_ranking(tour: str, rows) -> int:
    """Переписать рейтинг тура целиком. rows: (место, имя, страна)"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    f"DELETE FROM {SCHEMA}.tennis_ranking WHERE tour = $1", tour)
                await conn.executemany(
                    f"INSERT INTO {SCHEMA}.tennis_ranking (tour, place, name, country) "
                    "VALUES ($1, $2, $3, $4)",
                    [(tour, place, name, country) for place, name, country in rows])
        return len(rows)
    except Exception as e:
        logging.error(f"Рейтинг не сохранён: {e}")
        return 0


async def ranking_names(limit: int = 25):
    """Имена из первой сотни мест обоих туров"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT name, country FROM {SCHEMA}.tennis_ranking "
                "WHERE place <= $1", limit)
        return [(r["name"], r["country"]) for r in rows]
    except Exception as e:
        logging.error(f"Рейтинг недоступен: {e}")
        return []


async def ranking_top(tour: str, limit: int = 20):
    """(место, имя) — для показа админу"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT place, name FROM {SCHEMA}.tennis_ranking "
                "WHERE tour = $1 AND place <= $2 ORDER BY place", tour, limit)
        return [(r["place"], r["name"]) for r in rows]
    except Exception as e:
        logging.error(f"Рейтинг недоступен: {e}")
        return []


async def ranking_updated():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                f"SELECT MAX(updated_at) FROM {SCHEMA}.tennis_ranking")
    except Exception as e:
        logging.error(f"Дата рейтинга недоступна: {e}")
        return None


async def set_player_name(name_en: str, name_ru: str) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.player_names (name_en, name_ru) "
                "VALUES ($1, $2) ON CONFLICT (name_en) DO UPDATE "
                "SET name_ru = EXCLUDED.name_ru", name_en.strip(), name_ru.strip())
        return True
    except Exception as e:
        logging.error(f"Имя игрока не сохранено: {e}")
        return False


async def player_names():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT name_en, name_ru FROM {SCHEMA}.player_names")
        return {r["name_en"]: r["name_ru"] for r in rows}
    except Exception as e:
        logging.error(f"Свои имена недоступны: {e}")
        return {}


async def book_titles(category: str):
    """(id, автор и название) книг полки — для списка, по которому кликают"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, text_content FROM {SCHEMA}.books "
                "WHERE category = $1 ORDER BY id", category)
        return [(r["id"], (r["text_content"] or "").split("\n")[0][:60]) for r in rows]
    except Exception as e:
        logging.error(f"Названия книг недоступны: {e}")
        return []


async def books_all():
    """(id, категория, текст, обложка, номер поста) — для выкладки в канал"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, category, text_content, cover_file_id, channel_msg_id "
                f"FROM {SCHEMA}.books ORDER BY category, id")
        return [tuple(r) for r in rows]
    except Exception as e:
        logging.error(f"Книги недоступны: {e}")
        return []


async def set_book_msg(book_id: int, msg_id: int) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {SCHEMA}.books SET channel_msg_id = $1 WHERE id = $2",
                msg_id, book_id)
        return True
    except Exception as e:
        logging.error(f"Номер поста книги не сохранён: {e}")
        return False


async def books_without_cover(limit: int = 40):
    """(id, первая строка) книг без обложки"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, text_content FROM {SCHEMA}.books "
                "WHERE cover_file_id IS NULL OR cover_file_id = '' ORDER BY id LIMIT $1",
                limit)
        return [(r["id"], (r["text_content"] or "").split("\n")[0][:60]) for r in rows]
    except Exception as e:
        logging.error(f"Книги без обложки недоступны: {e}")
        return []


async def set_book_cover(book_id: int, file_id: str) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {SCHEMA}.books SET cover_file_id = $1 WHERE id = $2",
                file_id, book_id)
        return True
    except Exception as e:
        logging.error(f"Обложка не сохранена: {e}")
        return False


async def get_book_by_id(book_id: int):
    """(текст, обложка) книги — для публикации в канал"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT text_content, cover_file_id FROM {SCHEMA}.books WHERE id = $1",
                book_id)
        return (row["text_content"], row["cover_file_id"]) if row else None
    except Exception as e:
        logging.error(f"Книга не читается: {e}")
        return None


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


async def save_puzzle_answer(user_id: int, puzzle_id: int, is_correct: bool,
                             choice: int = None):
    """Фиксирует один ответ пользователя"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.puzzle_answers "
                "(user_id, puzzle_id, is_correct, choice) "
                "VALUES ($1, $2, $3, $4)",
                user_id, puzzle_id, is_correct, choice
            )
    except Exception as e:
        logging.error(f"БД недоступна при записи ответа на головоломку: {e}")


# ---------------------------------------------------------------------
# ЗАДАЧА ДНЯ В КАНАЛЕ
# ---------------------------------------------------------------------

async def mark_puzzle_published(puzzle_id: int, chat_id: int, message_id: int):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.puzzle_posts (puzzle_id, chat_id, message_id) "
                "VALUES ($1, $2, $3)", puzzle_id, chat_id, message_id)
    except Exception as e:
        logging.error(f"БД недоступна при отметке задачи дня: {e}")


async def published_puzzle_ids() -> set:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT DISTINCT puzzle_id FROM {SCHEMA}.puzzle_posts")
        return {r["puzzle_id"] for r in rows}
    except Exception as e:
        logging.error(f"БД недоступна при чтении вышедших задач: {e}")
        return set()


async def oldest_published_puzzle():
    """Задача, которая выходила давнее всех — её и повторяем"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                f"SELECT puzzle_id FROM {SCHEMA}.puzzle_posts "
                "GROUP BY puzzle_id ORDER BY MAX(published_at) LIMIT 1")
    except Exception as e:
        logging.error(f"БД недоступна при поиске давней задачи: {e}")
        return None


async def puzzle_answer_of(user_id: int, puzzle_id: int):
    """1, если человек уже отвечал на эту задачу, иначе None"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                f"SELECT 1 FROM {SCHEMA}.puzzle_answers "
                "WHERE user_id = $1 AND puzzle_id = $2 LIMIT 1",
                user_id, puzzle_id)
    except Exception as e:
        logging.error(f"БД недоступна при проверке ответа: {e}")
        return None


async def puzzle_choice_counts(puzzle_id: int) -> dict:
    """Сколько человек выбрало каждый вариант — для счётчика на кнопке"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT choice, COUNT(*) AS n FROM {SCHEMA}.puzzle_answers "
                "WHERE puzzle_id = $1 AND choice IS NOT NULL GROUP BY choice",
                puzzle_id)
        return {r["choice"]: r["n"] for r in rows}
    except Exception as e:
        logging.error(f"БД недоступна при счёте вариантов: {e}")
        return {}


async def last_puzzle_result():
    """Итог последней вышедшей задачи: сколько ответов и сколько верных"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(f"""
                SELECT p.puzzle_id,
                       COUNT(a.id) AS answers,
                       COUNT(a.id) FILTER (WHERE a.is_correct) AS correct
                FROM {SCHEMA}.puzzle_posts p
                LEFT JOIN {SCHEMA}.puzzle_answers a
                       ON a.puzzle_id = p.puzzle_id
                      AND a.answered_at >= p.published_at
                GROUP BY p.id, p.puzzle_id
                ORDER BY p.published_at DESC LIMIT 1""")
        return dict(row) if row else None
    except Exception as e:
        logging.error(f"БД недоступна при чтении итога задачи: {e}")
        return None


async def puzzle_channel_stats(limit: int = 12):
    """По каждой вышедшей задаче: вопрос, дата, ответы, верные"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT p.published_at, q.question,
                       COUNT(a.id) AS answers,
                       COUNT(a.id) FILTER (WHERE a.is_correct) AS correct
                FROM {SCHEMA}.puzzle_posts p
                JOIN {SCHEMA}.puzzles q ON q.id = p.puzzle_id
                LEFT JOIN {SCHEMA}.puzzle_answers a
                       ON a.puzzle_id = p.puzzle_id
                      AND a.answered_at >= p.published_at
                GROUP BY p.id, p.published_at, q.question
                ORDER BY p.published_at DESC LIMIT $1""", limit)
        return [dict(r) for r in rows]
    except Exception as e:
        logging.error(f"БД недоступна при статистике задач: {e}")
        return []


async def puzzle_people() -> dict:
    """Сколько всего людей отвечало и сколько возвращалось не раз"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(f"""
                SELECT COUNT(*) AS people,
                       COUNT(*) FILTER (WHERE n > 1) AS repeat
                FROM (SELECT user_id, COUNT(DISTINCT puzzle_id) AS n
                      FROM {SCHEMA}.puzzle_answers GROUP BY user_id) t""")
        return dict(row) if row else {"people": 0, "repeat": 0}
    except Exception as e:
        logging.error(f"БД недоступна при подсчёте участников: {e}")
        return {"people": 0, "repeat": 0}


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


# --- ОБЩИЙ КАЛЕНДАРЬ ---
#
# Здесь только чтение и запись строк; разворачивание серии в отдельные даты
# и поиск пересечений живут в planner.py — это правила показа, а не хранения.

async def plan_add(space_id: int, title: str, description: str, starts_at,
                   duration_min: int, repeat_rule: str, repeat_until,
                   user_id: int, user_name: str):
    """Заводит событие в конкретном календаре и возвращает его номер"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                f"INSERT INTO {SCHEMA}.plan_events "
                "(space_id, title, description, starts_at, duration_min, repeat_rule, "
                " repeat_until, created_by, created_by_name) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id",
                space_id, title, description or "", starts_at, duration_min,
                repeat_rule, repeat_until, user_id, user_name
            )
    except Exception as e:
        logging.error(f"Не удалось записать событие календаря: {e}")
        return None


async def plan_event(event_id: int):
    """Одно событие целиком, вместе с правилом повтора"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                f"SELECT * FROM {SCHEMA}.plan_events WHERE id = $1", event_id)
    except Exception as e:
        logging.error(f"БД недоступна при чтении события {event_id}: {e}")
        return None


async def plan_range(space_id: int, date_from, date_to):
    """События, которые МОГУТ попасть в диапазон дат.

    Разовое событие отбираем по своей дате, серию — по пересечению её окна
    жизни с диапазоном. Точные даты вхождений считает planner: серия «каждый
    вторник» пересекает любой месяц, но приходится в нём далеко не на все дни.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(
                f"SELECT * FROM {SCHEMA}.plan_events "
                "WHERE space_id = $3 AND NOT cancelled AND ("
                "  (repeat_rule IS NULL AND starts_at::date BETWEEN $1 AND $2)"
                "  OR (repeat_rule IS NOT NULL AND starts_at::date <= $2"
                "      AND (repeat_until IS NULL OR repeat_until >= $1))"
                ") ORDER BY starts_at",
                date_from, date_to, space_id
            )
    except Exception as e:
        logging.error(f"БД недоступна при чтении календаря: {e}")
        return []


async def plan_overrides(event_ids: list):
    """Переносы и отмены отдельных вхождений перечисленных серий"""
    if not event_ids:
        return []
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(
                f"SELECT * FROM {SCHEMA}.plan_overrides WHERE event_id = ANY($1::int[])",
                list(event_ids)
            )
    except Exception as e:
        logging.error(f"БД недоступна при чтении переносов календаря: {e}")
        return []


async def plan_set_override(event_id: int, occur_date, moved_to,
                            duration_min: int, user_id: int) -> bool:
    """Переносит (moved_to задан) или отменяет (moved_to = None) одно вхождение"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.plan_overrides "
                "(event_id, occur_date, moved_to, duration_min, changed_by, changed_at) "
                "VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP) "
                "ON CONFLICT (event_id, occur_date) DO UPDATE SET "
                "moved_to = EXCLUDED.moved_to, duration_min = EXCLUDED.duration_min, "
                "changed_by = EXCLUDED.changed_by, changed_at = CURRENT_TIMESTAMP",
                event_id, occur_date, moved_to, duration_min, user_id
            )
        return True
    except Exception as e:
        logging.error(f"Не удалось изменить вхождение {event_id}/{occur_date}: {e}")
        return False


async def plan_cancel(event_id: int) -> bool:
    """Отменяет событие целиком (серию — со всеми будущими вхождениями).

    Строку не удаляем: карточка отменённого занятия ещё может понадобиться,
    чтобы понять, кто и что убрал из общего расписания.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            done = await conn.execute(
                f"UPDATE {SCHEMA}.plan_events SET cancelled = TRUE WHERE id = $1", event_id)
        return done.endswith("1")
    except Exception as e:
        logging.error(f"Не удалось отменить событие {event_id}: {e}")
        return False


async def plan_reschedule(event_id: int, new_start, duration_min: int = None) -> bool:
    """Двигает событие целиком: разовое — насовсем, серию — вместе с правилом"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            done = await conn.execute(
                f"UPDATE {SCHEMA}.plan_events SET starts_at = $2, "
                "duration_min = COALESCE($3, duration_min) WHERE id = $1",
                event_id, new_start, duration_min
            )
        return done.endswith("1")
    except Exception as e:
        logging.error(f"Не удалось перенести событие {event_id}: {e}")
        return False


async def plan_set_description(event_id: int, text: str) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            done = await conn.execute(
                f"UPDATE {SCHEMA}.plan_events SET description = $2 WHERE id = $1",
                event_id, text or ""
            )
        return done.endswith("1")
    except Exception as e:
        logging.error(f"Не удалось изменить описание события {event_id}: {e}")
        return False


# --- КАЛЕНДАРИ: ВЛАДЕЛЬЦЫ, УЧАСТНИКИ, ПОДПИСКА ---
#
# Владелец бота видит только эти строки: кто ведёт календарь, сколько в нём
# людей и до какого числа оплачено. Событий чужой семьи он не читает — ни одна
# функция ниже не возвращает содержимое plan_events.

async def plan_space_create(title: str, owner_id: int, owner_name: str,
                            invite_code: str, paid_until):
    """Заводит календарь и сразу вписывает владельца в участники"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                space_id = await conn.fetchval(
                    f"INSERT INTO {SCHEMA}.plan_spaces "
                    "(title, owner_id, owner_name, invite_code, paid_until) "
                    "VALUES ($1, $2, $3, $4, $5) RETURNING id",
                    title, owner_id, owner_name, invite_code, paid_until)
                await conn.execute(
                    f"INSERT INTO {SCHEMA}.plan_members "
                    "(space_id, user_id, user_name, role) VALUES ($1, $2, $3, 'owner') "
                    "ON CONFLICT (space_id, user_id) DO NOTHING",
                    space_id, owner_id, owner_name)
        return space_id
    except Exception as e:
        logging.error(f"Не удалось создать календарь: {e}")
        return None


async def plan_space(space_id: int):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                f"SELECT * FROM {SCHEMA}.plan_spaces WHERE id = $1", space_id)
    except Exception as e:
        logging.error(f"БД недоступна при чтении календаря {space_id}: {e}")
        return None


async def plan_space_by_code(code: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                f"SELECT * FROM {SCHEMA}.plan_spaces "
                "WHERE invite_code = $1 AND NOT closed", code)
    except Exception as e:
        logging.error(f"БД недоступна при поиске календаря по коду: {e}")
        return None


async def plan_user_spaces(user_id: int):
    """Календари, в которых человек состоит, с его ролью в каждом"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(
                f"SELECT s.*, m.role FROM {SCHEMA}.plan_members m "
                f"JOIN {SCHEMA}.plan_spaces s ON s.id = m.space_id "
                "WHERE m.user_id = $1 AND NOT s.closed ORDER BY s.id",
                user_id)
    except Exception as e:
        logging.error(f"БД недоступна при чтении календарей участника: {e}")
        return []


async def plan_member(space_id: int, user_id: int):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                f"SELECT * FROM {SCHEMA}.plan_members "
                "WHERE space_id = $1 AND user_id = $2", space_id, user_id)
    except Exception as e:
        logging.error(f"БД недоступна при проверке участника: {e}")
        return None


async def plan_member_add(space_id: int, user_id: int, user_name: str,
                          role: str = "member") -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {SCHEMA}.plan_members (space_id, user_id, user_name, role) "
                "VALUES ($1, $2, $3, $4) ON CONFLICT (space_id, user_id) "
                "DO UPDATE SET user_name = EXCLUDED.user_name",
                space_id, user_id, user_name, role)
        return True
    except Exception as e:
        logging.error(f"Не удалось добавить участника в календарь {space_id}: {e}")
        return False


async def plan_member_drop(space_id: int, user_id: int) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            gone = await conn.execute(
                f"DELETE FROM {SCHEMA}.plan_members "
                "WHERE space_id = $1 AND user_id = $2 AND role <> 'owner'",
                space_id, user_id)
        return gone.endswith("1")
    except Exception as e:
        logging.error(f"Не удалось убрать участника из календаря {space_id}: {e}")
        return False


async def plan_members_of(space_id: int):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(
                f"SELECT * FROM {SCHEMA}.plan_members WHERE space_id = $1 "
                "ORDER BY role DESC, joined_at", space_id)
    except Exception as e:
        logging.error(f"БД недоступна при чтении участников: {e}")
        return []


async def plan_space_extend(space_id: int, paid_until) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            done = await conn.execute(
                f"UPDATE {SCHEMA}.plan_spaces SET paid_until = $2 WHERE id = $1",
                space_id, paid_until)
        return done.endswith("1")
    except Exception as e:
        logging.error(f"Не удалось продлить подписку календаря {space_id}: {e}")
        return False


async def plan_space_close(space_id: int, closed: bool = True) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            done = await conn.execute(
                f"UPDATE {SCHEMA}.plan_spaces SET closed = $2 WHERE id = $1",
                space_id, closed)
        return done.endswith("1")
    except Exception as e:
        logging.error(f"Не удалось закрыть календарь {space_id}: {e}")
        return False


async def plan_spaces_overview():
    """Витрина для владельца бота: кто, сколько людей, до какого числа оплачено.

    Событий здесь нет намеренно: тексты, описания и время чужих встреч
    владельцу бота не показываются нигде. Только количество — по нему видно,
    живой календарь или заброшенный.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(
                f"SELECT s.id, s.title, s.owner_id, s.owner_name, s.paid_until, "
                "       s.closed, s.created_at, "
                f"       (SELECT COUNT(*) FROM {SCHEMA}.plan_members m WHERE m.space_id = s.id) AS people, "
                f"       (SELECT COUNT(*) FROM {SCHEMA}.plan_events e "
                "         WHERE e.space_id = s.id AND NOT e.cancelled) AS events, "
                f"       (SELECT MAX(e.created_at) FROM {SCHEMA}.plan_events e "
                "         WHERE e.space_id = s.id) AS last_write "
                f"FROM {SCHEMA}.plan_spaces s ORDER BY s.id")
    except Exception as e:
        logging.error(f"БД недоступна при чтении списка календарей: {e}")
        return []
