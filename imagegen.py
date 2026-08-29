# imagegen.py — рисованные кадры к сценам мультфильма.
#
# Векторная отрисовка в браузере остаётся на месте как запасной путь: если
# ключа нет, генератор недоступен или кадр не пришёл, мультик всё равно
# играется. Картинка — улучшение, а не условие работы.
#
# Поддерживаются два поставщика, потому что у них разные сильные стороны:
# Gemini даёт бесплатный лимит без карты и лучше держит одного персонажа
# похожим в разных сценах; fal.ai (Flux) дешевле и быстрее на объёме.
# Берётся тот, чей ключ задан.
import asyncio
import base64
import logging
import os

import httpx

TIMEOUT = 90
PARALLEL = 3          # больше — упираемся в лимиты, меньше — долго ждать

GEMINI_MODEL = "gemini-2.5-flash-image"
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              f"{GEMINI_MODEL}:generateContent")
FAL_URL = "https://fal.run/fal-ai/flux/schnell"

# Общий для всех кадров зачин. Стиль задаётся один раз и слово в слово:
# любое расхождение в описании стиля — и соседние сцены выглядят из разных
# мультфильмов.
STYLE = ("Children's storybook illustration, soft gouache texture, warm "
         "lighting, clean shapes, gentle outlines, wide cinematic composition, "
         "no text, no letters, no watermark, no frame borders.")


def provider() -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("FAL_KEY"):
        return "fal"
    return ""


# =====================================================================
# ОПИСАНИЕ СЦЕНЫ СЛОВАМИ
# =====================================================================

SETTINGS = {
    "meadow": "a sunny green meadow with wildflowers",
    "forest": "a bright forest clearing among tall trees",
    "city": "a quiet city street with low houses",
    "room": "a cosy room with a window and wooden floor",
    "night": "a moonlit field under a starry sky",
    "sea": "a warm sandy beach by a calm sea",
    "space": "open space among stars and distant planets",
    "snow": "a snowy field under a pale winter sky",
    "castle": "the courtyard of a stone castle with towers",
    "throne": "a torch-lit stone throne hall with tall columns",
    "cave": "a dim rocky cave lit by a shaft of light",
    "ruins": "a burnt ruined town, smoke drifting over broken walls",
}
# Цвет вставляется в описание там, где ему место: у человека он на одежде,
# у зверя на шкуре. «Красная принцесса» — не тот образ, что «принцесса в
# красном платье», и модель рисует ровно то, что прочла.
SPECIES = {
    "girl": "a young girl in a {c} dress",
    "boy": "a young boy in a {c} shirt",
    "princess": "a princess in a {c} gown with a small golden crown",
    "king": "an old king with a white beard, a {c} robe and a golden crown",
    "knight": "a knight in polished plate armour with a closed visor and a {c} cloak",
    "wizard": "an old wizard with a long beard, a {c} robe and a pointed hat",
    "dragon": "a {c} dragon with folded wings, small horns and a spiked tail",
    "monster": "a friendly shaggy {c} monster with little horns",
    "cat": "a {c} cat", "dog": "a {c} dog", "bear": "a {c} bear",
    "rabbit": "a {c} rabbit", "horse": "a {c} horse", "bird": "a small {c} bird",
    "fish": "a {c} fish", "robot": "a small friendly {c} robot",
}
MOODS = {"happy": "smiling", "sad": "downcast and sad", "angry": "angry",
         "scared": "frightened", "calm": "calm"}
DOING = {"walk": "walking", "jump": "leaping", "turn": "turning away",
         "wave": "waving", "idle": "standing", "shake": "trembling",
         "grow": "growing larger", "fly": "flying", "breathe": "breathing fire"}


def _size_clause(size: float) -> str:
    """Рост словами. Он идёт отдельным оборотом, а не в общее описание:
    один и тот же дракон бывает детёнышем в начале и громадиной в конце,
    и описание, собранное по первому появлению, эту разницу теряет."""
    if size <= .7:
        return ", small and young"
    if size >= 1.35:
        return ", huge and towering"
    return ""


def character(a: dict) -> str:
    """Постоянное описание персонажа — слово в слово во всех сценах.

    Именно повторение слов удерживает одного и того же дракона похожим:
    модель не помнит прошлый кадр, она видит только этот текст. Поэтому
    рост сюда не входит — он меняется, а всё остальное нет.
    """
    template = SPECIES.get(a.get("kind"), "a {c} character")
    return template.format(c=color_name(a.get("color", "")) or "colourful")


COLOR_NAMES = [
    ((225, 55, 50), "red"), ((240, 140, 40), "orange"), ((245, 210, 70), "yellow"),
    ((90, 190, 90), "green"), ((45, 120, 70), "dark green"),
    ((70, 150, 230), "blue"), ((35, 60, 140), "deep blue"),
    ((150, 90, 210), "purple"), ((225, 40, 150), "magenta"),
    ((245, 165, 200), "pink"), ((140, 100, 70), "brown"),
    ((240, 240, 240), "white"), ((150, 155, 165), "grey"), ((45, 45, 50), "black"),
]


def color_name(hex_color: str) -> str:
    """Ближайшее словесное имя цвета: модели нужен «зелёный», а не #2fa85e"""
    try:
        n = int(hex_color.lstrip("#"), 16)
        r, g, b = n >> 16 & 255, n >> 8 & 255, n & 255
    except ValueError:
        return ""
    return min(COLOR_NAMES,
               key=lambda c: (c[0][0]-r)**2 + (c[0][1]-g)**2 + (c[0][2]-b)**2)[1]


def scene_prompt(scene: dict, cast: dict) -> str:
    """Текст одного кадра: место, кто в нём и что делает.

    Каждому персонажу — отдельное предложение. В одном перечислении через
    «and» настроение и действие липнут не к тому, к кому относятся.
    """
    setting = SETTINGS.get(scene.get("bg"), SETTINGS["meadow"])

    # Действие берём из первого такта: кадр один, и показать он может только
    # один миг сцены — тот, ради которого она снята.
    beat = (scene.get("beats") or [{}])[0]

    lines = []
    for a in scene.get("actors", []):
        who = cast.get(a["id"], character(a)) + _size_clause(a.get("size", 1))
        who = who[:1].upper() + who[1:]
        if beat.get("actor") == a["id"]:
            lines.append(f"{who}, is {DOING.get(beat.get('action'), 'standing')}, "
                         f"{MOODS.get(beat.get('mood'), 'calm')}.")
        else:
            lines.append(f"{who}, stands nearby.")

    # Текст рассказчика в запрос не идёт: он на языке истории, а подмешивать
    # кириллицу в английский запрос — верный способ получить каракули в кадре.
    return f"{STYLE} Scene: {setting}. " + " ".join(lines)


def build_cast(board: dict) -> dict:
    """Описание каждого персонажа, общее для всех сцен"""
    cast = {}
    for scene in board.get("scenes", []):
        for a in scene.get("actors", []):
            if a["id"] not in cast:
                cast[a["id"]] = character(a)
    return cast


# =====================================================================
# ПОСТАВЩИКИ
# =====================================================================

async def _gemini(client: httpx.AsyncClient, prompt: str):
    key = os.environ["GEMINI_API_KEY"]
    r = await client.post(
        GEMINI_URL, params={"key": key},
        json={"contents": [{"parts": [{"text": prompt}]}]},
    )
    if r.status_code != 200:
        logging.error(f"Кадр: Gemini ответил {r.status_code}: {r.text[:200]}")
        return None
    for part in r.json().get("candidates", [{}])[0].get("content", {}).get("parts", []):
        blob = part.get("inlineData") or part.get("inline_data")
        if blob and blob.get("data"):
            return base64.b64decode(blob["data"]), blob.get("mimeType", "image/png")
    logging.error("Кадр: Gemini не вернул изображения")
    return None


async def _fal(client: httpx.AsyncClient, prompt: str):
    r = await client.post(
        FAL_URL, headers={"Authorization": f"Key {os.environ['FAL_KEY']}"},
        json={"prompt": prompt, "image_size": "landscape_4_3", "num_images": 1},
    )
    if r.status_code != 200:
        logging.error(f"Кадр: fal ответил {r.status_code}: {r.text[:200]}")
        return None
    images = r.json().get("images") or []
    if not images:
        logging.error("Кадр: fal не вернул изображения")
        return None
    got = await client.get(images[0]["url"])
    if got.status_code != 200:
        return None
    return got.content, images[0].get("content_type", "image/jpeg")


async def render(board: dict):
    """[(номер сцены, байты, тип)] — сколько кадров удалось нарисовать.

    Неудача отдельного кадра не отменяет остальные: сцена без картинки
    просто отыграется прежней векторной отрисовкой.
    """
    which = provider()
    if not which:
        return []

    cast = build_cast(board)
    prompts = [(i, scene_prompt(s, cast)) for i, s in enumerate(board.get("scenes", []))]
    draw = _gemini if which == "gemini" else _fal
    gate = asyncio.Semaphore(PARALLEL)
    out = []

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async def one(index, prompt):
            async with gate:
                try:
                    got = await draw(client, prompt)
                except Exception as e:
                    logging.error(f"Кадр {index}: {type(e).__name__}: {e}")
                    return
                if got:
                    out.append((index, got[0], got[1]))

        await asyncio.gather(*(one(i, p) for i, p in prompts))

    logging.info(f"Кадры ({which}): нарисовано {len(out)} из {len(prompts)}")
    return sorted(out)
