# shop.py — раздел «Pro-Shop» внутри тенниса: каталог одежды и аксессуаров,
# собранный из постов партнёрского канала. Структура: пол → тип вещи → список
# → карточка со ссылкой на оригинальный пост.
import logging

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest

import config
import database

router = Router()

PAGE_SIZE = 15

# Разделы верхнего уровня
GENDERS = {
    "men": {"ru": "👔 Мужское", "en": "👔 Men"},
    "women": {"ru": "👗 Женское", "en": "👗 Women"},
    "acc": {"ru": "🧢 Аксессуары", "en": "🧢 Accessories"},
}

# Типы вещей внутри каждого раздела
TYPES = {
    "men": {
        "sneakers": {"ru": "👟 Кроссовки", "en": "👟 Sneakers"},
        "tshirts": {"ru": "👕 Футболки и поло", "en": "👕 T-shirts & polos"},
        "shorts": {"ru": "🩳 Шорты", "en": "🩳 Shorts"},
    },
    "women": {
        "sneakers": {"ru": "👟 Кроссовки", "en": "👟 Sneakers"},
        "dresses": {"ru": "👗 Платья", "en": "👗 Dresses"},
        "skirts": {"ru": "🩱 Юбки", "en": "🩱 Skirts"},
        "tshirts": {"ru": "👕 Футболки и топы", "en": "👕 T-shirts & tops"},
        "shorts": {"ru": "🩳 Шорты", "en": "🩳 Shorts"},
    },
    "acc": {
        "rackets": {"ru": "🎾 Ракетки", "en": "🎾 Rackets"},
        "bags": {"ru": "🎒 Сумки и рюкзаки", "en": "🎒 Bags & backpacks"},
        "balls": {"ru": "🟡 Мячи", "en": "🟡 Balls"},
        "grips": {"ru": "🧵 Намотки", "en": "🧵 Grips & overgrips"},
    },
}

# Ключевые слова для автоматической раскладки пересланного поста.
# Порядок важен: более длинные и специфичные слова проверяются раньше.
TYPE_KEYWORDS = {
    # Сумки проверяются РАНЬШЕ ракеток: «сумка для ракеток» и «чехол для
    # ракетки» — это сумки, а не ракетки.
    "bags": ["сумк", "рюкзак", "чехол", "тубус", "backpack", "bag"],
    "rackets": ["ракетк", "ракета", "racket", "racquet"],
    "grips": ["намотк", "обмотк", "овергрип", "грип", "overgrip", "grip"],
    "balls": ["мяч", "ball"],
    "sneakers": ["кроссовк", "кросовк", "кеды", "sneaker", "shoes"],
    "dresses": ["платье", "платья", "dress"],
    "skirts": ["юбк", "skirt"],
    "shorts": ["шорт", "short"],
    "tshirts": ["футболк", "поло", "топ ", "майк", "t-shirt", "tshirt", "polo"],
}

WOMEN_KEYWORDS = ["женск", "жен.", "women", "woman", "female", "wmn"]
MEN_KEYWORDS = ["мужск", "муж.", "men's", "mens", "male"]

# Типы, которые сами по себе определяют раздел, без слов о поле
ACCESSORY_TYPES = {"rackets", "bags", "balls", "grips"}
WOMEN_ONLY_TYPES = {"dresses", "skirts"}


def _label(mapping: dict, lang: str) -> str:
    return mapping.get(lang, mapping["en"])


def category_title(gender: str, item_type: str, lang: str) -> str:
    return f"{_label(GENDERS[gender], lang)} · {_label(TYPES[gender][item_type], lang)}"


# =====================================================================
# ВИТРИНА
# =====================================================================

SHOP_INTRO = {
    "ru": ("🛍 **Pro-Shop**\n\nПодборка теннисной экипировки от партнёрского магазина. "
           "Выберите раздел:"),
    "en": ("🛍 **Pro-Shop**\n\nA curated tennis gear selection from our partner store. "
           "Choose a section:"),
    "fr": ("🛍 **Pro-Shop**\n\nUne sélection d'équipement de tennis de notre boutique "
           "partenaire. Choisissez :"),
    "he": "🛍 **Pro-Shop**\n\nמבחר ציוד טניס מחנות שותפה. בחרו מדור:"
}

# Обращение к владельцам магазинов. Показывается под витриной — там, где человек
# уже увидел, как устроен каталог, и может примерить его на себя.
OWNER_PITCH = {
    "ru": ("\n\n———\n💼 **Владельцам магазинов**\n\n"
           "Хотите, чтобы ваш магазин работал лучше? Соберу такую же витрину под ваш "
           "ассортимент и возьму на себя полное сопровождение: раскладка по категориям, "
           "размётка ссылок, прозрачная аналитика переходов — видно, какие товары "
           "смотрят, а какие лежат мёртвым грузом.\n\n"
           "По сотрудничеству — кнопка «Оставить заявку» ниже."),
    "en": ("\n\n———\n💼 **For store owners**\n\n"
           "Want your store to work better? I can build the same storefront around your "
           "range and take on full support: category structure, link tagging and "
           "transparent click analytics — you see which items get looked at and which "
           "just sit there.\n\n"
           "For partnership, use the request button below."),
    "fr": ("\n\n———\n💼 **Pour les propriétaires de boutiques**\n\n"
           "Je peux construire la même vitrine pour votre catalogue et en assurer le suivi "
           "complet : structure par catégories, marquage des liens, analyse transparente "
           "des clics.\n\nPour toute collaboration, utilisez le bouton ci-dessous."),
    "he": ("\n\n———\n💼 **לבעלי חנויות**\n\n"
           "אבנה חלון ראווה כזה עבור המגוון שלכם ואקח על עצמי ליווי מלא: חלוקה לקטגוריות, "
           "תיוג קישורים וניתוח שקוף של הקליקים.\n\nלשיתוף פעולה — הכפתור למטה.")
}

BTN_REQUEST = {"ru": "✉️ Оставить заявку", "en": "✉️ Send a request",
               "fr": "✉️ Envoyer une demande", "he": "✉️ שלחו בקשה"}

EMPTY_SHOP = {
    "ru": "🛍 Каталог пока пуст. Товары появятся здесь совсем скоро.",
    "en": "🛍 The catalogue is empty for now. Items will appear here shortly.",
    "fr": "🛍 Le catalogue est vide pour l'instant. Les articles arriveront bientôt.",
    "he": "🛍 הקטלוג ריק כרגע. פריטים יופיעו כאן בקרוב."
}

EMPTY_CATEGORY = {
    "ru": "В этой категории пока ничего нет. Загляните в соседние разделы.",
    "en": "Nothing in this category yet. Try the neighbouring sections.",
    "fr": "Rien dans cette catégorie pour l'instant. Essayez les sections voisines.",
    "he": "אין כאן כלום עדיין. נסו את המדורים השכנים."
}

PICK_ITEM = {
    "ru": "👇 {category} — выберите товар:",
    "en": "👇 {category} — pick an item:",
    "fr": "👇 {category} — choisissez un article :",
    "he": "👇 {category} — בחרו פריט:"
}

PICK_ITEM_PAGED = {
    "ru": "👇 {category} — страница {page} из {pages}, всего {total}:",
    "en": "👇 {category} — page {page} of {pages}, {total} in total:",
    "fr": "👇 {category} — page {page} sur {pages}, {total} au total :",
    "he": "👇 {category} — עמוד {page} מתוך {pages}, סה\"כ {total}:"
}

OPEN_IN_CHANNEL = {
    "ru": "🔗 Открыть в магазине", "en": "🔗 Open in the store",
    "fr": "🔗 Ouvrir dans la boutique", "he": "🔗 פתחו בחנות"
}

BACK = {"ru": "🔙 Назад", "en": "🔙 Back", "fr": "🔙 Retour", "he": "🔙 חזרה"}


@router.callback_query(F.data == "tennis_shop_referral")
async def open_shop(call: CallbackQuery):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)

    # Один запрос на всю витрину вместо запроса на каждую категорию.
    # Считаем по известным типам: если категорию когда-нибудь уберут, её товары
    # не должны раздувать счётчик сверху, оставаясь недоступными в списках.
    counts = await database.get_shop_counts()

    rows = []
    for gender in GENDERS:
        count = sum(counts.get((gender, t), 0) for t in TYPES[gender])
        if count:
            rows.append([InlineKeyboardButton(
                text=f"{_label(GENDERS[gender], lang)} ({count})",
                callback_data=f"shopgen_{gender}"
            )])

    caption = _label(SHOP_INTRO, lang) if rows else _label(EMPTY_SHOP, lang)

    # Кнопку заявки показываем только когда заявке есть куда прийти
    if config.ADMIN_ID:
        caption += _label(OWNER_PITCH, lang)
        rows.append([InlineKeyboardButton(
            text=_label(BTN_REQUEST, lang), callback_data="ads_order")])

    rows.append([InlineKeyboardButton(text=_label(BACK, lang), callback_data="sport_tennis")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.TENNIS_BANNER, caption=caption, parse_mode="Markdown"),
            reply_markup=markup
        )
    except TelegramBadRequest:
        await call.message.answer_photo(
            photo=config.TENNIS_BANNER, caption=caption,
            parse_mode="Markdown", reply_markup=markup
        )


@router.callback_query(F.data.startswith("shopgen_"))
async def open_gender_section(call: CallbackQuery):
    await call.answer()
    gender = call.data.removeprefix("shopgen_")
    if gender not in TYPES:
        return

    lang = await database.get_user_language(call.from_user.id)

    counts = await database.get_shop_counts()

    rows = []
    for item_type in TYPES[gender]:
        count = counts.get((gender, item_type), 0)
        if count:
            rows.append([InlineKeyboardButton(
                text=f"{_label(TYPES[gender][item_type], lang)} ({count})",
                callback_data=f"shoplist_{gender}_{item_type}_0"
            )])

    caption = _label(GENDERS[gender], lang)
    if not rows:
        caption = f"{caption}\n\n{_label(EMPTY_CATEGORY, lang)}"
    rows.append([InlineKeyboardButton(text=_label(BACK, lang), callback_data="tennis_shop_referral")])

    try:
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.TENNIS_BANNER, caption=caption, parse_mode="Markdown"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    except TelegramBadRequest:
        await call.message.answer(caption, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def build_item_list(lang: str, gender: str, item_type: str, page: int):
    total = await database.count_shop_items(gender, item_type)
    if not total:
        return None, None

    pages = max(1, -(-total // PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    rows = await database.get_shop_titles(gender, item_type, PAGE_SIZE, page * PAGE_SIZE)

    buttons = []
    for item_id, title in rows:
        label = (title or "Товар").strip()
        if len(label) > 60:
            label = label[:57].rstrip() + "…"
        buttons.append([InlineKeyboardButton(
            text=label, callback_data=f"shopitem_{gender}_{item_type}_{page}_{item_id}"
        )])

    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="⬅", callback_data=f"shoplist_{gender}_{item_type}_{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(
                text="➡", callback_data=f"shoplist_{gender}_{item_type}_{page + 1}"))
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(
        text=_label(BACK, lang), callback_data=f"shopgen_{gender}")])

    category = category_title(gender, item_type, lang)
    if pages > 1:
        header = _label(PICK_ITEM_PAGED, lang).format(
            category=category, page=page + 1, pages=pages, total=total)
    else:
        header = _label(PICK_ITEM, lang).format(category=category)

    return header, InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data.startswith("shoplist_"))
async def show_item_list(call: CallbackQuery):
    await call.answer()
    try:
        _, gender, item_type, page = call.data.split("_", 3)
    except ValueError:
        return
    if gender not in TYPES or item_type not in TYPES[gender]:
        return

    lang = await database.get_user_language(call.from_user.id)
    header, markup = await build_item_list(lang, gender, item_type, int(page))
    if header is None:
        return

    try:
        await call.message.edit_text(header, reply_markup=markup)
    except TelegramBadRequest:
        await call.message.answer(header, reply_markup=markup)


@router.callback_query(F.data.startswith("shopitem_"))
async def show_item_card(call: CallbackQuery):
    await call.answer()
    try:
        _, gender, item_type, page, raw_id = call.data.split("_", 4)
        item_id = int(raw_id)
    except ValueError:
        return

    lang = await database.get_user_language(call.from_user.id)
    item = await database.get_shop_item(item_id)
    if not item:
        return

    title, description, photo_id, link = item
    caption = f"<b>{title}</b>\n\n{description}" if description else f"<b>{title}</b>"

    rows = []
    if link:
        rows.append([InlineKeyboardButton(text=_label(OPEN_IN_CHANNEL, lang), url=link)])
    rows.append([InlineKeyboardButton(
        text=_label(BACK, lang), callback_data=f"shoplist_{gender}_{item_type}_{page}")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)

    # Подпись к фото ограничена 1024 символами против 4096 у текста
    if photo_id and len(caption) <= 1024:
        await call.message.answer_photo(photo=photo_id, caption=caption, reply_markup=markup)
    elif photo_id:
        await call.message.answer_photo(photo=photo_id)
        await call.message.answer(caption, reply_markup=markup)
    else:
        await call.message.answer(caption, reply_markup=markup)


# =====================================================================
# ИМПОРТ ТОВАРОВ ПЕРЕСЫЛКОЙ
# =====================================================================

class ShopImportStates(StatesGroup):
    collecting = State()
    choosing_category = State()


_pending_items: dict[int, Message] = {}


def detect_category(text: str):
    """Определяет (пол, тип) по тексту поста. Любая часть может быть None."""
    lowered = (text or "").lower()

    item_type = None
    for candidate, words in TYPE_KEYWORDS.items():
        if any(word in lowered for word in words):
            item_type = candidate
            break

    if item_type in ACCESSORY_TYPES:
        return "acc", item_type

    gender = None
    if any(word in lowered for word in WOMEN_KEYWORDS):
        gender = "women"
    elif any(word in lowered for word in MEN_KEYWORDS):
        gender = "men"
    elif item_type in WOMEN_ONLY_TYPES:
        # Платье и юбка сами по себе достаточно однозначны
        gender = "women"

    return gender, item_type


def extract_item(message: Message) -> dict:
    text = (message.text or message.caption or "").strip()
    first_line = text.split("\n")[0].strip() if text else ""
    title = first_line or "Товар"
    if len(title) > 80:
        title = title[:77].rstrip() + "…"

    return {
        "title": title,
        "description": text,
        "photo_id": message.photo[-1].file_id if message.photo else None,
    }


def source_link(message: Message):
    """Ссылка на исходный пост канала и ключ для защиты от дублей"""
    origin = getattr(message, "forward_origin", None)
    chat = getattr(origin, "chat", None) if origin is not None else None
    message_id = getattr(origin, "message_id", None) if origin is not None else None

    if chat is None:
        chat = getattr(message, "forward_from_chat", None)
        message_id = getattr(message, "forward_from_message_id", None)

    if chat is None or message_id is None:
        return None, f"{message.chat.id}:{message.message_id}"

    key = f"{chat.id}:{message_id}"
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}", key

    # Закрытый канал: ссылка вида t.me/c/<id без префикса -100>/<message_id>
    internal = str(chat.id)
    if internal.startswith("-100"):
        return f"https://t.me/c/{internal[4:]}/{message_id}", key
    return None, key


def _category_markup(prefix: str = "shopcat", suffix: str = "") -> InlineKeyboardMarkup:
    """Клавиатура всех категорий. prefix=shopcat — выбор при импорте,
    prefix=shopmove — перенос уже сохранённого товара (suffix = его id)."""
    rows = []
    for gender, types in TYPES.items():
        for item_type in types:
            data = f"{prefix}_{gender}_{item_type}"
            rows.append([InlineKeyboardButton(
                text=f"{GENDERS[gender]['ru']} · {types[item_type]['ru']}",
                callback_data=f"{data}_{suffix}" if suffix else data
            )])
    if prefix == "shopcat":
        rows.append([InlineKeyboardButton(text="⏭ Пропустить", callback_data="shopcat_skip_skip")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _shop_summary() -> str:
    parts = []
    for gender in GENDERS:
        parts.append(f"{GENDERS[gender]['ru']}: <b>{await database.count_shop_items(gender)}</b>")
    return " · ".join(parts)


@router.message(F.text == "/shop")
async def shop_import_start(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    await state.set_state(ShopImportStates.collecting)
    await message.answer(
        "🛍 <b>Режим импорта товаров включён.</b>\n\n"
        f"Сейчас в каталоге — {await _shop_summary()}\n\n"
        "Пересылайте сюда посты из канала магазина. Категорию я определяю по тексту: "
        "«женские кроссовки», «платье», «ракетка», «намотка» и подобные слова.\n\n"
        "Если распознать не удастся — предложу выбрать кнопками.\n\n"
        "Когда закончите — отправьте /shop_done"
    )


@router.message(F.text == "/shop_done", ShopImportStates.collecting)
@router.message(F.text == "/shop_done", ShopImportStates.choosing_category)
async def shop_import_stop(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(f"✅ Импорт завершён. В каталоге — {await _shop_summary()}")


async def _save_item(gender: str, item_type: str, source: Message):
    """Сохраняет товар и возвращает (текст ответа, клавиатура или None)"""
    data = extract_item(source)
    link, key = source_link(source)

    result = await database.add_shop_item(
        gender, item_type, data["title"], data["description"],
        data["photo_id"], link, key
    )

    marks = []
    if data["photo_id"]:
        marks.append("фото")
    if link:
        marks.append("ссылка")
    extra = f" ({', '.join(marks)})" if marks else " (без фото и ссылки)"

    if result.startswith("added:"):
        item_id = result.split(":", 1)[1]
        # Автораскладка по словам иногда промахивается, поэтому даём поправить
        # категорию сразу, не отходя от подтверждения.
        fix = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="✏️ Другая категория", callback_data=f"shopfix_{item_id}")]])
        return (f"✅ <b>{category_title(gender, item_type, 'ru')}</b>{extra}\n"
                f"«{data['title']}»\n\nВ каталоге — {await _shop_summary()}"), fix

    if result == "duplicate":
        return f"↩️ Этот товар уже в каталоге. Сейчас — {await _shop_summary()}", None

    detail = result.split(":", 1)[1] if result.startswith("error:") else "причина неизвестна"
    return f"⚠️ Товар не сохранён.\n\n<code>{detail[:600]}</code>", None


@router.callback_query(F.data.startswith("shopfix_"))
async def shop_offer_move(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        return
    await call.answer()
    item_id = call.data.removeprefix("shopfix_")
    await call.message.edit_text(
        "В какую категорию перенести товар?",
        reply_markup=_category_markup(prefix="shopmove", suffix=item_id)
    )


@router.callback_query(F.data.startswith("shopmove_"))
async def shop_move_item(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        return
    await call.answer()
    try:
        _, gender, item_type, raw_id = call.data.split("_", 3)
        item_id = int(raw_id)
    except ValueError:
        return

    ok = await database.move_shop_item(item_id, gender, item_type)
    if ok:
        await call.message.edit_text(
            f"✅ Перенесено в <b>{category_title(gender, item_type, 'ru')}</b>\n\n"
            f"В каталоге — {await _shop_summary()}"
        )
    else:
        await call.message.edit_text("⚠️ Не удалось перенести — ошибка базы.")


@router.message(ShopImportStates.collecting, F.text | F.caption, ~F.text.startswith("/"))
async def shop_import_post(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return

    text = message.text or message.caption or ""
    gender, item_type = detect_category(text)

    if gender and item_type:
        text_reply, markup = await _save_item(gender, item_type, message)
        await message.answer(text_reply, reply_markup=markup)
        return

    await state.set_state(ShopImportStates.choosing_category)
    _pending_items[message.from_user.id] = message

    guess = ""
    if item_type:
        guess = f"\n\nПохоже на «{TYPES.get('women', {}).get(item_type, {}).get('ru', item_type)}», но не ясен пол."
    preview = text.strip().split("\n")[0][:60]
    await message.answer(
        f"❓ Не удалось разложить пост «{preview}».{guess}\n\nВыберите категорию:",
        reply_markup=_category_markup()
    )


@router.callback_query(F.data.startswith("shopcat_"), ShopImportStates.choosing_category)
async def shop_import_choose(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        return
    await call.answer()

    _, gender, item_type = call.data.split("_", 2)
    source = _pending_items.pop(call.from_user.id, None)
    await state.set_state(ShopImportStates.collecting)

    if gender == "skip" or source is None:
        await call.message.edit_text("⏭ Пост пропущен. Пересылайте следующий.")
        return

    text_reply, markup = await _save_item(gender, item_type, source)
    await call.message.edit_text(text_reply, reply_markup=markup)


@router.message(ShopImportStates.collecting, ~F.text.startswith("/"))
async def shop_import_hint(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    await message.answer(
        "В этом посте нет ни текста, ни подписи — сохранять нечего. "
        "Перешлите пост с описанием или отправьте /shop_done для выхода."
    )
