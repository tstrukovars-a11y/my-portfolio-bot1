# digest.py — публикация материалов бота в канал.
#
# Канал наполняется из того, что уже собрано разделами: генетика, рецепты,
# путешествия. Разделы чередуются, чтобы не выходило три рецепта подряд, а
# опубликованное запоминается — источники о канале ничего не знают и сами
# повторов не отследят.
#
# Цель публикации задаётся настройкой, а не константой: канал может смениться,
# и это не повод трогать код. Пока она пуста, публикация просто не идёт.
import asyncio
import html
import logging
from datetime import datetime, timezone
from urllib.parse import quote

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.exceptions import (TelegramForbiddenError, TelegramNetworkError,
                                TelegramRetryAfter)

import config
import database
import flags

router = Router()

TARGET_KEY = "digest_chat"       # id канала
THREAD_KEY = "digest_thread"     # тема, если целью выбрана группа с разделами
INTERVAL_HOURS = 12              # два поста в сутки: канал живой, но не назойливый

# Дубль в группу. Нужен потому, что Telegram не даёт привязать группу с темами
# как обсуждение канала, а ломать её разделы ради привязки — плохой размен.
# Пока настройка пуста, дубль не идёт и поведение прежнее.
MIRROR_KEY = "digest_mirror"
MIRROR_THREAD_KEY = "digest_mirror_thread"

# Тема задаётся отдельно для каждого раздела: в группе с разделами рецепт
# в теме про генетику выглядит ошибкой, а не публикацией. Раздел без своей
# темы падает на общую, а нет и её — уходит в общий поток группы.
SECTION_ALIASES = {
    "генетика": "genetics", "genetics": "genetics",
    "рецепты": "recipes", "кулинария": "recipes", "recipes": "recipes",
    "путешествия": "travel", "вокруг света": "travel", "travel": "travel",
}

# Время последней публикации. Хранится в базе, а не в памяти процесса:
# сервис перезапускается при каждом деплое, и интервал, отсчитанный от
# старта, превратил бы пять деплоев за вечер в пять постов подряд.
LAST_AT_KEY = "digest_last_at"

MAX_CAPTION = 1024
MAX_MESSAGE = 4096
MAX_FAILS = 3        # столько раз пробуем материал, прежде чем пропустить

# Порядок обхода. Меняется здесь же — раздел добавляется одной строкой,
# если он есть в database.DIGEST_SOURCES.
ROTATION = ["genetics", "recipes", "travel"]

SECTION_TITLES = {
    "genetics": "🧬 Генетика",
    "recipes": "🍳 Кулинария",
    "travel": "🌍 Путешествия",
}

# Вопрос читателю под каждым постом. Формулировка своя для раздела: «были
# там?» под рецептом бессмысленно. Это не украшение — вещание превращается
# в разговор, и по счётчику видно, что вообще читают.
VOTE_LABELS = {
    "genetics": "💡 Знали это",
    "recipes": "🍳 Готовили",
    "travel": "📍 Были здесь",
}


async def _target():
    """(чат, тема) либо (None, None), если канал ещё не задан"""
    chat = await database.get_setting(TARGET_KEY)
    if not chat:
        return None, None
    thread = await database.get_setting(THREAD_KEY)
    try:
        return int(chat), int(thread) if thread else None
    except (TypeError, ValueError):
        return None, None


async def _build(section: str, item_id: int):
    """(заголовок, текст, фото, видео, ссылка) материала конкретного раздела"""
    if section == "genetics":
        row = await database.get_article(item_id)
        if not row:
            return None
        title, text, photo, video, link = row
        return title, text, photo, video, link

    if section == "recipes":
        row = await database.get_recipe_by_id(item_id)
        if not row:
            return None
        text, video, link, photo = row
        title = (text or "").strip().split("\n")[0][:80]
        return title, text, photo, video, link

    if section == "travel":
        row = await database.get_travel_place(item_id)
        if not row:
            return None
        country, place, text, photo, video, link = row
        return f"{place} · {flags.with_flag(country)}", text, photo, video, link

    return None


def _split_caption(caption: str) -> tuple[str, str]:
    """Подпись под медиа и остаток. Режем по последнему переводу строки или
    пробелу, чтобы слово не разрывалось посередине."""
    if len(caption) <= MAX_CAPTION:
        return caption, ""
    head = caption[:MAX_CAPTION]
    cut = max(head.rfind("\n"), head.rfind(" "))
    if cut < MAX_CAPTION // 2:      # сплошной текст без пробелов — режем как есть
        cut = MAX_CAPTION
    return caption[:cut].rstrip(), caption[cut:].strip()


async def _send(bot: Bot, chat: int, thread, caption: str, photo, video, markup):
    """Отправляет пост и возвращает сообщение, к которому привязана публикация.

    При отказе повторяет один раз без кнопок: битая ссылка в кнопке — самая
    частая причина отказа, и пост без кнопки несравнимо лучше, чем материал,
    который третий день не может выйти.

    Повтор — только для той части, которая не прошла: общий повтор всего
    поста отправил бы картинку во второй раз.
    """
    async def once(send, kb, **kwargs):
        try:
            return await send(reply_markup=kb, **kwargs)
        except Exception as e:
            if not kb:
                raise
            logging.warning(f"Дайджест: отказ с кнопками ({e}) — повторяю без них")
            return await send(reply_markup=None, **kwargs)

    if photo or video:
        media = bot.send_video if video else bot.send_photo
        head, tail = _split_caption(caption)
        # Подпись под картинкой несёт настоящий текст, а не одно название
        # раздела: если продолжение не уйдёт, пост всё равно осмысленный.
        sent = await once(
            lambda **kw: media(chat, video or photo, caption=head, parse_mode=None,
                               message_thread_id=thread, **kw),
            None if tail else markup)
        if tail:
            await once(
                lambda **kw: bot.send_message(chat, tail[:MAX_MESSAGE], parse_mode=None,
                                              message_thread_id=thread, **kw),
                markup)
        return sent

    return await once(
        lambda **kw: bot.send_message(chat, caption[:MAX_MESSAGE], parse_mode=None,
                                      message_thread_id=thread, **kw),
        markup)


async def _mirror_thread(section: str) -> str:
    """Тема для раздела: своя, иначе общая, иначе общий поток группы"""
    return (await database.get_setting(f"{MIRROR_THREAD_KEY}_{section}")
            or await database.get_setting(MIRROR_THREAD_KEY))


async def _mirror(bot: Bot, from_chat: int, message_id: int, section: str):
    """Дублирует свежий пост в группу, если она задана.

    Именно пересылка, а не копия: у пересланного поста остаётся подпись
    канала, и по ней участники группы попадают в сам канал. Ради этого
    перехода дубль и нужен — копия без подписи роста не даёт.

    Ошибка дубля не отменяет публикацию: пост в канале уже вышел, и
    сбрасывать его из-за недоступной группы было бы хуже.
    """
    target = await database.get_setting(MIRROR_KEY)
    if not target:
        return
    thread = await _mirror_thread(section)
    try:
        await bot.forward_message(
            chat_id=int(target), from_chat_id=from_chat, message_id=message_id,
            message_thread_id=int(thread) if thread else None,
        )
    except Exception as e:
        logging.error(f"Дайджест: пост вышел, но дубль в группу не прошёл: {e}")


async def _ad_block() -> str:
    """Рекламная вставка, если она задана и срок не вышел"""
    text = await database.get_setting("digest_ad")
    if not text:
        return ""
    until = await database.get_setting("digest_ad_until")
    if until:
        try:
            if datetime.fromisoformat(until) < datetime.now():
                return ""
        except ValueError:
            pass
    return f"\n\n———\n{text}"


async def publish_next(bot: Bot) -> str:
    """Публикует следующий материал по ротации. Возвращает строку для лога."""
    chat, thread = await _target()
    if not chat:
        return "канал не задан — публикация пропущена"

    # Идём по кругу, начиная с раздела, следующего за прошлым: так разделы
    # чередуются, а исчерпанные не блокируют остальные.
    last = await database.get_setting("digest_last_section")
    order = ROTATION[ROTATION.index(last) + 1:] + ROTATION[:ROTATION.index(last) + 1] \
        if last in ROTATION else ROTATION

    for section in order:
        item_id = await database.next_for_digest(section)
        if not item_id:
            continue

        built = await _build(section, item_id)
        if not built:
            await database.mark_published(section, item_id)   # битую запись пропускаем
            continue

        title, text, photo, video, link = built
        head = SECTION_TITLES.get(section, section)
        body = (text or title or "").strip()
        caption = f"{head}\n\n{body}" + await _ad_block()

        rows = []
        # Ссылку чиним перед тем, как ставить в кнопку: материалы, ввезённые
        # до починки смещений, хранят обрубки вида «ttps://…», а такую кнопку
        # Telegram отвергает вместе со всем сообщением.
        import genetics
        safe_link = genetics.normalize_link(link)
        if safe_link:
            rows.append([InlineKeyboardButton(text="🔗 Подробнее", url=safe_link)])
        # Делимся каналом, а не отдельным постом: ссылка на пост приводит
        # читателя к одной записи, ссылка на канал — к подписке.
        # Отклик читателя. Счётчик показывается прямо на кнопке — пустая
        # кнопка «нравится» не говорит ничего, а «Были здесь · 14» говорит.
        label = VOTE_LABELS.get(section)
        if label:
            rows.append([InlineKeyboardButton(
                text=label, callback_data=f"vote_{section}_{item_id}")])

        channel_url = await database.get_setting("channel_url")
        if channel_url:
            rows.append([InlineKeyboardButton(
                text="📤 Поделиться",
                url="https://t.me/share/url?url=" + quote(channel_url, safe=""))])
        markup = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

        try:
            # parse_mode=None: текст пришёл из чужого поста и разметкой не является
            sent = await _send(bot, chat, thread, caption, photo, video, markup)
        except (TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter) as e:
            # Канал недоступен целиком — материал ни при чём. Очередь стоит
            # на месте: иначе за время недоступности весь архив пометился бы
            # вышедшим, ни разу не выйдя.
            await database.set_setting(
                "digest_last_error", f"канал недоступен: {str(e)[:180]}")
            logging.error(f"Дайджест: канал недоступен — {e}")
            return f"канал недоступен: {e}"
        except Exception as e:
            # Отказ по самому материалу. Три попытки — и пропускаем: один
            # непубликуемый материал три дня подряд не давал каналу ни одной
            # новой записи, и это хуже, чем потерять одну запись.
            key = f"digest_fail_{section}_{item_id}"
            fails = int(await database.get_setting(key) or 0) + 1
            await database.set_setting(key, str(fails))
            await database.set_setting(
                "digest_last_error", f"{section}/{item_id} ({fails}): {str(e)[:180]}")
            logging.error(f"Дайджест: {section}/{item_id} не вышел ({fails}/{MAX_FAILS}) — {e}")
            if fails >= MAX_FAILS:
                await database.mark_published(section, item_id)
                await database.set_setting(LAST_AT_KEY, datetime.now().isoformat())
                return f"материал пропущен после {fails} попыток: {e}"
            return f"ошибка публикации, попытка {fails} из {MAX_FAILS}: {e}"

        await database.mark_published(section, item_id, sent.message_id)
        await database.set_setting("digest_last_section", section)
        await database.set_setting(LAST_AT_KEY, datetime.now().isoformat())
        await _mirror(bot, chat, sent.message_id, section)
        return f"опубликовано: {section}/{item_id} — {title[:50]}"

    return "публиковать нечего: все материалы уже вышли"


async def _seconds_until_due() -> float:
    """Сколько ещё ждать — считая от прошлой публикации, а не от запуска"""
    raw = await database.get_setting(LAST_AT_KEY)
    if not raw:
        return 0.0
    try:
        last = datetime.fromisoformat(raw)
    except ValueError:
        return 0.0
    return max(0.0, INTERVAL_HOURS * 3600 - (datetime.now() - last).total_seconds())


async def scheduler(bot: Bot):
    """Фоновая публикация. Минута задержки на старте — чтобы бот успел
    подняться; дальше срок берётся из базы и перезапуск его не сбивает."""
    await asyncio.sleep(60)
    while True:
        wait = await _seconds_until_due()
        if wait > 0:
            await asyncio.sleep(min(wait, 3600))   # просыпаемся сверить время
            continue
        try:
            logging.info(f"Дайджест: {await publish_next(bot)}")
        except Exception as e:
            logging.error(f"Ошибка планировщика дайджеста: {e}")
        await asyncio.sleep(INTERVAL_HOURS * 3600)


# =====================================================================
# УПРАВЛЕНИЕ (только владелец)
# =====================================================================

@router.callback_query(F.data.startswith("vote_"))
async def take_vote(call: CallbackQuery):
    """Отклик читателя прямо под постом канала"""
    try:
        _, section, raw = call.data.split("_", 2)
        item_id = int(raw)
    except (ValueError, IndexError):
        await call.answer()
        return

    added, total = await database.toggle_vote(section, item_id, call.from_user.id)
    label = VOTE_LABELS.get(section, "Отклик")
    try:
        await call.message.edit_reply_markup(
            reply_markup=_with_vote(call.message.reply_markup, section, item_id,
                                    f"{label} · {total}" if total else label))
    except Exception:
        pass          # разметка могла не измениться — это не ошибка
    await call.answer("Отмечено" if added else "Отметка снята")


def _with_vote(markup, section: str, item_id: int, text: str):
    """Перерисовывает только кнопку отклика, не трогая остальные"""
    rows = []
    for row in (markup.inline_keyboard if markup else []):
        rows.append([
            InlineKeyboardButton(text=text, callback_data=b.callback_data)
            if b.callback_data == f"vote_{section}_{item_id}" else b
            for b in row])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == "/id")
async def show_chat_id(message: Message):
    """Показывает id чата и тему, откуда команду отправили.

    Нужно потому, что @userinfobot по пересланному сообщению показывает
    автора, а не чат: id группы через него не узнать в принципе.
    """
    if not config.is_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    thread = message.message_thread_id
    lines = [f"Чат: <code>{chat_id}</code>"]
    if thread:
        lines.append(f"Тема: <code>{thread}</code>")
    lines.append("\nГотовая команда — допишите раздел:")
    lines.append(f"<code>/digest mirror {chat_id}{f' {thread}' if thread else ''} генетика</code>")
    lines.append("\nРазделы: генетика, рецепты, путешествия")
    await message.answer("\n".join(lines))


@router.message(F.text.startswith("/digest"))
async def digest_command(message: Message, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=2)
    command = parts[1] if len(parts) > 1 else "status"

    if command == "now":
        await message.answer(f"📤 {await publish_next(bot)}")
        return

    if command == "chat" and len(parts) > 2:
        await database.set_setting(TARGET_KEY, parts[2].strip())
        await message.answer(f"✅ Канал публикации: <code>{html.escape(parts[2].strip())}</code>")
        return

    if command == "mirror" and len(parts) > 2:
        # «id_группы [номер_темы] [раздел]». Без раздела тема считается общей,
        # без темы — дубль идёт в общий поток группы.
        bits = parts[2].split()
        await database.set_setting(MIRROR_KEY, bits[0])
        thread = bits[1] if len(bits) > 1 else ""

        if len(bits) > 2:
            # Всё после номера темы — название раздела: у тем бывают имена
            # из нескольких слов, и обрывать их на первом было бы обидно.
            section = SECTION_ALIASES.get(" ".join(bits[2:]).lower())
            if not section:
                await message.answer(
                    "❌ Неизвестный раздел. Возможные: "
                    + ", ".join(sorted(set(SECTION_ALIASES) - set(SECTION_ALIASES.values())))
                )
                return
            await database.set_setting(f"{MIRROR_THREAD_KEY}_{section}", thread)
            await message.answer(
                f"✅ {SECTION_TITLES[section]} → группа "
                f"<code>{html.escape(bits[0])}</code>, тема {html.escape(thread) or 'общая'}"
            )
            return

        await database.set_setting(MIRROR_THREAD_KEY, thread)
        await message.answer(
            f"✅ Дубль в группу: <code>{html.escape(bits[0])}</code>"
            + (f" · тема {html.escape(thread)} для всех разделов без своей"
               if thread else " · общий поток")
        )
        return

    if command == "nomirror":
        await database.set_setting(MIRROR_KEY, "")
        for section in ROTATION:
            await database.set_setting(f"{MIRROR_THREAD_KEY}_{section}", "")
        await database.set_setting(MIRROR_THREAD_KEY, "")
        await message.answer("✅ Дубль в группу отключён, темы забыты.")
        return

    if command == "ad" and len(parts) > 2:
        await database.set_setting("digest_ad", parts[2])
        await message.answer("✅ Рекламный блок сохранён — пойдёт в следующие посты.")
        return

    if command == "noad":
        await database.set_setting("digest_ad", "")
        await message.answer("✅ Рекламный блок снят.")
        return

    chat, thread = await _target()
    stats = await database.digest_stats()
    lines = [
        "📤 <b>Дайджест-канал</b>",
        f"Цель: <code>{chat or 'не задана'}</code>"
        + (f" · тема {thread}" if thread else ""),
        f"Публикация раз в {INTERVAL_HOURS} ч",
    ]
    left = await _seconds_until_due()
    lines.append("Следующая: " + ("в ближайшую минуту" if left <= 0
                                  else f"через {int(left // 3600)} ч {int(left % 3600 // 60)} мин"))
    lines.append("")
    for section, data in stats.items():
        left = data["total"] - data["published"]
        lines.append(f"{SECTION_TITLES.get(section, section)}: "
                     f"{data['published']} из {data['total']}, осталось {left}")

    mirror = await database.get_setting(MIRROR_KEY)
    lines.append(f"\nДубль в группу: <code>{mirror or 'нет'}</code>")
    if mirror:
        for section in ROTATION:
            thread = await _mirror_thread(section)
            lines.append(f"  {SECTION_TITLES.get(section, section)} → "
                         + (f"тема {thread}" if thread else "общий поток"))

    ad = await database.get_setting("digest_ad")
    lines.append(f"Реклама: {'есть' if ad else 'нет'}")

    error = await database.get_setting("digest_last_error")
    if error:
        lines.append(f"\n⚠️ Последний сбой: <code>{html.escape(error)}</code>")
    lines.append("\n<code>/digest now</code> — опубликовать сейчас\n"
                 "<code>/digest chat -100…</code> — задать канал\n"
                 "<code>/digest mirror -100… тема раздел</code> — дубль в группу\n"
                 "<code>/digest nomirror</code> — не дублировать\n"
                 "<code>/digest ad текст</code> — рекламный блок\n"
                 "<code>/digest noad</code> — снять рекламу")
    await message.answer("\n".join(lines))
