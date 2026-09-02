# tennis_alerts.py — расписание матчей в канале и личные напоминания.
#
# Задача, которая казалась неразрешимой: канал общий, а напоминание должно
# быть личным. Развязка в том, что это разные каналы связи.
#
#   пост в канале   — общий, его видят все;
#   нажатие кнопки  — callback, его видит только бот;
#   ссылка к началу — личное сообщение, его получает один человек.
#
# Никто из подписчиков не видит, кто и что отметил. Счётчик на кнопке
# показывает лишь число — сколько людей собирается смотреть.
import asyncio
import html
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.exceptions import TelegramForbiddenError
from aiogram.dispatcher.event.bases import SkipHandler

import config
import database
import players_ru
import tennis_live

router = Router()

MAX_MATCHES = 8          # больше кнопок под постом не читается
CHECK_EVERY = 60         # раз в минуту: слать надо в момент начала,
                         # а не «когда-нибудь в ближайшие две»
# За сколько минут до начала слать. Десять — чтобы успеть включить
# трансляцию. Ноль означал бы «в момент начала».
LEAD_DEFAULT = 10
LEAD_KEY = "tennis_lead"
RESULTS_MAX = 12         # длиннее сводку с утра не читают


def _title(match) -> str:
    """Кто с кем — коротко, для кнопки"""
    sides = match.get("sides") or []
    names = [tennis_live._player(s) for s in sides[:2]]
    return " — ".join(n for n in names if n) or "матч"


def _with_flags(match) -> str:
    """Кто с кем, с флагами — для строки поста и для напоминания.

    На кнопке флагов нет: там дорог каждый символ, Telegram обрезает
    подпись, и имена важнее.
    """
    sides = match.get("sides") or []
    names = [tennis_live._named(s) for s in sides[:2]]
    return " — ".join(n for n in names if n) or "матч"


def _event(match) -> str:
    """Название турнира по-русски"""
    return players_ru.event(match.get("tournament") or "")


def _full_title(match) -> str:
    """Матч с турниром — для напоминания в личку.

    В канале турнир стоит заголовком над группой матчей, а в личное
    сообщение приходит один матч, и без турнира непонятно, о чём речь.
    """
    short = _with_flags(match)
    event = _event(match)
    return f"{event} · {short}" if event else short


def _starts(match):
    """Время начала как datetime либо None"""
    raw = match.get("date")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _today(tour: str):
    """Матчи сегодняшнего дня, которые ещё не сыграны.

    Источник отдаёт турнир целиком: на «Шлеме» это три недели и три сотни
    матчей. Отбора по дате не было, и в расписание лезли матчи недельной
    давности — «не completed» они потому, что так и не состоялись.

    День считаем по часам канала, а не сервера: Render живёт по UTC.
    """
    shift = await _shift()
    local_now = datetime.now(timezone.utc) + shift
    today = local_now.date()

    data = await tennis_live.fetch_scoreboard(tour)
    out = []
    for match in tennis_live._singles(data, tour, big_only=True):
        if match.get("completed") or not match.get("id"):
            continue
        when = _starts(match)
        if not when:
            continue
        local = when + shift
        # Начавшийся три часа назад и до сих пор не закрытый матч —
        # это брошенная запись источника, а не то, что стоит анонсировать.
        if local.date() != today or local < local_now - timedelta(hours=3):
            continue
        out.append(match)
    out.sort(key=lambda m: m.get("date") or "")
    return out


async def _lead() -> int:
    """За сколько минут предупреждать. Меняется без передеплоя."""
    try:
        return max(0, min(60, int(await database.get_setting(LEAD_KEY)
                                  or LEAD_DEFAULT)))
    except (TypeError, ValueError):
        return LEAD_DEFAULT


def _minutes_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "минуту"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "минуты"
    return "минут"


def _lead_phrase(lead: int) -> str:
    if lead <= 0:
        return "Напомню, когда матч начнётся."
    return f"Напомню за {lead} {_minutes_word(lead)} до начала."


async def _shift():
    """Разница между часами канала и UTC.

    Округляем до минуты: разность двух «сейчас» тянет за собой микросекунды,
    и матч в 18:00 превращался в 17:59.
    """
    import digest
    raw = await digest._local_now() - datetime.now(timezone.utc)
    return timedelta(minutes=round(raw.total_seconds() / 60))


def _matches_word(n: int) -> str:
    """матч / матча / матчей"""
    if n % 10 == 1 and n % 100 != 11:
        return "матч"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "матча"
    return "матчей"


def _watch_link(tour: str) -> str:
    return tennis_live.TOURS[tour]["schedule"]


def _watch_rows(tour: str):
    """Куда идти смотреть. Порядок неслучайный: сначала свои площадки —
    они на русском, без подписки и без региональных замков, — потом живой
    счёт на случай, если трансляции для этого матча нет."""
    return [
        [InlineKeyboardButton(text="📺 Канал «Больше»",
                              url=tennis_live.BOLSHE_URL)],
        [InlineKeyboardButton(text="📡 Прайм спорт",
                              url=tennis_live.PRIME_SPORT_URL)],
        [InlineKeyboardButton(text=f"📊 Счёт вживую · {tennis_live.TOURS[tour]['title']}",
                              url=_watch_link(tour))],
        [InlineKeyboardButton(text=f"🗓 Сетка {tennis_live.TOURS[tour]['title']}",
                              url=tennis_live.TOURS[tour]["draws"])],
    ]


# =====================================================================
# РАСПИСАНИЕ В КАНАЛ
# =====================================================================

async def publish_schedule(bot: Bot, chat: int, thread=None) -> str:
    """Один пост на тур со списком матчей и кнопками «напомнить»"""
    # Часы канала: у источника время в UTC, а в посте оно должно совпадать
    # с тем, что читатель видит на своих часах.
    shift = await _shift()
    lead = await _lead()

    posted = 0
    for tour in ("wta", "atp"):
        day = await _today(tour)
        if not day:
            continue
        # Показываем ближайшие по времени, а выводим сгруппированно по
        # турниру — иначе заголовки турниров пошли бы вперемешку.
        matches = sorted(day[:MAX_MATCHES],
                         key=lambda m: (_event(m), m.get("date") or ""))
        rest = len(day) - len(matches)

        lines = [f"🎾 <b>{tennis_live.TOURS[tour]['title']} — сегодня</b>"]
        rows = []
        # Матчи сгруппированы по турниру: без него список читается как
        # набор фамилий, а турнир — половина того, ради чего смотрят.
        current = None
        for m in matches:
            event = _event(m)
            if event != current:
                current = event
                lines.append(f"\n<b>{html.escape(event)}</b>" if event else "")
            when = _starts(m)
            clock = (when + shift).strftime("%H:%M") if when else "—"
            title = _title(m)
            rnd = players_ru.rnd(m.get("round") or "")
            lines.append(f"{clock} · {html.escape(_with_flags(m))}"
                         + (f" · <i>{html.escape(rnd)}</i>" if rnd else ""))
            rows.append([InlineKeyboardButton(
                text=f"🔔 {title[:38]}", callback_data=f"tmatch_{tour}_{m['id']}")])

        lines.append("")
        if rest:
            lines.append(f"И ещё {rest} {_matches_word(rest)} сегодня — в сетке.")
        lines.append(
            f"Нажмите на матч — пришлю ссылку на трансляцию в личные "
            f"сообщения, {('за ' + str(lead) + ' ' + _minutes_word(lead) + ' до начала') if lead else 'к началу'}.")

        # Сетка — последней строкой кнопок: список матчей на сегодня
        # отвечает «что смотреть», сетка — «кто с кем дальше».
        rows.append([InlineKeyboardButton(
            text=f"🗓 Сетка {tennis_live.TOURS[tour]['title']}",
            url=tennis_live.TOURS[tour]["draws"])])

        try:
            await bot.send_message(chat, "\n".join(lines),
                                   message_thread_id=thread,
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            posted += 1
        except Exception as e:
            logging.error(f"Расписание {tour} не вышло: {e}")
        await asyncio.sleep(3.2)

    return f"расписание: постов {posted}" if posted else "матчей на сегодня нет"


@router.message(F.text == "/tennis_schedule")
async def schedule_command(message: Message, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return
    import digest
    chat, thread = await digest._target()
    if not chat:
        await message.answer("❌ Канал не задан: <code>/digest chat -100…</code>")
        return
    await message.answer(f"🎾 {await publish_schedule(bot, chat, thread)}")


async def _finished(tour: str, day):
    """Сыгранные матчи названного дня, по часам канала"""
    shift = await _shift()
    data = await tennis_live.fetch_scoreboard(tour)
    out = []
    for match in tennis_live._singles(data, tour, big_only=True):
        if not match.get("completed"):
            continue
        when = _starts(match)
        if not when or (when + shift).date() != day:
            continue
        out.append(match)
    out.sort(key=lambda m: m.get("date") or "")
    return out


def _result_line(match) -> str:
    """Победитель жирным, счёт в конце — как в газетной таблице"""
    sides = sorted(match.get("sides") or [], key=lambda s: not s.get("winner"))
    if len(sides) < 2:
        return ""
    win, lose = sides[0], sides[1]
    score = tennis_live._score(win, lose)
    pair = (f"<b>{html.escape(tennis_live._named(win))}</b> — "
            f"{html.escape(tennis_live._named(lose))}")
    return pair + (f"  <code>{html.escape(score)}</code>" if score else "")


async def publish_results(bot: Bot, chat: int, thread=None) -> str:
    """Итоги вчерашнего дня — утром, пока результаты ещё новость"""
    shift = await _shift()
    yesterday = (datetime.now(timezone.utc) + shift - timedelta(days=1)).date()

    blocks = []
    for tour in ("wta", "atp"):
        played = await _finished(tour, yesterday)
        if not played:
            continue
        lines = [f"<b>{tennis_live.TOURS[tour]['title']}</b>"]
        current = None
        for m in played[:RESULTS_MAX]:
            event = _event(m)
            if event != current:
                current = event
                lines.append(f"<i>{html.escape(event)}</i>")
            line = _result_line(m)
            if line:
                lines.append(line)
        rest = len(played) - min(len(played), RESULTS_MAX)
        if rest:
            lines.append(f"<i>…и ещё {rest} {_matches_word(rest)}</i>")
        blocks.append("\n".join(lines))

    if not blocks:
        return "вчера крупных матчей не было"

    head = f"🎾 <b>Вчера на кортах — {yesterday.strftime('%d.%m')}</b>"
    text = head + "\n\n" + "\n\n".join(blocks)
    rows = [[InlineKeyboardButton(
        text=f"🗓 Сетка {tennis_live.TOURS[tour]['title']}",
        url=tennis_live.TOURS[tour]["draws"])] for tour in ("wta", "atp")]
    try:
        await bot.send_message(chat, text[:4096],
                               message_thread_id=thread,
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except Exception as e:
        logging.error(f"Сводка результатов не вышла: {e}")
        return f"ошибка: {e}"
    return "итоги вчерашнего дня"


@router.message(F.text.startswith("/tennis_lead"))
async def lead_command(message: Message):
    """За сколько минут предупреждать: 0 — ровно в момент начала"""
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) > 1:
        try:
            value = max(0, min(60, int(parts[1])))
        except ValueError:
            await message.answer("Нужно число минут: <code>/tennis_lead 0</code>")
            return
        await database.set_setting(LEAD_KEY, str(value))
        await message.answer(f"✅ {_lead_phrase(value)}")
        return
    await message.answer(
        f"Сейчас: {_lead_phrase(await _lead())}\n\n"
        "Изменить: <code>/tennis_lead 0</code> — в момент начала, "
        "<code>/tennis_lead 15</code> — за четверть часа.")


@router.message(F.text.regexp(r"^/start\s+tm-"))
async def start_with_match(message: Message, bot: Bot):
    """Пришёл из канала по кнопке напоминания: дооформляем подписку на матч.

    Этот роутер зарегистрирован раньше общего /start, поэтому в конце
    обязательно передаём ход дальше — иначе новый человек не увидит ни
    приветствия, ни выбора языка, а он тут первый раз.
    """
    await _handle_match_start(message, bot)
    raise SkipHandler


async def _handle_match_start(message: Message, bot: Bot):
    payload = message.text.split(maxsplit=1)[1].strip()
    try:
        _, tour, match_id = payload.split("-", 2)
    except ValueError:
        return
    if tour not in tennis_live.TOURS:
        return

    if not (config.is_admin(message.from_user.id)
            or await database.check_subscription(message.from_user.id)):
        await message.answer(NO_SUB)
        return

    matches = await _today(tour)
    match = next((m for m in matches if m["id"] == match_id), None)
    if not match:
        await message.answer("Этот матч уже начался или завершился.")
        return

    ok = await database.ensure_alert(
        message.from_user.id, match_id, tour, _full_title(match), _starts(match))
    if ok is None:
        await message.answer("Не получилось сохранить напоминание. "
                             "Попробуйте ещё раз через минуту.")
        return
    await _confirm(bot, message.from_user.id, tour, match_id,
                   _full_title(match), _starts(match))


@router.message(F.text.startswith("/tennis_test"))
async def test_command(message: Message, bot: Bot):
    """Проверка напоминаний целиком, а не на словах.

    Сначала присылает образец сразу — видно, как выглядит. Затем кладёт в
    базу настоящую запись на ближайшую минуту: её подберёт тот же
    планировщик, что и боевые. Если сломается запись — команда скажет об
    этом сразу, а не промолчит, как было.
    """
    if not config.is_admin(message.from_user.id):
        return

    # /tennis_test wta — проверить женский вариант: подписи и ссылки
    # у туров разные, и смотреть надо оба.
    parts = message.text.split()
    tour = parts[1].lower() if len(parts) > 1 and parts[1].lower() in tennis_live.TOURS else "atp"

    lead = await _lead()
    title = f"Проверка · {tennis_live.TOURS[tour]['title']} — тестовый матч"

    # 1. Образец прямо сейчас
    head = "Начинается" if lead <= 0 else f"Начнётся через {lead} {_minutes_word(lead)}"
    try:
        await bot.send_message(
            message.from_user.id,
            f"🎾 <b>{html.escape(title)}</b>\n\n{head}. Где смотреть:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=_watch_rows(tour)),
            disable_web_page_preview=True)
    except TelegramForbiddenError:
        await message.answer("❌ Бот не может вам писать. Нажмите «Старт» в личке.")
        return

    # 2. Настоящая запись — через минуту её должен взять планировщик
    match_id = f"test-{int(datetime.now(timezone.utc).timestamp())}"
    starts = datetime.now(timezone.utc) + timedelta(minutes=lead + 1)
    added, _ = await database.toggle_alert(
        message.from_user.id, match_id, tour, title, starts)

    if added is None:
        await message.answer(
            "☝️ Образец пришёл, но <b>запись в базу не удалась</b> — "
            "значит, боевые напоминания тоже не сохранятся. Причина в "
            "логах Render по слову «Напоминание не сохранено».")
        return
    await message.answer(
        "✅ Образец отправлен.\n"
        f"И поставлено настоящее напоминание: планировщик должен прислать "
        f"его в течение минуты. Придёт — значит, весь путь рабочий.")


@router.message(F.text == "/tennis_results")
async def results_command(message: Message, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return
    import digest
    chat, thread = await digest._target()
    if not chat:
        await message.answer("❌ Канал не задан: <code>/digest chat -100…</code>")
        return
    await message.answer(f"🎾 {await publish_results(bot, chat, thread)}")


# =====================================================================
# ЛИЧНАЯ ОТМЕТКА
# =====================================================================

NO_SUB = ("🎾 Напоминания о матчах — часть теннисной подписки.\n\n"
          "Оформить: откройте бота → Спорт → Большой теннис.")
NO_CHAT = ("Чтобы получать напоминания, откройте бота и нажмите «Старт» — "
           "иначе я не смогу вам написать.")


async def _deep_link(payload: str) -> str:
    """Ссылка, открывающая бота с параметром. Пусто — имя бота не задано."""
    username = await database.get_setting("bot_username")
    if not username:
        return ""
    return f"https://t.me/{username.lstrip('@')}?start={payload}"


async def _open_bot(call: CallbackQuery, payload: str, fallback: str) -> None:
    """Открыть бота у нажавшего.

    Читатель «Акцента» пришёл из репоста или поиска и о существовании бота
    не знает — предложение «нажмите Старт» для него бессмысленно. Telegram
    разрешает ответить на нажатие ссылкой на самого себя: человек одним
    касанием попадает в бота, и /start приходит уже с параметром.
    """
    url = await _deep_link(payload)
    if url:
        await call.answer(url=url)
    else:
        await call.answer(fallback, show_alert=True)


@router.callback_query(F.data.startswith("tmatch_"))
async def toggle_match(call: CallbackQuery):
    try:
        _, tour, match_id = call.data.split("_", 2)
    except ValueError:
        await call.answer()
        return

    # Подписка проверяется здесь, а не при показе: расписание видят все,
    # платят только за напоминание. Так пост работает и как витрина.
    if not (config.is_admin(call.from_user.id)
            or await database.check_subscription(call.from_user.id)):
        # Не «у вас нет подписки», а сразу экран, где её оформляют.
        await _open_bot(call, "sport_tennis", NO_SUB)
        return

    matches = await _today(tour)
    match = next((m for m in matches if m["id"] == match_id), None)
    title = _title(match) if match else "матч"
    starts = _starts(match) if match else None

    # В базу — с турниром (это уйдёт в личку), на кнопку — короткое имя.
    full = _full_title(match) if match else title
    added, total = await database.toggle_alert(
        call.from_user.id, match_id, tour, full, starts)

    if added is None:
        await call.answer("Не получилось сохранить. Нажмите ещё раз.",
                          show_alert=True)
        return

    try:
        await call.message.edit_reply_markup(
            reply_markup=_with_count(call.message.reply_markup,
                                     f"tmatch_{tour}_{match_id}", title, total))
    except Exception:
        pass

    # Кнопка в канале одна на всех: Telegram не умеет показывать разным
    # читателям разные подписи. Личный переключатель поэтому уезжает в
    # личку — там клавиатура своя у каждого, и колокольчик честно
    # показывает состояние.
    if added:
        sent = await _confirm(call.bot, call.from_user.id, tour, match_id, full, starts)
        if sent:
            lead = await _lead()
            await call.answer("🔔 " + _lead_phrase(lead))
        else:
            # Бот не может написать первым: открываем его нажатием, а матч
            # передаём параметром — подписка доедет сама.
            await _open_bot(call, f"tm-{tour}-{match_id}", NO_CHAT)
    else:
        await call.answer("🔕 Напоминание снято")


async def _confirm(bot: Bot, user_id: int, tour: str, match_id: str,
                   title: str, starts) -> bool:
    """Личное подтверждение с кнопкой «выключить». False — бот не пишет."""
    shift = await _shift()
    when = (starts + shift).strftime("%H:%M") if starts else "по расписанию"
    lead = await _lead()
    text = (f"🔔 <b>Напоминание включено</b>\n\n{html.escape(title)}\n"
            f"Начало в {when}. {_lead_phrase(lead)}")
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="🔕 Выключить напоминание",
        callback_data=f"tmute_{tour}_{match_id}")]])
    try:
        await bot.send_message(user_id, text, reply_markup=markup)
        return True
    except TelegramForbiddenError:
        return False
    except Exception as e:
        logging.warning(f"Подтверждение {user_id} не ушло: {e}")
        return False


@router.callback_query(F.data.startswith("tmute_"))
async def mute_match(call: CallbackQuery):
    """Выключение из личного сообщения — колокольчик меняется на месте"""
    try:
        _, tour, match_id = call.data.split("_", 2)
    except ValueError:
        await call.answer()
        return
    off = await database.drop_alert(call.from_user.id, match_id)
    try:
        await call.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🔔 Включить обратно",
                    callback_data=f"tback_{tour}_{match_id}")]]))
    except Exception:
        pass
    await call.answer("🔕 Выключено" if off else "Уже было выключено")


@router.callback_query(F.data.startswith("tback_"))
async def unmute_match(call: CallbackQuery):
    try:
        _, tour, match_id = call.data.split("_", 2)
    except ValueError:
        await call.answer()
        return
    matches = await _today(tour)
    match = next((m for m in matches if m["id"] == match_id), None)
    added = await database.ensure_alert(
        call.from_user.id, match_id, tour,
        _full_title(match) if match else "матч",
        _starts(match) if match else None)
    if added is None:
        await call.answer("Не получилось. Нажмите ещё раз.", show_alert=True)
        return
    try:
        await call.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🔕 Выключить напоминание",
                    callback_data=f"tmute_{tour}_{match_id}")]]))
    except Exception:
        pass
    await call.answer("🔔 Включено")


def _with_count(markup, data: str, title: str, total: int):
    """Обновляет только свою кнопку: соседние матчи не трогаем"""
    rows = []
    for row in (markup.inline_keyboard if markup else []):
        rows.append([
            InlineKeyboardButton(
                text=f"🔔 {title[:34]}" + (f" · {total}" if total else ""),
                callback_data=b.callback_data)
            if b.callback_data == data else b
            for b in row])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# =====================================================================
# ДОСТАВКА
# =====================================================================

async def alerts_scheduler(bot: Bot):
    """Раз в две минуты смотрит, кому пора слать ссылку.

    Заблокировавший бота помечается доставленным: повторять некому, а
    вечно висящее напоминание засоряет очередь.
    """
    await asyncio.sleep(90)
    while True:
        try:
            lead = await _lead()
            for user_id, match_id, tour, title in await database.due_alerts(lead):
                head = ("Начинается" if lead <= 0
                        else f"Начнётся через {lead} {_minutes_word(lead)}")
                text = (f"🎾 <b>{html.escape(title or 'Матч')}</b>\n\n"
                        f"{head}. Где смотреть:")
                markup = InlineKeyboardMarkup(inline_keyboard=_watch_rows(tour))
                try:
                    await bot.send_message(user_id, text,
                                           reply_markup=markup,
                                           disable_web_page_preview=True)
                except TelegramForbiddenError:
                    logging.info(f"Напоминание: {user_id} заблокировал бота")
                except Exception as e:
                    logging.warning(f"Напоминание {user_id} не ушло: {e}")
                    continue
                await database.mark_alert_sent(user_id, match_id)
                await asyncio.sleep(0.1)
        except Exception as e:
            logging.error(f"Ошибка рассылки напоминаний: {e}")
        await asyncio.sleep(CHECK_EVERY)
