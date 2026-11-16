# konkurs.py — конкурс «кто привёл больше подписчиков».
#
# Добавить человека в канал за него нельзя: Bot API такого не умеет
# вовсе, а через обычный аккаунт это нарушение правил Telegram, за
# которое платят аккаунтом и жалобами. Да и приведённый так человек не
# подписчик: он выходит в первый день.
#
# Поэтому считаем тех, кто пришёл сам. У каждого участника своя
# пригласительная ссылка, и Telegram в событии о вступлении сообщает,
# по какой именно ссылке человек вошёл. Это и есть весь счёт: ни кодов,
# ни скриншотов, ни «напишите, кого вы привели».
#
# Что видно людям. В таблице — значок и имя, и только они. Ни @ника, ни
# ссылки на профиль, ни того, кто кого привёл: человек соглашался
# участвовать, а не показывать свою переписку. Гость в таблицах не
# появляется никогда — он вообще ни на что не подписывался, его номер
# хранится только ради вычитания балла при выходе и стирается после
# призов.
#
# Накрутка отваливается сама: вышел из канала — балл снят. Себя по
# своей же ссылке привести нельзя.
import html
import logging

from aiogram import Router, F, Bot
from aiogram.types import (CallbackQuery, Message, ChatMemberUpdated,
                           InlineKeyboardMarkup, InlineKeyboardButton,
                           ReplyKeyboardMarkup, KeyboardButton,
                           ReplyKeyboardRemove)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import (ChatMemberUpdatedFilter, JOIN_TRANSITION,
                             LEAVE_TRANSITION)

import config
import database

router = Router()

ON_KEY = "konkurs_on"            # идёт ли конкурс
TEXT_KEY = "konkurs_text"        # объявление в канал
BOARD_KEY = "konkurs_board_msg"  # пост с таблицей, правим его же
TOP_SHOWN = 10                   # сколько строк видно в канале

# Значок вместо аватарки: таблица живёт текстом, и картинку в неё не
# вставить. Значок выдаётся по номеру — один и тот же у человека всегда.
ICONS = "🎾🦊🐬🦉🌿🔥🎈🍋🧩🐙🌙🪁🐝🍀🎺🦜"

DEFAULT_TEXT = (
    "🏆 <b>Конкурс: зовите своих</b>\n\n"
    "У каждого участника своя пригласительная ссылка. Кто приведёт "
    "больше людей за три дня — забирает приз.\n\n"
    "Считает бот, вручную ничего отправлять не надо."
)

JOIN_HEAD = "🏆 <b>Вы в конкурсе</b>"

RULES = (
    "Как это работает:\n"
    "• ссылка ниже — ваша личная, она считает пришедших;\n"
    "• отправляйте её кому хотите: в чат, историю, лично;\n"
    "• балл снимается, если человек выйдет из канала;\n"
    "• себя по своей ссылке привести нельзя.\n\n"
    "В таблице видно значок и имя — больше ничего: ни ника, ни "
    "профиля, ни того, кто кого привёл."
)


class Prize(StatesGroup):
    waiting_text = State()


def icon_for(user_id: int) -> str:
    return ICONS[user_id % len(ICONS)]


def _name(user) -> str:
    """Имя для таблицы: то же, что видно в канале, и ничего сверх."""
    return ((user.first_name or "").strip() or "Участник")[:24]


async def running() -> bool:
    return (await database.get_setting(ON_KEY) or "") == "1"


async def _channel() -> int:
    import digest
    chat, _ = await digest._target()
    return chat


async def _thread():
    import digest
    _, thread = await digest._target()
    return thread


# ───────────────────────── участник ─────────────────────────

def _link_kb(link: str) -> InlineKeyboardMarkup:
    share = ("https://t.me/share/url?url=" + link +
             "&text=" + "Заходите, тут интересно")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Отправить друзьям", url=share)],
        [InlineKeyboardButton(text="📊 Моё место", callback_data="konk_me")],
    ])


async def _make_link(bot: Bot, user_id: int) -> str:
    """Личная пригласительная ссылка. Пусто — если не получилось."""
    chat = await _channel()
    if not chat:
        return ""
    try:
        made = await bot.create_chat_invite_link(
            chat_id=chat, name=f"k{user_id}")
        return made.invite_link
    except Exception as e:
        logging.error(f"Конкурс: ссылка для {user_id} не создалась — {e}")
        return ""


async def _enter(bot: Bot, user, answer) -> None:
    """Записать в конкурс и показать ссылку. answer — куда отвечать."""
    if not await running():
        await answer("Конкурс сейчас не идёт. Как начнётся — объявлю в канале.")
        return

    import growth
    if not await growth.is_subscribed(bot, user.id):
        url = await database.get_setting(growth.LINK_KEY)
        rows = [[InlineKeyboardButton(text="📣 Подписаться", url=url)]] if url else []
        rows.append([InlineKeyboardButton(text="✅ Я подписался",
                                          callback_data="konk_in")])
        await answer("Сначала подпишитесь на канал — конкурс для своих.",
                     InlineKeyboardMarkup(inline_keyboard=rows))
        return

    row = await database.konkurs_member(user.id)
    if row and row.get("blocked"):
        await answer("Вы сняты с конкурса.")
        return

    link = (row or {}).get("link") or await _make_link(bot, user.id)
    if not link:
        await answer("Ссылка не создалась — я уже знаю, разберусь. "
                     "Попробуйте через час.")
        return

    await database.konkurs_join(user.id, _name(user), icon_for(user.id),
                                link, f"k{user.id}")
    await answer(f"{JOIN_HEAD}\n\n{RULES}\n\n{link}", _link_kb(link))


@router.message(F.text.regexp(r"^/start\s+konkurs\s*$"))
async def start_konkurs(message: Message, state: FSMContext, bot: Bot):
    """Переход по кнопке из канала. Выше общего /start по порядку роутеров."""
    await state.clear()

    async def answer(text, kb=None):
        await message.answer(text, reply_markup=kb,
                             disable_web_page_preview=True)

    await _enter(bot, message.from_user, answer)


@router.message(F.text.regexp(r"^/(конкурс|konkurs)\b"))
async def konkurs_command(message: Message, bot: Bot):
    async def answer(text, kb=None):
        await message.answer(text, reply_markup=kb,
                             disable_web_page_preview=True)

    await _enter(bot, message.from_user, answer)


@router.callback_query(F.data == "konk_in")
async def join_button(call: CallbackQuery, bot: Bot):
    await call.answer()

    async def answer(text, kb=None):
        await call.message.answer(text, reply_markup=kb,
                                  disable_web_page_preview=True)

    await _enter(bot, call.from_user, answer)


@router.callback_query(F.data == "konk_me")
async def my_place(call: CallbackQuery):
    await call.answer()
    table = await database.konkurs_table()
    mine, place = None, 0
    for i, row in enumerate(table, 1):
        if row["user_id"] == call.from_user.id:
            mine, place = row, i
            break
    if not mine:
        await call.message.answer("Вас ещё нет в конкурсе: /конкурс")
        return
    score = int(mine["score"])
    ahead = ""
    if place > 1:
        need = int(table[place - 2]["score"]) - score + 1
        ahead = f"\nДо места выше: <b>{need}</b>"
    await call.message.answer(
        f"📊 <b>Ваше место: {place}</b>\nПриведено: <b>{score}</b>{ahead}\n\n"
        + await board_text())


# ───────────────────────── таблица ─────────────────────────

async def board_text(limit: int = TOP_SHOWN) -> str:
    """Таблица для канала и для личного сообщения — одна и та же."""
    rows = [r for r in await database.konkurs_table() if not r.get("blocked")]
    lines = ["🏆 <b>Кто сколько привёл</b>", ""]
    if not rows:
        lines.append("<i>пока никого — ссылку можно взять в боте</i>")
        return "\n".join(lines)

    places = ["🥇", "🥈", "🥉"]
    for i, row in enumerate(rows[:limit]):
        mark = places[i] if i < 3 else f"{i + 1}."
        crown = " 🏅" if row.get("winner") else ""
        lines.append(f"{mark} {row.get('icon') or '•'} "
                     f"{html.escape(row.get('name') or 'Участник')} — "
                     f"<b>{int(row['score'])}</b>{crown}")
    if len(rows) > limit:
        lines.append(f"\n<i>и ещё {len(rows) - limit} участников</i>")
    return "\n".join(lines)


async def publish_board(bot: Bot) -> str:
    """Таблица в канале: правим свой пост, а не выкладываем новый"""
    chat = await _channel()
    if not chat:
        return "канал не задан"
    text = await board_text()
    saved = await database.get_setting(BOARD_KEY)
    if saved:
        try:
            await bot.edit_message_text(chat_id=chat, message_id=int(saved),
                                        text=text,
                                        disable_web_page_preview=True)
            return "таблица обновлена"
        except Exception as e:
            if "not modified" in str(e).lower():
                return "таблица и так верная"
            logging.warning(f"Конкурс: таблица не правится — {e}")
    try:
        sent = await bot.send_message(chat, text,
                                      message_thread_id=await _thread(),
                                      disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"Конкурс: таблица не вышла — {e}")
        return f"ошибка: {e}"
    await database.set_setting(BOARD_KEY, str(sent.message_id))
    return "таблица опубликована"


async def publish_call(bot: Bot) -> str:
    """Объявление конкурса с кнопкой в бота"""
    chat = await _channel()
    if not chat:
        return "канал не задан"
    me = await bot.get_me()
    text = await database.get_setting(TEXT_KEY) or DEFAULT_TEXT
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="🏆 Участвовать",
        url=f"https://t.me/{me.username}?start=konkurs")]])
    try:
        await bot.send_message(chat, text, reply_markup=kb,
                               message_thread_id=await _thread(),
                               disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"Конкурс: объявление не вышло — {e}")
        return f"ошибка: {e}"
    return "объявление вышло"


# ───────────────────── счёт по вступлениям ─────────────────────

@router.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def guest_joined(event: ChatMemberUpdated, bot: Bot):
    """Кто-то вошёл в канал. Считаем, если по чьей-то конкурсной ссылке."""
    chat = await _channel()
    if not chat or event.chat.id != chat or not await running():
        return
    link = event.invite_link
    name = getattr(link, "name", "") or ""
    if not name.startswith("k"):
        return
    host = await database.konkurs_by_link(name)
    if not host or host.get("blocked"):
        return
    guest = event.new_chat_member.user
    if guest.is_bot or not await database.konkurs_guest_join(guest.id,
                                                             host["user_id"]):
        return
    table = await database.konkurs_table()
    score = next((int(r["score"]) for r in table
                  if r["user_id"] == host["user_id"]), 0)
    try:
        await bot.send_message(
            host["user_id"],
            f"➕ По вашей ссылке пришёл человек. Теперь у вас: <b>{score}</b>")
    except Exception as e:
        logging.info(f"Конкурс: счёт не ушёл {host['user_id']} — {e}")


@router.chat_member(ChatMemberUpdatedFilter(LEAVE_TRANSITION))
async def guest_left(event: ChatMemberUpdated):
    """Вышел из канала — балл снимается у того, кто его привёл."""
    chat = await _channel()
    if not chat or event.chat.id != chat:
        return
    host = await database.konkurs_guest_left(event.new_chat_member.user.id)
    if host:
        logging.info(f"Конкурс: у {host} балл снят — гость вышел")


# ───────────────────── телефон победителя ─────────────────────

PHONE_ASK = ("🏅 <b>Вы выиграли</b>\n\nЧтобы договориться о призе, нужен "
             "телефон. Кнопка ниже отправит его мне — больше он никуда "
             "не пойдёт и в таблице не появится.\n\n"
             "Не хотите — просто напишите мне сюда словами.")


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📞 Отправить телефон",
                                  request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True)


@router.message(F.contact)
async def took_phone(message: Message):
    """Телефон берём только тот, что человек отдал сам этой кнопкой."""
    contact = message.contact
    if not contact or contact.user_id != message.from_user.id:
        await message.answer("Это чужой контакт — его я не возьму.",
                             reply_markup=ReplyKeyboardRemove())
        return
    if not await database.konkurs_member(message.from_user.id):
        # Контакт прислал не участник конкурса — пусть его разберёт
        # кто-нибудь другой, а не проглотит этот обработчик.
        from aiogram.dispatcher.event.bases import SkipHandler
        raise SkipHandler
    await database.konkurs_set_phone(message.from_user.id, contact.phone_number)
    await message.answer("Спасибо, записала. Свяжусь по призу.",
                         reply_markup=ReplyKeyboardRemove())
    if config.ADMIN_ID:
        try:
            await message.bot.send_message(
                config.ADMIN_ID,
                f"📞 Победитель прислал телефон: "
                f"{html.escape(contact.phone_number)} — "
                f"{html.escape(_name(message.from_user))}")
        except Exception:
            pass


# ───────────────────────── кабинет ─────────────────────────

async def _allowed(call: CallbackQuery) -> bool:
    if config.is_admin(call.from_user.id):
        return True
    await call.answer()
    return False


def _rows(pairs) -> list:
    return [[InlineKeyboardButton(text=t, callback_data=d)] for t, d in pairs]


async def home_text() -> str:
    people, guests = await database.konkurs_counts()
    state = "идёт" if await running() else "остановлен"
    return (f"🏆 <b>Конкурс</b>\n\nСостояние: <b>{state}</b>\n"
            f"Участников: <b>{people}</b>\nПриведено сейчас: <b>{guests}</b>")


async def home_kb() -> InlineKeyboardMarkup:
    on = await running()
    rows = _rows([
        ("⏸ Остановить" if on else "▶️ Начать конкурс", "konk_toggle"),
        ("📊 Таблица целиком", "konk_table"),
        ("📣 Объявление в канал", "konk_call"),
        ("🔄 Обновить таблицу в канале", "konk_board"),
        ("✍️ Текст объявления", "konk_text"),
        ("🧹 Стереть данные гостей", "konk_wipe"),
    ])
    rows.append([InlineKeyboardButton(text="⇦ Назад", callback_data="own_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text.regexp(r"^/(конкурс_кабинет|konkurs_admin)\b"))
async def cabinet_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    await message.answer(await home_text(), reply_markup=await home_kb())


@router.callback_query(F.data == "konk_home")
async def cabinet(call: CallbackQuery):
    if not await _allowed(call):
        return
    await call.answer()
    await call.message.answer(await home_text(), reply_markup=await home_kb())


@router.callback_query(F.data == "konk_toggle")
async def toggle(call: CallbackQuery):
    if not await _allowed(call):
        return
    now = not await running()
    await database.set_setting(ON_KEY, "1" if now else "0")
    await call.answer("Запущен" if now else "Остановлен")
    await call.message.answer(
        "▶️ Конкурс идёт. Объявление в канал — кнопкой ниже."
        if now else
        "⏸ Конкурс остановлен. Счёт сохранён, новые ссылки не выдаются.",
        reply_markup=await home_kb())


@router.callback_query(F.data == "konk_table")
async def full_table(call: CallbackQuery):
    """Таблица с управлением. Здесь цифры и кнопки, в канале — только имена."""
    if not await _allowed(call):
        return
    await call.answer()
    rows = await database.konkurs_table()
    if not rows:
        await call.message.answer("Пока никого.", reply_markup=await home_kb())
        return
    lines = ["📊 <b>Все участники</b>", ""]
    buttons = []
    for i, row in enumerate(rows, 1):
        mark = "🚫" if row.get("blocked") else ("🏅" if row.get("winner") else "")
        lines.append(f"{i}. {row.get('icon') or '•'} "
                     f"{html.escape(row.get('name') or '')} — "
                     f"<b>{int(row['score'])}</b> {mark}")
        buttons.append((f"{row.get('icon') or '•'} "
                        f"{(row.get('name') or '')[:18]} · "
                        f"{int(row['score'])}", f"konk_one_{row['user_id']}"))
    kb = _rows(buttons[:20])
    kb.append([InlineKeyboardButton(text="⇦ Назад", callback_data="konk_home")])
    await call.message.answer("\n".join(lines),
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data.startswith("konk_one_"))
async def one_member(call: CallbackQuery):
    if not await _allowed(call):
        return
    await call.answer()
    uid = int(call.data.rsplit("_", 1)[1])
    row = await database.konkurs_member(uid)
    if not row:
        await call.message.answer("Участника нет.", reply_markup=await home_kb())
        return
    lines = [f"{row.get('icon') or '•'} <b>{html.escape(row.get('name') or '')}</b>"]
    if row.get("phone"):
        lines.append(f"Телефон: <code>{html.escape(row['phone'])}</code>")
    if row.get("blocked"):
        lines.append("<i>снят с конкурса</i>")
    if row.get("winner"):
        lines.append("<i>отмечен победителем</i>")
    kb = _rows([
        ("🏅 Снять отметку победителя" if row.get("winner")
         else "🏅 Отметить победителем", f"konk_win_{uid}"),
        ("✅ Вернуть в конкурс" if row.get("blocked")
         else "🚫 Снять с конкурса", f"konk_block_{uid}"),
        ("📞 Попросить телефон", f"konk_phone_{uid}"),
    ])
    kb.append([InlineKeyboardButton(text="⇦ К таблице",
                                    callback_data="konk_table")])
    await call.message.answer("\n".join(lines),
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data.startswith("konk_win_"))
async def mark_winner(call: CallbackQuery):
    if not await _allowed(call):
        return
    uid = int(call.data.rsplit("_", 1)[1])
    row = await database.konkurs_member(uid) or {}
    await database.konkurs_flag(uid, "winner", not row.get("winner"))
    await call.answer("Отмечено")
    await call.message.answer(
        f"🏅 {html.escape(row.get('name') or '')} — "
        + ("больше не победитель." if row.get("winner") else "победитель."),
        reply_markup=await home_kb())


@router.callback_query(F.data.startswith("konk_block_"))
async def block_member(call: CallbackQuery):
    if not await _allowed(call):
        return
    uid = int(call.data.rsplit("_", 1)[1])
    row = await database.konkurs_member(uid) or {}
    await database.konkurs_flag(uid, "blocked", not row.get("blocked"))
    await call.answer("Готово")
    await call.message.answer(
        f"{html.escape(row.get('name') or '')} — "
        + ("снова в конкурсе." if row.get("blocked") else "снят с конкурса."),
        reply_markup=await home_kb())


@router.callback_query(F.data.startswith("konk_phone_"))
async def ask_phone(call: CallbackQuery, bot: Bot):
    """Просьба о телефоне уходит победителю. Кнопка — у него, не у нас."""
    if not await _allowed(call):
        return
    uid = int(call.data.rsplit("_", 1)[1])
    try:
        await bot.send_message(uid, PHONE_ASK, reply_markup=phone_kb())
        await call.answer("Спросила")
    except Exception as e:
        await call.answer()
        await call.message.answer(f"Не ушло: {html.escape(str(e))}")


@router.callback_query(F.data == "konk_call")
async def send_call(call: CallbackQuery, bot: Bot):
    if not await _allowed(call):
        return
    await call.answer("Публикую…")
    await call.message.answer(f"🏆 {html.escape(await publish_call(bot))}",
                              reply_markup=await home_kb())


@router.callback_query(F.data == "konk_board")
async def send_board(call: CallbackQuery, bot: Bot):
    if not await _allowed(call):
        return
    await call.answer("Обновляю…")
    await call.message.answer(f"🏆 {html.escape(await publish_board(bot))}",
                              reply_markup=await home_kb())


@router.callback_query(F.data == "konk_text")
async def edit_text(call: CallbackQuery, state: FSMContext):
    if not await _allowed(call):
        return
    await call.answer()
    await state.set_state(Prize.waiting_text)
    current = await database.get_setting(TEXT_KEY) or DEFAULT_TEXT
    await call.message.answer(
        "✍️ Пришлите текст объявления — он заменит нынешний.\n\n"
        "Сейчас такой:\n\n" + current)


@router.message(Prize.waiting_text)
async def save_text(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    await state.clear()
    await database.set_setting(TEXT_KEY,
                               (message.html_text or message.text or "").strip())
    await message.answer("✅ Текст сохранён.", reply_markup=await home_kb())


@router.callback_query(F.data == "konk_wipe")
async def wipe_ask(call: CallbackQuery):
    if not await _allowed(call):
        return
    await call.answer()
    await call.message.answer(
        "🧹 Стереть номера приглашённых?\n\n"
        "Счёт обнулится у всех: он и считается по этим записям. "
        "Делать это стоит после призов — тогда хранить чужие номера "
        "больше незачем.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧹 Да, стереть",
                                  callback_data="konk_wipe_yes")],
            [InlineKeyboardButton(text="⇦ Нет", callback_data="konk_home")]]))


@router.callback_query(F.data == "konk_wipe_yes")
async def wipe_do(call: CallbackQuery):
    if not await _allowed(call):
        return
    await call.answer("Чищу…")
    gone = await database.konkurs_forget_guests()
    await call.message.answer(f"🧹 Стёрто записей: <b>{gone}</b>.",
                              reply_markup=await home_kb())
