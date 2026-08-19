# genetics.py — база знаний раздела «Генетика»: посты из тематического канала,
# разложенные кликабельным списком по заголовкам.
import logging
import re

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest

import config
import database

router = Router()

SECTION = "genetics"
PAGE_SIZE = 15
MAX_CAPTION = 1024      # предел подписи к медиа в Telegram
MAX_MESSAGE = 4096      # предел обычного сообщения

EMPTY = {
    "ru": "🧬 База знаний пока пуста. Материалы подтягиваются из канала — загляните позже.",
    "en": "🧬 The knowledge base is empty for now. Material is pulled from the channel — check back later.",
    "fr": "🧬 La base de connaissances est vide pour l'instant. Revenez plus tard.",
    "he": "🧬 מאגר הידע ריק כרגע. החומרים נמשכים מהערוץ — בדקו מאוחר יותר."
}

PICK = {
    "ru": "🧬 **База знаний по генетике**\n\n👇 Выберите материал:",
    "en": "🧬 **Genetics knowledge base**\n\n👇 Choose an article:",
    "fr": "🧬 **Base de connaissances en génétique**\n\n👇 Choisissez un article :",
    "he": "🧬 **מאגר הידע בגנטיקה**\n\n👇 בחרו חומר:"
}

PICK_PAGED = {
    "ru": "🧬 **База знаний по генетике**\n\n👇 Страница {page} из {pages}, всего материалов: {total}",
    "en": "🧬 **Genetics knowledge base**\n\n👇 Page {page} of {pages}, {total} articles in total",
    "fr": "🧬 **Base de connaissances**\n\n👇 Page {page} sur {pages}, {total} articles",
    "he": "🧬 **מאגר הידע**\n\n👇 עמוד {page} מתוך {pages}, סה\"כ {total}"
}

BACK = {"ru": "🔙 Назад", "en": "🔙 Back", "fr": "🔙 Retour", "he": "🔙 חזרה"}
TO_LIST = {"ru": "🔙 К списку", "en": "🔙 Back to list",
           "fr": "🔙 Retour à la liste", "he": "🔙 חזרה לרשימה"}
SOURCE = {"ru": "🔗 Читать в канале", "en": "🔗 Read in the channel",
          "fr": "🔗 Lire dans le canal", "he": "🔗 קראו בערוץ"}
CHAPTER = {"ru": "Глава", "en": "Chapter", "fr": "Chapitre", "he": "פרק"}


def _t(mapping: dict, lang: str) -> str:
    return mapping.get(lang, mapping["en"])


# =====================================================================
# СПИСОК И ЧТЕНИЕ
# =====================================================================

async def build_list(lang: str, page: int):
    total = await database.count_articles(SECTION)
    if not total:
        return None, None

    pages = max(1, -(-total // PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    rows = await database.get_article_titles(SECTION, PAGE_SIZE, page * PAGE_SIZE)

    # Номер главы считается от позиции в общем списке, а не хранится в базе:
    # добавится материал в середину — нумерация пересоберётся сама.
    word = _t(CHAPTER, lang)
    buttons = []
    for index, (article_id, title) in enumerate(rows):
        prefix = f"{word} {page * PAGE_SIZE + index + 1}. "
        label = (title or "Материал").strip()
        room = 60 - len(prefix)
        if len(label) > room:
            label = label[:room - 1].rstrip() + "…"
        buttons.append([InlineKeyboardButton(
            text=prefix + label, callback_data=f"genitem_{page}_{article_id}")])

    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="⬅", callback_data=f"genlist_{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(text="➡", callback_data=f"genlist_{page + 1}"))
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(
        text=_t(BACK, lang), callback_data="intellect_genetics")])

    header = (_t(PICK_PAGED, lang).format(page=page + 1, pages=pages, total=total)
              if pages > 1 else _t(PICK, lang))
    return header, InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "genetics_channel_base")
async def open_knowledge_base(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    header, markup = await build_list(lang, 0)

    if header is None:
        await call.message.answer(_t(EMPTY, lang))
        return
    await call.message.answer(header, parse_mode="Markdown", reply_markup=markup)


@router.callback_query(F.data.startswith("genlist_"))
async def turn_page(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    header, markup = await build_list(lang, int(call.data.removeprefix("genlist_")))
    if header is None:
        return
    try:
        await call.message.edit_text(header, parse_mode="Markdown", reply_markup=markup)
    except TelegramBadRequest:
        await call.message.answer(header, parse_mode="Markdown", reply_markup=markup)


@router.callback_query(F.data.startswith("genitem_"))
async def open_article(call: CallbackQuery):
    await call.answer()
    try:
        _, page, raw_id = call.data.split("_", 2)
        article_id = int(raw_id)
    except ValueError:
        return

    lang = await database.get_user_language(call.from_user.id)
    article = await database.get_article(article_id)
    if not article:
        return

    title, text, photo_id, video_id, link = article
    body = text or title

    rows = []
    if link:
        rows.append([InlineKeyboardButton(text=_t(SOURCE, lang), url=link)])
    if config.is_admin(call.from_user.id):
        rows.append([InlineKeyboardButton(
            text="✏️ Переименовать", callback_data=f"genrename_{article_id}")])
    rows.append([InlineKeyboardButton(text=_t(TO_LIST, lang), callback_data=f"genlist_{page}")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)

    # Длинный материал не помещается ни в подпись, ни иногда в одно сообщение,
    # поэтому режем по границам абзацев и кнопку вешаем на последний кусок.
    # parse_mode=None обязателен. По умолчанию у бота включён HTML, а текст поста
    # приходит из канала как есть: любой символ «<» — например «p<0.05» — Telegram
    # принимает за начало тега и отклоняет сообщение целиком, текст пропадает.
    media_id = video_id or photo_id
    if media_id and len(body) <= MAX_CAPTION:
        if video_id:
            await call.message.answer_video(video=video_id, caption=body,
                                            parse_mode=None, reply_markup=markup)
        else:
            await call.message.answer_photo(photo=photo_id, caption=body,
                                            parse_mode=None, reply_markup=markup)
        return

    if media_id:
        if video_id:
            await call.message.answer_video(video=video_id)
        else:
            await call.message.answer_photo(photo=photo_id)

    chunks = _split(body, MAX_MESSAGE)
    for index, chunk in enumerate(chunks):
        is_last = index == len(chunks) - 1
        await call.message.answer(chunk, parse_mode=None,
                                  reply_markup=markup if is_last else None)


def _split(text: str, limit: int):
    """Режет длинный текст по абзацам, не разрывая слова"""
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(paragraph) > limit:
            cut = paragraph.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            chunks.append(paragraph[:cut])
            paragraph = paragraph[cut:].lstrip()
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


# =====================================================================
# НАПОЛНЕНИЕ
# =====================================================================

class GeneticsImport(StatesGroup):
    collecting = State()


def derive_title(text: str) -> str:
    """Достаёт читаемый заголовок из поста.

    Первая строка «как есть» не годится: в кнопках Telegram разметка не
    работает, поэтому `**Заголовок**` показывался бы со звёздочками. Кроме
    того, посты часто начинаются со строки хэштегов, декоративного разделителя
    или ряда эмодзи — такие строки пропускаем и берём первую осмысленную.
    """
    for raw in (text or "").split("\n"):
        line = raw.strip()
        if not line:
            continue

        line = re.sub(r"<[^>]+>", "", line)          # html-теги
        line = re.sub(r"#\S+", "", line)             # хэштеги
        line = re.sub(r"[*_`~]", "", line)           # markdown
        line = re.sub(r"\s+", " ", line).strip(" -—–·•|:>")

        # Строка из одних эмодзи или символов заголовком быть не может
        if len(re.sub(r"[^\w]", "", line, flags=re.UNICODE)) < 3:
            continue

        return line[:77].rstrip() + "…" if len(line) > 80 else line

    return "Материал"


def extract_article(message: Message) -> dict:
    text = (message.text or message.caption or "").strip()
    title = derive_title(text)

    link = None
    for entity in list(message.entities or []) + list(message.caption_entities or []):
        if entity.type == "text_link" and entity.url:
            link = entity.url
            break
        if entity.type == "url":
            link = text[entity.offset:entity.offset + entity.length]
            break

    return {
        "title": title,
        "text": text,
        "photo_id": message.photo[-1].file_id if message.photo else None,
        "video_id": message.video.file_id if message.video else None,
        "link": link,
    }


def source_key(message: Message) -> str:
    origin = getattr(message, "forward_origin", None)
    chat = getattr(origin, "chat", None) if origin is not None else None
    message_id = getattr(origin, "message_id", None) if origin is not None else None
    if chat is None:
        chat = getattr(message, "forward_from_chat", None)
        message_id = getattr(message, "forward_from_message_id", None)
    if chat is None or message_id is None:
        return f"{message.chat.id}:{message.message_id}"
    return f"{chat.id}:{message_id}"


async def _save(message: Message) -> str:
    data = extract_article(message)
    result = await database.add_article(
        SECTION, data["title"], data["text"], data["photo_id"],
        data["video_id"], data["link"], source_key(message)
    )
    total = await database.count_articles(SECTION)

    if result == "added":
        marks = [name for name, value in
                 (("фото", data["photo_id"]), ("видео", data["video_id"]), ("ссылка", data["link"]))
                 if value]
        extra = f" ({', '.join(marks)})" if marks else ""
        return f"✅ «{data['title']}»{extra}\n\nВ базе знаний: <b>{total}</b>"
    if result == "duplicate":
        return f"↩️ Этот пост уже добавлен. Всего: <b>{total}</b>"

    detail = result.split(":", 1)[1] if result.startswith("error:") else "причина неизвестна"
    return f"⚠️ Не сохранено.\n\n<code>{detail[:600]}</code>"


@router.message(F.text == "/genetics")
async def import_start(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    await state.set_state(GeneticsImport.collecting)
    await message.answer(
        "🧬 <b>Режим импорта материалов по генетике включён.</b>\n\n"
        f"Сейчас в базе знаний: <b>{await database.count_articles(SECTION)}</b>\n\n"
        "Пересылайте посты из канала — по одному или пачкой. Заголовком станет "
        "первая строка поста, по ней материал и будет виден в списке.\n\n"
        "Когда закончите — отправьте /genetics_done"
    )


@router.message(F.text == "/genetics_done", GeneticsImport.collecting)
async def import_stop(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(
        f"✅ Импорт завершён. В базе знаний: <b>{await database.count_articles(SECTION)}</b>")


@router.message(GeneticsImport.collecting, F.text | F.caption, ~F.text.startswith("/"))
async def import_post(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    await message.answer(await _save(message))


@router.message(GeneticsImport.collecting, ~F.text.startswith("/"))
async def import_hint(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    await message.answer(
        "В посте нет ни текста, ни подписи — сохранять нечего. "
        "Перешлите пост с текстом или отправьте /genetics_done."
    )


def _is_genetics_post(message: Message) -> bool:
    """Только свой канал: без этого материалы одного канала попадали бы в чужой раздел"""
    return bool(config.GENETICS_CHANNEL) and message.chat.id == config.GENETICS_CHANNEL


@router.channel_post(_is_genetics_post)
async def auto_collect(message: Message):
    if not (message.text or message.caption):
        return
    data = extract_article(message)
    result = await database.add_article(
        SECTION, data["title"], data["text"], data["photo_id"],
        data["video_id"], data["link"], source_key(message)
    )
    if result == "added":
        logging.info(f"🧬 АВТО-ГЕНЕТИКА: добавлен материал «{data['title']}»")


# =====================================================================
# 🌍 НОВОСТИ ГЕНЕТИКИ ПО СТРАНАМ
# =====================================================================

NEWS_COUNTRIES = {
    "gen_us": {"flag": "🇺🇸", "ru": "США", "en": "USA"},
    "gen_kr": {"flag": "🇰🇷", "ru": "Корея", "en": "South Korea"},
    "gen_il": {"flag": "🇮🇱", "ru": "Израиль", "en": "Israel"},
    "gen_cn": {"flag": "🇨🇳", "ru": "Китай", "en": "China"},
}

NEWS_HUB = {
    "ru": "🌍 **Новости генетики**\n\nСвежие научные публикации четырёх стран. Выберите страну:",
    "en": "🌍 **Genetics news**\n\nRecent research coverage from four countries. Pick one:",
    "fr": "🌍 **Actualités de la génétique**\n\nPublications récentes de quatre pays. Choisissez :",
    "he": "🌍 **חדשות גנטיקה**\n\nפרסומים מדעיים עדכניים מארבע מדינות. בחרו מדינה:"
}

NEWS_HEADER = {
    "ru": "{flag} **Генетика — {name}**\n\n",
    "en": "{flag} **Genetics — {name}**\n\n",
}

NEWS_EMPTY = {
    "ru": "Заголовки появятся здесь после ближайшего обновления — оно идёт раз в сутки.",
    "en": "Headlines will appear here after the next daily update.",
    "fr": "Les titres apparaîtront après la prochaine mise à jour quotidienne.",
    "he": "הכותרות יופיעו כאן לאחר העדכון היומי הבא."
}

# Заголовки лент приходят на английском намеренно: корейские и китайские
# оригиналы читатель бота не разберёт, а перевод исказил бы термины.
NEWS_NOTE = {
    "ru": "\n\n_Источники англоязычные — так термины остаются точными._",
    "en": "",
    "fr": "\n\n_Sources en anglais._",
    "he": "\n\n_המקורות באנגלית._"
}


@router.callback_query(F.data == "genetics_news")
async def open_news_hub(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    name_key = "ru" if lang == "ru" else "en"

    rows = [[InlineKeyboardButton(
        text=f"{meta['flag']} {meta[name_key]}", callback_data=f"gennews_{key}")]
        for key, meta in NEWS_COUNTRIES.items()]
    rows.append([InlineKeyboardButton(text=_t(BACK, lang), callback_data="intellect_genetics")])

    try:
        await call.message.edit_caption(
            caption=_t(NEWS_HUB, lang), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    except TelegramBadRequest:
        await call.message.answer(
            _t(NEWS_HUB, lang), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )


@router.callback_query(F.data.startswith("gennews_"))
async def show_country_news(call: CallbackQuery):
    await call.answer()
    key = call.data.removeprefix("gennews_")
    if key not in NEWS_COUNTRIES:
        return

    lang = await database.get_user_language(call.from_user.id)
    meta = NEWS_COUNTRIES[key]
    name_key = "ru" if lang == "ru" else "en"

    content, _ = await database.get_daily_news(key)
    header = NEWS_HEADER.get(lang, NEWS_HEADER["en"]).format(
        flag=meta["flag"], name=meta[name_key])
    body = (content + _t(NEWS_NOTE, lang)) if content else _t(NEWS_EMPTY, lang)

    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=_t(BACK, lang), callback_data="genetics_news")]])
    await call.message.answer(
        header + body, parse_mode="Markdown",
        disable_web_page_preview=True, reply_markup=markup
    )


# =====================================================================
# 🧪 ЗАКАЗ ИССЛЕДОВАНИЯ ИЛИ РАСШИФРОВКИ
# =====================================================================

ORDER_PITCH = {
    "ru": ("🧪 **Исследование и расшифровка генов**\n\n"
           "Консультирует врач-генетик. Разбор готового генетического теста, "
           "подбор панели под конкретную задачу, объяснение результатов понятным "
           "языком — что данные действительно показывают, а что нет.\n\n"
           "В заявке опишите: что уже сделано, какие анализы на руках и что хотите "
           "понять. Отвечу лично — что реально сделать, в какие сроки и на каких условиях."),
    "en": ("🧪 **Genetic research and interpretation**\n\n"
           "Consultation by a medical geneticist. Interpreting an existing genetic test, "
           "choosing a panel for your specific question, explaining the results in plain "
           "language — what the data actually shows and what it does not.\n\n"
           "In your request describe what has already been done, which results you have "
           "and what you want to understand. I reply personally: what is feasible, in what "
           "timeframe and on what terms."),
    "fr": ("🧪 **Recherche génétique et interprétation**\n\n"
           "Consultation assurée par un médecin généticien. Interprétation d'un test "
           "existant, choix d'un panel adapté, explication claire des résultats.\n\n"
           "Décrivez ce qui a déjà été fait et ce que vous souhaitez comprendre — "
           "je réponds personnellement."),
    "he": ("🧪 **מחקר גנטי ופענוח**\n\n"
           "הייעוץ ניתן על ידי רופא גנטיקאי. פענוח בדיקה גנטית קיימת, בחירת פאנל "
           "מתאים והסבר התוצאות בשפה ברורה.\n\n"
           "תארו מה כבר נעשה ומה תרצו להבין — אענה אישית.")
}

BTN_ORDER = {"ru": "✉️ Оставить заявку", "en": "✉️ Send a request",
             "fr": "✉️ Envoyer une demande", "he": "✉️ שלחו בקשה"}


@router.callback_query(F.data == "genetics_order")
async def open_order_pitch(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)

    rows = []
    if config.ADMIN_ID:
        rows.append([InlineKeyboardButton(
            text=_t(BTN_ORDER, lang), callback_data="ads_order")])
    rows.append([InlineKeyboardButton(text=_t(BACK, lang), callback_data="intellect_genetics")])

    try:
        await call.message.edit_caption(
            caption=_t(ORDER_PITCH, lang), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    except TelegramBadRequest:
        await call.message.answer(
            _t(ORDER_PITCH, lang), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )


# =====================================================================
# ✏️ ПРАВКА ЗАГОЛОВКОВ
# =====================================================================

class RenameState(StatesGroup):
    waiting_title = State()


@router.message(F.text == "/genetics_retitle")
async def retitle_all(message: Message):
    """Пересчитывает заголовки всех материалов по текущим правилам.

    Нужна потому, что посты уже импортированы со старыми, нечитаемыми
    заголовками, и переливать их заново было бы глупо.
    """
    if not config.is_admin(message.from_user.id):
        return

    rows = await database.get_articles_raw(SECTION)
    if not rows:
        await message.answer("Материалов пока нет.")
        return

    changed = []
    for article_id, old_title, text in rows:
        new_title = derive_title(text)
        if new_title != old_title:
            if await database.update_article_title(article_id, new_title):
                changed.append((old_title, new_title))

    if not changed:
        await message.answer(f"Все {len(rows)} заголовков уже в порядке.")
        return

    preview = "\n".join(f"• <s>{old[:40]}</s> → <b>{new[:40]}</b>" for old, new in changed[:12])
    tail = f"\n\n…и ещё {len(changed) - 12}" if len(changed) > 12 else ""
    await message.answer(
        f"✅ Обновлено заголовков: <b>{len(changed)}</b> из {len(rows)}\n\n{preview}{tail}"
    )


@router.callback_query(F.data.startswith("genrename_"))
async def ask_new_title(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        return
    await call.answer()

    article_id = call.data.removeprefix("genrename_")
    await state.set_state(RenameState.waiting_title)
    await state.update_data(article_id=int(article_id))
    await call.message.answer("✏️ Пришлите новый заголовок одной строкой:")


@router.message(RenameState.waiting_title, F.text, ~F.text.startswith("/"))
async def apply_new_title(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return

    data = await state.get_data()
    await state.clear()
    title = re.sub(r"\s+", " ", message.text).strip()[:80]

    if await database.update_article_title(data["article_id"], title):
        await message.answer(f"✅ Заголовок изменён на «{title}»")
    else:
        await message.answer("⚠️ Не удалось сохранить — ошибка базы.")
