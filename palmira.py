# palmira.py — свои анонсы участников «Трофеев Северной Пальмиры».
#
# Организаторы объявляют состав по одному игроку и когда захотят.
# Пересказывать их пост нельзя — это чужой текст, и в «Акценте» он
# неуместен. Поэтому свой анонс на каждое имя: кто это, чем известен,
# когда играет.
#
# Имя попадает в список заявленных только после подтверждения в кабинете.
# Автоматика тут ошибётся обязательно: в чужом посте фамилия может стоять
# в составе другого турнира, в прошедшем времени или вовсе в рекламе
# билетов. Бот поэтому только предлагает, а решает человек.
#
# Список живёт одним постом в канале: он не публикуется заново на каждое
# имя, а правится на месте. Иначе к началу турнира в ленте лежало бы
# полтора десятка почти одинаковых списков.
import html
import json
import logging
import re
from datetime import date

from aiogram import Router, F, Bot
from aiogram.types import (CallbackQuery, Message, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import config
import database

router = Router()

TOURNAMENT = "Трофеи Северной Пальмиры"
TOURNAMENT_IN = "Трофеях Северной Пальмиры"   # «на Трофеях», а не «на Трофеи»
WHEN = "27–29 ноября 2026"
WHERE = "КСК «Арена», Санкт-Петербург"

ROSTER_KEY = "palmira_roster"      # подтверждённые, JSON
QUEUE_KEY = "palmira_queue"        # ждут решения, JSON
LIST_MSG_KEY = "palmira_list_msg"  # id поста со списком в канале

# Объявленные на сегодня. Попадают не в список, а в очередь на
# подтверждение: пусть первый же заход в кабинет пройдёт тем же путём,
# которым пойдут все следующие.
SEED = ["Александр Бублик", "Елена Веснина", "Диана Шнайдер",
        "Карен Хачанов"]

# Кого стоит узнавать в чужих постах сверх словаря действующих игроков:
# на выставочный турнир приезжают и те, кто давно не в рейтинге.
EXTRA = ["Елена Веснина", "Мансур Бахрами", "Евгений Кафельников",
         "Марат Сафин", "Анастасия Мыскина", "Светлана Кузнецова",
         "Динара Сафина", "Вера Звонарёва", "Николай Давыденко",
         "Михаил Южный", "Дмитрий Турсунов", "Анна Чакветадзе",
         "Игорь Андреев", "Теймураз Габашвили", "Александр Метревели",
         "Анна Курникова", "Елена Дементьева", "Надежда Петрова"]

# Чем известен — одной строкой. Пишем только то, что проверяемо и не
# устаревает: титулы и медали, а не место в рейтинге, которое меняется
# каждый понедельник.
FACTS = {
    "александр бублик": "Казахстанский теннисист, чемпион травяного "
                        "турнира в Галле. Подача за 220 и удар снизу с "
                        "подрезкой там, где все бьют сверху.",
    "елена веснина": "Олимпийская чемпионка Рио в паре, победительница "
                     "Уимблдона и «Ролан Гаррос» в парном разряде.",
    "диана шнайдер": "Серебро Олимпиады в Париже в паре, первая "
                     "двадцатка одиночного рейтинга.",
    "карен хачанов": "Серебро Олимпиады в Токио, победитель «Мастерса» "
                     "в Париже.",
    "мансур бахрами": "Иранский теннисист, финалист «Ролан Гаррос» в "
                      "паре и самый известный в мире мастер трюкового "
                      "тенниса.",
    "андрей рублёв": "Победитель «Мастерса» в Монте-Карло, олимпийское "
                     "золото в миксте.",
    "даниил медведев": "Победитель US Open, первая ракетка мира в 2022 "
                       "году.",
    "мирра андреева": "Победительница «Мастерсов» в Дубае и "
                      "Индиан-Уэллсе, первая десятка рейтинга.",
}

ASK = ("✍️ <b>Имя участника</b>\n\n"
       "Фамилия и имя по-русски, одной строкой: "
       "<i>Карен Хачанов</i>.")


class Adding(StatesGroup):
    waiting_name = State()
    waiting_text = State()


# ───────────────────────── хранение ─────────────────────────

def _norm(name: str) -> str:
    return (name or "").strip().lower().replace("ё", "е")


async def _load(key: str) -> list:
    raw = await database.get_setting(key)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception as e:
        logging.error(f"Пальмира: {key} не прочитался — {e}")
        return []


async def _save(key: str, data: list) -> None:
    await database.set_setting(key, json.dumps(data, ensure_ascii=False))


async def roster() -> list:
    return await _load(ROSTER_KEY)


async def queue() -> list:
    """Очередь на подтверждение. Первое обращение кладёт объявленных."""
    raw = await database.get_setting(QUEUE_KEY)
    if raw is None:
        seeded = [{"name": n, "src": "объявлено организаторами",
                   "found": date.today().isoformat()} for n in SEED]
        await _save(QUEUE_KEY, seeded)
        return seeded
    return await _load(QUEUE_KEY)


async def known(name: str) -> bool:
    """Уже в списке или уже в очереди"""
    key = _norm(name)
    for row in await roster():
        if _norm(row.get("name")) == key:
            return True
    for row in await queue():
        if _norm(row.get("name")) == key:
            return True
    return False


async def enqueue(name: str, src: str = "") -> bool:
    """Поставить имя на подтверждение. False, если уже знаем."""
    if not (name or "").strip() or await known(name):
        return False
    rows = await queue()
    rows.append({"name": name.strip(), "src": src,
                 "found": date.today().isoformat()})
    await _save(QUEUE_KEY, rows)
    return True


# ───────────────────── узнавание имён в чужом тексте ─────────────────────

def _index() -> dict:
    """{основа фамилии: [полные имена]} — по словарю игроков и своему списку"""
    import players_ru
    idx = {}
    for full in list(players_ru._RU.values()) + EXTRA:
        parts = full.split()
        if len(parts) < 2:
            continue
        surname = _norm(parts[-1])
        # Падежи: «Веснина» в тексте стоит «Веснину», «Весниной».
        # Отрезаем последнюю букву у фамилий на гласную, остальное
        # добираем хвостом в самом поиске.
        stem = surname[:-1] if (len(surname) > 5
                                and surname[-1] in "аяойеь") else surname
        idx.setdefault(stem, [])
        if full not in idx[stem]:
            idx[stem].append(full)
    return idx


def names_in(text: str) -> list:
    """Имена известных теннисистов, упомянутые в тексте.

    Однофамильцы пропускаются, пока в тексте нет имени: сестёр Андреевых
    две, и в составе турнира может стоять любая.
    """
    low = _norm(text)
    if not low:
        return []
    found = []
    for stem, fulls in _index().items():
        if not re.search(rf"\b{re.escape(stem)}\w{{0,3}}\b", low):
            continue
        if len(fulls) == 1:
            pick = fulls[0]
        else:
            pick = ""
            for full in fulls:
                first = _norm(full.split()[0])
                if re.search(rf"\b{re.escape(first[:-1] or first)}\w{{0,3}}\b",
                             low):
                    pick = full
                    break
            if not pick:
                continue
        if pick not in found:
            found.append(pick)
    return found


async def catch(text: str, src: str = "") -> list:
    """Найденное в чужом посте — в очередь. Возвращает новые имена."""
    added = []
    for name in names_in(text):
        if await enqueue(name, src):
            added.append(name)
    return added


# ───────────────────────── тексты ─────────────────────────

def draft(name: str) -> str:
    """Анонс одного участника"""
    fact = FACTS.get(_norm(name), "")
    lines = [f"🎾 <b>{html.escape(name)}</b> — на «{TOURNAMENT_IN}»", ""]
    if fact:
        lines += [html.escape(fact), ""]
    lines += [f"{WHEN}, {WHERE}.", "",
              "Буду там и покажу, как это выглядит вблизи."]
    return "\n".join(lines)


async def list_text() -> str:
    """Пост со списком заявленных"""
    rows = await roster()
    lines = [f"📜 <b>Кто уже заявлен</b>",
             f"«{TOURNAMENT}» · {WHEN}", ""]
    if not rows:
        lines.append("<i>пока никого</i>")
    else:
        for i, row in enumerate(rows, 1):
            lines.append(f"{i}. {html.escape(row.get('name', ''))}")
    lines += ["", "Список пополняется — обновляю этот пост."]
    return "\n".join(lines)


# ───────────────────────── публикация ─────────────────────────

async def publish_one(bot: Bot, name: str, text: str = "") -> str:
    import digest
    chat, thread = await digest._target()
    if not chat:
        return "канал не задан"
    try:
        await bot.send_message(chat, text or draft(name),
                               message_thread_id=thread,
                               disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"Пальмира: анонс {name} не вышел — {e}")
        return f"ошибка: {e}"
    return f"анонс вышел: {name}"


async def publish_list(bot: Bot) -> str:
    """Список заявленных: править свой пост, а не выкладывать новый"""
    import digest
    chat, thread = await digest._target()
    if not chat:
        return "канал не задан"
    text = await list_text()
    saved = await database.get_setting(LIST_MSG_KEY)
    if saved:
        try:
            await bot.edit_message_text(chat_id=chat, message_id=int(saved),
                                        text=text,
                                        disable_web_page_preview=True)
            return "список обновлён"
        except Exception as e:
            # Пост удалили или текст не изменился — ниже решим по месту.
            if "not modified" in str(e).lower():
                return "список и так верный"
            logging.warning(f"Пальмира: список не правится — {e}")
    try:
        sent = await bot.send_message(chat, text, message_thread_id=thread,
                                      disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"Пальмира: список не вышел — {e}")
        return f"ошибка: {e}"
    await database.set_setting(LIST_MSG_KEY, str(sent.message_id))
    return "список опубликован"


# ───────────────────────── кабинет ─────────────────────────

HOME = ("🏛 <b>{t}</b>\n{when}\n{where}\n\n"
        "Заявлено: <b>{n}</b>\nЖдут решения: <b>{q}</b>")


def _rows(pairs) -> list:
    return [[InlineKeyboardButton(text=t, callback_data=d)] for t, d in pairs]


async def home_kb() -> InlineKeyboardMarkup:
    q = len(await queue())
    rows = _rows([
        (f"🆕 На подтверждении ({q})", "pal_queue"),
        ("📜 Список заявленных", "pal_list"),
        ("✍️ Добавить имя вручную", "pal_new"),
        ("📣 Выложить список в канал", "pal_post"),
    ])
    rows.append([InlineKeyboardButton(text="⇦ Назад", callback_data="own_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def home_text() -> str:
    return HOME.format(t=TOURNAMENT, when=WHEN, where=WHERE,
                       n=len(await roster()), q=len(await queue()))


async def _allowed(call: CallbackQuery) -> bool:
    if config.is_admin(call.from_user.id):
        return True
    await call.answer()
    return False


async def _home(call: CallbackQuery):
    await call.message.answer(await home_text(), reply_markup=await home_kb())


@router.message(F.text.regexp(r"^/(пальмира|palmira)\b"))
async def palmira_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    await message.answer(await home_text(), reply_markup=await home_kb())


@router.callback_query(F.data == "pal_home")
async def open_home(call: CallbackQuery):
    if not await _allowed(call):
        return
    await call.answer()
    await _home(call)


@router.callback_query(F.data == "pal_queue")
async def open_queue(call: CallbackQuery):
    if not await _allowed(call):
        return
    await call.answer()
    rows = await queue()
    if not rows:
        await call.message.answer(
            "🆕 <b>На подтверждении</b>\n\nПусто. Новые имена появятся "
            "здесь, когда организаторы их объявят.",
            reply_markup=await home_kb())
        return
    pairs = [(f"{i + 1}. {row.get('name', '')[:40]}", f"pal_card_{i}")
             for i, row in enumerate(rows)]
    kb = _rows(pairs)
    kb.append([InlineKeyboardButton(text="⇦ Назад", callback_data="pal_home")])
    await call.message.answer(
        "🆕 <b>На подтверждении</b>\n\nНажмите на имя — покажу анонс "
        "целиком, каким он уйдёт в канал.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


def card_kb(i: int) -> InlineKeyboardMarkup:
    rows = _rows([
        ("✅ Опубликовать анонс", f"pal_go_{i}"),
        ("➕ Только в список, без анонса", f"pal_add_{i}"),
        ("✍️ Править текст", f"pal_edit_{i}"),
        ("🗑 Убрать из очереди", f"pal_no_{i}"),
    ])
    rows.append([InlineKeyboardButton(text="⇦ Назад", callback_data="pal_queue")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _entry(i: int):
    rows = await queue()
    return (rows[i], rows) if 0 <= i < len(rows) else (None, rows)


@router.callback_query(F.data.startswith("pal_card_"))
async def open_card(call: CallbackQuery):
    if not await _allowed(call):
        return
    await call.answer()
    row, _ = await _entry(int(call.data.rsplit("_", 1)[1]))
    if not row:
        await call.message.answer("Имя уже обработано.",
                                  reply_markup=await home_kb())
        return
    i = int(call.data.rsplit("_", 1)[1])
    src = row.get("src") or "вручную"
    body = row.get("text") or draft(row["name"])
    await call.message.answer(
        f"<i>Откуда: {html.escape(src)}</i>\n\n{body}",
        reply_markup=card_kb(i), disable_web_page_preview=True)


async def _accept(i: int, announced: bool) -> str:
    """Перенести из очереди в список"""
    row, rows = await _entry(i)
    if not row:
        return ""
    rows.pop(i)
    await _save(QUEUE_KEY, rows)
    people = await roster()
    people.append({"name": row["name"], "at": date.today().isoformat(),
                   "announced": announced})
    await _save(ROSTER_KEY, people)
    return row["name"]


@router.callback_query(F.data.startswith("pal_go_"))
async def card_publish(call: CallbackQuery, bot: Bot):
    if not await _allowed(call):
        return
    i = int(call.data.rsplit("_", 1)[1])
    row, _ = await _entry(i)
    if not row:
        await call.answer("Уже обработано")
        return
    await call.answer("Публикую…")
    text = row.get("text") or draft(row["name"])
    result = await publish_one(bot, row["name"], text)
    if result.startswith("анонс вышел"):
        await _accept(i, True)
        result += "\n" + await publish_list(bot)
    await call.message.answer(f"🏛 {html.escape(result)}",
                              reply_markup=await home_kb())


@router.callback_query(F.data.startswith("pal_add_"))
async def card_add(call: CallbackQuery, bot: Bot):
    if not await _allowed(call):
        return
    i = int(call.data.rsplit("_", 1)[1])
    name = await _accept(i, False)
    if not name:
        await call.answer("Уже обработано")
        return
    await call.answer("В списке")
    await call.message.answer(
        f"➕ {html.escape(name)} — в списке, анонса не было.\n"
        "Общий пост со списком обновится кнопкой «Выложить список».",
        reply_markup=await home_kb())


@router.callback_query(F.data.startswith("pal_no_"))
async def card_drop(call: CallbackQuery):
    if not await _allowed(call):
        return
    i = int(call.data.rsplit("_", 1)[1])
    row, rows = await _entry(i)
    if not row:
        await call.answer("Уже обработано")
        return
    rows.pop(i)
    await _save(QUEUE_KEY, rows)
    await call.answer("Убрано")
    await call.message.answer(f"🗑 {html.escape(row['name'])} — убрано из "
                              "очереди.", reply_markup=await home_kb())


@router.callback_query(F.data.startswith("pal_edit_"))
async def card_edit(call: CallbackQuery, state: FSMContext):
    if not await _allowed(call):
        return
    i = int(call.data.rsplit("_", 1)[1])
    row, _ = await _entry(i)
    if not row:
        await call.answer("Уже обработано")
        return
    await call.answer()
    await state.set_state(Adding.waiting_text)
    await state.update_data(pal_index=i)
    await call.message.answer(
        "✍️ Пришлите текст анонса целиком — он заменит мой.\n"
        "Разметка обычная: <code>&lt;b&gt;жирный&lt;/b&gt;</code>.")


@router.message(Adding.waiting_text)
async def save_text(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()
    i = int(data.get("pal_index", -1))
    row, rows = await _entry(i)
    if not row:
        await message.answer("Имя уже обработано.",
                             reply_markup=await home_kb())
        return
    rows[i]["text"] = (message.html_text or message.text or "").strip()
    await _save(QUEUE_KEY, rows)
    await message.answer(f"<i>Откуда: {html.escape(rows[i].get('src') or '—')}"
                         f"</i>\n\n{rows[i]['text']}",
                         reply_markup=card_kb(i),
                         disable_web_page_preview=True)


@router.callback_query(F.data == "pal_new")
async def ask_name(call: CallbackQuery, state: FSMContext):
    if not await _allowed(call):
        return
    await call.answer()
    await state.set_state(Adding.waiting_name)
    await call.message.answer(ASK)


@router.message(Adding.waiting_name)
async def take_name(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    await state.clear()
    name = (message.text or "").strip()
    if not name:
        await message.answer("Пусто — ничего не добавила.")
        return
    if await enqueue(name, "добавлено вручную"):
        await message.answer(f"✅ {html.escape(name)} — на подтверждении.",
                             reply_markup=await home_kb())
    else:
        await message.answer(f"{html.escape(name)} уже есть.",
                             reply_markup=await home_kb())


@router.callback_query(F.data == "pal_list")
async def open_list(call: CallbackQuery):
    if not await _allowed(call):
        return
    await call.answer()
    rows = await roster()
    kb = _rows([(f"🗑 {row.get('name', '')[:36]}", f"pal_del_{i}")
                for i, row in enumerate(rows)])
    kb.append([InlineKeyboardButton(text="⇦ Назад", callback_data="pal_home")])
    await call.message.answer(
        await list_text() + "\n\n<i>Кнопка удаляет из списка.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data.startswith("pal_del_"))
async def list_remove(call: CallbackQuery):
    if not await _allowed(call):
        return
    i = int(call.data.rsplit("_", 1)[1])
    rows = await roster()
    if not 0 <= i < len(rows):
        await call.answer("Уже удалено")
        return
    gone = rows.pop(i)
    await _save(ROSTER_KEY, rows)
    await call.answer("Удалено")
    await call.message.answer(
        f"🗑 {html.escape(gone.get('name', ''))} — убрано из списка.\n"
        "Пост в канале обновится кнопкой «Выложить список».",
        reply_markup=await home_kb())


@router.callback_query(F.data == "pal_post")
async def post_list(call: CallbackQuery, bot: Bot):
    if not await _allowed(call):
        return
    await call.answer("Публикую…")
    result = await publish_list(bot)
    await call.message.answer(f"🏛 {html.escape(result)}",
                              reply_markup=await home_kb())
