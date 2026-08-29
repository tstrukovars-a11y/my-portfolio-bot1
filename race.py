# race.py — браузерная гонка, открываемая кнопкой из визитки.
#
# Страницу раздаёт тот же HTTP-сервер, что принимает вебхук: отдельный хостинг
# не нужен, а адрес у Render уже https, чего Telegram и требует от мини-приложений.
#
# Счёт присылает сама страница, то есть недоверенная сторона. Поэтому вместе
# со счётом приходит initData — строка, подписанная Telegram ключом бота.
# Без проверки подписи рекорд мог бы прислать кто угодно, от чьего угодно
# имени и любой величины.
import hashlib
import hmac
import html
import json
import logging
import os
import time
import urllib.parse

from aiogram import Router, F
from aiogram.types import (CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, WebAppInfo)

import config
import database
import inline_kb

router = Router()

PAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "race.html")
MAX_AGE = 86400          # сутки: дольше живущий initData принимать незачем
MAX_SCORE = 500_000      # выше физически недостижимо — верный признак подделки

_page_cache = None


def page() -> bytes:
    """HTML игры. Читаем один раз: файл меняется только вместе с деплоем."""
    global _page_cache
    if _page_cache is None:
        try:
            with open(PAGE_PATH, "rb") as f:
                _page_cache = f.read()
        except OSError as e:
            logging.error(f"Страница игры не читается: {e}")
            _page_cache = b"<h1>404</h1>"
    return _page_cache


def game_url() -> str:
    """Адрес игры или пустая строка, если внешнего адреса нет.

    Telegram открывает мини-приложения только по https, поэтому локально
    кнопки просто не будет — вместо ошибки при нажатии.
    """
    base = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    return f"{base}/game" if base.startswith("https://") else ""


def check_init_data(init_data: str, token: str):
    """Разобранный initData, если подпись Telegram верна, иначе None"""
    try:
        data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return None

    received = data.pop("hash", "")
    if not received:
        return None

    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received):
        return None

    try:
        if time.time() - int(data.get("auth_date", 0)) > MAX_AGE:
            return None
    except ValueError:
        return None
    return data


async def handle_score(body: bytes, token: str) -> tuple[int, dict]:
    """(код ответа, тело) для POST /game/score"""
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return 400, {"status": "error", "message": "bad json"}

    data = check_init_data(str(payload.get("initData", "")), token)
    if not data:
        logging.warning("Гонка: счёт с неверной подписью отклонён")
        return 403, {"status": "error", "message": "bad signature"}

    try:
        user = json.loads(data.get("user", "{}"))
        user_id = int(user["id"])
    except Exception:
        return 400, {"status": "error", "message": "no user"}

    try:
        score = int(payload.get("score", 0))
    except (TypeError, ValueError):
        return 400, {"status": "error", "message": "bad score"}
    if not 0 <= score <= MAX_SCORE:
        return 400, {"status": "error", "message": "out of range"}

    name = (user.get("first_name") or "").strip() or "Игрок"
    if user.get("last_name"):
        name = f"{name} {user['last_name'].strip()}"

    place, best = await database.save_race_score(user_id, name[:64], score)
    return 200, {"status": "ok", "place": place, "best": best}


# =====================================================================
# КНОПКИ В БОТЕ
# =====================================================================

INTRO = {
    "ru": "🏎 <b>Гонка</b>\n\nТри полосы, встречный поток и растущая скорость.\n"
          "Играется прямо здесь, ставить ничего не нужно.",
    "en": "🏎 <b>Race</b>\n\nThree lanes, oncoming traffic and rising speed.\n"
          "Plays right here, nothing to install.",
    "fr": "🏎 <b>Course</b>\n\nTrois voies, trafic venant en sens inverse et vitesse croissante.\n"
          "Se joue ici même, rien à installer.",
    "he": "🏎 <b>מרוץ</b>\n\nשלושה נתיבים, תנועה נגדית ומהירות שהולכת וגדלה.\n"
          "משחקים כאן, בלי להתקין כלום.",
}
PLAY = {"ru": "🏁 Играть", "en": "🏁 Play", "fr": "🏁 Jouer", "he": "🏁 לשחק"}
TOP = {"ru": "🏆 Таблица рекордов", "en": "🏆 Leaderboard",
       "fr": "🏆 Classement", "he": "🏆 טבלת שיאים"}
EMPTY = {"ru": "Пока никто не проехал. Будете первой строкой.",
         "en": "Nobody has raced yet. You can be the first line.",
         "fr": "Personne n'a encore couru. À vous la première ligne.",
         "he": "אף אחד עדיין לא נסע. אתם תהיו השורה הראשונה."}


def _menu(lang: str) -> InlineKeyboardMarkup:
    rows = []
    url = game_url()
    if url:
        rows.append([InlineKeyboardButton(text=PLAY.get(lang, PLAY["en"]),
                                          web_app=WebAppInfo(url=url))])
    rows.append([InlineKeyboardButton(text=TOP.get(lang, TOP["en"]),
                                      callback_data="race_top")])
    rows.append([InlineKeyboardButton(text=inline_kb.label(inline_kb.HOME_TEXTS, lang),
                                      callback_data="go_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "race_open")
async def open_race(call: CallbackQuery):
    lang = await database.get_user_language(call.from_user.id)
    await call.message.edit_caption(caption=INTRO.get(lang, INTRO["en"]),
                                    reply_markup=_menu(lang), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "race_top")
async def show_top(call: CallbackQuery):
    lang = await database.get_user_language(call.from_user.id)
    rows = await database.race_top(10)

    if not rows:
        body = EMPTY.get(lang, EMPTY["en"])
    else:
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (uid, name, best) in enumerate(rows):
            mark = medals[i] if i < 3 else f"{i + 1}."
            you = " ←" if uid == call.from_user.id else ""
            lines.append(f"{mark} {html.escape(name)} — <b>{best}</b>{you}")
        body = "\n".join(lines)

    await call.message.edit_caption(
        caption=f"{TOP.get(lang, TOP['en'])}\n\n{body}",
        reply_markup=_menu(lang), parse_mode="HTML")
    await call.answer()
