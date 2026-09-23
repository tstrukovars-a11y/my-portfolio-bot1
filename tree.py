# tree.py — разбор вопросами, собранный из своих же статей.
#
# Новость сама по себе не цепляет — цепляет вопрос, который она рождает.
# «Нашли мутацию в BRCA» остаётся шумом, пока человек не спросил себя «а
# у меня?». Дальше вопросы идут сами: носитель — это больной? риск —
# это сколько? что делают потом?
#
# Лонгрид с этими ответами человек закроет на третьем абзаце. Три кнопки
# подряд он пройдёт целиком, потому что каждое нажатие — его
# собственное. Материал тот же, разница только в том, кто ведёт.
#
# Дерево не пишется руками заново: оно собирается из статей раздела —
# тех, что уже написаны врачом-генетиком. Модель здесь не сочиняет
# содержание, а перекладывает написанное в вопросы и ответы. Поэтому:
#
#   • сборка запускается владелицей, а не сама;
#   • результат показывается ей до того, как его увидят люди;
#   • модели запрещено добавлять от себя, советовать и ставить диагнозы.
#
# Приписки «это не рекомендация» на экране нет намеренно. Объясняет врач
# своими же словами, и извинение от бота под её текстом выглядит так,
# будто сказанному нельзя верить.
import html
import json
import logging

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)

import config
import database

router = Router()

TREE_KEY = "genetics_tree"        # готовое дерево
DRAFT_KEY = "genetics_tree_draft"  # собранное, но не показанное людям
SECTION = "genetics"
MAX_NODES = 14                     # больше человек не проходит
MODEL = "claude-haiku-4-5-20251001"

PROMPT = (
    "Ты помогаешь врачу-генетику разложить её собственные статьи в "
    "короткий разговор с читателем.\n\n"
    "Сделай дерево из вопросов. Каждый узел — одна мысль в две-три "
    "строки и два-три варианта ответа. Читатель идёт по своим ответам и "
    "получает объяснение.\n\n"
    "Это не тест и не проверка знаний. У ответов нет верных и неверных: "
    "человек выбирает, о чём ему интересно, а не угадывает. Не хвали за "
    "выбор, не говори «правильно» и не предлагай пройти тест.\n\n"
    "Подписи кнопок — короткие, два-четыре слова, называют саму вещь: "
    "«Носительство», «Как считают риск», «У родственника». Без «хочу», "
    "«дальше», «расскажите», «узнать подробнее» — эти слова не несут "
    "смысла и удлиняют кнопку.\n\n"
    "Строгие правила:\n"
    "— бери только то, что есть в тексте статей; ничего не добавляй от "
    "себя, даже если знаешь;\n"
    "— объясняй, что значат слова, а не что человеку делать: никаких "
    "советов сдавать анализы, принимать лекарства или идти к врачу "
    "как рекомендации;\n"
    "— не ставь диагнозов и не оценивай риск конкретного человека;\n"
    "— пиши простыми словами: читатель не знает, что такое экзом;\n"
    "— спокойный тон, без «учёные доказали» и восклицаний.\n\n"
    "Каждая статья помечена номером в начале — [[12]]. В каждом узле "
    "укажи source: номер статьи, из которой он сделан.\n\n"
    "Ответь только JSON без пояснений:\n"
    '{"start": "id", "nodes": {"id": {"text": "вопрос или мысль", '
    '"source": 12, '
    '"options": [{"label": "короткий ответ", "next": "id другого узла"}]}}}\n\n'
    "У конечного узла options пустой, а text содержит объяснение. "
    f"Узлов не больше {MAX_NODES}."
)


# ---------------------------------------------------------------------
# ХРАНЕНИЕ
# ---------------------------------------------------------------------

async def tree(key: str = TREE_KEY) -> dict:
    raw = await database.get_setting(key)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) and data.get("nodes") else {}
    except (ValueError, TypeError):
        logging.error("Дерево разбора не читается")
        return {}


async def save_tree(data: dict, key: str = TREE_KEY):
    await database.set_setting(key, json.dumps(data, ensure_ascii=False))


def check(data: dict) -> str:
    """Что не так с деревом. Пусто — значит можно показывать.

    Проверяем до людей, а не после: дерево, где кнопка ведёт в
    несуществующий узел, обрывает разговор на середине, и человек решает,
    что сломано всё.
    """
    nodes = (data or {}).get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        return "нет узлов"
    start = data.get("start")
    if start not in nodes:
        return "начало указывает в никуда"
    if len(nodes) > MAX_NODES:
        return f"слишком много узлов: {len(nodes)}"

    for node_id, node in nodes.items():
        if not isinstance(node, dict) or not str(node.get("text", "")).strip():
            return f"узел {node_id} пуст"
        for option in node.get("options") or []:
            label = str(option.get("label", "")).strip()
            if not label:
                return f"в узле {node_id} безымянная кнопка"
            # Длинная подпись обрезается Телеграмом на середине слова, и
            # человек выбирает между двумя огрызками.
            if len(label) > 40:
                return f"в узле {node_id} слишком длинная кнопка: «{label[:30]}…»"
            if option.get("next") not in nodes:
                return f"из {node_id} ведёт в несуществующий {option.get('next')}"

    # Узел, из которого нет выхода и нет объяснения, — тупик. Разговор,
    # обрывающийся вопросом, хуже, чем его отсутствие.
    if not any(not (node.get("options") or []) for node in nodes.values()):
        return "нет ни одного конца — разговор не заканчивается"
    return ""


# Вводные слова модель приписывает даже там, где промпт их запрещает:
# «дальше хочу узнать про…», «расскажите подробнее о…». Смысла в них
# нет, а кнопку они удлиняют так, что название вещи не помещается.
# Предлог оставляем: «про носительство» читается, а «носительство» после
# «расскажите про» осталось бы в неверном падеже — склонять обратно
# нечем. Поэтому режем только глагольную часть.
FILLER = (
    "дальше хочу узнать", "я хочу узнать", "хочу узнать",
    "расскажите подробнее", "расскажи подробнее", "расскажите",
    "расскажи", "узнать подробнее", "хотелось бы узнать",
    "подробнее", "дальше", "хочу",
)


def tidy_label(text: str) -> str:
    """Кнопка без вводных слов и с заглавной буквы.

    Если от подписи ничего не остаётся — «подробнее» целиком вводное, —
    возвращаем как было: пустая кнопка хуже лишнего слова.
    """
    original = str(text or "").strip().strip("«»\"")
    said = original
    low = said.lower()
    for word in FILLER:
        if low.startswith(word):
            said = said[len(word):].lstrip(" ,:—-")
            break
    said = said.rstrip(" .!?")
    if not said:
        said = original.rstrip(" .!?")
    return (said[0].upper() + said[1:]) if said else said


def tidy(data: dict) -> dict:
    """Пройтись по всем подписям разом — после сборки, до показа"""
    for node in (data.get("nodes") or {}).values():
        for option in node.get("options") or []:
            option["label"] = tidy_label(option.get("label"))
    return data


def unreachable(data: dict) -> list:
    """Узлы, до которых не дойти. Не ошибка, но мёртвый груз."""
    nodes = data.get("nodes") or {}
    seen, queue = set(), [data.get("start")]
    while queue:
        node_id = queue.pop()
        if node_id in seen or node_id not in nodes:
            continue
        seen.add(node_id)
        queue += [o.get("next") for o in nodes[node_id].get("options") or []]
    return sorted(set(nodes) - seen)


# ---------------------------------------------------------------------
# СБОРКА
# ---------------------------------------------------------------------

async def source_text(limit: int = 12000):
    """(текст для модели, номера вошедших статей, номера отрезанных).

    Отрезанные считаем отдельно: статья, не попавшая даже в исходник,
    не могла оказаться в дереве, и знать об этом надо до того, как
    удивляться, почему темы нет.
    """
    rows = await database.get_articles_raw(SECTION)
    parts, took, left = [], [], []
    size = 0
    for article_id, title, text in rows:
        piece = f"{title or ''}\n{text or ''}".strip()
        if not piece:
            continue
        if size >= limit:
            left.append(article_id)
            continue
        parts.append(f"[[{article_id}]] {piece}")
        took.append(article_id)
        size += len(piece)
    return "\n\n---\n\n".join(parts), took, left


async def build() -> tuple:
    """(дерево, что пошло не так). Ничего не сохраняет."""
    source, took, cut = await source_text()
    if not source.strip():
        return {}, "в разделе нет статей — собирать не из чего"

    try:
        import block4_claude
        client = block4_claude.claude_client
    except Exception as e:
        return {}, f"клиент недоступен: {e}"
    if client is None:
        return {}, "нет ключа Anthropic"

    try:
        answer = await client.messages.create(
            model=MODEL, max_tokens=3000, system=PROMPT,
            messages=[{"role": "user", "content": source}])
        raw = (answer.content[0].text or "").strip()
    except Exception as e:
        return {}, f"{type(e).__name__}: {str(e)[:120]}"

    # Модель любит обернуть JSON в пояснения и в ```json — вырезаем то,
    # что между первой фигурной скобкой и последней.
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return {}, "ответ не похож на JSON"
    try:
        data = json.loads(raw[start:end + 1])
    except ValueError as e:
        return {}, f"JSON не разобрался: {e}"

    data = tidy(data)
    problem = check(data)
    if problem:
        return {}, problem
    # Запоминаем, что вообще показывали модели: без этого «не вошло»
    # неотличимо от «не поместилось в исходник».
    data["given"] = took
    data["cut"] = cut
    return data, ""


def used_articles(data: dict) -> set:
    """Номера статей, на которые опирается хоть один узел"""
    out = set()
    for node in (data.get("nodes") or {}).values():
        source = node.get("source")
        if source is None:
            continue
        try:
            out.add(int(source))
        except (TypeError, ValueError):
            continue
    return out


async def coverage(data: dict) -> dict:
    """Что из статей вошло в дерево, а что осталось за бортом.

    Дерево ограничено четырнадцатью узлами, а статей может быть втрое
    больше. Молчать об этом нельзя: автор считает, что тема раскрыта, а
    половины её в разговоре нет.
    """
    rows = await database.get_articles_raw(SECTION)
    titles = {article_id: (title or f"№{article_id}")
              for article_id, title, _ in rows}
    used = used_articles(data) & set(titles)
    cut = [x for x in (data.get("cut") or []) if x in titles]
    unused = [x for x in titles if x not in used and x not in cut]
    return {"all": len(titles), "used": sorted(used), "cut": cut,
            "unused": unused, "titles": titles}


# ---------------------------------------------------------------------
# РАЗГОВОР
# ---------------------------------------------------------------------

def _node_kb(node_id: str, node: dict, draft: bool) -> InlineKeyboardMarkup:
    prefix = "trd_" if draft else "tre_"
    rows = [[InlineKeyboardButton(text=str(option["label"])[:64],
                                  callback_data=f"{prefix}{option['next']}")]
            for option in (node.get("options") or [])]
    if not rows:
        # Конец ветки: отсюда либо заново, либо в раздел — но не в пустоту.
        rows.append([InlineKeyboardButton(text="🔁 Ещё раз",
                                          callback_data=f"{prefix}start")])
        rows.append([InlineKeyboardButton(text="🧬 Генетика в боте",
                                          callback_data="intellect_genetics")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show(message: Message, node_id: str, draft: bool = False,
               replace: bool = False):
    """Показать узел.

    Шаг разговора заменяет предыдущий, а не добавляет новый: иначе
    переписка заполняется вопросами, на которые уже ответили, и человек
    перестаёт понимать, где он находится.

    Картинка мешает замене — сообщение с фотографией нельзя превратить в
    текстовое. Поэтому узел с картинкой присылается новым сообщением, а
    старое убирается.
    """
    data = await tree(DRAFT_KEY if draft else TREE_KEY)
    nodes = data.get("nodes") or {}
    if node_id == "start":
        node_id = data.get("start")
    node = nodes.get(node_id)
    if not node:
        await message.answer("Этот разбор больше недоступен.")
        return

    text = html.escape(str(node.get("text", "")))
    markup = _node_kb(node_id, node, draft)
    photo = await _photo_of(node)

    if replace:
        if not photo and not getattr(message, "photo", None):
            try:
                await message.edit_text(text, reply_markup=markup)
                return
            except Exception:
                pass
        try:
            await message.delete()
        except Exception:
            # Старое сообщение удаляется не всегда: через двое суток
            # Telegram уже не даёт. Тогда просто снимаем кнопки, чтобы на
            # него нельзя было нажать второй раз.
            try:
                await message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

    if photo:
        await message.answer_photo(photo, caption=text[:1024],
                                   reply_markup=markup)
        return
    await message.answer(text, reply_markup=markup)


async def _photo_of(node: dict):
    """Картинка статьи, из которой сделан узел"""
    source = node.get("source")
    if not source:
        return None
    try:
        row = await database.get_article(int(source))
    except (TypeError, ValueError):
        return None
    # get_article отдаёт (title, text, photo, video, link)
    return row[2] if row and len(row) > 2 else None


@router.message(F.text.regexp(r"^/(разбор|explain)\b"))
async def start_command(message: Message):
    if not await tree():
        await message.answer("Разбор пока не собран.")
        return
    await show(message, "start")


@router.callback_query(F.data == "tree_open")
async def open_tree(call: CallbackQuery):
    await call.answer()
    if not await tree():
        await call.answer("Разбор пока не собран", show_alert=True)
        return
    await show(call.message, "start")


@router.callback_query(F.data.startswith("tre_"))
async def step(call: CallbackQuery):
    await call.answer()
    await show(call.message, call.data[len("tre_"):], replace=True)


@router.callback_query(F.data.startswith("trd_"))
async def step_draft(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await show(call.message, call.data[len("trd_"):], draft=True, replace=True)


# ---------------------------------------------------------------------
# СЛУЖЕБНОЕ
# ---------------------------------------------------------------------

async def coverage_text(data: dict) -> str:
    """Охват словами: сколько тем вошло и какие остались"""
    got = await coverage(data)
    if not got["all"]:
        return "Статей в разделе нет."

    lines = [f"📚 <b>Охват</b>: {len(got['used'])} статей из {got['all']}"]

    def names(ids):
        shown = [html.escape(got["titles"][x][:36]) for x in ids[:8]]
        more = f" и ещё {len(ids) - 8}" if len(ids) > 8 else ""
        return "\n".join(f"• {name}" for name in shown) + more

    if got["unused"]:
        lines += ["", f"<b>Не вошли ({len(got['unused'])})</b> — модель их "
                  f"видела, но места не хватило:", names(got["unused"])]
    if got["cut"]:
        lines += ["", f"<b>Не дошли до модели ({len(got['cut'])})</b> — "
                  f"исходник ограничен размером:", names(got["cut"])]
    if not got["unused"] and not got["cut"]:
        lines.append("\nВошло всё.")
    else:
        lines.append("\n<i>Дерево держится на четырнадцати узлах: длинное "
                     "никто не проходит. Чтобы охватить остальное, стоит "
                     "собрать второе дерево по другим статьям.</i>")
    return "\n".join(lines)


@router.message(F.text.regexp(r"^/дерево"))
async def tree_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=1)
    action = parts[1].strip().lower() if len(parts) > 1 else ""

    if action in ("собрать", "build"):
        await message.answer("Собираю из статей раздела…")
        data, problem = await build()
        if problem:
            await message.answer(f"⚠️ Не вышло: {html.escape(problem)}")
            return
        await save_tree(data, DRAFT_KEY)
        lost = unreachable(data)
        note = (f"\nНедостижимых узлов: {len(lost)} — {', '.join(lost)}"
                if lost else "")
        await message.answer(
            f"✅ Собрала: узлов {len(data['nodes'])}.{note}\n\n"
            + await coverage_text(data) +
            f"\n\nПосмотрите черновик — <code>/дерево черновик</code>. "
            f"Людям он пока не виден.\n"
            f"Опубликовать: <code>/дерево опубликовать</code>")
        return

    if action in ("охват", "coverage"):
        data = await tree(DRAFT_KEY) or await tree(TREE_KEY)
        if not data:
            await message.answer("Дерева пока нет.")
            return
        await message.answer(await coverage_text(data))
        return

    if action in ("черновик", "draft"):
        draft = await tree(DRAFT_KEY)
        if not draft:
            await message.answer("Черновика нет. Собрать: "
                                 "<code>/дерево собрать</code>")
            return
        await show(message, "start", draft=True)
        return

    if action in ("опубликовать", "publish"):
        draft = await tree(DRAFT_KEY)
        problem = check(draft)
        if problem:
            await message.answer(f"⚠️ Публиковать нельзя: {html.escape(problem)}")
            return
        await save_tree(draft, TREE_KEY)
        await message.answer("✅ Опубликовано. Читателям — <code>/разбор</code>.")
        return

    if action in ("убрать", "off"):
        await database.set_setting(TREE_KEY, "")
        await message.answer("Убрала. Людям разбор больше не показывается.")
        return

    live = await tree()
    draft = await tree(DRAFT_KEY)
    await message.answer(
        "🌳 <b>Разбор вопросами</b>\n\n"
        f"Показывается людям: {len(live.get('nodes') or {})} узлов\n"
        f"Черновик: {len(draft.get('nodes') or {})} узлов\n\n"
        "Собирается из ваших статей раздела «генетика». Модель не "
        "сочиняет содержание — она перекладывает написанное в вопросы.\n\n"
        "<code>/дерево собрать</code> — заново из статей\n"
        "<code>/дерево охват</code> — что вошло, а что нет\n"
        "<code>/дерево черновик</code> — пройти самой\n"
        "<code>/дерево опубликовать</code> — показать людям\n"
        "<code>/дерево убрать</code> — скрыть")
