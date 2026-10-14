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


NO_RIGHTS = (
    "🎨 Карточка «{title}» завелась, но кнопки под постом не встали.\n\n"
    "Боту нужно право <b>«Редактировать сообщения других»</b> в канале: "
    "пост написан вами, и без этого права бот не может ничего к нему "
    "добавить.\n\n"
    "Канал → Администраторы → бот → включить. Потом поправьте пост — "
    "кнопки встанут.\n\n"
    "<code>{error}</code>"
)


async def attach_buttons(bot: Bot, message: Message, work_id: int,
                         title: str) -> bool:
    """Повесить кнопки под пост, который написан рукой.

    Пост пишет владелица, а кнопки нужны боту — значит, он должен
    дописать их к чужому сообщению. В канале это разрешено
    администратору с правом править чужие посты; есть оно у бота или
    нет, заранее не известно.

    Поэтому не молчим при отказе. Кнопки — единственный путь из канала
    в бота: без них пост остаётся картинкой, примерить работу нельзя и
    цену спросить не у кого, а понять это по тишине невозможно.
    """
    username = await database.get_setting("bot_username")
    rows = try_row(work_id, username or "")
    if not rows:
        logging.warning("Канал картин: имя бота не известно — кнопок не будет")
        return False
    try:
        await bot.edit_message_reply_markup(
            chat_id=message.chat.id, message_id=message.message_id,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        return True
    except Exception as e:
        logging.error(f"Кнопки под постом «{title}» не встали: {e}")
        try:
            await bot.send_message(
                config.ADMIN_ID,
                NO_RIGHTS.format(title=html.escape(title),
                                 error=html.escape(str(e)[:160])))
        except Exception:
            pass
        return False


@router.channel_post(_is_art_post)
async def take_post(message: Message, bot: Bot = None):
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

    if bot is not None:
        await attach_buttons(bot, message, work_id, data["title"])


@router.edited_channel_post(_is_art_post)
async def fix_post(message: Message, bot: Bot = None):
    """Поправили пост — поправилась карточка.

    Если карточки ещё нет, правка её заводит. Это не щедрость, а
    единственный способ забрать то, что опубликовано раньше бота:
    новые посты приходят сами, а старые не придут никогда — Telegram
    историю канала не пересказывает.

    Поэтому «подобрать уже висящий пост» — это открыть его, поставить
    точку и сохранить. Отдельная команда разбора канала была бы честнее
    на вид, но Telegram не даёт боту читать прошлое, и команда всё
    равно умела бы только это.
    """
    work_id = await database.art_by_channel_msg(message.message_id)
    data = parse(message.text or message.caption or "")
    if not data:
        return
    if not work_id:
        await take_post(message, bot)
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

    # Правка — второй шанс для кнопок: если в первый раз у бота не было
    # права, владелица его выдала и поправила пост именно затем.
    if bot is not None and not message.reply_markup:
        await attach_buttons(bot, message, work_id, data["title"])


# ---------------------------------------------------------------------
# ПРИМЕРИТЬ У СЕБЯ
# ---------------------------------------------------------------------

class TryOn(StatesGroup):
    waiting_wall = State()
    waiting_width = State()


class Valuing(StatesGroup):
    """Человек считает свою работу"""
    waiting_size = State()
    waiting_technique = State()
    waiting_sold = State()


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
        "себя при разном свете.")

    # Пока ждёт ответа — показываем, откуда вообще берутся цены на
    # картины. Человек спросил о цене: значит, вопрос «сколько это
    # стоит и почему» у него уже возник, и отвечать на него надо
    # сейчас, а не когда он остынет.
    await _value_screen(message, work)
    raise SkipHandler


async def _value_screen(message: Message, work: dict) -> None:
    """Откуда берётся цена этой работы — и предложение посчитать свою"""
    import art_value

    width, height = _size_of(work.get("size") or "")
    sold = await database.art_sold_count()

    if art_value.is_commission(work["title"], work.get("technique") or ""):
        text = art_value.explain(width, height,
                                 work.get("technique") or "",
                                 sold, work["title"])
    elif width:
        text = art_value.explain(width, height,
                                 work.get("technique") or "", sold)
    else:
        text = ("📐 У этой работы не записан размер — посчитать ориентир "
                "не из чего.")

    rows = [[InlineKeyboardButton(text="🖼 Примерить у себя",
                                  callback_data=f"try_open_{work['id']}")],
            [InlineKeyboardButton(text="📐 Посчитать свою работу",
                                  callback_data="val_start")],
            [InlineKeyboardButton(text="🎨 Я художник, хочу продавать здесь",
                                  callback_data="mkt_start")]]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(
        inline_keyboard=rows))


# ---------------------------------------------------------------------
# ПОСЧИТАТЬ СВОЮ РАБОТУ
# ---------------------------------------------------------------------
#
# Развилка после вопроса о цене. Человек, которому интересно, сколько
# стоит чужая картина, почти всегда либо собирается купить, либо пишет
# сам — и второй случай ценнее: покупатель приходит один раз, художник
# приносит работы.

@router.callback_query(F.data == "val_start")
async def value_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(Valuing.waiting_size)
    await call.message.answer(
        "📐 <b>Посчитаем вашу работу</b>\n\n"
        "Размер в сантиметрах — ширина и высота.\n"
        "Например: <code>60 на 80</code>")


@router.message(Valuing.waiting_size, F.text)
async def value_size(message: Message, state: FSMContext):
    import art_value
    width, height = art_value.parse_size(message.text)
    if not width:
        await message.answer("Не разобрала размер. Напишите как "
                             "<code>60 на 80</code>.")
        return
    await state.update_data(width=width, height=height)
    await state.set_state(Valuing.waiting_technique)
    rows = [[InlineKeyboardButton(text=name, callback_data=f"val_t_{key}")]
            for key, name in (("холст_масло", "Холст, масло"),
                              ("картон_масло", "Картон, масло"),
                              ("акрил", "Акрил"),
                              ("акварель", "Акварель"),
                              ("графика", "Графика"))]
    await message.answer("Чем написана?",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("val_t_"), Valuing.waiting_technique)
async def value_technique(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.update_data(technique=call.data[len("val_t_"):])
    await state.set_state(Valuing.waiting_sold)
    rows = [[InlineKeyboardButton(text=name, callback_data=f"val_s_{n}")]
            for n, name in ((0, "Пока ничего не продавал"),
                            (1, "Одну-две"),
                            (5, "Около пяти"),
                            (15, "Больше пятнадцати"))]
    await call.message.answer(
        "Сколько работ уже продали?\n\n"
        "<i>Это главный множитель: пока продаж нет, цену держит только "
        "размер.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("val_s_"), Valuing.waiting_sold)
async def value_result(call: CallbackQuery, state: FSMContext):
    import art_value
    await call.answer("Считаю…")
    data = await state.get_data()
    try:
        sold = int(call.data[len("val_s_"):])
    except ValueError:
        sold = 0
    await state.clear()

    text = art_value.explain(data.get("width", 0), data.get("height", 0),
                             data.get("technique", ""), sold)
    await call.message.answer(text, reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📐 Посчитать ещё одну",
                                  callback_data="val_start")],
            [InlineKeyboardButton(text="🎨 Предложить работы в канал",
                                  callback_data="mkt_start")]]))


# Форма «расскажите о себе» жила здесь, пока приём чужих работ был
# обещанием. Теперь он есть и устроен иначе: художник размещается
# сам и продаёт сам — см. art_market.py. Анкета «напишите, и я
# отвечу» на её фоне стала тупиком: человек пишет и ждёт, вместо
# того чтобы разместиться за пять шагов.


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
              "#город", "#море", "#цветы", "#фигура", "#герб"),
    # Основа важна не меньше краски: по картону и холсту вещь висит
    # по-разному и стоит по-разному, и спрашивают об этом первым делом.
    "чем и на чём": ("#холст_масло", "#картон_масло", "#акрил",
                     "#акварель", "#пастель", "#графика", "#смешанная"),
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


def _money(value) -> str:
    return (f"{int(value):,}".replace(",", " ") + " ₽") if value else "—"


# ---------------------------------------------------------------------
# ИЗ ВИТРИНЫ В ЖУРНАЛ
# ---------------------------------------------------------------------
#
# Канал картин — полка: там лежат все работы, и там их ищут. «Акцент» —
# журнал, и у него свой голос.
#
# Слать туда каждую работу нельзя: журнал превратится в ленту товаров, а
# читают его не за этим. Но новая работа — это событие, и молчать о ней
# значит выкладывать на полку, мимо которой никто не ходит.
#
# Поэтому отбор руками. Команда, а не автоматическая пересылка: решает,
# какая работа достойна журнала, человек.

async def publish_to_journal(bot: Bot, work_id: int) -> str:
    """Показать работу в «Акценте» и продублировать в клуб"""
    import digest

    work = await database.art_get(work_id)
    if not work:
        return f"работы №{work_id} нет"

    chat, thread = await digest._target()
    if not chat:
        return "канал не задан: /digest chat -100…"

    sold = work.get("status") == "sold"
    head = "🖼 <b>Новая работа</b>" if not sold else "✅ <b>Работа нашла дом</b>"
    lines = [head, "", f"<b>{html.escape(work['title'])}</b>"]

    facts = [x for x in (str(work["year"]) if work.get("year") else "",
                         work.get("technique") or "",
                         work.get("size") or "") if x]
    if facts:
        lines.append(" · ".join(html.escape(f) for f in facts))
    if work.get("story"):
        lines.append("")
        lines.append(html.escape(work["story"])[:900])

    username = await database.get_setting("bot_username")
    rows = []
    if username and not sold:
        rows = try_row(work_id, username)
    club = await digest._club_row("art", bot)
    if club:
        rows.append(club)

    try:
        sent = await bot.send_photo(
            chat, work["photo_file_id"], caption="\n".join(lines)[:1024],
            message_thread_id=thread,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
            if rows else None)
    except Exception as e:
        logging.error(f"Работа №{work_id} в журнал не вышла: {e}")
        return f"ошибка: {e}"

    # Дубль в группу — в свою тему. Картина в теме про генетику
    # выглядит ошибкой, а не публикацией.
    #
    # Кнопки передаём: в группе их и будут нажимать. Там человек уже
    # разговаривает, и «примерить у себя» оттуда ближе, чем из канала,
    # где он молча листает.
    await digest._mirror(bot, chat, sent.message_id, "art",
                         InlineKeyboardMarkup(inline_keyboard=rows)
                         if rows else None)
    return f"«{work['title']}» — в «Акценте»"


async def publish_next(bot: Bot) -> str:
    """Очередная работа в журнал — по расписанию, без выбора руками.

    Сначала выход из витрины был командой: мол, решает человек, какая
    работа достойна журнала. На деле это значило, что работы не выходят
    вовсе — команду надо вспомнить и набрать, а канал ждать не станет.
    Расписание держит ритм там, где воля человека его не держит.

    Отбор остаётся, но наоборот: не «какую показать», а «какую не
    показывать». Работа выходит один раз, по очереди добавления.
    """
    work = await database.art_next_unannounced()
    if not work:
        return "показаны все работы"

    result = await publish_to_journal(bot, work["id"])
    if result.startswith(("ошибка", "канал", "работы")):
        return result

    from datetime import datetime, timezone
    await database.art_set(
        work["id"],
        announced_at=datetime.now(timezone.utc).replace(tzinfo=None))
    left = await database.art_waiting()
    return f"{result} · в очереди ещё {left}"


@router.message(F.text.regexp(r"^/art_queue"))
async def queue_command(message: Message):
    """Что и когда выйдет. Очередь невидима, пока о ней не спросишь."""
    if not config.is_admin(message.from_user.id):
        return
    left = await database.art_waiting()
    following = await database.art_next_unannounced()
    lines = ["🖼 <b>Очередь в журнал</b>", ""]
    if following:
        lines.append(f"Следующая: <b>{html.escape(following['title'])}</b>")
        lines.append(f"Ждут выхода: {left}")
    else:
        lines.append("<i>Все работы показаны. Новая выйдет в тот же день, "
                     "когда появится в канале картин.</i>")
    lines.append("")
    lines.append("Выходят в 17:30, по одной.\n"
                 "Показать сейчас: <code>/art_post 1</code>\n"
                 "Вернуть в очередь: <code>/art_again 1</code>")
    await message.answer("\n".join(lines))


@router.message(F.text.regexp(r"^/art_again"))
async def again_command(message: Message):
    """Вернуть работу в очередь — показать ещё раз.

    Нужна не для повторов ради повторов: работу правят, дописывают
    рассказ, снижают цену. Показанная однажды и забытая навсегда — это
    потеря, а не порядок.
    """
    if not config.is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Так: <code>/art_again 1</code> — работа "
                             "вернётся в очередь и выйдет снова.")
        return
    if not await database.art_set(int(parts[1]), announced_at=None):
        await message.answer(f"Работы №{parts[1]} нет.")
        return
    await message.answer(f"🖼 Работа №{parts[1]} снова в очереди.")


@router.message(F.text.regexp(r"^/art_post"))
async def post_command(message: Message, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(
            "🖼 <b>Показать работу в «Акценте»</b>\n\n"
            "<code>/art_post 1</code>\n\n"
            "Номер работы — в <code>/art_price</code>.\n\n"
            "<i>Не каждую: канал картин — полка, «Акцент» — журнал. "
            "Слать туда всё подряд значит превратить журнал в ленту "
            "товаров, а читают его не за этим.</i>")
        return
    await message.answer(f"🖼 {await publish_to_journal(bot, int(parts[1]))}")


@router.message(F.text.regexp(r"^/art_sold"))
async def sold_command(message: Message):
    """За сколько работа ушла на самом деле.

    Отдельно от «прошу за» намеренно. «Прошу» — намерение: оно меняется
    и бывает неверным. «Продано за» — факт: он не меняется никогда, и в
    нём весь смысл. По реализованным ценам считается, сколько стоит
    следующая работа, и из них же растёт довод для покупателя. Одно
    поле на оба превращает будущую статистику в список догадок.
    """
    if not config.is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer(
            "💼 <b>Отметить продажу</b>\n\n"
            "<code>/art_sold 1 1500000</code>\n\n"
            "Работа получит отметку «продана» и записанную цену "
            "продажи. Из канала она не исчезнет: проданное — лучший "
            "довод для следующего покупателя.\n\n"
            "Отменить: <code>/art_sold 1 нет</code>")
        return

    work_id = int(parts[1])
    raw = parts[2].lower()
    if raw in ("нет", "-", "0"):
        if not await database.art_set(work_id, status="available",
                                      sold_price=None, sold_at=None):
            await message.answer(f"Работы №{work_id} нет.")
            return
        await message.answer(f"Работа №{work_id} снова в наличии.")
        return

    value = int(re.sub(r"\D", "", parts[2]) or 0)
    if not value:
        await message.answer("Нужна сумма: <code>/art_sold 1 1500000</code>")
        return

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not await database.art_set(work_id, status="sold", sold_price=value,
                                  sold_at=now):
        await message.answer(f"Работы №{work_id} нет.")
        return
    await message.answer(
        f"💼 Работа №{work_id} продана за {_money(value)}.\n\n"
        f"<i>Это первая запись в статистике реализованного. По ней и "
        f"считается цена следующих работ — и она же главный довод для "
        f"того, кто придёт после.</i>")


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
        sold_total = 0
        for work in works or []:
            if work.get("status") == "sold":
                # Проданную показываем ценой продажи, а не той, что
                # просили: просили — намерение, продали — факт.
                got = work.get("sold_price") or work.get("price")
                sold_total += int(got or 0)
                lines.append(f"✅ <code>{work['id']}</code> "
                             f"{html.escape(work['title'][:32])} — "
                             f"продана за {_money(got)}")
                continue
            lines.append(f"· <code>{work['id']}</code> "
                         f"{html.escape(work['title'][:32])} — "
                         f"{_money(work.get('price'))}")
        if not works:
            lines.append("<i>Работ пока нет. Опубликуйте пост в канале "
                         "картин — карточка заведётся сама.</i>")
        if sold_total:
            lines.append("")
            lines.append(f"<b>Реализовано: {_money(sold_total)}</b>")
        lines.append("")
        lines.append("Прошу за: <code>/art_price 7 45000</code>\n"
                     "Продана:  <code>/art_sold 7 1500000</code>\n"
                     "Снять:    <code>/art_price 7 нет</code>")
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


# =====================================================================
# ЭКРАН КАРТИН В СЛУЖЕБНОМ МЕНЮ
# =====================================================================
#
# Команд у раздела набралось восемь, и все они помнятся только тем, кто
# их писал. Кнопки ничего нового не умеют — они делают возможное
# очевидным, и этого достаточно, чтобы работа делалась.

@router.callback_query(F.data == "admin_art")
async def art_screen(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()

    works = await database.art_list()
    waiting = await database.art_waiting()
    sold = [w for w in works or [] if w.get("status") == "sold"]
    earned = sum(int(w.get("sold_price") or 0) for w in sold)
    listings = await database.listing_list()
    unpaid = [x for x in listings if x.get("status") == "waiting"]

    lines = ["🖼 <b>Картины</b>", ""]
    lines.append(f"Работ: {len(works or [])}, продано: {len(sold)}")
    if earned:
        lines.append(f"Реализовано: {_money(earned)}")
    lines.append(f"Ждут выхода в журнал: {waiting}")
    if listings:
        lines.append("")
        lines.append(f"Объявления художников: {len(listings)}"
                     + (f", ждут оплаты: {len(unpaid)}" if unpaid else ""))

    rows = [
        [InlineKeyboardButton(text="💰 Прайс и продажи",
                              callback_data="art_prices")],
        [InlineKeyboardButton(text="🗓 Очередь в журнал",
                              callback_data="art_queue_btn")],
        [InlineKeyboardButton(text="🏷 Метки для постов",
                              callback_data="art_tags_btn")],
        [InlineKeyboardButton(text="📝 Разметка поста",
                              callback_data="art_markup_btn")],
    ]
    if listings:
        rows.append([InlineKeyboardButton(text="🎨 Объявления художников",
                                          callback_data="art_listings_btn")])
    rows.append([InlineKeyboardButton(text="⇦ Назад",
                                      callback_data="admin_panel")])
    await call.message.answer("\n".join(lines),
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


def _as_command(call: CallbackQuery, text: str):
    """Нажатие как набранная команда — чтобы не копировать обработчик.

    Два пути к одному и тому же расходятся на первой же правке: один
    чинят, про второй забывают. Поэтому кнопка зовёт тот же код, а не
    повторяет его.
    """
    call.message.text = text
    call.message.from_user = call.from_user
    return call.message


@router.callback_query(F.data == "art_prices")
async def prices_button(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await price_command(_as_command(call, "/art_price"))


@router.callback_query(F.data == "art_queue_btn")
async def queue_button(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await queue_command(_as_command(call, "/art_queue"))


@router.callback_query(F.data == "art_tags_btn")
async def tags_button(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await tags_help(_as_command(call, "/art_tags"))


@router.callback_query(F.data == "art_markup_btn")
async def markup_button(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await markup_help(_as_command(call, "/art_markup"))


@router.callback_query(F.data == "art_listings_btn")
async def listings_button(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    import art_market
    await art_market.listing_board(_as_command(call, "/listings"))
