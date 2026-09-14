# tennis_game.py — теннис в мини-приложении, как гонка.
#
# Устройство ровно то же, что у гонки: страницу раздаёт тот же HTTP-сервер,
# что принимает вебхук, а счёт приходит вместе с initData — строкой,
# подписанной ключом бота. Проверку подписи не переписываю, а беру из
# race: одна реализация, одна ошибка, если она найдётся.
#
# Счёт здесь — длина розыгрыша: каждый отбитый мяч очко, непринятый
# соперником — три. Рекорд у игрока один, история попыток не хранится.
import html
import json
import logging
import os

from aiogram import Router, F
from aiogram.types import (CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, WebAppInfo)

import config
import database
import inline_kb
import race

router = Router()

PAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis.html")
MAX_SCORE = 100_000        # выше не бывает: розыгрыш кончается промахом

_page_cache = None


def page() -> bytes:
    """HTML игры. Читаем один раз: файл меняется только вместе с деплоем."""
    global _page_cache
    if _page_cache is None:
        try:
            with open(PAGE_PATH, "rb") as f:
                _page_cache = f.read()
        except OSError as e:
            logging.error(f"Страница тенниса не читается: {e}")
            _page_cache = b"<h1>404</h1>"
    return _page_cache


def game_url() -> str:
    """Адрес игры или пустая строка, если внешнего адреса нет.

    Telegram открывает мини-приложения только по https, поэтому локально
    кнопки просто не будет — вместо ошибки при нажатии.
    """
    base = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    return f"{base}/tennis" if base.startswith("https://") else ""


async def handle_score(body: bytes, token: str):
    """(код ответа, тело) для POST /tennis/score"""
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return 400, {"status": "error", "message": "bad json"}

    data = race.check_init_data(str(payload.get("initData", "")), token)
    if not data:
        logging.warning("Теннис: счёт с неверной подписью отклонён")
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

    place, best = await database.save_tennis_score(user_id, name[:64], score)
    return 200, {"status": "ok", "place": place, "best": best}


# =====================================================================
# КНОПКИ В БОТЕ
# =====================================================================

INTRO = {
    "ru": "🎾 <b>Теннис</b>\n\nОтбивайте мяч ракеткой внизу. Каждый удар — очко, "
          "с каждым ударом мяч быстрее.\nИграется прямо здесь, ставить ничего не нужно.",
    "en": "🎾 <b>Tennis</b>\n\nReturn the ball with the racket below. Every shot is a point, "
          "and every shot makes the ball faster.\nPlays right here, nothing to install.",
    "fr": "🎾 <b>Tennis</b>\n\nRenvoyez la balle avec la raquette du bas. Chaque coup "
          "rapporte un point et accélère la balle.\nSe joue ici même, rien à installer.",
    "he": "🎾 <b>טניס</b>\n\nהחזירו את הכדור עם המחבט שלמטה. כל חבטה היא נקודה, "
          "וכל חבטה מאיצה את הכדור.\nמשחקים כאן, בלי להתקין כלום.",
}
PLAY = {"ru": "🎾 Играть", "en": "🎾 Play", "fr": "🎾 Jouer", "he": "🎾 לשחק"}
TOP = {"ru": "🏆 Таблица рекордов", "en": "🏆 Leaderboard",
       "fr": "🏆 Classement", "he": "🏆 טבלת שיאים"}
EMPTY = {"ru": "Пока никто не играл. Будете первой строкой.",
         "en": "Nobody has played yet. You can be the first line.",
         "fr": "Personne n'a encore joué. À vous la première ligne.",
         "he": "אף אחד עדיין לא שיחק. אתם תהיו השורה הראשונה."}


def _menu(lang: str) -> InlineKeyboardMarkup:
    rows = []
    url = game_url()
    if url:
        rows.append([InlineKeyboardButton(text=PLAY.get(lang, PLAY["en"]),
                                          web_app=WebAppInfo(url=url))])
    rows.append([InlineKeyboardButton(text=TOP.get(lang, TOP["en"]),
                                      callback_data="tgame_top")])
    rows.append([InlineKeyboardButton(text=inline_kb.label(inline_kb.HOME_TEXTS, lang),
                                      callback_data="go_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "tgame_open")
async def open_game(call: CallbackQuery):
    lang = await database.get_user_language(call.from_user.id)
    await call.message.edit_caption(caption=INTRO.get(lang, INTRO["en"]),
                                    reply_markup=_menu(lang), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "tgame_top")
async def show_top(call: CallbackQuery):
    lang = await database.get_user_language(call.from_user.id)
    rows = await database.tennis_top(10)

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
