# owner.py — управление содержимым кнопками, без команд.
#
# Команд в боте около девяноста, и половина из них — служебные. Держать
# их в голове нельзя, подглядывать в шпаргалку каждый раз — значит не
# пользоваться ими вовсе. Поэтому то же самое кнопками.
#
# Здесь не заводится ни одной новой возможности: каждая кнопка вызывает
# то, что уже работает. Старые команды остаются на местах — они быстрее,
# когда помнишь, и ничего не стоят, пока не набраны.
#
# Всё закрыто дважды. Права проверяются в каждом обработчике: кнопку
# видно только владелице, но callback приходит от кого угодно, и
# подделать его ничего не стоит. А в общем чате этих экранов нет вовсе —
# ни один callback не внесён в public.PUBLIC_OK, и граница на входе в
# диспетчер закрывает их по умолчанию.
import html
import logging

from aiogram import Router, F, Bot
from aiogram.types import (CallbackQuery, Message, InlineKeyboardMarkup,
                           InlineKeyboardButton)

import config

router = Router()

HOME = "🎛 <b>Управление</b>\n\nВсё, что выходит в канал, — отсюда."

# Разделы выпуска: слот → подпись на кнопке. Берём из расписания, а не
# списком: появится новый слот — он появится и здесь, без правки.
PUB_HEAD = ("📣 <b>Опубликовать сейчас</b>\n\n"
            "Выпуск выйдет немедленно и не станет ждать своего часа. "
            "Пропущенное утро иначе до завтра не вернуть.")

# Теннис живёт не только слотами: чемпион, нарезки и события выходят по
# своему обходу, а не по расписанию выпуска.
TENNIS_HEAD = ("🎾 <b>Теннис</b>\n\n"
               "Это выходит само, когда появляется повод. Кнопки — чтобы "
               "не ждать обхода.")

SETTINGS_HEAD = ("⚙️ <b>Куда и чем</b>\n\n"
                 "Каналы, ссылки и слежение. Показывает, что задано "
                 "сейчас; менять по-прежнему командой — адрес руками "
                 "не наберёшь кнопкой.")


def _rows(pairs) -> list:
    return [[InlineKeyboardButton(text=text, callback_data=data)]
            for text, data in pairs]


def menu_kb() -> InlineKeyboardMarkup:
    rows = _rows([
        ("📋 Что выйдет сегодня", "own_today"),
        ("📣 Опубликовать сейчас", "own_pub"),
        ("🎾 Теннис", "own_tennis"),
        ("📂 Материалы: править и удалять", "admin_content"),
        ("🖼 Картины", "admin_art"),
        ("📚 Книги", "admin_books"),
        ("🗓 План публикаций", "admin_plan"),
        ("📦 Запасы содержимого", "planstock"),
        ("⚙️ Куда и чем", "own_set"),
        ("🛠 Остальное служебное", "admin_panel"),
    ])
    rows.append([InlineKeyboardButton(text="⇦ В главное меню",
                                      callback_data="go_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pub_kb() -> InlineKeyboardMarkup:
    import digest
    pairs = []
    for _, slot, _ in digest.SCHEDULE:
        title = digest.SLOT_TITLES.get(slot, slot)
        pairs.append((title, f"ownpub_{slot}"))
    rows = _rows(pairs)
    rows.append([InlineKeyboardButton(text="⇦ Назад", callback_data="own_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tennis_kb() -> InlineKeyboardMarkup:
    rows = _rows([
        ("🏆 Чемпион турнира", "ownt_champion"),
        ("🎬 Нарезки матчей", "ownt_highlights"),
        ("⚡️ Громкие события", "ownt_events"),
        ("👀 Проверить чужие каналы", "ownt_watch"),
    ])
    rows.append([InlineKeyboardButton(text="⇦ Назад", callback_data="own_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _allowed(call: CallbackQuery) -> bool:
    """Права проверяются заново на каждом экране.

    Кнопку рисуем только владелице, но нажатие приходит от кого угодно:
    callback_data видно в клиенте, и повторить её ничего не стоит.
    """
    if config.is_admin(call.from_user.id):
        return True
    await call.answer()
    return False


@router.message(F.text.regexp(r"^/(управление|owner)\b"))
async def owner_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    await message.answer(HOME, reply_markup=menu_kb())


@router.callback_query(F.data == "own_menu")
async def open_menu(call: CallbackQuery):
    if not await _allowed(call):
        return
    await call.answer()
    await call.message.answer(HOME, reply_markup=menu_kb())


TODAY_HEAD = ("📋 <b>Что выйдет сегодня</b>\n\n"
              "Нажмите на строку — откроется сам материал: текст, "
              "фотография, правка, удаление.")


async def _today_lines():
    """[(подпись кнопки, callback)] и текст экрана.

    Выбор делается ровно так же, как при публикации: очередь раздела,
    первый, кто собирается и проходит проверку готовности. Иначе экран
    показывал бы одно, а в канал уходило другое.
    """
    import database
    import digest

    lines, buttons, taken = [], [], set()
    for at, slot, _ in digest.SCHEDULE:
        title = digest.SLOT_TITLES.get(slot, slot)
        section = digest.SLOT_SECTION.get(slot)

        if slot == "art":
            work = await database.art_next_unannounced()
            name = (work or {}).get("title")
            lines.append(f"{at} — {title}: "
                         + (html.escape(str(name)) if name
                            else "<i>все работы показаны</i>"))
            continue

        if not section:
            # Утро, итоги, расписание, задача и спортивный факт собираются
            # в момент выхода: показывать заранее нечего.
            lines.append(f"{at} — {title} <i>(по факту дня)</i>")
            continue

        picked = None
        for candidate in await database.next_candidates(section, limit=40):
            if (section, candidate) in taken:
                continue
            built = await digest._build(section, candidate)
            if not built or digest.readiness(section, built):
                continue
            taken.add((section, candidate))
            picked = (candidate, (built[0] or "")[:46])
            break

        if not picked:
            lines.append(f"{at} — {title}: <i>нечего</i>")
            continue
        item_id, name = picked
        lines.append(f"{at} — {title}: {html.escape(name)}")
        buttons.append((f"{at} · {name[:34]}", f"ce_open_{section}_{item_id}"))

    return lines, buttons


@router.callback_query(F.data == "own_today")
async def open_today(call: CallbackQuery):
    if not await _allowed(call):
        return
    await call.answer("Собираю…")
    try:
        lines, buttons = await _today_lines()
    except Exception as e:
        logging.error(f"Управление: что выйдет сегодня — {e}")
        await call.message.answer(f"Не собралось: {html.escape(str(e))}")
        return
    rows = _rows(buttons)
    rows.append([InlineKeyboardButton(text="⇦ Назад", callback_data="own_menu")])
    await call.message.answer(
        TODAY_HEAD + "\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "own_pub")
async def open_pub(call: CallbackQuery):
    if not await _allowed(call):
        return
    await call.answer()
    await call.message.answer(PUB_HEAD, reply_markup=pub_kb())


@router.callback_query(F.data.startswith("ownpub_"))
async def run_slot(call: CallbackQuery, bot: Bot):
    """Выпустить раздел немедленно"""
    if not await _allowed(call):
        return
    slot = call.data[len("ownpub_"):]
    import digest
    if slot not in [s for _, s, _ in digest.SCHEDULE]:
        await call.answer()
        return
    await call.answer("Выпускаю…")
    try:
        result = await digest.publish_slot(bot, slot)
    except Exception as e:
        logging.error(f"Управление: слот {slot} не вышел: {e}")
        result = f"ошибка: {e}"
    title = digest.SLOT_TITLES.get(slot, slot)
    await call.message.answer(
        f"{title}\n\n{html.escape(str(result))}", reply_markup=pub_kb())


@router.callback_query(F.data == "own_tennis")
async def open_tennis(call: CallbackQuery):
    if not await _allowed(call):
        return
    await call.answer()
    await call.message.answer(TENNIS_HEAD, reply_markup=tennis_kb())


@router.callback_query(F.data.startswith("ownt_"))
async def run_tennis(call: CallbackQuery, bot: Bot):
    """Теннисные обходы вручную"""
    if not await _allowed(call):
        return
    what = call.data[len("ownt_"):]
    await call.answer("Проверяю…")
    import digest
    chat, thread = await digest._target()
    try:
        if what == "watch":
            import tg_watch
            result = await tg_watch.check(bot)
        elif not chat:
            result = "канал не задан"
        elif what == "champion":
            import tennis_champion
            result = await tennis_champion.publish(bot, chat, thread)
        elif what == "highlights":
            import tennis_highlights
            result = await tennis_highlights.publish(bot, chat, thread)
        elif what == "events":
            import tennis_alerts
            result = await tennis_alerts.publish_events(bot, chat, thread)
        else:
            return
    except Exception as e:
        logging.error(f"Управление: теннис {what} — {e}")
        result = f"ошибка: {e}"
    await call.message.answer(f"🎾 {html.escape(str(result))}",
                              reply_markup=tennis_kb())


@router.callback_query(F.data == "own_set")
async def open_settings(call: CallbackQuery):
    """Что куда настроено. Показ, а не правка: адрес кнопкой не наберёшь."""
    if not await _allowed(call):
        return
    await call.answer()
    import database
    import digest

    async def shown(key: str) -> str:
        value = (await database.get_setting(key) or "").strip()
        return f"<code>{html.escape(value[:80])}</code>" if value else "—"

    lines = [SETTINGS_HEAD, ""]
    chat, thread = await digest._target()
    lines.append(f"Канал журнала: <code>{chat or '—'}</code>")
    lines.append(f"Канал картин: {await shown('art_channel')}")
    lines.append(f"Канал путешествий: {await shown('travel_channel')}")
    lines.append(f"Сайт художника: {await shown('art_site_url')}")
    lines.append(f"Слежу за каналами: {await shown('tg_watch_list')}")
    lines.append("")
    lines.append("<code>/art_site</code> · <code>/travel_channel</code> · "
                 "<code>/watch</code> · <code>/digest shop</code>")
    rows = [[InlineKeyboardButton(text="⇦ Назад", callback_data="own_menu")]]
    await call.message.answer("\n".join(lines),
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
