# rally.py — теннис сверху: розыгрыш на вылет.
#
# Вторая теннисная игра, и она не заменяет первую. В той ракетка — линия
# внизу экрана, и от настольного тенниса её не отличить. Здесь корт виден
# сверху, игрок — круг, который бегает по своей половине, а очко берётся
# не отбиванием, а тем, что соперник не добежал.
#
# Отсюда и разница в устройстве: там важна реакция, здесь — куда вы
# посылаете мяч и успеет ли он. После каждого удара соперник возвращается
# в центр, как настоящий теннисист, — поэтому его можно выманить вперёд
# укороченным и перебросить в дальний угол.
#
# Счёт в таблице — самый длинный розыгрыш за гейм, а не выигранные очки:
# выиграть 7:0 у новичка может каждый, а длинный розыгрыш случается
# только в настоящей борьбе.
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

PAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rally.html")
MAX_SCORE = 1000        # розыгрыш длиннее тысячи ударов — признак подделки

_page_cache = None


def page() -> bytes:
    """HTML игры. Читаем один раз: файл меняется только вместе с деплоем."""
    global _page_cache
    if _page_cache is None:
        try:
            with open(PAGE_PATH, "rb") as f:
                _page_cache = f.read()
        except OSError as e:
            logging.error(f"Страница розыгрыша не читается: {e}")
            _page_cache = b"<h1>404</h1>"
    return _page_cache


def game_url() -> str:
    """Адрес игры или пусто, если внешнего адреса нет.

    Telegram открывает мини-приложения только по https, поэтому локально
    кнопки просто не будет — вместо ошибки при нажатии.
    """
    base = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    return f"{base}/rally" if base.startswith("https://") else ""


async def handle_score(body: bytes, token: str):
    """(код ответа, тело) для POST /rally/score"""
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return 400, {"status": "error", "message": "bad json"}

    data = race.check_init_data(str(payload.get("initData", "")), token)
    if not data:
        logging.warning("Розыгрыш: счёт с неверной подписью отклонён")
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

    place, best = await database.save_rally_score(user_id, name[:64], score)
    return 200, {"status": "ok", "place": place, "best": best}


# =====================================================================
# КНОПКИ В БОТЕ
# =====================================================================

INTRO = {
    "ru": "🎾 <b>Розыгрыш</b>\n\nКорт сверху, вы — синий круг. Ведите пальцем: "
          "резкое движение бьёт сильно, медленное — укороченный, вбок — "
          "с закруткой.\n\nСоперник после каждого удара возвращается в центр. "
          "Выманите его вперёд и перебросьте в дальний угол — очко ваше.",
    "en": "🎾 <b>Rally</b>\n\nTop-down court, you are the blue circle. Drag to "
          "move: a sharp flick hits hard, a slow one drops short, sideways "
          "adds spin.\n\nThe opponent returns to the centre after every shot. "
          "Pull him forward, then send it to the far corner.",
    "fr": "🎾 <b>Échange</b>\n\nCourt vu du dessus, vous êtes le cercle bleu. "
          "Glissez pour vous déplacer : un geste vif frappe fort, un geste lent "
          "fait un amorti, sur le côté ajoute de l'effet.\n\nL'adversaire "
          "revient au centre après chaque coup.",
    "he": "🎾 <b>חילופי חבטות</b>\n\nמגרש ממבט על, אתם העיגול הכחול. גררו כדי "
          "לזוז: תנועה חדה חובטת חזק, איטית — חבטה מקוצרת, הצידה — עם סיבוב.",
}
PLAY = {"ru": "🎾 На корт", "en": "🎾 Play", "fr": "🎾 Jouer", "he": "🎾 לשחק"}
TOP = {"ru": "🏆 Самые длинные розыгрыши", "en": "🏆 Longest rallies",
       "fr": "🏆 Plus longs échanges", "he": "🏆 החילופים הארוכים"}
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
                                      callback_data="rally_top")])
    rows.append([InlineKeyboardButton(text=inline_kb.label(inline_kb.HOME_TEXTS, lang),
                                      callback_data="go_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "rally_open")
async def open_game(call: CallbackQuery):
    lang = await database.get_user_language(call.from_user.id)
    await call.message.edit_caption(caption=INTRO.get(lang, INTRO["en"]),
                                    reply_markup=_menu(lang), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "rally_top")
async def show_top(call: CallbackQuery):
    lang = await database.get_user_language(call.from_user.id)
    rows = await database.rally_top(10)

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
