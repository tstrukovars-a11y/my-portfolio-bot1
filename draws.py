#  draws.py — конкурс на мероприятии: панель владелицы.
#
#  ПЯТЬ ДЕЙСТВИЙ, РАДИ КОТОРЫХ ЭТО НАПИСАНО:
#    1. начать конкурс;
#    2. добавить фотографии призов за места;
#    3. разослать призёрам место встречи и время;
#    4. переписываться с каждым выигравшим;
#    5. завершить конкурс фотографией.
#
#  ВСЁ ТОЛЬКО В ЛИЧКЕ И ТОЛЬКО У ВЛАДЕЛИЦЫ. Кнопки этого модуля
#  сознательно НЕ внесены в public.PUBLIC_OK: под постом в канале им
#  делать нечего, и если такая кнопка там окажется, граница её не
#  пропустит. На это есть тест.
#
#  ПОЧЕМУ ФОТОГРАФИЯ МЕСТА ВСТРЕЧИ ВАЖНЕЕ, ЧЕМ КАЖЕТСЯ. На большой
#  площадке «подойдите к организатору» не находят. Снимок стойки находят
#  сразу — и это снимает половину вопросов ещё до того, как их зададут.
#
#  ПЕРЕПИСКА — НЕ ПОДДЕРЖКА. Это разговор внутри конкретного конкурса:
#  «куда подойти», «я уже тут», «спасибо». Поэтому он не перехватывает
#  все сообщения человека: разговор начинается нажатием кнопки и живёт в
#  своём состоянии, а не в обработчике всех входящих подряд.

import html
import logging
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

import config
import database
import draw_bracket

router = Router()

# Сколько мест объявляем вслух. Остальные призёры получают приглашение
# личным сообщением: «четвёртое место» звучит как «почти», а приглашение
# за брелоком — совсем иначе.
DEFAULT_PRIZES = 3


class Draw(StatesGroup):
    title = State()          # создание: название
    prize_photo = State()    # фото приза за место
    meet_photo = State()     # фото места вручения
    meet_text = State()      # где и во сколько
    final_photo = State()    # фотография, которой завершаем
    schedule = State()       # расписание матчей одним сообщением
    talking = State()        # владелица отвечает призёру
    replying = State()       # призёр пишет владелице


# Транслитерация словарём, а не str.maketrans: часть букв даёт по две
# латинских (ж → zh, щ → sch), а maketrans отображает символ в символ и
# на таком наборе просто падает.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


# Сколько минут принимаются ответы после начала матча. Зритель смотрит
# на корт и отвечает по ходу — отсюда и окно, а не «до начала».
POLL_MINUTES = 15

# Разделители между фамилиями в расписании. Люди пишут по-разному, и
# заставлять набирать именно длинное тире — верный способ получить
# «строка не разобралась» на половине списка.
_DASHES = ("—", "–", "-", " vs ", " VS ")


def parse_schedule(text: str, day=None):
    """Строки «18:00 Окунев — Кураков» -> [(время, первый, второй)].

    Возвращает (разобранное, нераспознанные строки). Нераспознанные
    показываем владелице как есть: молча проглотить строку расписания
    хуже, чем сказать «вот эту я не поняла».
    """
    day = day or datetime.now().date()
    good, bad = [], []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            bad.append(line)
            continue
        clock, rest = parts[0].replace(".", ":"), parts[1]
        try:
            hour, minute = (int(x) for x in clock.split(":", 1))
            when = datetime.combine(day, datetime.min.time()).replace(
                hour=hour, minute=minute)
        except (ValueError, TypeError):
            bad.append(line)
            continue

        pair = None
        for dash in _DASHES:
            if dash in rest:
                left, right = rest.split(dash, 1)
                if left.strip() and right.strip():
                    pair = (left.strip()[:40], right.strip()[:40])
                break
        if not pair:
            bad.append(line)
            continue
        good.append((when, pair[0], pair[1]))
    return good, bad


def _slug(title: str) -> str:
    """Короткое имя для ссылки по QR.

    «Северная Пальмира» -> «severnaya-palmira». Ссылку печатают кодом и
    вешают на входе, поэтому она должна читаться и латиницей.
    """
    out = []
    for char in (title or "").strip().lower():
        if char in _TRANSLIT:
            out.append(_TRANSLIT[char])
        elif char.isalnum() and char.isascii():
            out.append(char)
        else:
            out.append("-")
    base = "-".join(x for x in "".join(out).split("-") if x)
    return (base or "event")[:40].strip("-") or "event"


# ---------------------------------------------------------------------
# Панель
# ---------------------------------------------------------------------

async def _panel_text(event) -> str:
    prizes = await database.draw_prizes(event["id"])
    winners = await database.draw_winners(event["id"])
    lines = [f"🎁 <b>{html.escape(event['title'])}</b>",
             f"<code>{html.escape(event['slug'])}</code> · {event['status']}"]
    lines.append("")
    lines.append(f"Призы заведены: {len(prizes)}")
    lines.append(f"Призёров определено: {len(winners)}")
    if event.get("meet_place"):
        lines.append(f"Место вручения: {html.escape(event['meet_place'])}")
    else:
        lines.append("Место вручения: не указано")
    return "\n".join(lines)


def _panel_kb(event) -> InlineKeyboardMarkup:
    eid = event["id"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Призы за места",
                              callback_data=f"drprizes_{eid}")],
        [InlineKeyboardButton(text="📅 Расписание матчей",
                              callback_data=f"drsched_{eid}")],
        [InlineKeyboardButton(text="📊 Что происходит сейчас",
                              callback_data=f"drstatus_{eid}")],
        [InlineKeyboardButton(text="🚀 Объявить конкурс в канале",
                              callback_data=f"drlaunch_{eid}")],
        [InlineKeyboardButton(text="🎲 Жеребьёвка и старт сетки",
                              callback_data=f"drdraw_{eid}")],
        [InlineKeyboardButton(text="📄 Выгрузить сетку файлом",
                              callback_data=f"drsheet_{eid}")],
        [InlineKeyboardButton(text="📍 Место и время вручения",
                              callback_data=f"drmeet_{eid}")],
        [InlineKeyboardButton(text="📨 Разослать призёрам",
                              callback_data=f"drsend_{eid}")],
        [InlineKeyboardButton(text="🏁 Завершить и объявить итоги",
                              callback_data=f"drfinish_{eid}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="draws_list")],
    ])


@router.message(F.text == "/draws")
async def draws_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    await message.answer(*await _list_view())


async def _list_view():
    events = await database.draw_events_list()
    if events:
        lines = ["🎁 <b>Конкурсы</b>", ""]
        rows = []
        for e in events:
            mark = "🟢" if e["status"] == "open" else "⚪️"
            lines.append(f"{mark} {html.escape(e['title'])}")
            rows.append([InlineKeyboardButton(
                text=f"{mark} {e['title'][:30]}",
                callback_data=f"drevent_{e['id']}")])
    else:
        lines = ["🎁 <b>Конкурсы</b>", "", "Пока ни одного."]
        rows = []
    rows.append([InlineKeyboardButton(text="➕ Начать конкурс",
                                      callback_data="drnew")])
    return "\n".join(lines), {"reply_markup": InlineKeyboardMarkup(
        inline_keyboard=rows), "parse_mode": "HTML"}


@router.callback_query(F.data == "draws_list")
async def draws_list(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    text, kw = await _list_view()
    await call.message.answer(text, **kw)


@router.callback_query(F.data.startswith("drevent_"))
async def draw_event_open(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    event = await database.draw_event(event_id=int(call.data.split("_")[1]))
    if not event:
        await call.message.answer("Конкурс не найден.")
        return
    await call.message.answer(await _panel_text(event),
                              reply_markup=_panel_kb(event),
                              parse_mode="HTML")


# ---------------------------------------------------------------------
# 1. Начать конкурс
# ---------------------------------------------------------------------

@router.callback_query(F.data == "drnew")
async def draw_new(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await state.set_state(Draw.title)
    await call.message.answer(
        "Как называется конкурс?\n\n"
        "<i>Например: Северная Пальмира. Короткое имя для ссылки по QR "
        "составлю сама.</i>")


@router.message(Draw.title)
async def draw_new_save(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if len(title) < 3:
        await message.answer("Слишком коротко. Как называется конкурс?")
        return
    await state.clear()

    slug = _slug(title)
    event_id = await database.draw_event_create(
        slug, title[:120], event_date=datetime.now().date(),
        prizes=DEFAULT_PRIZES)
    if not event_id:
        await message.answer("⚠ Не сохранилось. Попробуйте ещё раз.")
        return

    link = await _qr_link(slug)
    event = await database.draw_event(event_id=event_id)
    await message.answer(
        f"✅ Конкурс создан.\n\n"
        f"Ссылка для QR-кода:\n<code>{html.escape(link)}</code>\n\n"
        f"<i>Напечатайте её кодом и раздайте на входе — зритель нажимает "
        f"и сразу оказывается в конкурсе.</i>",
        reply_markup=_panel_kb(event), parse_mode="HTML")


async def _qr_link(slug: str) -> str:
    username = await database.get_setting("bot_username")
    if not username:
        return "имя бота не задано — /setup"
    return f"https://t.me/{username.lstrip('@')}?start=draw-{slug}"


# ---------------------------------------------------------------------
# 2. Призы за места
# ---------------------------------------------------------------------

@router.callback_query(F.data.startswith("drprizes_"))
async def prizes_menu(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    event_id = int(call.data.split("_")[1])
    have = await database.draw_prizes(event_id)
    rows = []
    for place in (1, 2, 3, 4):
        mark = "✅" if place in have else "➕"
        tail = " (без объявления)" if place > DEFAULT_PRIZES else ""
        rows.append([InlineKeyboardButton(
            text=f"{mark} {place} место{tail}",
            callback_data=f"drprize_{event_id}_{place}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад",
                                      callback_data=f"drevent_{event_id}")])
    await call.message.answer(
        "🖼 <b>Призы за места</b>\n\n"
        "Пришлите фотографию приза — подпись к фотографии станет его "
        "описанием.\n\n"
        f"<i>Первые {DEFAULT_PRIZES} места объявляются вслух. Четвёртое "
        f"не объявляется: это звучит как «почти». За призом зовём лично.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML")


@router.callback_query(F.data.startswith("drprize_"))
async def prize_ask(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    try:
        _, event_id, place = call.data.split("_")
    except ValueError:
        await call.answer()
        return
    await call.answer()
    await state.set_state(Draw.prize_photo)
    await state.update_data(event_id=int(event_id), place=int(place))
    await call.message.answer(
        f"Пришлите фотографию приза за {place} место.\n\n"
        f"<i>Подпись к фотографии станет описанием приза.</i>")


@router.message(Draw.prize_photo, F.photo)
async def prize_save(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    ok = await database.draw_prize_set(
        data["event_id"], data["place"],
        message.photo[-1].file_id, (message.caption or "").strip()[:200] or None)
    event = await database.draw_event(event_id=data["event_id"])
    await message.answer(
        f"✅ Приз за {data['place']} место сохранён." if ok
        else "⚠ Не сохранилось.",
        reply_markup=_panel_kb(event) if event else None)


@router.message(Draw.prize_photo)
async def prize_need_photo(message: Message):
    await message.answer("Нужна именно фотография. Пришлите снимок приза.")


# ---------------------------------------------------------------------
# 3. Место и время вручения
# ---------------------------------------------------------------------

@router.callback_query(F.data.startswith("drmeet_"))
async def meet_ask(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await state.set_state(Draw.meet_photo)
    await state.update_data(event_id=int(call.data.split("_")[1]))
    await call.message.answer(
        "📍 Пришлите фотографию места, где вручаете призы.\n\n"
        "<i>На большой площадке «подойдите к организатору» не находят, а "
        "снимок стойки находят сразу. Нет фотографии — напишите «пропустить».</i>")


@router.message(Draw.meet_photo, F.photo)
async def meet_photo_save(message: Message, state: FSMContext):
    await state.update_data(meet_photo=message.photo[-1].file_id)
    await state.set_state(Draw.meet_text)
    await message.answer(
        "Теперь одной строкой: где и во сколько.\n\n"
        "<i>Например: у стойки регистрации, справа от входа, в 19:30.</i>")


@router.message(Draw.meet_photo)
async def meet_photo_skip(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() not in ("пропустить", "-", "нет"):
        await message.answer("Пришлите фотографию или напишите «пропустить».")
        return
    await state.update_data(meet_photo=None)
    await state.set_state(Draw.meet_text)
    await message.answer("Одной строкой: где и во сколько.")


@router.message(Draw.meet_text)
async def meet_text_save(message: Message, state: FSMContext):
    place = (message.text or "").strip()
    if len(place) < 3:
        await message.answer("Слишком коротко. Где и во сколько?")
        return
    data = await state.get_data()
    await state.clear()
    await database.draw_event_update(
        data["event_id"], meet_place=place[:300],
        meet_photo=data.get("meet_photo"))
    event = await database.draw_event(event_id=data["event_id"])
    await message.answer(
        "✅ Место вручения сохранено. Осталось разослать призёрам.",
        reply_markup=_panel_kb(event) if event else None)


# ---------------------------------------------------------------------
# 4. Рассылка призёрам
# ---------------------------------------------------------------------

def _place_word(place: int) -> str:
    return {1: "🥇 Первое место", 2: "🥈 Второе место",
            3: "🥉 Третье место"}.get(place, f"{place}-е место")


async def _tell_winner(bot: Bot, event, place: int, user_id: int,
                       prizes: dict) -> bool:
    """Личное сообщение призёру: место, приз и куда подойти."""
    quiet = place > (event.get("prizes") or DEFAULT_PRIZES)
    head = _place_word(place)
    lines = [f"<b>{head}</b>", "", html.escape(event["title"])]
    if quiet:
        # Четвёртое место не объявляли вслух — и в письме тоже не делаем
        # вид, что это пьедестал. Зовём за подарком, а не вручаем медаль.
        lines = [f"🎁 <b>Для вас есть подарок</b>", "",
                 html.escape(event["title"]),
                 "Вы совсем немного не дошли до пьедестала — "
                 "и мы приготовили вам кое-что в утешение."]

    if event.get("meet_place"):
        lines.append("")
        lines.append(f"📍 {html.escape(event['meet_place'])}")

    prize = prizes.get(place)
    caption = "\n".join(lines)
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="✍️ Написать организатору",
        callback_data=f"drreply_{event['id']}")]])
    try:
        if prize and prize.get("photo"):
            await bot.send_photo(user_id, prize["photo"], caption=caption,
                                 reply_markup=markup)
        else:
            await bot.send_message(user_id, caption, reply_markup=markup)
        # Фотография места — отдельным сообщением: в одном с призом она
        # потерялась бы, а искать по ней будут глазами
        if event.get("meet_photo"):
            await bot.send_photo(user_id, event["meet_photo"],
                                 caption="Вот это место.")
        await database.draw_winner_notified(event["id"], user_id)
        return True
    except Exception as e:
        logging.warning(f"Призёр {user_id} не оповещён: {e}")
        return False


@router.callback_query(F.data.startswith("drsend_"))
async def send_winners(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    event_id = int(call.data.split("_")[1])
    event = await database.draw_event(event_id=event_id)
    winners = await database.draw_winners(event_id)
    if not event or not winners:
        await call.answer("Призёры ещё не определены.", show_alert=True)
        return

    await call.answer("Рассылаю…")
    prizes = await database.draw_prizes(event_id)
    sent = 0
    for place, user_id, _, _ in winners:
        if await _tell_winner(call.bot, event, place, user_id, prizes):
            sent += 1
    await call.message.answer(
        f"📨 Отправлено: {sent} из {len(winners)}.\n\n"
        f"<i>Кому не дошло — тот не начинал разговор с ботом. "
        f"Такие увидят сообщение, как только откроют его.</i>")


# ---------------------------------------------------------------------
# 5. Переписка
# ---------------------------------------------------------------------

# ---------------------------------------------------------------------
# Что происходит сейчас
# ---------------------------------------------------------------------

@router.callback_query(F.data.startswith("drstatus_"))
async def status_view(call: CallbackQuery):
    """Живая картина: кто вошёл, кто ответил, кто сыграл.

    Главное здесь — ВИДНО ЛИ ОТКЛИК. Половина нажавших «Участвовать»
    делает это из любопытства и больше не возвращается; строить на них
    сетку значит получить вечер из неявок.
    """
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    event_id = int(call.data.split("_")[1])
    event = await database.draw_event(event_id=event_id)
    if not event:
        await call.message.answer("Конкурс не найден.")
        return

    members = await database.draw_members(event_id)
    polls = await database.draw_polls_of_event(event_id)
    guessed = await database.draw_all_guessed(event_id)
    winners = await database.draw_winners(event_id)

    lines = [f"📊 <b>{html.escape(event['title'])}</b>", ""]
    lines.append(f"Нажали «Участвовать»: <b>{len(members)}</b>")

    if polls:
        answered = sum(1 for p in polls if p["sent"])
        decided = sum(1 for p in polls if p["correct"] is not None)
        lines.append(f"Матчей в расписании: {len(polls)}")
        lines.append(f"Вопросов разослано: {answered}")
        lines.append(f"Исход отмечен: {decided} из {len(polls)}")
        if decided < len(polls):
            lines.append("<i>Пока не отмечены все исходы, угадавших не "
                         "посчитать.</i>")

    if guessed:
        lines.append("")
        lines.append(f"Угадали все матчи: <b>{len(guessed)}</b>")
    if winners:
        lines.append("")
        lines.append("<b>Призёры определены:</b>")
        for place, _, name, notified in winners:
            mark = "📨" if notified else "•"
            lines.append(f"{mark} {_place_word(place)} — "
                         f"{html.escape(name or '')}")

    await call.message.answer("\n".join(lines),
                              reply_markup=_panel_kb(event),
                              parse_mode="HTML")


@router.callback_query(F.data.startswith("drdraw_"))
async def draw_bracket_now(call: CallbackQuery):
    """Жеребьёвка вручную — когда вы увидели, что партии сыграны."""
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    event_id = int(call.data.split("_")[1])
    await call.answer("Строю сетку…")
    import draws_runner
    result = await draws_runner.start_bracket(call.bot, event_id)
    await call.message.answer(f"🎲 {result}")


@router.callback_query(F.data.startswith("drsheet_"))
async def sheet_now(call: CallbackQuery):
    """Выгрузить текущую сетку файлом — по требованию, а не только при
    смене круга."""
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    event_id = int(call.data.split("_")[1])
    event = await database.draw_event(event_id=event_id)
    bracket = await database.bracket_of_event(event_id)
    if not event or not bracket:
        await call.answer("Сетки ещё нет.", show_alert=True)
        return
    await call.answer("Готовлю файл…")
    import draws_runner
    await draws_runner._send_owner_sheet(call.bot, bracket["id"], event)


# ---------------------------------------------------------------------
# Расписание матчей
# ---------------------------------------------------------------------

@router.callback_query(F.data.startswith("drsched_"))
async def schedule_ask(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    event_id = int(call.data.split("_")[1])
    await state.set_state(Draw.schedule)
    await state.update_data(event_id=event_id)

    existing = await database.draw_polls_of_event(event_id)
    head = (f"Сейчас заведено матчей: {len(existing)}.\n\n"
            if existing else "")
    await call.message.answer(
        f"📅 <b>Расписание матчей</b>\n\n{head}"
        f"Пришлите список одним сообщением, по строке на матч:\n\n"
        f"<code>18:00 Окунев — Кураков\n"
        f"19:30 Новиков — Кабочкин\n"
        f"21:00 Хали́лов — Бланк</code>\n\n"
        f"<i>Вопрос по каждому матчу уйдёт участникам в минуту начала, "
        f"ответы принимаются {POLL_MINUTES} минут. Разделитель между "
        f"фамилиями любой: тире, дефис или «vs».</i>")


@router.message(Draw.schedule)
async def schedule_save(message: Message, state: FSMContext):
    data = await state.get_data()
    event_id = data["event_id"]
    good, bad = parse_schedule(message.text or "")

    if not good:
        await message.answer(
            "Ни одной строки разобрать не вышло. Формат: время, пробел, "
            "две фамилии через тире.")
        return

    await state.clear()
    created = 0
    for when, first, second in good:
        poll_id = await database.draw_poll_open(
            event_id,
            question=f"Кто выиграет: {first} — {second}?",
            option_a=first, option_b=second,
            closes_at=when + timedelta(minutes=POLL_MINUTES),
            opens_at=when)
        if poll_id:
            created += 1

    lines = [f"✅ Заведено матчей: {created}."]
    if bad:
        lines.append("")
        lines.append("<b>Не разобрала эти строки:</b>")
        lines += [f"<code>{html.escape(x)}</code>" for x in bad[:8]]
    event = await database.draw_event(event_id=event_id)
    await message.answer("\n".join(lines),
                         reply_markup=_panel_kb(event) if event else None,
                         parse_mode="HTML")


# ---------------------------------------------------------------------
# Запуск: объявление в канале
# ---------------------------------------------------------------------

@router.callback_query(F.data.startswith("drlaunch_"))
async def launch(call: CallbackQuery):
    """Одно нажатие — и конкурс объявлен в канале.

    Фотография приза берётся из настроек, кнопка «Участвовать» ведёт
    не на страницу, а прямо в бота: нажавший попадает в список
    участников, и именно ему потом придут вопросы.
    """
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    event_id = int(call.data.split("_")[1])
    event = await database.draw_event(event_id=event_id)
    if not event:
        await call.answer("Конкурс не найден.", show_alert=True)
        return

    polls = await database.draw_polls_of_event(event_id)
    if not polls:
        await call.answer(
            "Сначала заведите расписание матчей — иначе участникам нечего "
            "будет присылать.", show_alert=True)
        return

    import digest
    chat, thread = await digest._target()
    if not chat:
        await call.answer("Канал не задан: /digest chat -100…", show_alert=True)
        return

    prizes = await database.draw_prizes(event_id)
    lines = [f"⚡️ <b>Внимание, конкурс</b>", "",
             f"<b>{html.escape(event['title'])}</b>", ""]
    lines.append(f"Сегодня {len(polls)} "
                 f"{'матч' if len(polls) == 1 else 'матча' if len(polls) < 5 else 'матчей'}. "
                 f"Перед каждым пришлём вопрос: кто победит. "
                 f"Отвечать можно {POLL_MINUTES} минут после начала — "
                 f"прямо глядя на корт.")
    if prizes:
        lines.append("")
        lines.append("<b>Призы:</b>")
        for place in sorted(prizes):
            caption = prizes[place].get("caption") or "приз"
            if place <= (event.get("prizes") or DEFAULT_PRIZES):
                lines.append(f"{_place_word(place)} — {html.escape(caption)}")
    lines.append("")
    lines.append("<i>Нажмите «Участвовать» — вопросы придут вам в личные "
                 "сообщения. В канале никто не увидит ни ваших ответов, "
                 "ни того, что вы участвуете.</i>")

    body = "\n".join(lines)
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="🎾 Участвовать", callback_data=f"drjoin_{event_id}")]])

    first_photo = next((prizes[p]["photo"] for p in sorted(prizes)
                        if prizes[p].get("photo")), None)
    try:
        if first_photo:
            await call.bot.send_photo(chat, first_photo, caption=body,
                                      message_thread_id=thread,
                                      reply_markup=markup)
        else:
            await call.bot.send_message(chat, body, message_thread_id=thread,
                                        reply_markup=markup)
    except Exception as e:
        await call.answer(f"Не вышло: {e}", show_alert=True)
        return

    await call.answer("Объявлено")
    await call.message.answer(
        "🚀 Конкурс объявлен в канале. Вопросы уйдут участникам сами, "
        "по времени из расписания.")


@router.callback_query(F.data.startswith("drjoin_"))
async def join(call: CallbackQuery):
    """«Участвовать» под постом канала.

    ЕДИНСТВЕННАЯ кнопка этого модуля, которой МОЖНО работать в канале
    (см. public.PUBLIC_OK). Поэтому ответ строго личный: в канале не
    должно быть видно ни кто участвует, ни сколько их.
    """
    try:
        event_id = int(call.data.split("_")[1])
    except (IndexError, ValueError):
        await call.answer()
        return

    event = await database.draw_event(event_id=event_id)
    if not event or event.get("status") != "open":
        await call.answer("Этот конкурс уже закрыт.", show_alert=True)
        return

    await database.draw_join(event_id, call.from_user.id)
    try:
        await call.bot.send_message(
            call.from_user.id,
            f"🎾 <b>Вы в конкурсе</b>\n\n{html.escape(event['title'])}\n\n"
            f"Перед каждым матчем пришлю вопрос: кто победит. Отвечать "
            f"можно {POLL_MINUTES} минут после начала — глядя на корт.\n\n"
            f"<i>Угадаете все матчи — попадёте в сетку розыгрыша призов.</i>")
        # Знак участника — сразу. По нему он найдёт себя в сетке, и
        # искать там чужие фотографии не придётся.
        try:
            import draw_image
            from aiogram.types import BufferedInputFile
            png = draw_image.avatar(call.from_user.id, 256)
            import io
            buffer = io.BytesIO()
            png.save(buffer, format="PNG")
            await call.bot.send_photo(
                call.from_user.id,
                BufferedInputFile(buffer.getvalue(), filename="znak.png"),
                caption="Это ваш знак на сегодня. По нему вы найдёте себя "
                        "в сетке розыгрыша — он не повторяется у других "
                        "и не меняется.")
        except Exception as e:
            logging.warning(f"Знак участника не ушёл: {e}")

        await call.answer("Вы в конкурсе — подробности в личке")
    except Exception:
        # Бот не может писать первым. Открываем его нажатием, а номер
        # конкурса передаём параметром — участие доедет само.
        username = await database.get_setting("bot_username")
        if username:
            await call.answer(
                url=f"https://t.me/{username.lstrip('@')}?start=draw-{event['slug']}")
        else:
            await call.answer(
                "Откройте бота и нажмите «Старт», потом нажмите сюда снова.",
                show_alert=True)


@router.callback_query(F.data.startswith("drtalk_"))
async def chat_open(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    try:
        _, event_id, user_id = call.data.split("_")
    except ValueError:
        await call.answer()
        return
    await call.answer()
    event_id, user_id = int(event_id), int(user_id)

    thread = await database.draw_chat_thread(event_id, user_id)
    lines = ["💬 <b>Переписка</b>", ""]
    if thread:
        for row in thread:
            who = "Вы" if row["from_owner"] else "Он"
            body = row["text"] or "📷 фотография"
            lines.append(f"<b>{who}:</b> {html.escape(body)[:200]}")
    else:
        lines.append("<i>Пока пусто.</i>")
    lines.append("")
    lines.append("Напишите сообщение — оно уйдёт ему личным сообщением.")

    await state.set_state(Draw.talking)
    await state.update_data(event_id=event_id, to_user=user_id)
    await call.message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Draw.talking)
async def chat_send(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    to_user = data.get("to_user")
    event_id = data.get("event_id")
    if not to_user:
        await state.clear()
        return

    text = (message.text or message.caption or "").strip()
    photo = message.photo[-1].file_id if message.photo else None
    if not text and not photo:
        await message.answer("Нечего отправить.")
        return

    try:
        if photo:
            await bot.send_photo(to_user, photo, caption=text or None)
        else:
            await bot.send_message(to_user, text)
    except Exception as e:
        await message.answer(f"⚠ Не доставлено: {e}")
        return

    await database.draw_chat_add(event_id, to_user, True, text or None, photo)
    # Состояние НЕ сбрасываем: разговор обычно не из одной реплики, и
    # выбирать собеседника заново перед каждой — издевательство.
    await message.answer(
        "✅ Отправлено.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🛑 Закончить разговор",
                                 callback_data=f"drstop_{event_id}")]]))


@router.callback_query(F.data.startswith("drstop_"))
async def chat_stop(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await state.clear()
    await call.answer("Разговор закрыт")


@router.callback_query(F.data.startswith("drreply_"))
async def winner_reply_start(call: CallbackQuery, state: FSMContext):
    """Призёр отвечает организатору. Разговор начинается нажатием, а не
    перехватом всех его сообщений: человек мог быть занят другим."""
    await call.answer()
    await state.set_state(Draw.replying)
    await state.update_data(event_id=int(call.data.split("_")[1]))
    await call.message.answer(
        "Напишите сообщение — организатор его получит.\n\n"
        "<i>Одно сообщение. Понадобится ещё — нажмите кнопку снова.</i>")


@router.message(Draw.replying)
async def winner_reply_send(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    event_id = data.get("event_id")

    text = (message.text or message.caption or "").strip()
    photo = message.photo[-1].file_id if message.photo else None
    if not text and not photo:
        await message.answer("Нечего отправить.")
        return

    await database.draw_chat_add(event_id, message.from_user.id, False,
                                 text or None, photo)
    if config.ADMIN_ID:
        who = html.escape(message.from_user.first_name or "Призёр")
        head = f"💬 <b>{who}</b> пишет по конкурсу:"
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="✍️ Ответить",
            callback_data=f"drtalk_{event_id}_{message.from_user.id}")]])
        try:
            if photo:
                await bot.send_photo(config.ADMIN_ID, photo,
                                     caption=f"{head}\n\n{html.escape(text)}",
                                     reply_markup=markup)
            else:
                await bot.send_message(config.ADMIN_ID,
                                       f"{head}\n\n{html.escape(text)}",
                                       reply_markup=markup)
        except Exception as e:
            logging.warning(f"Сообщение призёра не дошло владелице: {e}")
    await message.answer("✅ Передала организатору.")


# ---------------------------------------------------------------------
# 6. Завершение
# ---------------------------------------------------------------------

@router.callback_query(F.data.startswith("drfinish_"))
async def finish_ask(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await state.set_state(Draw.final_photo)
    await state.update_data(event_id=int(call.data.split("_")[1]))
    await call.message.answer(
        "🏁 Пришлите фотографию, которой завершаем конкурс.\n\n"
        "<i>Она уйдёт всем участникам вместе с итогами. Подпись к "
        "фотографии станет текстом сообщения.</i>")


@router.message(Draw.final_photo, F.photo)
async def finish_send(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    event_id = data["event_id"]
    event = await database.draw_event(event_id=event_id)
    if not event:
        await message.answer("Конкурс не найден.")
        return

    await database.draw_event_update(
        event_id, final_photo=message.photo[-1].file_id, status="closed")

    winners = await database.draw_winners(event_id)
    loud = [w for w in winners
            if w[0] <= (event.get("prizes") or DEFAULT_PRIZES)]
    lines = [f"🏁 <b>{html.escape(event['title'])}</b> — итоги", ""]
    for place, _, name, _ in loud:
        lines.append(f"{_place_word(place)} — {html.escape(name or 'участник')}")
    caption = (message.caption or "").strip()
    if caption:
        lines += ["", html.escape(caption)]
    body = "\n".join(lines)

    # В КАНАЛ — тоже. Конкурс объявляли там, и итоги должны вернуться
    # туда же: иначе читатель, который не участвовал, так и не узнает,
    # чем всё кончилось, — а ради него половина этого и затевалась.
    channel_body = body + (
        "\n\nСпасибо всем, кто играл. Следите за матчами — "
        "следующий конкурс скоро.")
    posted = False
    try:
        import digest
        chat, thread = await digest._target()
        if chat:
            await bot.send_photo(chat, message.photo[-1].file_id,
                                 caption=channel_body,
                                 message_thread_id=thread)
            posted = True
    except Exception as e:
        logging.warning(f"Итоги конкурса в канал не вышли: {e}")

    members = await database.draw_members(event_id)
    sent = 0
    for user_id in members:
        try:
            await bot.send_photo(user_id, message.photo[-1].file_id,
                                 caption=body)
            sent += 1
        except Exception:
            continue
    await message.answer(
        f"✅ Конкурс завершён. Итоги получили {sent} из {len(members)}."
        + ("\nВ канале опубликовано." if posted
           else "\n⚠ В канал не вышло — проверьте /digest chat."))


@router.message(Draw.final_photo)
async def finish_need_photo(message: Message):
    await message.answer("Нужна фотография — ею и завершаем.")
