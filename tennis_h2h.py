#  tennis_h2h.py
#  Личные встречи перед матчем: бот спрашивает — владелица отвечает.
#
#  ЗАЧЕМ ВРУЧНУЮ. Источник табло отдаёт расписание и счёт, но не историю
#  встреч: ни кто кого обыгрывал, ни на каком покрытии, ни в каком году.
#  Своей истории у нас тоже нет — таблица рейтинга хранит место, имя и
#  страну, и больше ничего. Значит, остаются два пути: выдумать или
#  спросить у человека. Выдумывать запрещено тем же правилом, по
#  которому отложено движение по рейтингу и по которому в books_seed.py
#  нельзя генерировать книги.
#
#  ПОЧЕМУ ПО ПОЛЯМ, А НЕ ОДНИМ ТЕКСТОМ. Отдельные колонки дают два
#  свойства, которых у свободного текста нет: пост собирается одинаково
#  у каждого матча, и видно, чего именно не хватает. Платим за это
#  четырьмя вопросами вместо одного сообщения.
#
#  ВЕСЬ ДИАЛОГ — ТОЛЬКО В ЛИЧКЕ И ТОЛЬКО У ВЛАДЕЛИЦЫ. Кнопки этого
#  модуля сознательно НЕ внесены в public.PUBLIC_OK: под постом в канале
#  им делать нечего, и если такая кнопка там однажды окажется, граница
#  её не пропустит.

import html
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

import config
import database

router = Router()


class Filling(StatesGroup):
    meetings = State()
    wins_first = State()
    surfaces = State()
    years = State()
    note = State()


# Сколько встреч считаем правдоподобным. Не защита от злого умысла —
# защита от опечатки: «44» вместо «4» уехало бы в канал как факт.
MAX_MEETINGS = 60

SKIP = ("-", "–", "—", "нет", "пропустить", "далее")


def _skipped(text: str) -> bool:
    return (text or "").strip().lower() in SKIP


def _title_from(text: str) -> str:
    """Строка с парой фамилий из сообщения.

    Берём первую строку, в которой есть тире между двумя словами, —
    это и есть «Жабин — Петров». Разбор по номеру абзаца ломался, как
    только та же кнопка появилась в другом сообщении.
    """
    for line in (text or "").splitlines():
        line = line.strip()
        for dash in (" — ", " – ", " - "):
            if dash in line:
                left, right = line.split(dash, 1)
                if left.strip() and right.strip():
                    return line
    return ""


def _names(title: str):
    """«Рублёв — Алькарас» -> («Рублёв», «Алькарас»)"""
    for dash in (" — ", " - ", " – "):
        if dash in title:
            left, right = title.split(dash, 1)
            return left.strip(), right.strip()
    return title.strip(), ""


# ---------------------------------------------------------------------
# История, которую бот копит сам
# ---------------------------------------------------------------------
#
# Статистику присылает владелица — но только потому, что у источника её
# нет. Своя история постепенно набирается сама: каждый завершённый матч
# записывается парой игроков, с покрытием, счётом и турниром. Через
# сезон заполнять руками придётся всё реже.


def normalize(name: str) -> str:
    """Фамилия в виде, пригодном для сравнения.

    Нижний регистр и без инициалов: «Шелтон», «Б. Шелтон» и «ШЕЛТОН» —
    один человек. Без этого пара не сойдётся сама с собой.
    """
    name = (name or "").strip()
    # Инициал отрезаем: «Б. Шелтон» -> «Шелтон»
    parts = [x for x in name.replace(".", ". ").split() if x]
    parts = [x for x in parts if not (len(x.rstrip(".")) == 1)]
    return " ".join(parts).lower().replace("ё", "е")


def pair_key(first: str, second: str):
    """Пара в постоянном порядке: «А против Б» и «Б против А» — одно."""
    return tuple(sorted([normalize(first), normalize(second)]))


def summarize(history: list, first: str, second: str) -> dict:
    """Свести историю пары к числам для поста."""
    a = normalize(first)
    wins_first = sum(1 for row in history if normalize(row["winner"]) == a)
    surfaces, years = [], []
    for row in history:
        if row.get("surface") and row["surface"] not in surfaces:
            surfaces.append(row["surface"])
        played = row.get("played_on")
        if played and played.year not in years:
            years.append(played.year)
    return {
        "meetings": len(history),
        "wins_first": wins_first,
        "surfaces": ", ".join(surfaces) or None,
        "years": ", ".join(str(y) for y in sorted(years)) or None,
        "note": None,
    }


async def auto_stats(first: str, second: str):
    """Готовый блок по накопленной истории или None, если её нет."""
    history = await database.h2h_pair(*pair_key(first, second))
    if not history:
        return None
    return _stats_block(first, second, summarize(history, first, second),
                        partial=True)


# ---------------------------------------------------------------------
# Запрос владелице
# ---------------------------------------------------------------------

def _ask_markup(tour: str, match_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Заполнить",
                              callback_data=f"h2hfill_{tour}_{match_id}")],
        [InlineKeyboardButton(text="🔄 Обновить",
                              callback_data=f"h2hgo_{tour}_{match_id}")],
    ])


async def request_batch(bot: Bot, tour: str, matches: list) -> int:
    """Один список вместо двадцати сообщений.

    Статистики не хватает почти всегда, и просить её по каждому матчу
    отдельным письмом — значит превратить личку в ленту уведомлений,
    которую перестают читать. Поэтому одно сообщение на тур, кнопка на
    матч.

    ПАРЫ, КОТОРЫЕ УЖЕ ЗАПОЛНЕНЫ, не переспрашиваем — но именно пары, а
    не матчи: те же двое могут встретиться на другом турнире, и матч
    будет новый, а история та же.
    """
    if not config.ADMIN_ID or not matches:
        return 0

    done = await database.h2h_filled_pairs()
    rows, listed = [], []
    for match_id, title, first, second in matches:
        if "|".join(pair_key(first, second)) in done:
            continue
        if await database.h2h_get(match_id):
            continue
        listed.append(title)
        rows.append([InlineKeyboardButton(
            text=f"✍️ {title[:36]}",
            callback_data=f"h2hfill_{tour}_{match_id}")])
        if len(rows) >= 10:      # больше кнопок под сообщением не читается
            break

    if not rows:
        return 0

    try:
        await bot.send_message(
            config.ADMIN_ID,
            f"📊 <b>Нет личных встреч</b> — {tour.upper()}\n\n"
            + "\n".join(f"• {html.escape(x)}" for x in listed)
            + "\n\n<i>Заполнять всё не нужно: возьмите те матчи, о "
              "которых будете писать. Пары, которые вы уже внесли, сюда "
              "не попадают.</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        return len(rows)
    except Exception as e:
        logging.warning(f"Список незаполненных встреч не ушёл: {e}")
        return 0


async def request_missing(bot: Bot, tour: str, match_id: str,
                          title: str) -> bool:
    """Написать владелице, что статистики по матчу нет.

    Молчим, если она уже заполнена: повторная просьба по тому же матчу
    превращает бота в надоеду, а список дел — в шум, который перестают
    читать.
    """
    if not config.ADMIN_ID:
        return False
    if await database.h2h_get(match_id):
        return False

    try:
        await bot.send_message(
            config.ADMIN_ID,
            f"📊 <b>Статистики по этому матчу нет</b>\n\n"
            f"{html.escape(title)}\n\n"
            f"Заполните личные встречи — и матч можно анонсировать. "
            f"Если встреч не было, так и укажите: «0» в первом вопросе.",
            reply_markup=_ask_markup(tour, match_id))
        return True
    except Exception as e:
        logging.warning(f"Запрос статистики {match_id} не ушёл: {e}")
        return False


# ---------------------------------------------------------------------
# Покрытие незнакомых турниров
# ---------------------------------------------------------------------

async def request_surfaces(bot: Bot) -> int:
    """Спросить покрытие у турниров, которых нет в справочнике.

    Справочник знает крупные турниры и не меняется. Малые появляются и
    меняют покрытие, и угадывать за них нельзя: выдуманный грунт в
    истории встреч выглядит ровно как настоящий.
    """
    if not config.ADMIN_ID:
        return 0
    unknown = await database.surfaces_unknown(8)
    if not unknown:
        return 0

    sent = 0
    for name, tour in unknown:
        pretty = name.title()
        try:
            await bot.send_message(
                config.ADMIN_ID,
                f"🎾 <b>Какое покрытие?</b>\n\n{html.escape(pretty)}"
                + (f" · {tour.upper()}" if tour else "")
                + "\n\n<i>Этого турнира нет в справочнике. Покрытие "
                  "проставится и задним числом — всем уже сыгранным "
                  "матчам тоже.</i>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🟫 Грунт",
                                         callback_data=f"surf_clay_{name}"),
                    InlineKeyboardButton(text="🟩 Трава",
                                         callback_data=f"surf_grass_{name}"),
                    InlineKeyboardButton(text="🟦 Хард",
                                         callback_data=f"surf_hard_{name}"),
                ], [
                    # Четвёртый ответ, и он не про покрытие: у
                    # показательного турнира покрытие ни на что не
                    # влияет, потому что в историю встреч он не идёт.
                    InlineKeyboardButton(text="🎭 Показательный — не считать",
                                         callback_data=f"surf_exhib_{name}"),
                ]]))
            sent += 1
        except Exception as e:
            logging.warning(f"Запрос покрытия «{name}» не ушёл: {e}")
    return sent


@router.callback_query(F.data.startswith("surf_"))
async def set_surface(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    try:
        _, kind, name = call.data.split("_", 2)
    except ValueError:
        await call.answer()
        return

    import surfaces
    if kind == "exhib":
        removed = await database.tournament_mark_exhibition(name)
        await call.answer("Показательный — в историю не идёт")
        tail = (f"\n\nУбрала из истории встреч матчей: {removed}."
                if removed else "")
        try:
            await call.message.edit_text(
                f"🎭 <b>{html.escape(name.title())}</b> — показательный, "
                f"в историю встреч не идёт.{tail}")
        except Exception:
            await call.message.answer(
                f"🎭 {html.escape(name.title())} — показательный.{tail}")
        return

    chosen = {"clay": surfaces.CLAY, "grass": surfaces.GRASS,
              "hard": surfaces.HARD}.get(kind)
    if not chosen:
        await call.answer()
        return

    await database.surface_set(name, chosen)
    # И задним числом: ответ, который достаётся только будущим матчам,
    # оставил бы уже сыгранные без покрытия навсегда.
    touched = await database.h2h_fill_surface(name, chosen)

    await call.answer(f"Записала: {chosen}")
    tail = (f"\n\nПроставила в уже сыгранных матчах: {touched}."
            if touched else "")
    try:
        await call.message.edit_text(
            f"🎾 <b>{html.escape(name.title())}</b> — {chosen}.{tail}")
    except Exception:
        await call.message.answer(f"✅ {html.escape(name.title())} — {chosen}.{tail}")


# ---------------------------------------------------------------------
# Диалог
# ---------------------------------------------------------------------

@router.callback_query(F.data.startswith("h2hfill_"))
async def start_filling(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    try:
        _, tour, match_id = call.data.split("_", 2)
    except ValueError:
        await call.answer()
        return
    await call.answer()

    # Название матча ищем надёжнее, чем «второй абзац»: эта же кнопка
    # теперь стоит и в карточке подписки, а там разметка другая — там
    # второй абзац это статистика или вопрос прогноза.
    title = _title_from(call.message.text or "")
    first, second = _names(title)
    await state.set_state(Filling.meetings)
    await state.update_data(tour=tour, match_id=match_id, title=title,
                            first=first, second=second)
    await call.message.answer(
        f"1/4. Сколько раз они играли между собой?\n\n"
        f"<i>Число. Если встреч не было — 0.</i>")


@router.message(Filling.meetings)
async def take_meetings(message: Message, state: FSMContext):
    try:
        meetings = int((message.text or "").strip())
        if meetings < 0 or meetings > MAX_MEETINGS:
            raise ValueError
    except ValueError:
        await message.answer(
            f"Нужно число от 0 до {MAX_MEETINGS}. Сколько раз играли?")
        return

    data = await state.update_data(meetings=meetings)

    # Нисколько — остальные три вопроса бессмысленны: не на каком
    # покрытии и не в какие годы они не играли.
    if meetings == 0:
        await state.clear()
        ok = await database.h2h_save(
            data["match_id"], data["tour"], data["title"],
            0, 0, None, None, None,
            pair_key="|".join(pair_key(data.get("first") or "",
                                       data.get("second") or "")))
        await _show_summary(message, data, ok, meetings=0, wins_first=0,
                            surfaces=None, years=None, note=None)
        return

    first = data.get("first") or "первый"
    await state.set_state(Filling.wins_first)
    await message.answer(
        f"2/4. Сколько из этих {meetings} выиграл: {html.escape(first)}?\n\n"
        f"<i>Второе число посчитаю сам.</i>")


@router.message(Filling.wins_first)
async def take_wins(message: Message, state: FSMContext):
    data = await state.get_data()
    meetings = data.get("meetings") or 0
    try:
        wins = int((message.text or "").strip())
        if wins < 0 or wins > meetings:
            raise ValueError
    except ValueError:
        await message.answer(
            f"Нужно число от 0 до {meetings} — больше встреч, чем было, "
            f"выиграть нельзя. Сколько?")
        return

    await state.update_data(wins_first=wins)
    await state.set_state(Filling.surfaces)
    await message.answer(
        "3/4. На каких покрытиях играли?\n\n"
        "<i>Через запятую: хард, грунт. Пропустить — поставьте прочерк.</i>")


@router.message(Filling.surfaces)
async def take_surfaces(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    await state.update_data(surfaces=None if _skipped(text) else text[:120])
    await state.set_state(Filling.years)
    await message.answer(
        "4/4. В каких годах?\n\n"
        "<i>Через запятую: 2023, 2024. Пропустить — прочерк.</i>")


@router.message(Filling.years)
async def take_years(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    await state.update_data(years=None if _skipped(text) else text[:120])
    await state.set_state(Filling.note)
    await message.answer(
        "Хотите добавить строчку своими словами? Она встанет в конце поста.\n\n"
        "<i>Не нужно — поставьте прочерк.</i>")


@router.message(Filling.note)
async def take_note(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    note = None if _skipped(text) else text[:400]
    data = await state.get_data()
    await state.clear()

    ok = await database.h2h_save(
        data["match_id"], data["tour"], data["title"],
        data.get("meetings") or 0, data.get("wins_first") or 0,
        data.get("surfaces"), data.get("years"), note,
        pair_key="|".join(pair_key(data.get("first") or "",
                                   data.get("second") or "")))

    await _show_summary(message, data, ok,
                        meetings=data.get("meetings") or 0,
                        wins_first=data.get("wins_first") or 0,
                        surfaces=data.get("surfaces"),
                        years=data.get("years"), note=note)


async def _show_summary(message: Message, data, ok: bool, **fields) -> None:
    """Показать, что получилось, до публикации.

    Исправлять дешевле, чем отзывать: пост в канале уже прочитали, а
    эту карточку видит только владелица.
    """
    if not ok:
        await message.answer("⚠ Не сохранилось. Нажмите «Заполнить» ещё раз.")
        return

    body = _stats_block(data.get("first"), data.get("second"), fields)
    await message.answer(
        f"Вот что получилось:\n\n{body}\n\nПубликуем?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📤 Опубликовать",
                callback_data=f"h2hgo_{data['tour']}_{data['match_id']}")],
            [InlineKeyboardButton(
                text="✍️ Заполнить заново",
                callback_data=f"h2hfill_{data['tour']}_{data['match_id']}")],
        ]))


# ---------------------------------------------------------------------
# Текст поста
# ---------------------------------------------------------------------

def _stats_block(first: str, second: str, f, partial: bool = False) -> str:
    """Готовый кусок про личные встречи.

    Имена ставятся ПОСЛЕ двоеточия, а не в середину фразы: склонять
    фамилии автоматически нельзя, и «ведёт Алькарас» на месте «ведёт
    Медведев» превратилось бы в «ведёт Медведев» там, где нужно
    «ведёт Медведева». Та же оговорка уже стоит в _pick_verdict.
    """
    meetings = f.get("meetings") or 0
    if not meetings:
        # Сказать «играют впервые» можно только о том, что заполнено
        # руками: наша собственная история начинается с того дня, как
        # мы начали записывать, и её пустота ничего не доказывает.
        return "" if partial else "Играют между собой впервые."

    wins_first = f.get("wins_first") or 0
    wins_second = meetings - wins_first

    # ГЛАВНОЕ ОТЛИЧИЕ НАКОПЛЕННОГО ОТ ЗАПОЛНЕННОГО. Заполненное
    # владелицей — это полная история пары. Накопленное нами — только
    # то, что мы успели увидеть: вчера сыграли, сегодня в статистике
    # одна встреча, а позавчера их было пять, и мы о них не знаем.
    # Писать «Личные встречи: 1» значит выдать наблюдение за факт.
    lines = [f"Мы видели встреч: {meetings}" if partial
             else f"Личные встречи: {meetings}"]
    score = f"Счёт — {wins_first}:{wins_second}"
    if wins_first != wins_second:
        ahead = first if wins_first > wins_second else second
        if ahead:
            score += f", впереди: {html.escape(ahead)}"
    else:
        score += ", поровну"
    lines.append(score)

    if f.get("surfaces"):
        lines.append(f"Покрытия: {html.escape(f['surfaces'])}")
    if f.get("years"):
        lines.append(f"Годы: {html.escape(f['years'])}")
    if f.get("note"):
        lines.append("")
        lines.append(html.escape(f["note"]))
    if partial:
        lines.append("<i>Считаем только матчи, которые видели сами, — "
                     "более ранние встречи сюда не вошли.</i>")
    return "\n".join(lines)


def preview_text(row) -> str:
    """Пост «Перед матчем» целиком"""
    title = row.get("title") or "матч"
    first, second = _names(title)
    block = _stats_block(first, second, row)
    return (f"📊 <b>Перед матчем</b>\n\n"
            f"<b>{html.escape(title)}</b>\n\n"
            f"{block}")


# ---------------------------------------------------------------------
# Публикация
# ---------------------------------------------------------------------

async def publish(bot: Bot, chat: int, tour: str, match_id: str,
                  thread=None) -> str:
    """Выпустить анонс. Возвращает строку отчёта для владелицы."""
    row = await database.h2h_get(match_id)
    if not row:
        return "статистики всё ещё нет"
    if row.get("published"):
        return "этот матч уже анонсирован"

    try:
        await bot.send_message(chat, preview_text(row),
                               message_thread_id=thread,
                               disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"Анонс {match_id} не вышел: {e}")
        return f"не вышло: {e}"

    await database.h2h_mark_published(match_id)
    return "опубликовано"


@router.callback_query(F.data.startswith("h2hgo_"))
async def publish_now(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    try:
        _, tour, match_id = call.data.split("_", 2)
    except ValueError:
        await call.answer()
        return

    # Канал — тот же, куда выходит дайджест: он задаётся настройкой, а не
    # константой, и расходиться с остальными постами здесь незачем.
    import digest
    chat, thread = await digest._target()
    if not chat:
        await call.answer("Канал не задан.", show_alert=True)
        return

    await call.answer("Публикую…")
    result = await publish(call.bot, chat, tour, match_id, thread)
    await call.message.answer(f"📊 {result}")
