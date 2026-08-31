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
import json
import logging
import os
from datetime import datetime, timedelta, timezone
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

# =====================================================================
# СЕТКА ВЕЩАНИЯ
#
# День канала расписан по часам, а не отдан ротации: читатель привыкает
# к тому, что утром новости, а вечером рецепт, и приходит сам. Ротация
# «что-нибудь раз в двенадцать часов» такой привычки не создаёт.
#
# Время местное для читателя, а не для сервера: канал русскоязычный,
# поэтому по умолчанию Москва. Смена часового пояса — настройка, потому
# что каналов будет четыре и у каждого своё утро.
# =====================================================================

SCHEDULE = [
    ("08:00", "morning",  "Доброе утро. Вот что случилось вчера — коротко и по делу."),
    ("11:00", "books",    None),
    ("13:00", "genetics", None),
    ("16:00", "travel",   None),
    ("19:00", "sport",    None),
    ("20:30", "dinner",   "Приятного вечера."),
]

# Профильные каналы. «Акцент» показывает подборку, а весь материал лежит
# в своём справочнике — и ссылка на него идёт кнопкой под каждым постом.
# Адреса хранятся настройками: каналов будет больше, а код от этого
# меняться не должен.
REF_CHANNELS = {
    "travel": ("ref_travel", "🌍 Все места"),
    "recipes": ("ref_recipes", "🍳 Все рецепты"),
    "books": ("ref_books", "📚 Все книги"),
    "genetics": ("ref_genetics", "🧬 Вся генетика"),
}

TZ_KEY = "digest_tz"             # смещение от UTC в часах
TZ_DEFAULT = 3                   # Москва
NEWS_COUNTRY_KEY = "digest_news_country"
NEWS_COUNTRY_DEFAULT = "Россия"

TARGET_KEY = "digest_chat"       # id канала
THREAD_KEY = "digest_thread"     # тема, если целью выбрана группа с разделами

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

# Время последней публикации. Расписание держится не на нём — слот
# помечается датой, — но отметка полезна: по ней видно, когда канал
# в последний раз что-то сказал.
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
    "books": "📚 Деловая литература",
}

# Вопрос читателю под каждым постом. Формулировка своя для раздела: «были
# там?» под рецептом бессмысленно. Это не украшение — вещание превращается
# в разговор, и по счётчику видно, что вообще читают.
# Рамка повтора. Материал, вышедший месяц назад, публикуется не как
# новость, а как приглашение: «приготовим лазанью? напоминаю рецепт».
# Тот же текст в другой рамке — это другой пост, а не задвоение.
# Название стоит первым и в именительном падеже. «Приготовим лазанья
# болоньезе?» — то, что выходит при подстановке в середину фразы: склонять
# русские названия автоматически нельзя, а так грамматика верна всегда.
REPEAT_LEAD = {
    "books": "📚 {title} — перечитать?\n\nНапоминаю, о чём она.",
    "recipes": "🍳 {title} — приготовим?\n\nНапоминаю рецепт.",
    "travel": "🌍 {title} — помните это место?\n\nНапоминаю, чем оно хорошо.",
    "genetics": "🧬 {title} — напоминаю коротко.",
}
REPEAT_MIN_DAYS = 30      # раньше повтор читается как сбой, а не как «а помните»

VOTE_LABELS = {
    "genetics": "💡 Знали это",
    "recipes": "🍳 Готовили",
    "travel": "📍 Были здесь",
    "books": "📖 Читали",
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

    if section == "books":
        row = await database.get_book_by_id(item_id)
        if not row:
            return None
        text, cover = row
        title = (text or "").strip().split("\n")[0][:80]
        return title, text, cover, None, None

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


async def publish_next(bot: Bot, only: str = None, lead: str = None,
                       farewell: str = None) -> str:
    """Публикует материал. С only — строго из этого раздела, по сетке;
    без него — по кругу, как было до появления расписания."""
    chat, thread = await _target()
    if not chat:
        return "канал не задан — публикация пропущена"

    if only:
        order = [only]
    else:
        # Идём по кругу, начиная с раздела, следующего за прошлым: так разделы
        # чередуются, а исчерпанные не блокируют остальные.
        last = await database.get_setting("digest_last_section")
        order = ROTATION[ROTATION.index(last) + 1:] + ROTATION[:ROTATION.index(last) + 1] \
            if last in ROTATION else ROTATION

    for section in order:
        # Идём по кандидатам, пока не найдётся годный к публикации.
        # Непрошедшие остаются в очереди и ждут вас в буфере.
        item_id, built, repeat = None, None, False
        for candidate in await database.next_candidates(section):
            made = await _build(section, candidate)
            if not made:
                await database.mark_published(section, candidate)  # битую запись пропускаем
                continue
            if readiness(section, made):
                continue
            item_id, built, repeat = candidate, made, False
            break

        # Нового годного нет — берём давнее напоминанием
        if not item_id:
            candidate = await database.oldest_published(section, REPEAT_MIN_DAYS)
            made = await _build(section, candidate) if candidate else None
            if made and not readiness(section, made):
                item_id, built, repeat = candidate, made, True

        if not item_id:
            continue

        title, text, photo, video, link = built
        head = SECTION_TITLES.get(section, section)
        if repeat:
            # Название в вопросе обязательно: «приготовим лазанью?» зовёт,
            # а безымянное «приготовим?» не значит ничего.
            # Для путешествий заголовок собран как «Живерни · 🇫🇷 Франция»;
            # в вопрос идёт только само место.
            short = title.split(" · ")[0].strip()
            head = REPEAT_LEAD.get(section, head).format(title=short)
        if lead:
            head = lead
        body = (text or title or "").strip()
        caption = f"{head}\n\n{body}"
        if farewell:
            caption += f"\n\n{farewell}"
        caption += await _ad_block()

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
        # Ссылка на профильный справочник: пост — подборка, а всё остальное
        # лежит там, и путь туда должен быть в один щелчок.
        ref = REF_CHANNELS.get(section)
        if ref:
            url = await database.get_setting(ref[0])
            if url:
                rows.append([InlineKeyboardButton(text=ref[1], url=url)])

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

        if repeat:
            await database.mark_repeated(section, item_id, sent.message_id)
        else:
            await database.mark_published(section, item_id, sent.message_id)
        await database.set_setting("digest_last_section", section)
        await database.set_setting(LAST_AT_KEY, datetime.now().isoformat())
        await _mirror(bot, chat, sent.message_id, section)
        kind = "напоминание" if repeat else "опубликовано"
        return f"{kind}: {section}/{item_id} — {title[:50]}"

    return "публиковать нечего: новых нет, а повторы ещё не отлежались"


# =====================================================================
# СЛОТЫ ДНЯ
# =====================================================================

async def _local_now():
    """Время у читателя, а не на сервере: Render живёт по UTC, а канал —
    по часам своей аудитории."""
    try:
        offset = int(await database.get_setting(TZ_KEY) or TZ_DEFAULT)
    except (TypeError, ValueError):
        offset = TZ_DEFAULT
    return datetime.now(timezone.utc) + timedelta(hours=offset)


async def _due_slot():
    """Слот, которому пора выйти сегодня, либо None.

    Берём самый поздний из наступивших и ещё не вышедших: если сервис спал
    полдня, выходит один свежий пост, а не залп из трёх пропущенных.
    """
    now = await _local_now()
    today = now.strftime("%Y-%m-%d")
    ready = None
    for at, slot, greeting in SCHEDULE:
        hh, mm = (int(x) for x in at.split(":"))
        if (now.hour, now.minute) < (hh, mm):
            continue
        if await database.get_setting(f"digest_slot_{slot}") == today:
            continue
        ready = (slot, greeting)
    return ready


async def _mark_slot(slot: str):
    now = await _local_now()
    await database.set_setting(f"digest_slot_{slot}", now.strftime("%Y-%m-%d"))


async def _news_post() -> str:
    """Утренние заголовки со ссылками. Пусто — значит выпуск не состоится:
    «новостей нет» в новостном слоте хуже, чем его отсутствие."""
    country = await database.get_setting(NEWS_COUNTRY_KEY) or NEWS_COUNTRY_DEFAULT
    content = await database.get_daily_news(country)
    return (content or "").strip()


def _sport_fact(index: int) -> str:
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "data", "sport_facts.json"), encoding="utf-8") as f:
            facts = json.load(f).get("facts") or []
    except Exception as e:
        logging.error(f"Спортивные факты не читаются: {e}")
        return ""
    return facts[index % len(facts)]["text"] if facts else ""


# =====================================================================
# ГОТОВНОСТЬ К ПУБЛИКАЦИИ
#
# Буфер — не отдельное хранилище, а состояние материала. Вещь, которая
# не проходит проверку, не публикуется и показывается владельцу с
# причиной; исправил — публикуется сама, ничего не нажимая. Отдельный
# список черновиков пришлось бы поддерживать вручную, и он разошёлся бы
# с действительностью в первую же неделю.
# =====================================================================

# Разделы, где пост без фотографии бессмыслен. Место без снимка — это
# заметка, а не публикация; глава по генетике без картинки — нормально.
NEEDS_PHOTO = {"travel"}


def _plural(n: int, one: str, few: str, many: str) -> str:
    """«1 знак», «904 знака», «905 знаков». Русские числительные требуют
    согласования, и «на 904 знаков» выдаёт машину так же верно, как
    опечатка."""
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def readiness(section: str, built) -> str:
    """Пусто, если публиковать можно. Иначе — причина, понятная человеку."""
    title, text, photo, video, link = built
    body = (text or title or "").strip()

    if not body:
        return "текст пустой"

    limit = MAX_CAPTION if (photo or video) else MAX_MESSAGE
    if len(body) > limit:
        over = len(body) - limit
        what = "подписи под фотографией" if (photo or video) else "сообщения"
        word = _plural(over, "знак", "знака", "знаков")
        return f"текст длиннее {what} на {over} {word} — нужно сократить"

    if section in NEEDS_PHOTO and not (photo or video):
        return "нет фотографии"

    return ""


SLOT_SECTION = {"genetics": "genetics", "travel": "travel",
                "dinner": "recipes", "books": "books"}

DINNER_LEAD = "🍳 Что приготовить на ужин"
SPORT_LEAD = "🏅 Спортивный факт дня"


async def publish_slot(bot: Bot) -> str:
    """Публикует то, что положено по времени. Строка — для лога."""
    due = await _due_slot()
    if not due:
        return "не время"
    slot, greeting = due

    chat, thread = await _target()
    if not chat:
        return "канал не задан"

    # Новости и спорт живут вне разделов дайджеста, поэтому идут отдельно.
    if slot == "morning":
        news = await _news_post()
        if not news:
            logging.warning("Дайджест: утренних новостей нет — выпуск пропущен")
            return "новостей нет"
        parts = [f"☀️ {greeting}", news]
        try:
            import fx_rates
            rates = await fx_rates.morning_block()
            if rates:
                parts.append(rates)
        except Exception as e:
            logging.warning(f"Дайджест: курсы к утру не подоспели: {e}")
        text = "\n\n".join(parts)
        try:
            await bot.send_message(chat, text[:MAX_MESSAGE],
                                   message_thread_id=thread,
                                   parse_mode="Markdown",
                                   disable_web_page_preview=True)
        except Exception as e:
            logging.error(f"Дайджест: утренний выпуск не вышел: {e}")
            return f"ошибка: {e}"
        await _mark_slot(slot)
        return "утренние новости"

    if slot == "sport":
        try:
            n = int(await database.get_setting("digest_sport_n") or 0)
        except (TypeError, ValueError):
            n = 0
        fact = _sport_fact(n)
        if not fact:
            return "фактов нет"
        try:
            sent = await bot.send_message(chat, f"{SPORT_LEAD}\n\n{fact}",
                                          message_thread_id=thread, parse_mode=None)
        except Exception as e:
            logging.error(f"Дайджест: спортивный факт не вышел: {e}")
            return f"ошибка: {e}"
        await database.set_setting("digest_sport_n", str(n + 1))
        await _mark_slot(slot)
        await _mirror(bot, chat, sent.message_id, "sport")
        return f"спортивный факт №{n + 1}"

    section = SLOT_SECTION.get(slot)
    if not section:
        return "слот без источника"

    lead = DINNER_LEAD if slot == "dinner" else None
    result = await publish_next(bot, only=section, lead=lead, farewell=greeting)
    if not result.startswith(("ошибка", "канал", "публиковать")):
        await _mark_slot(slot)
    return result


async def scheduler(bot: Bot):
    """Ведёт день по сетке. Просыпается часто и коротко: слот в 08:00
    должен выйти в восемь, а не когда придёт черёд двенадцатичасового
    круга."""
    await asyncio.sleep(60)
    while True:
        try:
            result = await publish_slot(bot)
            if result != "не время":
                logging.info(f"Дайджест: {result}")
        except Exception as e:
            logging.error(f"Ошибка планировщика дайджеста: {e}")
        await asyncio.sleep(300)


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


@router.message(F.text.startswith("/buffer"))
async def buffer_command(message: Message):
    """Что сейчас нельзя опубликовать и почему.

    Не хранимый список, а ответ на вопрос в момент вопроса: причина
    вычисляется по самому материалу, поэтому буфер не может разойтись
    с действительностью.
    """
    if not config.is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    only = parts[1].strip().lower() if len(parts) > 1 else ""
    only = SECTION_ALIASES.get(only, only)

    sections = [only] if only in SECTION_TITLES else list(SECTION_TITLES)
    lines, total = [], 0

    for section in sections:
        stuck = []
        for candidate in await database.next_candidates(section, limit=60):
            built = await _build(section, candidate)
            if not built:
                continue
            why = readiness(section, built)
            if why:
                stuck.append((candidate, (built[0] or "")[:44], why))
        total += len(stuck)
        if not stuck:
            continue
        lines.append(f"\n<b>{SECTION_TITLES.get(section, section)}</b> — {len(stuck)}")
        for _, title, why in stuck[:12]:
            lines.append(f"• {html.escape(title)}\n  <i>{html.escape(why)}</i>")
        if len(stuck) > 12:
            lines.append(f"  …и ещё {len(stuck) - 12}")

    if not total:
        await message.answer("🗂 <b>Буфер пуст</b>\n\nВсё готово к публикации.")
        return

    await message.answer(
        f"🗂 <b>Буфер</b> — ждёт правки: {total}\n" + "\n".join(lines)
        + "\n\n<i>Исправьте причину — материал опубликуется сам, "
          "ничего нажимать не нужно.</i>\n\n"
          "<code>/buffer путешествия</code> — только один раздел")


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

    if command == "slot":
        # Принудительный запуск сетки: удобно проверять, не дожидаясь часа.
        await message.answer(f"📤 {await publish_slot(bot)}")
        return

    if command == "tz" and len(parts) > 2:
        await database.set_setting(TZ_KEY, parts[2].strip())
        now = await _local_now()
        await message.answer(f"✅ Часовой пояс UTC{parts[2].strip():+}\n"
                             f"Сейчас у читателя: {now:%H:%M}")
        return

    if command == "ref" and len(parts) > 2:
        # «/digest ref travel https://t.me/…» — справочник для раздела
        bits = parts[2].split()
        key = REF_CHANNELS.get(bits[0].lower() if bits else "")
        if not key or len(bits) < 2:
            await message.answer("Формат: <code>/digest ref travel https://t.me/имя</code>\n"
                                 "Разделы: " + ", ".join(REF_CHANNELS))
            return
        await database.set_setting(key[0], bits[1])
        await message.answer(f"✅ {key[1]} → {html.escape(bits[1])}")
        return

    if command == "country" and len(parts) > 2:
        await database.set_setting(NEWS_COUNTRY_KEY, parts[2].strip())
        await message.answer(f"✅ Новости берём для: {html.escape(parts[2].strip())}")
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
    now = await _local_now()
    country = await database.get_setting(NEWS_COUNTRY_KEY) or NEWS_COUNTRY_DEFAULT
    lines = [
        "📤 <b>Дайджест-канал</b>",
        f"Цель: <code>{chat or 'не задана'}</code>"
        + (f" · тема {thread}" if thread else ""),
        f"Время у читателя: {now:%H:%M}, новости для: {html.escape(country)}",
        "",
        "<b>Сетка дня</b>",
    ]
    today = now.strftime("%Y-%m-%d")
    for at, slot, _ in SCHEDULE:
        done = await database.get_setting(f"digest_slot_{slot}") == today
        titles = {"morning": "новости", "genetics": "наука", "travel": "путешествия",
                  "sport": "спортивный факт", "dinner": "рецепт на ужин"}
        lines.append(f"{'✅' if done else '⬜️'} {at} — {titles.get(slot, slot)}")
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
    lines.append("\n<code>/digest slot</code> — выпустить то, что по времени\n"
                 "<code>/digest tz 3</code> — часовой пояс читателя\n"
                 "<code>/digest country Россия</code> — чьи новости утром\n"
                 "<code>/digest ref travel https://t.me/…</code> — справочник раздела\n"
                 "<code>/digest now</code> — опубликовать вне сетки\n"
                 "<code>/digest chat -100…</code> — задать канал\n"
                 "<code>/digest mirror -100… тема раздел</code> — дубль в группу\n"
                 "<code>/digest nomirror</code> — не дублировать\n"
                 "<code>/digest ad текст</code> — рекламный блок\n"
                 "<code>/digest noad</code> — снять рекламу")
    await message.answer("\n".join(lines))
