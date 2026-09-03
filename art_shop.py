# art_shop.py — галерея-магазин собственных картин.
#
# Денег бот не принимает намеренно. Живопись покупают не как футболку:
# спрашивают про размер, про раму, про доставку, торгуются. Поэтому кнопка
# ведёт не к оплате, а к разговору: заявка уходит владельцу в личку вместе с
# контактом покупателя, дальше человек с человеком.
#
# Проданные работы из галереи не исчезают, а помечаются. Пустая галерея
# выглядит как «ничего не покупают», галерея с отметками — наоборот.
import asyncio
import html
import logging

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramForbiddenError
from aiogram.dispatcher.event.bases import SkipHandler

import config
import database

router = Router()

CHANNEL_KEY = "art_channel"     # канал-справочник с работами
PAUSE = 3.2                     # Telegram пропускает около 20 постов в минуту

STATUS = {
    "available": "",
    "reserved": "⏳ забронирована",
    "sold": "🔴 продана",
}
STATUS_WORDS = {
    "свободна": "available", "доступна": "available", "available": "available",
    "бронь": "reserved", "забронирована": "reserved", "reserved": "reserved",
    "продана": "sold", "продано": "sold", "sold": "sold",
}


def _price(work) -> str:
    """Цена или честное «по запросу» — для живописи это нормальная позиция"""
    value = work.get("price")
    if not value:
        return "Цена по запросу"
    return f"{int(value):,}".replace(",", " ") + " ₽"


def _card(work) -> str:
    """Карточка работы: сначала то, что видно глазом, потом цена"""
    lines = [f"🖼 <b>{html.escape(work['title'])}</b>"]

    facts = [f for f in (work.get("technique"), work.get("size"),
                         str(work["year"]) if work.get("year") else None) if f]
    if facts:
        lines.append(html.escape(" · ".join(facts)))

    story = (work.get("story") or "").strip()
    if story:
        lines += ["", html.escape(story)]

    mark = STATUS.get(work.get("status") or "available", "")
    lines += ["", f"<b>{_price(work)}</b>" + (f"  {mark}" if mark else "")]
    return "\n".join(lines)


def _work_buttons(work, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = []
    if (work.get("status") or "available") == "available":
        rows.append([InlineKeyboardButton(
            text="✉️ Хочу эту работу", callback_data=f"artask_{work['id']}")])
    rows.append([InlineKeyboardButton(text="🖼 Другие работы",
                                      callback_data="art_my_portfolio")])
    rows.append([InlineKeyboardButton(text="🔙 Назад",
                                      callback_data="creative_paintings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# =====================================================================
# ГАЛЕРЕЯ ДЛЯ ПОСЕТИТЕЛЯ
# =====================================================================

async def show_gallery(call: CallbackQuery):
    works = await database.art_list()
    if not works:
        await call.message.answer(
            "🖼 Галерея пока пуста.\n\nРаботы появятся здесь совсем скоро.")
        return

    rows = []
    for work in works[:30]:
        mark = STATUS.get(work.get("status") or "available", "")
        label = work["title"][:32] + (f" · {mark.split()[-1]}" if mark else "")
        rows.append([InlineKeyboardButton(
            text=label, callback_data=f"artwork_{work['id']}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад",
                                      callback_data="creative_paintings")])

    free = sum(1 for w in works if (w.get("status") or "available") == "available")
    await call.message.answer(
        f"🖼 <b>Мои работы</b>\n\nВсего {len(works)}, свободны {free}. "
        f"Выберите работу — покажу целиком.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("artwork_"))
async def open_work(call: CallbackQuery):
    try:
        work_id = int(call.data.split("_", 1)[1])
    except ValueError:
        await call.answer()
        return
    work = await database.art_get(work_id)
    if not work:
        await call.answer("Работа больше не выставлена", show_alert=True)
        return

    await call.answer()
    markup = _work_buttons(work)
    if work.get("photo_file_id"):
        await call.message.answer_photo(work["photo_file_id"],
                                        caption=_card(work)[:1024],
                                        reply_markup=markup)
    else:
        await call.message.answer(_card(work), reply_markup=markup)


@router.callback_query(F.data.startswith("artask_"))
async def ask_work(call: CallbackQuery, bot: Bot):
    """Заявка: покупателю — подтверждение, владельцу — контакт и работа"""
    try:
        work_id = int(call.data.split("_", 1)[1])
    except ValueError:
        await call.answer()
        return
    work = await database.art_get(work_id)
    if not work:
        await call.answer("Работа больше не выставлена", show_alert=True)
        return

    user = call.from_user
    username = f"@{user.username}" if user.username else None
    await database.art_request(work_id, user.id, username)

    contact = username or f"<a href='tg://user?id={user.id}'>{html.escape(user.full_name)}</a>"
    text = (f"✉️ <b>Спрашивают про работу</b>\n\n"
            f"«{html.escape(work['title'])}» · {_price(work)}\n"
            f"От: {contact}")
    try:
        await bot.send_message(config.ADMIN_ID, text)
    except Exception as e:
        logging.error(f"Заявка на картину не дошла: {e}")

    await call.answer()
    await call.message.answer(
        f"✉️ Передала: «{html.escape(work['title'])}».\n\n"
        "Отвечу вам здесь же — расскажу про размер, раму и доставку.")


# =====================================================================
# АДМИНКА
# =====================================================================

class Adding(StatesGroup):
    photo = State()
    title = State()
    details = State()
    price = State()
    story = State()


SKIP = ("-", "нет", "пропустить", "skip")


@router.message(F.text.startswith("/art_add"))
async def art_add(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    await state.set_state(Adding.photo)
    await message.answer(
        "🖼 <b>Новая работа</b>\n\n"
        "Пришлите фотографию картины. Лучше без рамы и без бликов — "
        "снимок и есть витрина.\n\nОтменить — /cancel")


@router.message(Adding.photo, F.photo)
async def got_photo(message: Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await state.set_state(Adding.title)
    await message.answer("Название работы?")


@router.message(Adding.photo)
async def need_photo(message: Message, state: FSMContext):
    if (message.text or "").startswith("/cancel"):
        await state.clear()
        await message.answer("Отменила.")
        return
    await message.answer("Нужна фотография — пришлите её как фото, не файлом.")


@router.message(Adding.title, F.text)
async def got_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip()[:120])
    await state.set_state(Adding.details)
    await message.answer(
        "Техника, размер и год — одной строкой.\n"
        "Например: <code>холст, масло · 60×80 см · 2024</code>\n\n"
        "Пропустить — <code>-</code>")


@router.message(Adding.details, F.text)
async def got_details(message: Message, state: FSMContext):
    text = message.text.strip()
    if text.lower() not in SKIP:
        # Разбираем по разделителю, но не требуем порядка: год узнаём по
        # четырём цифрам, размер по знаку умножения, остальное — техника.
        year, size, technique = None, None, []
        for chunk in [c.strip() for c in text.replace("|", "·").split("·")]:
            digits = "".join(ch for ch in chunk if ch.isdigit())
            if len(chunk) <= 6 and len(digits) == 4:
                year = int(digits)
            elif any(x in chunk.lower() for x in ("х", "x", "×")) and digits:
                size = chunk
            elif chunk:
                technique.append(chunk)
        await state.update_data(year=year, size=size,
                                technique=", ".join(technique) or None)
    await state.set_state(Adding.price)
    await message.answer(
        "Цена в рублях, только число: <code>45000</code>\n\n"
        "Если цена по запросу — <code>-</code>")


@router.message(Adding.price, F.text)
async def got_price(message: Message, state: FSMContext):
    text = message.text.strip().replace(" ", "")
    price = int(text) if text.isdigit() else None
    await state.update_data(price=price)
    await state.set_state(Adding.story)
    await message.answer(
        "Пара строк о работе — что в ней, откуда она.\n"
        "Это то, что продаёт картину сильнее цены.\n\nПропустить — <code>-</code>")


@router.message(Adding.story, F.text)
async def got_story(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    story = message.text.strip()
    await state.clear()

    work_id = await database.art_add(data.get("title") or "Без названия",
                                     data.get("photo"))
    if not work_id:
        await message.answer("❌ Не сохранилось. Попробуйте ещё раз.")
        return
    await database.art_set(
        work_id, year=data.get("year"), size=data.get("size"),
        technique=data.get("technique"), price=data.get("price"),
        story=None if story.lower() in SKIP else story[:800])

    work = await database.art_get(work_id)
    await message.answer(f"✅ Работа №{work_id} в галерее.")
    if work.get("photo_file_id"):
        await message.answer_photo(work["photo_file_id"], caption=_card(work)[:1024])
    else:
        await message.answer(_card(work))


@router.message(F.text.startswith("/art_list"))
async def art_list(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    works = await database.art_list()
    if not works:
        await message.answer("Галерея пуста. Добавить: <code>/art_add</code>")
        return
    lines = ["🖼 <b>Галерея</b>", ""]
    for w in works:
        mark = STATUS.get(w.get("status") or "available", "свободна")
        lines.append(f"<code>{w['id']}</code> — {html.escape(w['title'][:40])} · "
                     f"{_price(w)} · {mark or 'свободна'}")
    lines += ["", "Статус: <code>/art_status 3 продана</code>",
              "Цена: <code>/art_price 3 45000</code>",
              "Убрать: <code>/art_del 3</code>",
              "Заявки: <code>/art_requests</code>"]
    await message.answer("\n".join(lines))


@router.message(F.text.startswith("/art_status"))
async def art_status(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer("Например: <code>/art_status 3 продана</code>\n"
                             "Слова: свободна, бронь, продана")
        return
    status = STATUS_WORDS.get(parts[2].lower())
    if not status:
        await message.answer("Не знаю такого статуса. Свободна, бронь, продана.")
        return
    ok = await database.art_set(int(parts[1]), status=status)
    await message.answer("✅ Готово" if ok else "❌ Работа не найдена")


@router.message(F.text.startswith("/art_price"))
async def art_price(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer("Например: <code>/art_price 3 45000</code>\n"
                             "Убрать цену: <code>/art_price 3 -</code>")
        return
    raw = parts[2].replace(" ", "")
    price = int(raw) if raw.isdigit() else None
    ok = await database.art_set(int(parts[1]), price=price)
    await message.answer("✅ Готово" if ok else "❌ Работа не найдена")


@router.message(F.text.startswith("/art_del"))
async def art_del(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Например: <code>/art_del 3</code>")
        return
    ok = await database.art_delete(int(parts[1]))
    await message.answer("✅ Убрала из галереи" if ok else "❌ Работа не найдена")


@router.message(F.text.startswith("/art_requests"))
async def art_requests(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    rows = await database.art_requests()
    if not rows:
        await message.answer("Заявок пока не было.")
        return
    lines = ["✉️ <b>Кто спрашивал про работы</b>", ""]
    for r in rows:
        when = r["created_at"].strftime("%d.%m %H:%M") if r["created_at"] else "—"
        who = r["username"] or f"id {r['user_id']}"
        lines.append(f"{when} · {html.escape(r['title'] or 'работа удалена')} — "
                     f"{html.escape(who)}")
    await message.answer("\n".join(lines))


# =====================================================================
# КАНАЛ-СПРАВОЧНИК
# =====================================================================
#
# Канал — полка: там лежат все работы. Бот его наполняет и правит на месте,
# поэтому смена цены или отметка «продана» не плодит вторую карточку, а
# меняет существующую.

async def _channel():
    raw = await database.get_setting(CHANNEL_KEY)
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


async def _bot_link(work_id: int):
    """Кнопка из канала в бота — на эту же работу"""
    username = await database.get_setting("bot_username")
    if not username:
        return None
    return [InlineKeyboardButton(
        text="✉️ Спросить о работе",
        url=f"https://t.me/{username.lstrip('@')}?start=art-{work_id}")]


async def _publish_one(bot: Bot, chat: int, work) -> str:
    """Выложить или обновить одну работу. Строка — для отчёта."""
    caption = _card(work)[:1024]
    rows = [r for r in (await _bot_link(work["id"]),) if r]
    markup = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

    msg_id = work.get("channel_msg_id")
    if msg_id:
        try:
            await bot.edit_message_caption(chat_id=chat, message_id=msg_id,
                                           caption=caption, reply_markup=markup)
            return f"{work['id']} обновлена"
        except Exception as e:
            # Пост мог быть удалён вручную — тогда выкладываем заново.
            logging.warning(f"Картина {work['id']}: правка не прошла ({e})")

    try:
        if work.get("photo_file_id"):
            sent = await bot.send_photo(chat, work["photo_file_id"],
                                        caption=caption, reply_markup=markup)
        else:
            sent = await bot.send_message(chat, caption, reply_markup=markup)
    except Exception as e:
        logging.error(f"Картина {work['id']} не вышла: {e}")
        return f"{work['id']} ошибка: {e}"

    await database.art_set(work["id"], channel_msg_id=sent.message_id)
    return f"{work['id']} опубликована"


@router.message(F.text.startswith("/art_channel"))
async def art_channel(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) > 1:
        value = parts[1].strip()
        if value.lower() in ("нет", "off"):
            await database.set_setting(CHANNEL_KEY, "")
            await message.answer("✅ Канал отвязан.")
            return
        try:
            int(value)
        except ValueError:
            await message.answer("Нужен номер канала: <code>/art_channel -100…</code>")
            return
        await database.set_setting(CHANNEL_KEY, value)
        await message.answer(
            f"✅ Канал картин: <code>{value}</code>\n\n"
            "Выложить работы: <code>/art_publish все</code>")
        return

    chat = await _channel()
    await message.answer(
        f"🖼 Канал картин: <code>{chat or 'не задан'}</code>\n\n"
        "Задать: <code>/art_channel -1001234567890</code>\n"
        "Номер канала бот покажет, если переслать в него <code>/id</code>.\n"
        "Отвязать: <code>/art_channel нет</code>")


@router.message(F.text.startswith("/art_publish"))
async def art_publish(message: Message, bot: Bot):
    """Выложить работы в канал: одну, все новые или все с обновлением"""
    if not config.is_admin(message.from_user.id):
        return
    chat = await _channel()
    if not chat:
        await message.answer("Сначала задайте канал: <code>/art_channel -100…</code>")
        return

    parts = message.text.split()
    arg = parts[1].lower() if len(parts) > 1 else ""
    works = await database.art_list()

    if arg.isdigit():
        works = [w for w in works if w["id"] == int(arg)]
    elif arg in ("все", "всё", "all"):
        pass
    else:
        works = [w for w in works if not w.get("channel_msg_id")]

    if not works:
        await message.answer(
            "Нечего выкладывать — все работы уже в канале.\n"
            "Обновить существующие: <code>/art_publish все</code>")
        return

    await message.answer(f"⏳ Работ к публикации: {len(works)}")
    done = []
    for work in reversed(works):        # старые сверху, новые последними
        done.append(await _publish_one(bot, chat, work))
        await asyncio.sleep(PAUSE)
    await message.answer("🖼 " + "\n".join(done[-30:]))


@router.message(F.text.regexp(r"^/start\s+art-"))
async def start_from_channel(message: Message, bot: Bot):
    """Пришли из канала по кнопке «Спросить о работе»"""
    payload = message.text.split(maxsplit=1)[1].strip()
    try:
        work_id = int(payload.split("-", 1)[1])
    except (ValueError, IndexError):
        raise SkipHandler
    work = await database.art_get(work_id)
    if work:
        markup = _work_buttons(work)
        if work.get("photo_file_id"):
            await message.answer_photo(work["photo_file_id"],
                                       caption=_card(work)[:1024],
                                       reply_markup=markup)
        else:
            await message.answer(_card(work), reply_markup=markup)
    raise SkipHandler
