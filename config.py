# config.py
import os
from aiogram.types import FSInputFile
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("CLAUDE_KEY")
REQUIRED_CHANNEL = int(os.getenv("REQUIRED_CHANNEL", -1001234567890))
QUIZ_CHANNEL = int(os.getenv("QUIZ_CHANNEL", -1002648861151))

# Telegram-id владельца бота. Нужен для импорта головоломок: только этот
# пользователь может пересылать боту опросы из канала и пополнять банк задач.
# Пока переменная не задана (0), режим импорта выключен целиком.
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

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
GENETICS_BANNER = get_banner("AgACAgIAAxkDAAPgagtm_U8YM5obddnWLhCd2FEUdZIAAtUaaxts1mFIepn6ZMSRdg0BAAMCAAN5AAM7BA")

# Локальные лимиты ИИ
user_languages = {}
user_ai_limits = {}
