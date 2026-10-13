# art_market.py — чужая работа на своей полке.
#
# Площадка не продаёт чужое. Художник размещается сам, платит один раз
# за размещение и дальше договаривается с покупателем напрямую — как на
# доске объявлений.
#
# Это не осторожность, а другая конструкция. Продавать чужое значит
# встать между двумя людьми: отвечать за подлинность, за доставку, за
# возврат, за деньги на своём счёте и за налог с чужой выручки.
# Размещение — своя услуга, оказанная один раз, и дальше площадка из
# сделки выходит.
#
# Отсюда всё остальное устройство:
#
#   Контакт в объявлении — продавца, не площадки. Иначе она снова
#   посередине, что бы ни было написано в правилах.
#
#   Согласия — обязательные и записанные. Не «он согласился», а «он
#   согласился вот с этим»: текст правок не переживает, версия
#   переживает.
#
#   Маркировка рекламы. Платное размещение чужого товара — реклама, и
#   без erid её публиковать нельзя. Бот и не публикует.
import html
import logging
import re
from datetime import datetime, timezone

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import config
import database

router = Router()

PRICE_KEY = "art_listing_price"     # сколько стоит размещение
PRICE_DEFAULT = 500

# Версия текста согласий. Меняется вместе с текстом — иначе однажды
# придётся доказывать согласие с правилами, которых в тот день ещё не
# существовало.
CONSENT_VERSION = "2026-10-12"

CONSENTS = (
    ("rules", "Правила размещения",
     "Размещение платное и разовое. Деньги — за публикацию, а не за "
     "продажу: работа может не продаться, и плата не возвращается."),
    ("rights", "Работа моя",
     "Я автор этой работы или имею право её продавать. Фотография — "
     "моя, прав третьих лиц в ней нет."),
    ("deal", "Сделка — моя",
     "Договариваюсь с покупателем я сам: цена, оплата, доставка, "
     "возврат. Площадка в сделке не участвует и за неё не отвечает."),
    ("data", "Данные",
     "Согласен, что мои имя, контакт и город будут опубликованы в "
     "объявлении и сохранены для связи со мной."),
)


class Listing(StatesGroup):
    photo = State()
    title = State()
    size = State()
    price = State()
    city = State()
    contact = State()
    consents = State()


def _money(value) -> str:
    return (f"{int(value):,}".replace(",", " ") + " ₽") if value else "—"


async def _fee() -> int:
    try:
        return int(await database.get_setting(PRICE_KEY) or PRICE_DEFAULT)
    except (TypeError, ValueError):
        return PRICE_DEFAULT


# ---------------------------------------------------------------------
# ФОРМА
# ---------------------------------------------------------------------

START = (
    "🎨 <b>Разместить работу</b>\n\n"
    "Вы продаёте сами: в объявлении будет ваш контакт, с покупателем "
    "договариваетесь напрямую. Площадка берёт плату за размещение и в "
    "сделку не вмешивается.\n\n"
    "Размещение — {fee}, разово.\n\n"
    "Шесть вопросов и согласия. Начнём с фотографии работы — "
    "пришлите её картинкой."
)


@router.callback_query(F.data == "mkt_start")
async def start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(Listing.photo)
    await call.message.answer(START.format(fee=_money(await _fee())))


@router.message(F.text.regexp(r"^/разместить|^/listing"))
async def start_command(message: Message, state: FSMContext):
    await state.set_state(Listing.photo)
    await message.answer(START.format(fee=_money(await _fee())))


@router.message(Listing.photo, F.photo)
async def got_photo(message: Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await state.set_state(Listing.title)
    await message.answer("Название работы и ваше имя как автора.\n\n"
                         "Например: <code>Тишина в полдень, Анна Петрова</code>")


@router.message(Listing.photo)
async def need_photo(message: Message):
    await message.answer("Нужна фотография работы — пришлите картинкой, "
                         "не файлом.")


@router.message(Listing.title, F.text)
async def got_title(message: Message, state: FSMContext):
    parts = [x.strip() for x in message.text.split(",", 1)]
    await state.update_data(title=parts[0][:80],
                            author=(parts[1][:60] if len(parts) > 1 else ""))
    await state.set_state(Listing.size)
    await message.answer("Размер и техника.\n\n"
                         "Например: <code>60 на 80, холст, масло</code>")


@router.message(Listing.size, F.text)
async def got_size(message: Message, state: FSMContext):
    import art_value
    width, height = art_value.parse_size(message.text)
    if not width:
        await message.answer("Не разобрала размер. Нужны сантиметры: "
                             "<code>60 на 80, холст, масло</code>")
        return
    tail = re.sub(r"^[^,]*,\s*", "", message.text).strip()
    await state.update_data(size=f"{width:g} × {height:g} см",
                            technique=tail[:60], width=width, height=height)
    await state.set_state(Listing.price)

    # Ориентир показываем до того, как человек назовёт цену: названную
    # он уже защищает, и расчёт после неё читается как спор.
    hint = art_value.explain(width, height, tail, 0)
    await message.answer(hint)
    await message.answer("Ваша цена в рублях. Одним числом.")


@router.message(Listing.price, F.text)
async def got_price(message: Message, state: FSMContext):
    digits = re.sub(r"\D", "", message.text)
    if not digits:
        await message.answer("Нужно число: <code>45000</code>")
        return
    await state.update_data(price=int(digits))
    await state.set_state(Listing.city)
    await message.answer("Город — покупателю важно, откуда везти.")


@router.message(Listing.city, F.text)
async def got_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip()[:40])
    await state.set_state(Listing.contact)
    await message.answer(
        "Как с вами связаться покупателю? Телеграм, почта или телефон.\n\n"
        "<i>Это попадёт в объявление: договариваетесь вы напрямую.</i>")


@router.message(Listing.contact, F.text)
async def got_contact(message: Message, state: FSMContext):
    await state.update_data(contact=message.text.strip()[:80], ticked=[])
    await state.set_state(Listing.consents)
    await message.answer(await _consent_text(state),
                         reply_markup=_consent_kb([]))


# ---------------------------------------------------------------------
# СОГЛАСИЯ
# ---------------------------------------------------------------------

async def _consent_text(state: FSMContext) -> str:
    data = await state.get_data()
    lines = ["📋 <b>Прежде чем публиковать</b>", ""]
    lines.append(f"<b>{html.escape(data.get('title', 'Работа'))}</b> · "
                 f"{html.escape(data.get('size', ''))} · "
                 f"{_money(data.get('price'))}")
    lines.append(f"{html.escape(data.get('city', ''))} · "
                 f"{html.escape(data.get('contact', ''))}")
    lines.append("")
    for _, name, body in CONSENTS:
        lines.append(f"<b>{name}.</b> {body}")
        lines.append("")
    lines.append("Отметьте все четыре — без этого публиковать нельзя.")
    return "\n".join(lines)


def _consent_kb(ticked) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=("✅ " if key in ticked else "☐ ") + name,
        callback_data=f"mkt_c_{key}")] for key, name, _ in CONSENTS]
    if len(ticked) == len(CONSENTS):
        rows.append([InlineKeyboardButton(text="➡️ Отправить на публикацию",
                                          callback_data="mkt_send")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("mkt_c_"), Listing.consents)
async def tick(call: CallbackQuery, state: FSMContext):
    key = call.data[len("mkt_c_"):]
    if key not in {k for k, _, _ in CONSENTS}:
        await call.answer()
        return
    data = await state.get_data()
    ticked = list(data.get("ticked") or [])
    if key in ticked:
        ticked.remove(key)
    else:
        ticked.append(key)
    await state.update_data(ticked=ticked)
    await call.answer()
    try:
        await call.message.edit_reply_markup(reply_markup=_consent_kb(ticked))
    except Exception:
        pass


@router.callback_query(F.data == "mkt_send", Listing.consents)
async def send(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    ticked = set(data.get("ticked") or [])
    if ticked != {k for k, _, _ in CONSENTS}:
        await call.answer("Отмечены не все согласия", show_alert=True)
        return

    user = call.from_user
    username = f"@{user.username}" if user.username else ""
    listing_id = await database.listing_add(user.id, username, {
        **data,
        "consent_version": CONSENT_VERSION,
        "consent_at": datetime.now(timezone.utc).replace(tzinfo=None),
    })
    await state.clear()
    if not listing_id:
        await call.answer()
        await call.message.answer("Не получилось сохранить. Попробуйте ещё раз.")
        return

    fee = await _fee()
    await call.answer()
    await call.message.answer(
        f"📋 Объявление №{listing_id} принято.\n\n"
        f"Осталось оплатить размещение — {_money(fee)}. Я напишу, как "
        f"только подтвержу оплату, и объявление выйдет в канал.\n\n"
        f"<i>Деньги за размещение, а не за продажу: работа может не "
        f"продаться, и плата не возвращается — вы это отметили.</i>")

    try:
        await bot.send_message(
            config.ADMIN_ID,
            f"🎨 <b>Новое объявление №{listing_id}</b>\n\n"
            f"{html.escape(data.get('title', ''))} · "
            f"{html.escape(data.get('size', ''))} · "
            f"{_money(data.get('price'))}\n"
            f"{html.escape(data.get('city', ''))} · "
            f"{html.escape(data.get('contact', ''))}\n"
            f"От: {username or user.id}\n\n"
            f"Оплата: <code>/listing_paid {listing_id}</code>\n"
            f"Публикация: <code>/listing_post {listing_id} erid</code>")
    except Exception as e:
        logging.error(f"Объявление №{listing_id} не дошло владелице: {e}")


# ---------------------------------------------------------------------
# ПУБЛИКАЦИЯ
# ---------------------------------------------------------------------

def render(listing: dict) -> str:
    """Текст объявления.

    Пометка «Реклама» и данные рекламодателя — не оформление, а
    требование закона к платному размещению чужого товара. Ставим их
    так, чтобы их было видно, а не прятали в конец мелким шрифтом.
    """
    lines = [f"🖼 <b>{html.escape(listing.get('title') or 'Работа')}</b>"]
    facts = [x for x in (listing.get("size"), listing.get("technique")) if x]
    if facts:
        lines.append(" · ".join(html.escape(f) for f in facts))
    if listing.get("story"):
        lines.append("")
        lines.append(html.escape(listing["story"])[:600])
    lines.append("")
    lines.append(f"<b>{_money(listing.get('price'))}</b>")
    if listing.get("city"):
        lines.append(f"📍 {html.escape(listing['city'])}")
    lines.append("")
    lines.append(f"Автор: {html.escape(listing.get('author') or '—')}")
    lines.append("")
    lines.append("<i>По вопросам приобретения обращаться к автору работы. "
                 "Канал за сопровождение сделки ответственности не несёт.</i>")
    lines.append(f"<i>Реклама. {html.escape(listing.get('author') or '')} "
                 f"erid: {html.escape(listing.get('erid') or '')}</i>")
    return "\n".join(lines)


def contact_row(listing_id: int, username: str):
    """Контакт автора — за кнопкой, а не строкой в посте.

    Строкой он работает хуже по двум причинам. Первая: написанный в
    канале контакт достаётся и тем, кто пришёл не покупать, — спам
    собирается по открытым каналам в первую очередь. Вторая важнее для
    дела: нажатие видно, а переписанный глазами телеграм — нет, и
    художник не узнает, сколько человек им заинтересовалось.

    Из этого же вырастает возможность когда-нибудь брать за контакт
    деньги. Сегодня он бесплатен, но путь уже проложен: считать
    обращения задним числом нельзя, а не считать их — значит не знать
    о площадке ничего.
    """
    if not username:
        return None
    return [InlineKeyboardButton(
        text="✉️ Написать автору",
        url=f"https://t.me/{username.lstrip('@')}?start=lead-{listing_id}")]


@router.message(F.text.regexp(r"^/start\s+lead-"))
async def give_contact(message: Message, bot: Bot):
    """Отдать контакт автора и записать обращение"""
    from aiogram.dispatcher.event.bases import SkipHandler

    raw = (message.text or "").split("lead-", 1)[1].strip()
    if not raw.isdigit():
        raise SkipHandler
    listing = await database.listing_get(int(raw))
    if not listing or listing.get("status") != "live":
        await message.answer("Это объявление больше не действует.")
        raise SkipHandler

    await database.listing_lead(listing["id"], message.from_user.id)

    await message.answer(
        f"✉️ <b>{html.escape(listing.get('title') or 'Работа')}</b>\n"
        f"{html.escape(listing.get('size') or '')} · "
        f"{_money(listing.get('price'))}\n\n"
        f"Автор: {html.escape(listing.get('author') or '—')}\n"
        f"Связаться: {html.escape(listing.get('contact') or '—')}\n\n"
        f"<i>Дальше вы договариваетесь напрямую. Канал в сделке не "
        f"участвует: ни оплату, ни доставку, ни возврат не ведёт.</i>")

    # Художнику — что им заинтересовались. Это и есть то, за что он
    # платил: не публикация сама по себе, а люди, которые дошли.
    try:
        count = await database.listing_leads(listing["id"])
        await bot.send_message(
            listing["user_id"],
            f"✉️ Вашей работой «{html.escape(listing.get('title') or '')}» "
            f"заинтересовались. Всего обращений: {count}.\n\n"
            f"<i>Контакт у человека есть — ждите сообщения.</i>")
    except Exception:
        pass
    raise SkipHandler


@router.message(F.text.regexp(r"^/listing_paid"))
async def mark_paid(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Так: <code>/listing_paid 3</code>")
        return
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not await database.listing_set(int(parts[1]), paid_at=now,
                                      status="paid"):
        await message.answer(f"Объявления №{parts[1]} нет.")
        return
    await message.answer(
        f"💰 Объявление №{parts[1]}: оплата отмечена.\n\n"
        f"Публикация: <code>/listing_post {parts[1]} erid</code>\n\n"
        f"<i>erid берётся в ОРД — без него платное объявление "
        f"публиковать нельзя.</i>")


@router.message(F.text.regexp(r"^/listing_post"))
async def post(message: Message, bot: Bot):
    """Опубликовать объявление в канал картин.

    Без erid не публикуем. Это не придирка: платное размещение чужого
    товара — реклама, маркировка обязательна, и штраф придёт площадке,
    а не художнику.
    """
    if not config.is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer(
            "Так: <code>/listing_post 3 2Vfnxw...</code>\n\n"
            "Второе — это <b>erid</b>, токен из ОРД. Платное размещение "
            "чужого товара — реклама: без маркировки публиковать нельзя, "
            "и отвечает за это площадка, а не художник.")
        return

    listing = await database.listing_get(int(parts[1]))
    if not listing:
        await message.answer(f"Объявления №{parts[1]} нет.")
        return
    if not listing.get("paid_at"):
        await message.answer("Размещение не оплачено. Сначала "
                             f"<code>/listing_paid {parts[1]}</code>")
        return

    listing["erid"] = parts[2]
    chat = await database.get_setting("art_channel")
    if not chat:
        await message.answer("Канал картин не задан: "
                             "<code>/art_channel -100…</code>")
        return

    username = await database.get_setting("bot_username")
    row = contact_row(listing["id"], username or "")
    try:
        sent = await bot.send_photo(
            int(chat), listing["photo_file_id"],
            caption=render(listing)[:1024],
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[row])
            if row else None)
    except Exception as e:
        logging.error(f"Объявление №{listing['id']} не вышло: {e}")
        await message.answer(f"Не вышло: {html.escape(str(e))}")
        return

    await database.listing_set(listing["id"], erid=parts[2], status="live",
                               channel_msg_id=sent.message_id)
    await message.answer(f"✅ Объявление №{listing['id']} опубликовано.")

    try:
        await bot.send_message(
            listing["user_id"],
            "🖼 Ваше объявление вышло в канале. Дальше покупатели будут "
            "писать вам напрямую — по контакту, который вы оставили.")
    except Exception:
        pass


@router.message(F.text.regexp(r"^/listings"))
async def listing_board(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    rows = await database.listing_list()
    if not rows:
        await message.answer(
            "🎨 <b>Объявления</b>\n\n<i>Пока ни одного.</i>\n\n"
            f"Цена размещения: {_money(await _fee())} "
            f"(<code>/listing_price 500</code>)")
        return
    marks = {"waiting": "⏳ ждёт оплаты", "paid": "💰 оплачено",
             "live": "✅ в канале"}
    lines = ["🎨 <b>Объявления</b>", ""]
    for row in rows:
        leads = await database.listing_leads(row["id"])
        # Обращения — единственное, что площадка действительно даёт
        # художнику. Доска без них показывает работу, а не результат.
        tail = f" · обращений {leads}" if leads else ""
        lines.append(f"<code>{row['id']}</code> "
                     f"{html.escape((row.get('title') or '')[:26])} — "
                     f"{marks.get(row.get('status'), row.get('status'))}{tail}")
    lines.append("")
    lines.append(f"Цена размещения: {_money(await _fee())}")
    total = await database.listing_leads()
    if total:
        lines.append(f"Всего обращений: {total}")
    await message.answer("\n".join(lines))


@router.message(F.text.regexp(r"^/listing_price"))
async def set_fee(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(f"Сейчас {_money(await _fee())}. "
                             f"Изменить: <code>/listing_price 500</code>")
        return
    await database.set_setting(PRICE_KEY, parts[1])
    await message.answer(f"💰 Размещение теперь {_money(int(parts[1]))}.")
