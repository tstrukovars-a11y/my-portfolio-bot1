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

# Два вида разбора. Механика одна — вопросы, ветки, переходы, — а
# отличаются они источником и сроком жизни.
#
# Генетика собирается из статей и живёт месяцами: что такое ген, не
# меняется к четвергу. Экономика собирается из событий дня и устаревает
# вместе с ними — её пересобирают каждое утро, и вчерашняя сборка в ней
# бесполезна так же, как вчерашняя газета.
KINDS = {
    "g": {"title": "🧬 Генетика", "live": "genetics_tree",
          "draft": "genetics_tree_draft", "articles": True},
    "e": {"title": "📊 Экономика", "live": "economy_tree",
          "draft": "economy_tree_draft", "articles": False},
}


def keys(kind: str) -> tuple:
    meta = KINDS.get(kind) or KINDS["g"]
    return meta["live"], meta["draft"]
MAX_NODES = 14                     # больше человек не проходит
MAX_TREES = 5                      # больше тем на входе — снова список, который листают
MODEL = "claude-haiku-4-5-20251001"

PROMPT = (
    "Ты помогаешь врачу-генетику разложить её собственные статьи в "
    "короткие разговоры с читателем.\n\n"
    "Сгруппируй статьи по темам и сделай на каждую тему своё дерево "
    "вопросов. Дерево — это узлы: одна мысль в две-три строки и два-три "
    "варианта ответа. Читатель идёт по своим ответам и получает "
    "объяснение.\n\n"
    "Темы пересекаются, и это хорошо: если в одном дереве человек "
    "упирается в тему соседнего, дай кнопку с переходом туда — "
    "go: «id другого дерева». Так разговор продолжается, а не обрывается "
    "на «об этом в другой раз».\n\n"
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
    '{"trees": {"gen": {"title": "Что такое ген", "start": "a", '
    '"nodes": {"a": {"text": "мысль", "source": 12, "options": '
    '[{"label": "Короткий ответ", "next": "b"}, '
    '{"label": "Про риск", "go": "risk"}]}}}}}\n\n'
    "У конечного узла options пустой, а text содержит объяснение. "
    f"Деревьев от двух до {MAX_TREES}, узлов в каждом не больше "
    f"{MAX_NODES}."
)


ECONOMY_PROMPT = (
    "Ты помогаешь автору делового телеграм-канала объяснить сегодняшние "
    "новости обычному человеку.\n\n"
    "Начни с главного вопроса: как это касается лично его. Первый узел "
    "каждого дерева — про положение читателя, а не про рынок: он "
    "наёмный работник, у него своё дело, он копит или тратит в валюте. "
    "От его ответа и разворачивается объяснение.\n\n"
    "Дальше — связь события с цифрой: почему индекс двинулся именно "
    "так, что стоит за движением. Объясняй механику, а не итог.\n\n"
    "Сгруппируй по темам и сделай на каждую своё дерево. Где тема "
    "упирается в соседнюю, ставь переход go: «id другого дерева».\n\n"
    "Это не тест и не проверка знаний. У ответов нет верных и неверных. "
    "Подписи кнопок — два-четыре слова, без «хочу», «дальше», "
    "«расскажите».\n\n"
    "Строгие правила:\n"
    "— бери только то, что есть в заголовках и цифрах ниже; ничего не "
    "додумывай, не вспоминай прошлые события;\n"
    "— никаких советов покупать, продавать, вкладывать, переводить "
    "сбережения или менять валюту — ни прямо, ни намёком;\n"
    "— не называй отдельные компании как удачную или неудачную покупку;\n"
    "— не предсказывай, что будет дальше: объясняй, что уже случилось;\n"
    "— спокойный тон, без паники и без восторга.\n\n"
    "Ответь только JSON без пояснений:\n"
    '{"trees": {"rate": {"title": "Ставка и ваши деньги", "start": "a", '
    '"nodes": {"a": {"text": "мысль", "options": '
    '[{"label": "Короткий ответ", "next": "b"}]}}}}}\n\n'
    "У конечного узла options пустой, а text содержит объяснение. "
    f"Деревьев от двух до {MAX_TREES}, узлов в каждом не больше "
    f"{MAX_NODES}."
)


# ---------------------------------------------------------------------
# ХРАНЕНИЕ
# ---------------------------------------------------------------------

async def tree(key: str = TREE_KEY, kind: str = None) -> dict:
    if kind:
        key = keys(kind)[1] if key == "draft" else keys(kind)[0]
    raw = await database.get_setting(key)
    if not raw:
        return {}
    try:
        data = normalise(json.loads(raw))
        return data if data.get("trees") else {}
    except (ValueError, TypeError):
        logging.error("Дерево разбора не читается")
        return {}


async def save_tree(data: dict, key: str = TREE_KEY, kind: str = None):
    if kind:
        key = keys(kind)[1] if key == "draft" else keys(kind)[0]
    await database.set_setting(key, json.dumps(data, ensure_ascii=False))


def normalise(data: dict) -> dict:
    """Привести к виду «несколько деревьев».

    Первое дерево собиралось одно и лежало без обёртки. Старую запись
    не выбрасываем: она превращается в набор из одного дерева, и человек
    ничего не замечает.
    """
    if not isinstance(data, dict):
        return {}
    if data.get("trees"):
        return data
    if data.get("nodes"):
        return {"trees": {"main": {"title": "Разбор", **data}},
                "given": data.get("given") or [], "cut": data.get("cut") or []}
    return {}


def compact(data: dict) -> dict:
    """Переименовать деревья и узлы в короткие имена.

    Модель называет узлы как хочет — «что_такое_ген_подробнее». Такое имя
    не помещается в callback_data (64 байта на всё), и кнопка молча
    перестаёт работать. Переименовываем сами: t1/n3 влезут всегда.
    """
    trees = data.get("trees") or {}
    tree_names = {old: f"t{i}" for i, old in enumerate(trees, 1)}

    out = {}
    for old_tree, tree_body in trees.items():
        nodes = tree_body.get("nodes") or {}
        node_names = {old: f"n{i}" for i, old in enumerate(nodes, 1)}
        new_nodes = {}
        for old_node, node in nodes.items():
            options = []
            for option in node.get("options") or []:
                fresh = {"label": option.get("label", "")}
                if option.get("go") in tree_names:
                    fresh["go"] = tree_names[option["go"]]
                elif option.get("next") in node_names:
                    fresh["next"] = node_names[option["next"]]
                else:
                    continue          # ведёт в никуда — кнопку не рисуем
                options.append(fresh)
            new_nodes[node_names[old_node]] = {
                "text": node.get("text", ""),
                "source": node.get("source"),
                "options": options,
            }
        out[tree_names[old_tree]] = {
            "title": str(tree_body.get("title") or "Разбор")[:40],
            "start": node_names.get(tree_body.get("start"),
                                    next(iter(new_nodes), "")),
            "nodes": new_nodes,
        }
    return {"trees": out, "given": data.get("given") or [],
            "cut": data.get("cut") or []}


def check(data: dict) -> str:
    """Что не так. Пусто — значит можно показывать.

    Проверяем до людей, а не после: кнопка в несуществующий узел
    обрывает разговор на середине, и человек решает, что сломано всё.
    """
    trees = (data or {}).get("trees")
    if not isinstance(trees, dict) or not trees:
        return "нет деревьев"
    if len(trees) > MAX_TREES:
        return f"слишком много тем: {len(trees)}"

    for tree_id, body in trees.items():
        if not str(body.get("title") or "").strip():
            return f"дерево {tree_id} без названия"
        nodes = body.get("nodes")
        if not isinstance(nodes, dict) or not nodes:
            return f"в дереве {tree_id} нет узлов"
        if body.get("start") not in nodes:
            return f"в дереве {tree_id} начало указывает в никуда"
        if len(nodes) > MAX_NODES:
            return f"в дереве {tree_id} слишком много узлов: {len(nodes)}"

        for node_id, node in nodes.items():
            if not isinstance(node, dict) or not str(node.get("text", "")).strip():
                return f"узел {tree_id}/{node_id} пуст"
            for option in node.get("options") or []:
                label = str(option.get("label", "")).strip()
                if not label:
                    return f"в узле {tree_id}/{node_id} безымянная кнопка"
                # Длинная подпись обрезается Телеграмом на середине слова,
                # и человек выбирает между двумя огрызками.
                if len(label) > 40:
                    return (f"в узле {tree_id}/{node_id} слишком длинная "
                            f"кнопка: «{label[:30]}…»")
                if option.get("go"):
                    if option["go"] not in trees:
                        return (f"из {tree_id}/{node_id} переход в "
                                f"несуществующее дерево {option['go']}")
                elif option.get("next") not in nodes:
                    return (f"из {tree_id}/{node_id} ведёт в несуществующий "
                            f"{option.get('next')}")

        # Узел без выхода и без объяснения — тупик. Разговор,
        # обрывающийся вопросом, хуже, чем его отсутствие.
        if not any(not (node.get("options") or []) for node in nodes.values()):
            return f"в дереве {tree_id} нет ни одного конца"
    return ""


def unreachable(data: dict) -> list:
    """Узлы, до которых не дойти. Не ошибка, но мёртвый груз."""
    lost = []
    for tree_id, body in (data.get("trees") or {}).items():
        nodes = body.get("nodes") or {}
        seen, queue = set(), [body.get("start")]
        while queue:
            node_id = queue.pop()
            if node_id in seen or node_id not in nodes:
                continue
            seen.add(node_id)
            queue += [o.get("next") for o in nodes[node_id].get("options") or []
                      if o.get("next")]
        lost += [f"{tree_id}/{x}" for x in sorted(set(nodes) - seen)]
    return lost


# Вводные слова модель приписывает даже там, где промпт их запрещает:
# «дальше хочу узнать про…». Смысла в них нет, а кнопку они удлиняют так,
# что название вещи не помещается.
#
# Предлог оставляем: «носительство» после «расскажите про» осталось бы в
# неверном падеже — склонять обратно нечем. Режем только глагольную часть.
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
    for body in (data.get("trees") or {}).values():
        for node in (body.get("nodes") or {}).values():
            for option in node.get("options") or []:
                option["label"] = tidy_label(option.get("label"))
    return data


def crossings(data: dict) -> list:
    """Переходы между деревьями: («откуда», «куда», подпись)"""
    out = []
    trees = data.get("trees") or {}
    for tree_id, body in trees.items():
        for node in (body.get("nodes") or {}).values():
            for option in node.get("options") or []:
                if option.get("go") in trees:
                    out.append((body.get("title", tree_id),
                                trees[option["go"]].get("title", option["go"]),
                                option.get("label", "")))
    return out


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


async def economy_source() -> str:
    """Сегодняшние заголовки и движение индексов — одним куском.

    Цифры идут вместе с новостями не для красоты: разбор строится на
    связи «событие → движение», и без чисел модель объяснит одно, а
    рынок в этот день делал другое.
    """
    parts = []
    try:
        import digest
        headlines = await digest._news_text(await digest._news_country())
        if headlines:
            parts.append("СЕГОДНЯШНИЕ ЗАГОЛОВКИ:\n" + headlines)
    except Exception as e:
        logging.warning(f"Экономика: заголовки не прочитались: {e}")

    try:
        import indices
        series = await indices.fetch_series()
        rows = []
        for symbol, meta in indices.INDICES.items():
            closes = series.get(symbol)
            if not closes:
                continue
            day, month = indices.moves(closes)
            rows.append(f"{meta['ru']}: {closes[-1]:.0f}, "
                        f"{day:+.2f}% за сутки, {month:+.1f}% за месяц")
        if rows:
            parts.append("ИНДЕКСЫ:\n" + "\n".join(rows))
    except Exception as e:
        logging.warning(f"Экономика: индексы не прочитались: {e}")

    return "\n\n".join(parts)


async def build(kind: str = "g") -> tuple:
    """(дерево, что пошло не так). Ничего не сохраняет."""
    if KINDS[kind]["articles"]:
        source, took, cut = await source_text()
        prompt = PROMPT
        empty = "в разделе нет статей — собирать не из чего"
    else:
        source, took, cut = await economy_source(), [], []
        prompt = ECONOMY_PROMPT
        empty = "нет ни заголовков, ни индексов — собирать не из чего"
    if not source.strip():
        return {}, empty

    try:
        import block4_claude
        client = block4_claude.claude_client
    except Exception as e:
        return {}, f"клиент недоступен: {e}"
    if client is None:
        return {}, "нет ключа Anthropic"

    try:
        answer = await client.messages.create(
            model=MODEL, max_tokens=3000, system=prompt,
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

    data = tidy(compact(normalise(data)))
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
    for body in (data.get("trees") or {}).values():
        for node in (body.get("nodes") or {}).values():
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

def _node_kb(kind: str, tree_id: str, node: dict,
             draft: bool) -> InlineKeyboardMarkup:
    prefix = ("trd_" if draft else "tre_") + kind + "_"
    rows = []
    for option in node.get("options") or []:
        if option.get("go"):
            # Переход в соседнюю тему: туда же, но с её начала.
            target = f"{option['go']}_start"
        else:
            target = f"{tree_id}_{option['next']}"
        rows.append([InlineKeyboardButton(text=str(option["label"])[:64],
                                          callback_data=prefix + target)])
    if not rows:
        # Конец ветки: отсюда либо в другую тему, либо в раздел — но не
        # в пустоту. Человек дочитал и должен видеть, куда идти дальше.
        rows.append([InlineKeyboardButton(text="📚 Другие темы",
                                          callback_data=prefix + "list")])
        home = ("intellect_genetics" if kind == "g" else "go_home")
        rows.append([InlineKeyboardButton(
            text=KINDS[kind]["title"] + " в боте", callback_data=home)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _list_kb(kind: str, data: dict, draft: bool) -> InlineKeyboardMarkup:
    prefix = ("trd_" if draft else "tre_") + kind + "_"
    rows = [[InlineKeyboardButton(text=body.get("title", tree_id)[:60],
                                  callback_data=f"{prefix}{tree_id}_start")]
            for tree_id, body in (data.get("trees") or {}).items()]
    rows.append([InlineKeyboardButton(text="⇦", callback_data="go_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


LIST_TEXT = ("🌳 <b>{title}: разбор вопросами</b>\n\n"
             "С чего начать? Темы связаны между собой — из любой можно "
             "перейти в соседнюю, когда до неё дойдёт разговор.")


async def show_list(message: Message, kind: str = "g", draft: bool = False,
                    replace: bool = False):
    data = await tree("draft" if draft else "live", kind)
    if not data:
        await message.answer("Разбор пока не собран.")
        return
    text = LIST_TEXT.format(title=KINDS[kind]["title"])
    markup = _list_kb(kind, data, draft)
    if replace:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except Exception:
            try:
                await message.delete()
            except Exception:
                pass
    await message.answer(text, reply_markup=markup)


async def show(message: Message, where: str, kind: str = "g",
               draft: bool = False, replace: bool = False):
    """Показать узел. where — «дерево_узел».

    Шаг разговора заменяет предыдущий, а не добавляет новый: иначе
    переписка заполняется вопросами, на которые уже ответили, и человек
    перестаёт понимать, где он находится.

    Картинка мешает замене — сообщение с фотографией нельзя превратить в
    текстовое. Поэтому узел с картинкой присылается новым сообщением, а
    старое убирается.
    """
    if where == "list":
        await show_list(message, kind, draft, replace)
        return

    data = await tree("draft" if draft else "live", kind)
    tree_id, _, node_id = where.partition("_")
    body = (data.get("trees") or {}).get(tree_id)
    if not body:
        await message.answer("Этот разбор больше недоступен.")
        return
    if node_id in ("", "start"):
        node_id = body.get("start")
    node = (body.get("nodes") or {}).get(node_id)
    if not node:
        await message.answer("Этот разбор больше недоступен.")
        return

    text = html.escape(str(node.get("text", "")))
    markup = _node_kb(kind, tree_id, node, draft)
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
    await show_list(message, "g")


@router.callback_query(F.data.in_({"tree_open", "eco_open"}))
async def open_tree(call: CallbackQuery):
    await call.answer()
    await show_list(call.message, "g" if call.data == "tree_open" else "e")


@router.callback_query(F.data.startswith("tre_"))
async def step(call: CallbackQuery):
    kind, _, where = call.data[len("tre_"):].partition("_")
    await call.answer()
    if kind not in KINDS:
        return
    await show(call.message, where, kind, replace=True)


@router.callback_query(F.data.startswith("trd_"))
async def step_draft(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    kind, _, where = call.data[len("trd_"):].partition("_")
    await call.answer()
    if kind not in KINDS:
        return
    await show(call.message, where, kind, draft=True, replace=True)


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


@router.message(F.text.regexp(r"^/(дерево|эконом)"))
async def tree_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return

    kind = "e" if (message.text or "").startswith("/эконом") else "g"
    parts = (message.text or "").split(maxsplit=1)
    action = parts[1].strip().lower() if len(parts) > 1 else ""
    name = KINDS[kind]["title"]

    if action in ("собрать", "build"):
        await message.answer("Собираю…")
        data, problem = await build(kind)
        if problem:
            await message.answer(f"⚠️ Не вышло: {html.escape(problem)}")
            return
        await save_tree(data, "draft", kind)
        trees = data.get("trees") or {}
        links = crossings(data)
        lost = unreachable(data)
        note = (f"\nНедостижимых узлов: {len(lost)} — {', '.join(lost)}"
                if lost else "")
        note += (f"\nПереходов между темами: {len(links)}" if links else
                 "\nПереходов между темами нет — темы не связаны.")
        total = sum(len(b.get("nodes") or {}) for b in trees.values())
        extra = ("\n\n" + await coverage_text(data)
                 if KINDS[kind]["articles"] else "")
        await message.answer(
            f"✅ {name}: тем {len(trees)}, узлов {total}.{note}{extra}\n\n"
            f"Посмотреть черновик — <code>{_cmd(kind)} черновик</code>. "
            f"Людям он пока не виден.\n"
            f"Опубликовать: <code>{_cmd(kind)} опубликовать</code>")
        return

    if action in ("охват", "coverage"):
        if not KINDS[kind]["articles"]:
            await message.answer("Экономика собирается из новостей дня — "
                                 "охват статей тут ни при чём.")
            return
        data = await tree("draft", kind) or await tree("live", kind)
        if not data:
            await message.answer("Дерева пока нет.")
            return
        await message.answer(await coverage_text(data))
        return

    if action in ("черновик", "draft"):
        if not await tree("draft", kind):
            await message.answer(f"Черновика нет. Собрать: "
                                 f"<code>{_cmd(kind)} собрать</code>")
            return
        await show_list(message, kind, draft=True)
        return

    if action in ("опубликовать", "publish"):
        draft = await tree("draft", kind)
        problem = check(draft)
        if problem:
            await message.answer(f"⚠️ Публиковать нельзя: {html.escape(problem)}")
            return
        await save_tree(draft, "live", kind)
        await message.answer(f"✅ {name} опубликована.")
        return

    if action in ("убрать", "off"):
        await database.set_setting(keys(kind)[0], "")
        await message.answer("Убрала. Людям разбор больше не показывается.")
        return

    live = await tree("live", kind)
    draft = await tree("draft", kind)
    source = ("ваших статей раздела" if KINDS[kind]["articles"]
              else "сегодняшних новостей и движения индексов")
    await message.answer(
        f"🌳 <b>{name}: разбор вопросами</b>\n\n"
        f"Показывается людям: {len(live.get('trees') or {})} тем\n"
        f"Черновик: {len(draft.get('trees') or {})} тем\n\n"
        f"Собирается из {source}. Модель не сочиняет содержание — она "
        f"перекладывает написанное в вопросы.\n\n"
        f"<code>{_cmd(kind)} собрать</code> — заново\n"
        + (f"<code>{_cmd(kind)} охват</code> — что вошло, а что нет\n"
           if KINDS[kind]["articles"] else "")
        + f"<code>{_cmd(kind)} черновик</code> — пройти самой\n"
          f"<code>{_cmd(kind)} опубликовать</code> — показать людям\n"
          f"<code>{_cmd(kind)} убрать</code> — скрыть")


def _cmd(kind: str) -> str:
    return "/дерево" if kind == "g" else "/эконом"
