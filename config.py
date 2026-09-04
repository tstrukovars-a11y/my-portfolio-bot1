# config.py
import logging
import os
from aiogram.types import FSInputFile
from dotenv import load_dotenv

load_dotenv()


def env_int(name: str, default: int = 0) -> int:
    """Читает числовую переменную окружения, не роняя бот на пустом значении.

    os.getenv(name, default) подставляет default, только если переменной нет
    вовсе. Заведённая, но пустая переменная возвращает "" — и int("") валит
    весь процесс ещё на импорте конфига, до запуска бота. Пустое, пробельное
    и нечисловое значение здесь трактуются как «не задано».
    """
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logging.warning(f"Переменная {name}={raw!r} не число — использую {default}")
        return default


TOKEN = os.getenv("BOT_TOKEN")
def _api_key(name: str):
    """Ключ Anthropic или None, если он не настроен.

    Заглушки вроде «ВАШ_КЛЮЧ» и любые нелатинские символы отсекаем здесь:
    иначе запрос падает внутри http-клиента с UnicodeEncodeError, и вместо
    понятного «ключ не задан» пользователь видит ошибку кодировки.
    """
    raw = (os.getenv(name) or "").strip()
    if not raw or not raw.isascii() or not raw.startswith("sk-"):
        if raw:
            logging.warning(f"{name} не похож на ключ Anthropic — раздел ИИ отключён")
        return None
    return raw


ANTHROPIC_API_KEY = _api_key("CLAUDE_KEY")
REQUIRED_CHANNEL = env_int("REQUIRED_CHANNEL", -1001234567890)
QUIZ_CHANNEL = env_int("QUIZ_CHANNEL", -1002648861151)

# Telegram-id владельца бота. Нужен для импорта головоломок: только этот
# пользователь может пересылать боту опросы из канала и пополнять банк задач.
# На Render эта переменная называется ORGANIZER_TELEGRAM_ID, поэтому читаем оба
# имени. Пока ни одно не задано (0), режим импорта выключен целиком.
ADMIN_ID = env_int("ORGANIZER_TELEGRAM_ID") or env_int("ADMIN_ID")


def is_admin(user_id: int) -> bool:
    """Владелец бота? Пока ADMIN_ID не задан, админских режимов нет ни у кого."""
    return bool(ADMIN_ID) and user_id == ADMIN_ID


# Кому календарь достаётся без подписки: своя тестовая группа и владелец бота.
# Список можно переопределить переменной PLAN_FREE_USERS ("111,222"), но и без
# неё эти люди заводят себе календарь сами и бессрочно.
def _free_calendar_users() -> set:
    raw = (os.getenv("PLAN_FREE_USERS") or "").replace(",", " ").split()
    ids = {int(x) for x in raw if x.isdigit()}
    return ids or {1097484776, 132276171, 5135747687}


PLAN_FREE_USERS = _free_calendar_users()


def calendar_is_free(user_id: int) -> bool:
    """Заводит календарь без оплаты и без пробного периода"""
    return user_id in PLAN_FREE_USERS or is_admin(user_id)


# Один бот сидит админом в нескольких каналах, поэтому каждый сборщик слушает
# только свой. Если переменная не задана (0), фильтр по каналу отключён и пост
# принимается откуда угодно — так поведение не ломается, пока id не проставлены.
CULINARY_CHANNEL = env_int("CULINARY_CHANNEL")
BOOKS_CHANNEL = env_int("BOOKS_CHANNEL")
GENETICS_CHANNEL = env_int("GENETICS_CHANNEL")


# Пригласительная ссылка в закрытый гольф-канал и пароль к ней. Держим в
# переменных окружения: ссылки Telegram истекают, и менять их через Render
# быстрее, чем правкой кода. Значения по умолчанию — текущие рабочие.
GOLF_INVITE_URL = os.getenv("GOLF_INVITE_URL") or "https://t.me/+a5gt9GCsK75kZDIy"
GOLF_PASSWORD = os.getenv("GOLF_PASSWORD") or "гольфонутые"

# Пароли остальных закрытых разделов — тоже через окружение.
# ВНИМАНИЕ: значения по умолчанию уже попали в историю git и секретом больше не
# являются. Чтобы разделы действительно закрылись, задайте в Render новые
# значения — умолчания здесь только чтобы бот не сломался без переменных.
VPN_PASSWORD = os.getenv("VPN_PASSWORD") or "единорог2026"
PROFILES_PASSWORD = os.getenv("PROFILES_PASSWORD") or "проект будущего"


def channel_allowed(configured_channel: int, chat_id: int) -> bool:
    """Пришёл ли пост из того канала, который закреплён за разделом"""
    return not configured_channel or chat_id == configured_channel

def get_banner(file_id_or_path: str):
    # Если строка похожа на file_id от Telegram, возвращаем её как есть
    if file_id_or_path.startswith("AgAC") or (len(file_id_or_path) > 30 and "/" not in file_id_or_path and "\\" not in file_id_or_path):
        return file_id_or_path
    # Если это путь к файлу на компьютере, упаковываем в FSInputFile
    return FSInputFile(file_id_or_path)

# Ваши сохраненные file_id баннеров
MAIN_BANNER = get_banner("AgACAgIAAxkDAAPgagtm983BGj8mNN0_gspgL8EFOjsAAtMaaxts1mFI4UNK-uuf9mkBAAMCAAN5AAM7BA")
SPORT_BANNER = get_banner("AgACAgIAAxkDAAPvaguVH5xhUsabUkNXZZj5G7jcKFIAApobaxts1mFIjpbZVl4RtPgBAAMCAAN5AAM7BA")
ART_BANNER = get_banner("AgACAgIAAxkDAAIBF2oM1DfqKn3eK7pdmKWK4260V3RUAAJZH2sbKDphSECAng7NxGWEAQADAgADeQADOwQ")
CLOD_BANNER = get_banner("AgACAgIAAxkDAAIBM2oNry6z7yw-yjPuwr9i8KP68ZuwAAK7GmsbKDppSL_hawWauR8eAQADAgADbQADOwQ")
SCIENCE_BANNER = get_banner("AgACAgIAAxkDAAPgagtm_U8YM5obddnWLhCd2FEUdZIAAtUaaxts1mFIepn6ZMSRdg0BAAMCAAN5AAM7BA")
CEO_BANNER = get_banner("AgACAgIAAxkDAAPgagtm_U8YM5obddnWLhCd2FEUdZIAAtUaaxts1mFIepn6ZMSRdg0BAAMCAAN5AAM7BA")

# ДОБАВЛЯЕМ НЕДОСТАЮЩИЕ БАННЕРЫ ДЛЯ ПОДРАЗДЕЛОВ БЛОКА 1
MUSIC_BANNER = get_banner("AgACAgIAAxkDAAPvaguVIfaP6SPjCYJvQJCJoarzGNYAApsbaxts1mFIKtdBzq2Qnl0BAAMCAAN5AAM7BA")
TRAVEL_BANNER = get_banner("AgACAgIAAxkDAAPvaguVLLhgZRhPqKkEW2N7SF5zfGQAAp0baxts1mFIkwLEfeaMSqcBAAMCAAN3AAM7BA")
TENNIS_BANNER = get_banner("AgACAgIAAxkDAAIBF2oM1CVRVBUmS1ii-q0jBGq_BHVrAAJWH2sbKDphSHUrlw3F7-r7AQADAgADdwADOwQ")
HORSE_BANNER = get_banner("AgACAgIAAxkDAAIBF2oM1CkKJUOnVWctImC1hrjq99VSAAJXH2sbKDphSKZwbLJshLrsAQADAgADeQADOwQ")
GOLF_BANNER = get_banner("AgACAgIAAxkDAAIBF2oM1CwKAAGHPxlNfs06WwqVwFDg8AACWB9rGyg6YUh2fXAk3VCcCQEAAwIAA3cAAzsE")
NEWS_BANNER = get_banner("AgACAgIAAxkDAAPvaguVJxOmmqa0QldJljv8gSU9YiMAApwbaxts1mFIJcdcLR-tIkwBAAMCAAN3AAM7BA")

# Баннеры для падела и настольного тенниса (временно = баннер спорта; замените на свои фото по желанию)
PADEL_BANNER = SPORT_BANNER
TABLE_TENNIS_BANNER = SPORT_BANNER

# ДОБАВЛЯЕМ НЕДОСТАЮЩИЕ БАННЕРЫ ДЛЯ ПОДРАЗДЕЛОВ БЛОКА 3
BOOKS_BANNER = get_banner("AgACAgIAAxkDAAPgagtm_U8YM5obddnWLhCd2FEUdZIAAtUaaxts1mFIepn6ZMSRdg0BAAMCAAN5AAM7BA")
PUZZLE_BANNER = get_banner("AgACAgIAAxkDAAPgagtm_U8YM5obddnWLhCd2FEUdZIAAtUaaxts1mFIepn6ZMSRdg0BAAMCAAN5AAM7BA")
# У кулинарии своей картинки не было — показывалась «творческая». Заводим
# отдельную: по умолчанию та же, дальше меняется через /banner кухня.
FOOD_BANNER = ART_BANNER

GENETICS_BANNER = get_banner("AgACAgIAAxkDAAPgagtm_U8YM5obddnWLhCd2FEUdZIAAtUaaxts1mFIepn6ZMSRdg0BAAMCAAN5AAM7BA")

# Локальные лимиты ИИ
user_languages = {}
user_ai_limits = {}
