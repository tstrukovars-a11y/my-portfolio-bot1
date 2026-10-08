# art_channel.py — канал с картинами: одна работа — один пост.
#
# Все работы одним постом — это альбом, а не витрина. У альбома нет
# того, ради чего всё затевается: на отдельную картину нельзя дать
# ссылку, под ней нельзя поставить кнопку, её нельзя обсудить отдельно
# и нельзя посчитать, сколько раз её смотрели.
#
# Поэтому так же, как с рецептами: пост в канале — источник, бот его
# читает и заводит карточку. Писать приходится в канале, одной рукой, с
# телефона — значит, разметка должна прощать. Она не формат, а
# привычка: пропущенная строка ничего не ломает, перепутанный порядок
# тоже.
#
# Под постом — «примерить у себя». Главное возражение против покупки
# картины не «дорого», а «не представляю, как она будет выглядеть».
# Сантиметры на это не отвечают, а своя стена отвечает сразу.
import html
import logging
import os
import re

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, FSInputFile, BufferedInputFile)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.dispatcher.event.bases import SkipHandler

import config
import database

router = Router()

CHANNEL_KEY = "art_channel"

# Разделители, которыми в одной строке перечисляют год, технику и размер.
SPLIT = re.compile(r"\s*[·•|]\s*|\s+[-—–]\s+")

# Размер: «60 × 80», «60x80», «60 на 80». Икс бывает латинский, русский
# и типографский — человек ставит тот, что попался под руку.
SIZE = re.compile(r"(\d{1,3}(?:[.,]\d)?)\s*(?:[x×хХ*]|на)\s*(\d{1,3}(?:[.,]\d)?)")
YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")
# Пробелы внутри числа перечислены поимённо, а не через \s: тот ловит и
# перенос строки, и «60 × 80» на строке выше склеивалось с «45 000» на
# строке ниже в восемь миллионов.
PRICE = re.compile(r"(\d[\d    ]{2,})[  ]*(?:₽|руб|р\.|rub)",
                   re.I)

SOLD = ("продана", "продано", "sold", "в коллекции")


def _number(raw: str) -> float:
    return float(raw.replace(",", "."))


def parse(text: str) -> dict:
    """Разобрать пост о картине.

    Разметка рекомендуемая, а не обязательная:

        Тишина в полдень
        2024 · холст, масло · 60 × 80 см
        45 000 ₽

        Писала с балкона, когда гроза уже ушла…

    Первая строка — название, дальше что найдётся. Ничего не нашлось —
    останется название и рассказ: карточка выйдет неполной, но выйдет.
    Пост, который бот отказался понять, хуже неполной карточки.
    """
    lines = [x.strip() for x in (text or "").splitlines()]
    lines = [x for x in lines if x]
    if not lines:
        return {}

    title = lines[0].lstrip("#").strip()
    if len(title) > 80:
        title = title[:77].rstrip() + "…"

    body = "\n".join(lines[1:])
    found = {"title": title, "year": None, "technique": "", "size": "",
             "width": 0.0, "height": 0.0, "price": 0, "status": "available"}

    size = SIZE.search(body)
    if size:
        found["width"] = _number(size.group(1))
        found["height"] = _number(size.group(2))
        found["size"] = f"{found['width']:g} × {found['height']:g} см"

    year = YEAR.search(body)
    if year:
        found["year"] = int(year.group(1))

    price = PRICE.search(body)
    if price:
        digits = re.sub(r"\D", "", price.group(1))
        if digits:
            found["price"] = int(digits)

    if any(word in body.lower() for word in SOLD):
        found["status"] = "sold"

    # Техника — то, что осталось в строке после года, цены и размера.
    # Отдельного слова для неё нет, а перечисление «холст, масло» стоит
    # там же, и вырезать лишнее надёжнее, чем угадывать нужное.
    for line in lines[1:4]:
        if not SIZE.search(line) and not YEAR.search(line):
            continue
        # Вырезаем известное из куска, а не выбрасываем кусок целиком:
        # «холст 40х50» — это и техника, и размер в одной строке, и
        # выброшенный кусок уносил бы с собой холст.
        parts = []
        for piece in SPLIT.split(line):
            piece = PRICE.sub(" ", SIZE.sub(" ", YEAR.sub(" ", piece)))
            piece = piece.strip(" ,;.·•-—–")
            if not piece or piece.lower() in ("см", "cm") or piece.isdigit():
                continue
            if piece.lower() in SOLD:
                continue
            parts.append(piece)
        if parts:
            found["technique"] = ", ".join(parts)[:80]
            break

    # Рассказ — всё, что ниже строки с данными. Он и продаёт: размер
    # говорит, поместится ли вещь, рассказ — зачем она нужна.
    story = []
    for line in lines[1:]:
        if SIZE.search(line) or PRICE.search(line):
            continue
        if YEAR.search(line) and len(line) < 60:
            continue
        if line.startswith("#"):
            continue
        # «Продана» — пометка о состоянии, а не фраза рассказа. В
        # карточке она уже учтена статусом, и повторять её текстом
        # значит писать покупателю «продана» дважды.
        if line.strip().lower().strip(".!") in SOLD:
            continue
        story.append(line)
    found["story"] = "\n".join(story).strip()
    return found


# ---------------------------------------------------------------------
# ЧТЕНИЕ КАНАЛА
# ---------------------------------------------------------------------

async def _is_art_post(message: Message) -> bool:
    raw = await database.get_setting(CHANNEL_KEY)
    try:
        return bool(raw) and message.chat.id == int(raw)
    except (TypeError, ValueError):
        return False


def _photo_of(message: Message):
    return message.photo[-1].file_id if message.photo else None


@router.channel_post(_is_art_post)
async def take_post(message: Message):
    """Новая работа из канала.

    Номер поста запоминаем: правка в канале должна менять карточку, а
    не заводить вторую. Альбом и так был одним постом — плодить копии
    здесь было бы заменой одной беды другой.
    """
    data = parse(message.text or message.caption or "")
    if not data:
        return
    photo = _photo_of(message)
    if not photo:
        logging.info("Канал картин: пост без фотографии — пропускаю")
        return

    work_id = await database.art_add(data["title"], photo)
    if not work_id:
        return
    await database.art_set(
        work_id, year=data["year"], technique=data["technique"],
        size=data["size"], price=data["price"] or None,
        story=data["story"], status=data["status"])
    await database.art_set_channel_msg(work_id, message.message_id)
    logging.info(f"🎨 Канал картин: добавлена «{data['title']}» (#{work_id})")

    # Цена в посте — не ошибка разбора, а решение, принятое наоборот:
    # прайс держим отдельно. Молчать об этом нельзя — число уже видят
    # подписчики, и чем позже это заметят, тем дороже правка.
    if data["price"]:
        logging.warning(f"Канал картин: в посте «{data['title']}» "
                        f"напечатана цена — она видна всем")


@router.edited_channel_post(_is_art_post)
async def fix_post(message: Message):
    """Поправили пост — поправилась карточка"""
    work_id = await database.art_by_channel_msg(message.message_id)
    if not work_id:
        return
    data = parse(message.text or message.caption or "")
    if not data:
        return
    fields = {"title": data["title"], "year": data["year"],
              "technique": data["technique"], "size": data["size"],
              "price": data["price"] or None, "story": data["story"],
              "status": data["status"]}
    photo = _photo_of(message)
    if photo:
        fields["photo_file_id"] = photo
    await database.art_set(work_id, **fields)
    logging.info(f"🎨 Канал картин: поправлена работа #{work_id}")


# ---------------------------------------------------------------------
# ПРИМЕРИТЬ У СЕБЯ
# ---------------------------------------------------------------------

class TryOn(StatesGroup):
    waiting_wall = State()
    waiting_width = State()


ASK_WALL = (
    "🖼 <b>Примерим у вас</b>\n\n"
    "Пришлите фотографию стены, на которую смотрите.\n\n"
    "Как снимать: встаньте напротив, камера на уровне груди, "
    "без наклона. Чем ровнее — тем точнее ляжет."
)

ASK_WIDTH = (
    "Теперь одно число: <b>сколько примерно сантиметров стены попало "
    "в кадр по ширине</b>?\n\n"
    "Без него размер можно только угадать, а угаданный выглядит как "
    "ответ и обманывает сильнее, чем его отсутствие."
)

WIDTHS = (200, 300, 400, 500)


def _width_kb(work_id: int):
    rows = [[InlineKeyboardButton(text=f"{w // 100} м",
                                  callback_data=f"try_w_{work_id}_{w}")
             for w in WIDTHS]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def try_row(work_id: int, username: str):
    """Кнопки под постом в канале.

    Цены на посте нет намеренно. Прайс живёт отдельно, у автора: цена,
    напечатанная в канале, живёт там вечно и для каждого одна, а
    разговор о цене — это разговор про размер, раму и доставку, и
    начинается он с человека, а не с числа.
    """
    if not username:
        return None
    base = f"https://t.me/{username.lstrip('@')}?start="
    return [
        [InlineKeyboardButton(text="🖼 Примерить у себя",
                              url=f"{base}try-{work_id}")],
        [InlineKeyboardButton(text="💬 Запросить цену",
                              url=f"{base}ask-{work_id}")],
    ]


@router.message(F.text.regexp(r"^/start\s+ask-"))
async def start_ask(message: Message, bot: Bot):
    """Пришёл из канала спросить цену.

    Цену не называем сами, даже если она записана: прайс отдельный, и
    решает, кому и какую назвать, автор. Бот доносит вопрос вместе с
    контактом — дальше человек с человеком, как и во всём остальном
    разделе.
    """
    raw = (message.text or "").split("ask-", 1)[1].strip()
    if not raw.isdigit():
        raise SkipHandler
    work = await database.art_get(int(raw))
    if not work:
        await message.answer("Эта работа больше недоступна.")
        raise SkipHandler

    user = message.from_user
    username = f"@{user.username}" if user.username else None
    await database.art_request(work["id"], user.id, username)

    contact = username or (f"<a href='tg://user?id={user.id}'>"
                           f"{html.escape(user.full_name)}</a>")
    # Записанную цену показываем владелице, а не спрашивающему: чтобы
    # ответить одним сообщением, не поднимая прайс.
    price = (f"{work['price']:,}".replace(",", " ") + " ₽") \
        if work.get("price") else "цена не записана"
    try:
        await bot.send_message(
            config.ADMIN_ID,
            f"💬 <b>Спрашивают цену</b>\n\n"
            f"«{html.escape(work['title'])}»"
            + (f" · {html.escape(work.get('size') or '')}" if work.get("size") else "")
            + f"\nВ прайсе: {price}\nОт: {contact}")
    except Exception as e:
        logging.error(f"Вопрос о цене не дошёл: {e}")

    await message.answer_photo(
        work["photo_file_id"],
        caption=f"<b>{html.escape(work['title'])}</b>"
                + (f"\n{html.escape(work['size'])}" if work.get("size") else ""))
    await message.answer(
        "💬 Передала вопрос — отвечу здесь же.\n\n"
        "Заодно расскажу про раму, доставку и то, как работа ведёт "
        "себя при разном свете.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🖼 Пока примерить у себя",
                                 callback_data=f"try_open_{work['id']}")]]))
    raise SkipHandler


@router.message(F.text.regexp(r"^/start\s+try-"))
async def start_try(message: Message, state: FSMContext):
    """Пришёл из канала примерять работу.

    Роутер зарегистрирован раньше общего /start, поэтому в конце
    обязательно передаём ход дальше: человек здесь может быть впервые,
    и без приветствия он останется один на один с просьбой про стену.
    """
    raw = (message.text or "").split("try-", 1)[1].strip()
    if not raw.isdigit():
        raise SkipHandler
    work = await database.art_get(int(raw))
    if not work:
        await message.answer("Эта работа больше недоступна.")
        raise SkipHandler

    await state.set_state(TryOn.waiting_wall)
    await state.update_data(work_id=int(raw))
    await message.answer_photo(
        work["photo_file_id"],
        caption=f"<b>{html.escape(work['title'])}</b>"
                + (f"\n{html.escape(work['size'])}" if work.get("size") else ""))
    await message.answer(ASK_WALL)
    raise SkipHandler


@router.callback_query(F.data.startswith("try_open_"))
async def open_try(call: CallbackQuery, state: FSMContext):
    """То же самое из переписки с ботом"""
    raw = call.data[len("try_open_"):]
    if not raw.isdigit():
        await call.answer()
        return
    await call.answer()
    await state.set_state(TryOn.waiting_wall)
    await state.update_data(work_id=int(raw))
    await call.message.answer(ASK_WALL)


@router.message(TryOn.waiting_wall, F.photo)
async def got_wall(message: Message, state: FSMContext):
    await state.update_data(wall=message.photo[-1].file_id)
    await state.set_state(TryOn.waiting_width)
    data = await state.get_data()
    await message.answer(ASK_WIDTH,
                         reply_markup=_width_kb(data.get("work_id", 0)))


@router.message(TryOn.waiting_wall)
async def not_a_wall(message: Message):
    await message.answer("Нужна именно фотография стены — пришлите "
                         "её картинкой, не файлом.")


@router.message(TryOn.waiting_width, F.text.regexp(r"^\s*\d{2,4}\s*$"))
async def typed_width(message: Message, state: FSMContext, bot: Bot):
    await _render(message, state, bot, int(message.text.strip()))


@router.callback_query(F.data.startswith("try_w_"))
async def picked_width(call: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        _, width = call.data[len("try_w_"):].rsplit("_", 1)
        centimetres = int(width)
    except ValueError:
        await call.answer()
        return
    await call.answer("Собираю…")
    await _render(call.message, state, bot, centimetres)


async def _render(message: Message, state: FSMContext, bot: Bot,
                  wall_cm: int) -> None:
    """Собрать и прислать примерку"""
    data = await state.get_data()
    work = await database.art_get(data.get("work_id", 0))
    if not work or not data.get("wall"):
        await state.clear()
        await message.answer("Что-то потерялось — начните заново.")
        return

    width_cm, height_cm = _size_of(work.get("size") or "")
    if not width_cm:
        await state.clear()
        await message.answer(
            "У этой работы не записан размер — примерить не получится. "
            "Напишите мне, подскажу размеры руками.")
        return

    import io
    from PIL import Image
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "tools"))
    import interior

    try:
        wall_file = await bot.download(data["wall"])
        art_file = await bot.download(work["photo_file_id"])
        out = interior.on_photo(Image.open(art_file), Image.open(wall_file),
                                width_cm, height_cm, wall_cm)
    except ValueError as e:
        await message.answer(f"Не вышло: {html.escape(str(e))}")
        return
    except Exception as e:
        logging.error(f"Примерка не собралась: {e}")
        await message.answer("Не получилось собрать примерку. "
                             "Попробуйте другую фотографию стены.")
        return

    buffer = io.BytesIO()
    out.save(buffer, format="JPEG", quality=90)
    buffer.seek(0)

    await state.clear()
    await message.answer_photo(
        BufferedInputFile(buffer.read(), filename="interior.jpg"),
        caption=(f"<b>{html.escape(work['title'])}</b> — "
                 f"{html.escape(work.get('size') or '')}\n\n"
                 f"<i>Масштаб по вашей оценке: {wall_cm} см стены в кадре. "
                 f"Настоящий размер работы — в подписи выше.</i>"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🖼 Другая стена",
                                 callback_data=f"try_open_{work['id']}")]]))


def _size_of(size: str):
    """«60 × 80 см» → (60.0, 80.0). Нет размера — (0, 0)."""
    found = SIZE.search(size or "")
    if not found:
        return 0.0, 0.0
    return _number(found.group(1)), _number(found.group(2))


# ---------------------------------------------------------------------
# СЛУЖЕБНОЕ
# ---------------------------------------------------------------------

MARKUP = (
    "🎨 <b>Как писать пост о картине</b>\n\n"
    "Одна работа — один пост, с фотографией:\n\n"
    "<code>Тишина в полдень\n"
    "2024 · холст, масло · 60 × 80 см\n\n"
    "Писала с балкона, когда гроза уже ушла, а свет ещё не вернулся.\n\n"
    "#пейзаж #холст_масло #среднее #тихое</code>\n\n"
    "Первая строка — название. Вторая — год, техника и размер через «·», "
    "в любом порядке.\n\n"
    "Дальше рассказ: размер говорит, поместится ли вещь, рассказ — "
    "зачем она нужна.\n\n"
    "<b>Цену в пост не ставим.</b> Под постом кнопка «запросить» — "
    "вопрос приходит вам вместе с контактом и записанной ценой. "
    "Прайс держим отдельно: <code>/art_price</code>\n\n"
    "Разметка прощает: пропущенная строка ничего не ломает, "
    "перепутанный порядок тоже. Обязательны только фотография, название "
    "и размер — без размера не работает примерка.\n\n"
    "Проданную помечайте словом <code>продана</code> в тексте: "
    "из канала она не исчезнет, а отметку получит.\n\n"
    "Метки: <code>/art_tags</code> · Канал: <code>/art_channel -100…</code>"
)

# Метки — не украшение, а навигация. Telegram делает из каждой ссылку на
# поиск по каналу, и набор работает только пока он один и тот же:
# «#пейзаж» и «#пейзажи» — две разные полки, на каждой по половине.
#
# Поэтому список закрытый, по четырём осям, и в посте берётся не больше
# одной метки с оси. Пять меток — потолок: дальше они читаются как шум
# и перестают быть указателем.
TAGS = {
    "о чём": ("#пейзаж", "#портрет", "#натюрморт", "#абстракция",
              "#город", "#море", "#цветы", "#фигура"),
    "чем и на чём": ("#холст_масло", "#акрил", "#акварель", "#пастель",
                     "#графика", "#смешанная"),
    "какого размера": ("#маленькое", "#среднее", "#большое", "#вертикаль",
                       "#горизонталь", "#квадрат"),
    "какое по настроению": ("#тихое", "#яркое", "#тёплое", "#холодное",
                            "#светлое", "#тёмное"),
}

TAG_SIZES = (
    ("#маленькое", "до 40 см по большей стороне"),
    ("#среднее", "40–80 см"),
    ("#большое", "от 80 см"),
)

TAG_HELP = (
    "🏷 <b>Метки</b>\n\n"
    "Telegram делает из каждой метки ссылку на поиск по каналу. Это не "
    "украшение, а полки: по ним человек ходит, когда ищет «что-нибудь "
    "в спальню».\n\n"
    "Работает только закрытый список. «#пейзаж» и «#пейзажи» — две "
    "разные полки, на каждой по половине работ, и обе бесполезны.\n\n"
    "<b>Берите по одной метке с каждой оси, всего три-пять.</b> Больше "
    "читается как шум.\n\n"
    + "\n\n".join(
        f"<b>{axis}</b>\n" + "  ".join(f"<code>{t}</code>" for t in tags)
        for axis, tags in TAGS.items())
    + "\n\n<b>Размер по большей стороне:</b>\n"
    + "\n".join(f"  <code>{tag}</code> — {what}" for tag, what in TAG_SIZES)
    + "\n\nПример: <code>#пейзаж #холст_масло #среднее #тихое</code>\n\n"
      "<i>Пробел внутри метки её обрывает — пишите через нижнее "
      "подчёркивание. Русские метки Telegram понимает.</i>"
)


@router.message(F.text.regexp(r"^/art_tags"))
async def tags_help(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    await message.answer(TAG_HELP)


@router.message(F.text.regexp(r"^/art_markup"))
async def markup_help(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    await message.answer(MARKUP)


@router.message(F.text.regexp(r"^/art_price"))
async def price_command(message: Message):
    """Прайс — здесь, а не в канале.

    В канале цена живёт вечно и для каждого одна: её видит и тот, кому
    вы сделали бы скидку, и тот, кто пришёл через год, когда цена
    выросла. Здесь она ваша и меняется одной строкой.
    """
    if not config.is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        works = await database.art_list()
        lines = ["💰 <b>Прайс</b> — виден только вам", ""]
        for work in works or []:
            price = (f"{work['price']:,}".replace(",", " ") + " ₽") \
                if work.get("price") else "—"
            mark = "🔴" if work.get("status") == "sold" else "·"
            lines.append(f"{mark} <code>{work['id']}</code> "
                         f"{html.escape(work['title'][:34])} — {price}")
        if not works:
            lines.append("<i>Работ пока нет. Опубликуйте пост в канале "
                         "картин — карточка заведётся сама.</i>")
        lines.append("")
        lines.append("Поставить цену: <code>/art_price 7 45000</code>\n"
                     "Снять: <code>/art_price 7 нет</code>")
        await message.answer("\n".join(lines))
        return

    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer("Нужно так: <code>/art_price 7 45000</code>")
        return

    work_id = int(parts[1])
    raw = parts[2].lower()
    value = None if raw in ("нет", "-", "0") else \
        int(re.sub(r"\D", "", parts[2]) or 0) or None
    if not await database.art_set(work_id, price=value):
        await message.answer(f"Работы №{work_id} нет.")
        return
    shown = (f"{value:,}".replace(",", " ") + " ₽") if value else "снята"
    await message.answer(f"💰 Работа №{work_id}: {shown}.\n\n"
                         f"<i>В канал это не уходит — цену называете вы.</i>")


@router.message(F.text.regexp(r"^/art_channel"))
async def set_channel(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        current = await database.get_setting(CHANNEL_KEY) or "не задан"
        await message.answer(
            f"🎨 Канал с работами: <code>{html.escape(current)}</code>\n\n"
            f"Задать: <code>/art_channel -100123…</code>\n"
            f"Разметка поста: <code>/art_markup</code>")
        return
    await database.set_setting(CHANNEL_KEY, parts[1].strip())
    await message.answer(
        "🎨 Канал записан. Публикуйте по одной работе в пост — "
        "карточки заведутся сами.\n\nРазметка: <code>/art_markup</code>")
