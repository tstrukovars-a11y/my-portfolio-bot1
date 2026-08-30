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
import urllib.parse

import httpx

TIMEOUT = 90
PARALLEL = 3          # больше — упираемся в лимиты, меньше — долго ждать

# Имя модели вынесено в переменную окружения: у Google оно меняется от
# версии к версии, и подобрать верное должно быть можно без выкладки кода.
GEMINI_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
FAL_URL = "https://fal.run/fal-ai/flux/schnell"


def gemini_url(model: str = None) -> str:
    return f"{GEMINI_BASE}/models/{model or GEMINI_MODEL}:generateContent"


# Порядок перебора: от самых дешёвых к дорогим. У бесплатного доступа квота
# на картинки разная у разных моделей, и облегчённая часто работает там, где
# старшая отвечает «квота исчерпана».
PREFERRED = [
    "gemini-3.1-flash-lite-image",
    "gemini-3.1-flash-image",
    "gemini-2.5-flash-image",
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image",
    "gemini-3-pro-image-preview",
]

# Найденная рабочая модель запоминается на время жизни процесса: искать её
# заново перед каждым кадром значит тратить квоту на заведомые отказы.
_working = None


async def image_models(client: httpx.AsyncClient) -> list:
    """Картиночные модели аккаунта, от дешёвых к дорогим"""
    try:
        r = await client.get(f"{GEMINI_BASE}/models",
                             params={"key": os.environ.get("GEMINI_API_KEY", "")})
        if r.status_code != 200:
            return []
        names = [m.get("name", "").replace("models/", "") for m in r.json().get("models", [])]
    except Exception as e:
        logging.error(f"Кадр: список моделей недоступен: {e}")
        return []

    have = [n for n in names if "image" in n]
    ordered = [n for n in PREFERRED if n in have]
    ordered += [n for n in have if n not in ordered]
    # Заданная владельцем модель идёт первой, если она вообще есть
    if GEMINI_MODEL in ordered:
        ordered.remove(GEMINI_MODEL)
        ordered.insert(0, GEMINI_MODEL)
    return ordered

# Общий для всех кадров зачин. Стиль задаётся один раз и слово в слово:
# любое расхождение в описании стиля — и соседние сцены выглядят из разных
# мультфильмов.
# Стиль разрезан надвое намеренно. Короткий якорь идёт в начало запроса,
# где внимание модели наибольшее, — иначе картинка выходит в чужой манере.
# Подробности уезжают в конец, чтобы не оттеснять героев из начала.
STYLE_LEAD = "Children's storybook illustration, soft gouache painting."
STYLE_TAIL = ("Warm lighting, clean rounded shapes, gentle outlines, friendly faces, "
              "wide cinematic composition. No text, no letters, no watermark.")
STYLE = STYLE_LEAD + " " + STYLE_TAIL


def providers() -> list:
    """Поставщики, у которых есть ключ, в порядке предпочтения.

    Порядок важен: у Gemini ключ может лежать с бесплатных времён и давать
    сплошной отказ по квоте. Если рядом есть второй ключ, надо переходить
    к нему, а не упираться в первый.
    """
    have = []
    if os.environ.get("FAL_KEY"):
        have.append("fal")
    if os.environ.get("GEMINI_API_KEY"):
        have.append("gemini")
    # Бесплатный рисовальщик идёт последним и не требует ключа вовсе. Он
    # медленнее и без обещаний доступности, но позволяет увидеть результат
    # до всякой оплаты — и остаётся страховкой, когда платный отказал.
    have.append("free")

    prefer = os.environ.get("IMAGE_PROVIDER", "").strip().lower()
    if prefer in have:
        have.remove(prefer)
        have.insert(0, prefer)
    return have


def provider() -> str:
    """Первый доступный поставщик либо пусто — для тех, кому нужен один ответ"""
    got = providers()
    return got[0] if got else ""


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
        return ", enormous, towering over everyone else"
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

    # Действующий персонаж идёт первым и с действием, остальные следом.
    # Порядок решает: модель дописывает картинку слева направо по тексту и
    # то, что стоит в конце длинного запроса, попросту не рисует — так из
    # кадра пропал дракон, ради которого сцена и снималась.
    actors = list(scene.get("actors", []))
    actors.sort(key=lambda a: a["id"] != beat.get("actor"))

    parts = []
    for i, a in enumerate(actors):
        who = cast.get(a["id"], character(a)) + _size_clause(a.get("size", 1))
        if i == 0 and beat.get("actor") == a["id"]:
            parts.append(f"{who}, {DOING.get(beat.get('action'), 'standing')}, "
                         f"{MOODS.get(beat.get('mood'), 'calm')}")
        else:
            parts.append(who)

    count = {1: "One character", 2: "Two characters", 3: "Three characters"}.get(
        len(parts), f"{len(parts)} characters")
    who_line = f"{count} in one picture: " + "; and ".join(parts) if len(parts) > 1 \
        else parts[0] if parts else "an empty landscape"

    # Текст рассказчика в запрос не идёт: он на языке истории, а подмешивать
    # кириллицу в английский запрос — верный способ получить каракули в кадре.
    # Стиль в конце: начало запроса модель слушает внимательнее, и тратить
    # его на манеру рисования вместо героев — значит терять героев.
    return f"{STYLE_LEAD} {who_line}. Setting: {setting}. {STYLE_TAIL}"


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

def _picture(payload):
    """Достаёт картинку из ответа Gemini, как бы он её ни назвал"""
    for cand in payload.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            blob = part.get("inlineData") or part.get("inline_data")
            if blob and blob.get("data"):
                return (base64.b64decode(blob["data"]),
                        blob.get("mimeType") or blob.get("mime_type") or "image/png")
    return None


async def _gemini_call(client: httpx.AsyncClient, prompt: str, model: str = None):
    """(картинка, описание ошибки). Описание нужно, чтобы проверка могла
    показать владельцу настоящую причину, а не «не получилось»."""
    key = os.environ.get("GEMINI_API_KEY", "")
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        # Без этого поля модель отвечает текстом «вот ваша картинка» и
        # никакой картинки. С ним — картинкой. Старые версии поля не знают,
        # поэтому при отказе повторяем без него.
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    for attempt in (body, {"contents": body["contents"]}):
        r = await client.post(gemini_url(model), params={"key": key}, json=attempt)
        if r.status_code == 200:
            got = _picture(r.json())
            if got:
                return got, None
            return None, "ответ без изображения: " + r.text[:200]
        if r.status_code != 400:
            return None, f"HTTP {r.status_code}: {r.text[:200]}"
    return None, f"HTTP 400: {r.text[:250]}"


async def _gemini(client: httpx.AsyncClient, prompt: str):
    """Рисует кадр, перебирая модели, пока не найдётся та, где есть квота.

    Отказ по квоте (429) — не поломка, а свойство бесплатного доступа: на
    одной модели лимит исчерпан, на соседней ещё есть. Поэтому перебираем,
    а найденную запоминаем.
    """
    global _working

    if _working:
        got, error = await _gemini_call(client, prompt, _working)
        if got:
            return got
        logging.warning(f"Кадр: модель {_working} перестала отвечать — {error}")
        _working = None

    for model in await image_models(client) or [GEMINI_MODEL]:
        got, error = await _gemini_call(client, prompt, model)
        if got:
            if model != _working:
                logging.info(f"Кадры рисует модель {model}")
            _working = model
            return got
        logging.warning(f"Кадр: {model} — {error}")
    return None


async def diagnose():
    """Строки отчёта для команды проверки: что с ключами, моделями и запросом"""
    out = []
    fal_key = os.environ.get("FAL_KEY", "")
    key = os.environ.get("GEMINI_API_KEY", "")
    out.append("Порядок поставщиков: " + (", ".join(providers()) or "ни одного ключа"))
    out.append("")

    if fal_key:
        out.append(f"FAL_KEY: виден, {len(fal_key)} знаков")
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            try:
                got = await _fal(client, STYLE + " Scene: a sunny meadow. A green dragon stands nearby.")
                out.append("fal.ai: " + (f"РАБОТАЕТ, {len(got[0]) // 1024} КБ" if got
                                         else "не вернул кадр, подробности в логах"))
            except Exception as e:
                out.append(f"fal.ai: {type(e).__name__}: {str(e)[:120]}")
        out.append("")

    out.append(f"Ключ GEMINI_API_KEY: {'виден, ' + str(len(key)) + ' знаков' if key else 'НЕ ЗАДАН'}")
    out.append(f"Модель: {GEMINI_MODEL}")
    if not key:
        return out

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.get(f"{GEMINI_BASE}/models", params={"key": key})
            if r.status_code != 200:
                out.append(f"Список моделей: HTTP {r.status_code} — {r.text[:160]}")
            else:
                names = [m.get("name", "").replace("models/", "")
                         for m in r.json().get("models", [])]
                image = [n for n in names if "image" in n]
                out.append(f"Моделей доступно: {len(names)}")
                out.append("С картинками: " + (", ".join(image[:8]) if image else "ни одной"))
                out.append("Нужная модель в списке: "
                           + ("да" if GEMINI_MODEL in names else "НЕТ"))
        except Exception as e:
            out.append(f"Список моделей: {type(e).__name__}: {e}")

        # Перебираем модели по очереди: важно не «работает ли Gemini вообще»,
        # а какая именно модель доступна этому аккаунту прямо сейчас.
        probe = STYLE + " Scene: a sunny meadow. A green dragon stands nearby."
        out.append("")
        found = None
        for model in await image_models(client) or [GEMINI_MODEL]:
            if found:
                out.append(f"{model}: не проверяли")
                continue
            try:
                got, error = await _gemini_call(client, probe, model)
            except Exception as e:
                out.append(f"{model}: {type(e).__name__}")
                continue
            if got:
                found = model
                out.append(f"{model}: РАБОТАЕТ, {len(got[0]) // 1024} КБ")
            elif "429" in (error or ""):
                out.append(f"{model}: квота исчерпана")
            else:
                out.append(f"{model}: {(error or '')[:90]}")

        out.append("")
        out.append("Итог: рисуем моделью " + found if found
                   else "Итог: ни одна модель не доступна — нужен платёжный аккаунт")
    return out


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


FREE_URL = "https://image.pollinations.ai/prompt/"


async def _free(client: httpx.AsyncClient, prompt: str):
    """Бесплатный рисовальщик без ключа.

    Отдаёт картинку прямо в ответ на GET, поэтому обходится без учётной
    записи. Взамен — ни скорости, ни гарантий: отказ здесь ожидаем и
    просто означает, что сцена отыграется векторно.
    """
    url = FREE_URL + urllib.parse.quote(prompt[:1400], safe="")
    r = await client.get(url, params={"width": 1024, "height": 768,
                                      "nologo": "true", "model": "flux"})
    if r.status_code != 200:
        logging.error(f"Кадр: бесплатный рисовальщик ответил {r.status_code}")
        return None
    if not r.content or not r.headers.get("content-type", "").startswith("image/"):
        logging.error("Кадр: бесплатный рисовальщик вернул не картинку")
        return None
    return r.content, r.headers.get("content-type", "image/jpeg")


async def render(board: dict):
    """[(номер сцены, байты, тип)] — сколько кадров удалось нарисовать.

    Неудача отдельного кадра не отменяет остальные: сцена без картинки
    просто отыграется прежней векторной отрисовкой.
    """
    available = providers()
    if not available:
        return []

    cast = build_cast(board)
    prompts = [(i, scene_prompt(s, cast)) for i, s in enumerate(board.get("scenes", []))]
    gate = asyncio.Semaphore(PARALLEL)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Если первый поставщик не дал ни одного кадра — пробуем следующего.
        # Частичная удача второй попытки не нужна: перерисовывать уже готовое
        # значит платить дважды.
        for which in available:
            draw = {"gemini": _gemini, "fal": _fal, "free": _free}[which]
            out = []

            async def one(index, prompt):
                async with gate:
                    try:
                        got = await draw(client, prompt)
                    except Exception as e:
                        logging.error(f"Кадр {index} ({which}): {type(e).__name__}: {e}")
                        return
                    if got:
                        out.append((index, got[0], got[1]))

            await asyncio.gather(*(one(i, p) for i, p in prompts))
            logging.info(f"Кадры ({which}): нарисовано {len(out)} из {len(prompts)}")
            if out:
                return sorted(out)

    return []
