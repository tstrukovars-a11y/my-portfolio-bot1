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
PRICE = re.compile(r"(\d[\d\s  ]{2,})\s*(?:₽|руб|р\.|rub)", re.I)

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
    """Кнопка под постом в канале"""
    if not username:
        return None
    return [InlineKeyboardButton(
        text="🖼 Примерить у себя",
        url=f"https://t.me/{username.lstrip('@')}?start=try-{work_id}")]


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
    "2024 · холст, масло · 60 × 80 см\n"
    "45 000 ₽\n\n"
    "Писала с балкона, когда гроза уже ушла, а свет ещё не вернулся.\n\n"
    "#живопись #пейзаж</code>\n\n"
    "Первая строка — название. Вторая — год, техника и размер через «·», "
    "в любом порядке. Третья — цена, если ставите.\n\n"
    "Дальше рассказ: размер говорит, поместится ли вещь, рассказ — "
    "зачем она нужна.\n\n"
    "Разметка прощает: пропущенная строка ничего не ломает, "
    "перепутанный порядок тоже. Обязательны только фотография, название "
    "и размер — без размера не работает примерка.\n\n"
    "Проданную помечайте словом <code>продана</code> в тексте: "
    "из канала она не исчезнет, а отметку получит.\n\n"
    "Канал для работ: <code>/art_channel -100…</code>"
)


@router.message(F.text.regexp(r"^/art_markup"))
async def markup_help(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    await message.answer(MARKUP)


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
