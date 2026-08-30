# cartoon.py — мультфильм по описанию.
#
# Видео-модели у Anthropic нет, а сторонние берут деньги за каждый ролик.
# Поэтому кино здесь не генерируется, а разыгрывается: Claude превращает
# рассказ в раскадровку строгого формата, а страница её проигрывает —
# персонажи ходят, говорят, сцены сменяются.
#
# Цена такого мультика — один вызов модели, доли цента, и она не растёт от
# того, сколько раз ролик посмотрят. Ролик от видео-модели стоил бы доллары
# и существовал бы файлом, который надо где-то хранить.
#
# Раскадровка — JSON и приходит от модели, то есть из ненадёжного источника.
# Поэтому она не идёт на страницу как есть: всё проверяется и приводится к
# допустимым значениям. Иначе одна опечатка модели ломает проигрыватель.
import html
import json
import logging
import os
import re

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, WebAppInfo)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import config
import database
import imagegen
import inline_kb

router = Router()

try:
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else None
except ImportError:
    client = None

MODEL = "claude-haiku-4-5-20251001"
MAX_STORY = 1500          # длиннее — уже не история, а повесть
MAX_SCENES = 6
MAX_ACTORS = 4
MAX_BEATS = 6

# Допустимые значения. Модель обязана выбирать из них, а всё постороннее
# заменяется ближайшим разумным: проигрыватель умеет рисовать только это.
BACKDROPS = ["meadow", "forest", "city", "room", "night", "sea", "space", "snow",
             "castle", "throne", "cave", "ruins"]
KINDS = ["girl", "boy", "princess", "king", "knight", "wizard",
         "dragon", "monster", "cat", "dog", "bear", "rabbit", "horse",
         "bird", "fish", "robot"]
ACTIONS = ["walk", "jump", "turn", "wave", "idle", "shake", "grow", "fly", "breathe"]
MOODS = ["happy", "sad", "angry", "scared", "calm"]

DIRECTOR = """Ты раскадровщик детского мультфильма. По рассказу пользователя
верни ТОЛЬКО JSON, без пояснений и без markdown-обёртки.

Схема:
{{"title": "короткое название",
  "scenes": [
    {{"bg": один из {backdrops},
      "narration": "фраза рассказчика, до 120 знаков",
      "actors": [{{"id": "латиницей", "name": "имя", "kind": один из {kinds},
                  "color": "#rrggbb", "x": 0.0..1.0, "size": 0.5..1.8,
                  "own": "имя из списка своих персонажей, если это он"}}],
      "beats": [{{"actor": "id", "action": один из {actions},
                 "mood": один из {moods},
                 "to": 0.0..1.0, "say": "реплика до 80 знаков"}}]
    }}
  ]}}

Правила:
- от 2 до {max_scenes} сцен, в каждой до {max_actors} персонажей и до {max_beats} действий;
- "to" нужен только для walk — куда персонаж идёт;
- "say" необязателен; без реплики персонаж просто действует;
- "size" — рост относительно взрослого человека: ребёнок 0.6, взрослый 1.0,
  крупный зверь 1.4. Если персонаж по ходу истории растёт, ставьте ему
  разный размер в разных сценах;
- "mood" обязателен и должен отражать чувство персонажа в этот миг: на нём
  держится половина смысла;
- имена и текст на языке рассказа;
- цвета разные у разных персонажей;
- сложные и печальные сюжеты допустимы, сцен жестокости не рисуем.{own_block}"""


class Making(StatesGroup):
    waiting_story = State()


# =====================================================================
# ПРОВЕРКА РАСКАДРОВКИ
# =====================================================================

def _num(value, lo, hi, default):
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def _color(value):
    return value if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) \
        else "#f2a03d"


def sanitize(raw: dict, own: dict = None) -> dict:
    """Приводит присланную моделью раскадровку к тому, что умеет проигрыватель.

    Молча чиним, а не отвергаем: модель ошибается в мелочах — лишний ключ,
    неизвестный фон, персонаж без цвета, — и терять из-за этого весь мультик
    было бы обидно.
    """
    scenes = []
    for s in (raw.get("scenes") or [])[:MAX_SCENES]:
        if not isinstance(s, dict):
            continue

        actors, ids = [], set()
        for a in (s.get("actors") or [])[:MAX_ACTORS]:
            if not isinstance(a, dict):
                continue
            aid = re.sub(r"[^a-zA-Z0-9_]", "", str(a.get("id", "")))[:20] or f"a{len(actors)}"
            if aid in ids:
                continue
            ids.add(aid)
            kind = a.get("kind")
            # Своего персонажа принимаем только по имени из списка автора:
            # модель может выдумать имя, а показывать чужой рисунок нельзя.
            token = (own or {}).get(str(a.get("own", "")).strip().lower())
            actors.append({
                "own": token,
                "id": aid,
                "name": str(a.get("name", ""))[:24],
                "kind": kind if kind in KINDS else "girl",
                "color": _color(a.get("color")),
                "x": _num(a.get("x"), 0.05, 0.95, .5),
                "size": _num(a.get("size"), 0.45, 1.9, 1.0),
            })

        beats = []
        for b in (s.get("beats") or [])[:MAX_BEATS]:
            if not isinstance(b, dict):
                continue
            action, mood = b.get("action"), b.get("mood")
            beats.append({
                "actor": re.sub(r"[^a-zA-Z0-9_]", "", str(b.get("actor", "")))[:20],
                "action": action if action in ACTIONS else "idle",
                "mood": mood if mood in MOODS else "calm",
                "to": _num(b.get("to"), 0.05, 0.95, .5),
                "say": str(b.get("say", ""))[:80],
            })

        bg = s.get("bg")
        scenes.append({
            "bg": bg if bg in BACKDROPS else "meadow",
            "narration": str(s.get("narration", ""))[:120],
            "actors": actors,
            "beats": [b for b in beats if b["actor"] in ids],
        })

    return {
        "title": str(raw.get("title", ""))[:60] or "Мультфильм",
        "scenes": [s for s in scenes if s["actors"]],
    }


async def build(story: str, own: dict = None):
    """(раскадровка, ошибка). Ровно одно из двух заполнено."""
    if not client:
        return None, "Модель не подключена: не задан ANTHROPIC_API_KEY."

    own_block = ""
    if own:
        own_block = ("\n\nУ автора есть свои нарисованные персонажи: "
                     + ", ".join(sorted(own)) +
                     ".\nЕсли история про кого-то из них — поставьте это имя в поле "
                     '"own" слово в слово, а "kind" выберите похожий по смыслу.')
    prompt = DIRECTOR.format(backdrops=BACKDROPS, kinds=KINDS, actions=ACTIONS,
                             moods=MOODS, max_scenes=MAX_SCENES,
                             max_actors=MAX_ACTORS, max_beats=MAX_BEATS,
                             own_block=own_block)
    try:
        response = await client.messages.create(
            model=MODEL, max_tokens=2000, system=prompt,
            messages=[{"role": "user", "content": story[:MAX_STORY]}],
        )
        text = response.content[0].text.strip()
    except Exception as e:
        logging.error(f"Мультфильм: модель не ответила: {type(e).__name__}: {e}")
        if "credit balance" in str(e).lower() or "billing" in str(e).lower():
            return None, "Закончились средства на счёте Anthropic."
        return None, "Не удалось обратиться к модели."

    # Модель иногда оборачивает JSON в ```json — снимаем обёртку, а не падаем.
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    brace = text.find("{")
    if brace > 0:
        text = text[brace:]

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        logging.error(f"Мультфильм: раскадровка не разобралась: {e}; ответ: {text[:300]}")
        return None, "Модель прислала неразборчивый сценарий. Попробуйте ещё раз."

    story_board = sanitize(raw, own)
    if not story_board["scenes"]:
        return None, "В сценарии не оказалось ни одной сцены. Опишите историю подробнее."
    return story_board, None


# =====================================================================
# АДРЕСА
# =====================================================================

PAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cartoon.html")
_page_cache = None


def page() -> bytes:
    global _page_cache
    if _page_cache is None:
        try:
            with open(PAGE_PATH, "rb") as f:
                _page_cache = f.read()
        except OSError as e:
            logging.error(f"Страница мультфильма не читается: {e}")
            _page_cache = b"<h1>404</h1>"
    return _page_cache


def watch_url(cartoon_id: int) -> str:
    base = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    return f"{base}/cartoon?id={cartoon_id}" if base.startswith("https://") else ""


# =====================================================================
# ДИАЛОГ
# =====================================================================

ASK = {
    "ru": "🎬 <b>Мультфильм по описанию</b>\n\nРасскажите историю — кто, где и что "
          "делает. Двух-трёх предложений достаточно, но чем подробнее, тем живее выйдет.\n\n"
          "<i>Например: «Кот Барсик потерял мяч во дворе. Он спросил у птицы, та "
          "показала на дерево. Барсик залез и достал мяч».</i>",
    "en": "🎬 <b>Cartoon from a description</b>\n\nTell a story — who, where, and what "
          "they do. Two or three sentences are enough.",
    "fr": "🎬 <b>Dessin animé à partir d'une description</b>\n\nRacontez une histoire — "
          "qui, où et ce qu'ils font. Deux ou trois phrases suffisent.",
    "he": "🎬 <b>סרטון לפי תיאור</b>\n\nספרו סיפור — מי, איפה ומה עושים. שני משפטים מספיקים.",
}
MAKING = {"ru": "🎬 Снимаю…", "en": "🎬 Filming…",
          "fr": "🎬 Tournage…", "he": "🎬 מצלם…"}
WATCH = {"ru": "▶️ Смотреть", "en": "▶️ Watch", "fr": "▶️ Regarder", "he": "▶️ לצפות"}
AGAIN = {"ru": "🎬 Ещё историю", "en": "🎬 Another story",
         "fr": "🎬 Une autre histoire", "he": "🎬 עוד סיפור"}


MY_CHARS = {"ru": "🎨 Мои персонажи", "en": "🎨 My characters",
            "fr": "🎨 Mes personnages", "he": "🎨 הדמויות שלי"}


def _back(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=MY_CHARS.get(lang, MY_CHARS["en"]),
                              callback_data="char_list")],
        [InlineKeyboardButton(text=inline_kb.label(inline_kb.HOME_TEXTS, lang),
                              callback_data="go_home")]])


@router.message(F.text == "/imagetest")
async def image_test(message: Message):
    """Проверка рисовальщика прямо в чате.

    Логи Render владельцу неудобны, а причина отказа нужна дословно:
    неверное имя модели и незаданный ключ выглядят одинаково — «кадров нет».
    """
    if not config.is_admin(message.from_user.id):
        return
    note = await message.answer("🔍 Проверяю рисовальщик…")
    try:
        lines = await imagegen.diagnose()
    except Exception as e:
        lines = [f"Проверка сорвалась: {type(e).__name__}: {e}"]
    await note.edit_text("🔍 <b>Рисовальщик</b>\n\n" + "\n".join(
        f"• {html.escape(str(l))}" for l in lines))


@router.callback_query(F.data == "cartoon_open")
async def open_cartoon(call: CallbackQuery, state: FSMContext):
    lang = await database.get_user_language(call.from_user.id)
    await state.set_state(Making.waiting_story)
    await call.message.answer(ASK.get(lang, ASK["en"]), reply_markup=_back(lang))
    await call.answer()


@router.message(Making.waiting_story, F.text & ~F.text.startswith("/"))
async def make_cartoon(message: Message, state: FSMContext):
    lang = await database.get_user_language(message.from_user.id)
    note = await message.answer(MAKING.get(lang, MAKING["en"]))

    own = {name.lower(): token
           for _, name, _, token in await database.own_characters(message.from_user.id)}
    board, error = await build(message.text, own)
    if error:
        await note.edit_text(f"⚠️ {error}")
        return

    cartoon_id = await database.save_cartoon(
        message.from_user.id, message.text[:MAX_STORY], json.dumps(board, ensure_ascii=False))
    if not cartoon_id:
        await note.edit_text("⚠️ Не удалось сохранить мультфильм.")
        return

    # Кадры рисуются дольше сценария, поэтому сперва отдаём готовый мультик,
    # а картинки подставляем следом: смотреть можно уже сейчас.
    # Если в мультике играют свои персонажи, кадры не рисуем вовсе: их
    # рисунок — то, ради чего человек его присылал, и подменять героя
    # выдуманной иллюстрацией значит отменять его работу.
    uses_own = any(a.get("own") for s in board["scenes"] for a in s["actors"])
    drawn = 0
    if uses_own:
        pass
    elif imagegen.provider():
        await note.edit_text(f"🎬 <b>{board['title']}</b>\n\nРисую кадры…")
        try:
            drawn = await database.save_cartoon_frames(
                cartoon_id, await imagegen.render(board))
        except Exception as e:
            logging.error(f"Мультфильм: кадры не нарисовались: {e}")

    url = watch_url(cartoon_id)
    rows = []
    if url:
        rows.append([InlineKeyboardButton(text=WATCH.get(lang, WATCH["en"]),
                                          web_app=WebAppInfo(url=url))])
    rows.append([InlineKeyboardButton(text=AGAIN.get(lang, AGAIN["en"]),
                                      callback_data="cartoon_open")])
    rows.append([InlineKeyboardButton(text=inline_kb.label(inline_kb.HOME_TEXTS, lang),
                                      callback_data="go_home")])

    scenes = len(board["scenes"])
    # О кадрах говорим всегда, в том числе когда их ноль: молчание в этом
    # месте неотличимо от «всё хорошо», и владелец ищет неисправность там,
    # где её нет.
    if uses_own:
        art = "🎨 Играют ваши персонажи — кадры не рисовались."
    elif not imagegen.provider():
        art = "🖍 Рисованные кадры выключены: ключ не задан."
    elif drawn:
        art = f"🎨 Кадров нарисовано: {drawn} из {scenes}."
    else:
        art = ("⚠️ Кадры не нарисовались — мультик играется векторно.\n"
               "Причину покажет <code>/imagetest</code>.")
    await note.edit_text(
        f"🎬 <b>{board['title']}</b>\n\nСцен: {scenes}. {art}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await state.clear()
