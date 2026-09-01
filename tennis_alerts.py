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

import config
import database
import players_ru
import tennis_live

router = Router()

MAX_MATCHES = 8          # больше кнопок под постом не читается
CHECK_EVERY = 120        # как часто смотреть, кому пора слать
LEAD_MINUTES = 10        # за сколько до начала


def _title(match) -> str:
    """Кто с кем — коротко, для кнопки"""
    sides = match.get("sides") or []
    names = [tennis_live._player(s) for s in sides[:2]]
    return " — ".join(n for n in names if n) or "матч"


def _event(match) -> str:
    """Название турнира по-русски"""
    return players_ru.event(match.get("tournament") or "")


def _full_title(match) -> str:
    """Матч с турниром — для напоминания в личку.

    В канале турнир стоит заголовком над группой матчей, а в личное
    сообщение приходит один матч, и без турнира непонятно, о чём речь.
    """
    short = _title(match)
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
    for match in tennis_live._singles(data, tour):
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


# =====================================================================
# РАСПИСАНИЕ В КАНАЛ
# =====================================================================

async def publish_schedule(bot: Bot, chat: int, thread=None) -> str:
    """Один пост на тур со списком матчей и кнопками «напомнить»"""
    # Часы канала: у источника время в UTC, а в посте оно должно совпадать
    # с тем, что читатель видит на своих часах.
    shift = await _shift()

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
            lines.append(f"{clock} · {html.escape(title)}"
                         + (f" · <i>{html.escape(rnd)}</i>" if rnd else ""))
            rows.append([InlineKeyboardButton(
                text=f"🔔 {title[:38]}", callback_data=f"tmatch_{tour}_{m['id']}")])

        lines.append("")
        if rest:
            lines.append(f"И ещё {rest} {_matches_word(rest)} сегодня — в сетке.")
        lines.append("Нажмите на матч — пришлю ссылку на трансляцию к началу, "
                     "в личные сообщения.")

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


# =====================================================================
# ЛИЧНАЯ ОТМЕТКА
# =====================================================================

NO_SUB = ("🎾 Напоминания о матчах — часть теннисной подписки.\n\n"
          "Оформить: откройте бота → Спорт → Большой теннис.")
NO_CHAT = ("Чтобы получать напоминания, откройте бота и нажмите «Старт» — "
           "иначе я не смогу вам написать.")


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
        await call.answer(NO_SUB, show_alert=True)
        return

    matches = await _today(tour)
    match = next((m for m in matches if m["id"] == match_id), None)
    title = _title(match) if match else "матч"
    starts = _starts(match) if match else None

    # В базу — с турниром (это уйдёт в личку), на кнопку — короткое имя.
    added, total = await database.toggle_alert(
        call.from_user.id, match_id, tour,
        _full_title(match) if match else title, starts)

    try:
        await call.message.edit_reply_markup(
            reply_markup=_with_count(call.message.reply_markup,
                                     f"tmatch_{tour}_{match_id}", title, total))
    except Exception:
        pass
    await call.answer("Напомню к началу" if added else "Напоминание снято")


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
            for user_id, match_id, tour, title in await database.due_alerts(LEAD_MINUTES):
                text = (f"🎾 <b>{html.escape(title or 'Матч')}</b>\n\n"
                        f"Начинается. Трансляция и счёт:\n{_watch_link(tour)}")
                draw = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text=f"🗓 Сетка {tennis_live.TOURS[tour]['title']}",
                        url=tennis_live.TOURS[tour]["draws"])]])
                try:
                    await bot.send_message(user_id, text,
                                           reply_markup=draw,
                                           disable_web_page_preview=False)
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
