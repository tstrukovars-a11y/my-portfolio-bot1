# admin.py — служебный раздел владельца бота: шпаргалка по хэштегам и командам,
# управление паролями закрытых разделов.
#
# Всё здесь видно только пользователю с ORGANIZER_TELEGRAM_ID. Кнопка в главном
# меню другим просто не рисуется, а каждый обработчик проверяет права заново —
# кнопку можно подделать, callback приходит от кого угодно.
from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import asyncio
import html

import config
import database

router = Router()

# Пароли: ключ в базе, подпись, значение по умолчанию из окружения
PASSWORDS = {
    "vpn_password": ("🔌 Premium VPN", lambda: config.VPN_PASSWORD),
    "profiles_password": ("💼 Профили HH & LinkedIn", lambda: config.PROFILES_PASSWORD),
    "golf_password": ("⛳ Гольф-канал", lambda: config.GOLF_PASSWORD),
}


async def current_password(key: str) -> str:
    """Пароль раздела: заданный из бота либо исходный из окружения"""
    label_default = PASSWORDS[key][1]()
    return await database.get_setting(key, label_default) or label_default


class PasswordState(StatesGroup):
    waiting_new = State()


CHEATSHEET = (
    "🔖 <b>Шпаргалка</b>\n\n"
    "<b>Хэштеги в каналах</b>\n"
    "Пост подхватывается автоматически, если бот админ канала.\n\n"
    "🍳 <i>Кулинария</i>\n"
    "<code>#видеорецепты</code> — видеорецепты\n"
    "<code>#рецепты</code> — рецепты\n"
    "<code>#полезное</code> — полезное\n\n"
    "📚 <i>Библиотека</i>\n"
    "<code>#бизнес</code> — бизнес и лидерство\n"
    "<code>#кругозор</code> — кругозор и наука\n"
    "<code>#инструменты</code> — полезный инструментарий\n\n"
    "🧬 <i>Генетика</i> — хэштег не нужен, берётся всё из своего канала\n"
    "🧩 <i>Головоломки</i> — берутся все quiz-опросы своего канала\n\n"
    "<b>Импорт пересылкой</b>\n"
    "<code>/recipes</code> … <code>/recipes_done</code> — рецепты\n"
    "<code>/shop</code> … <code>/shop_done</code> — товары Pro-Shop\n"
    "<code>/genetics</code> … <code>/genetics_done</code> — материалы по генетике\n"
    "<code>/puzzles</code> … <code>/puzzles_done</code> — задачи\n\n"
    "<b>Правка</b>\n"
    "<code>/genetics_edit 4</code> — переименовать или дописать главу\n"
    "<code>/genetics_retitle</code> — пересчитать все заголовки\n\n"
    "<b>Служебное</b>\n"
    "<code>/admin</code> — это меню\n"
    "<code>/db</code> — состояние базы, <code>/db заново</code> — переподключиться\n"
    "<code>/доход</code> — заработок с партнёрских ссылок, <code>/доход литрес 1250</code> — вписать\n"
    "<code>/clicks</code> — переходы по кнопкам магазинов\n"
    "<code>/kab</code> — кабинеты партнёрских программ\n\n"
    "<i>Видно только вам.</i>"
)


# Что делать при типичных отказах базы. Текст ошибки понятен тому, кто
# писал драйвер; владельцу нужен следующий шаг, а не диагноз на латыни.
DB_HINTS = (
    ("closed in the middle",
     "Соединение обрывается сразу после установки. Так ведёт себя "
     "приостановленная или истёкшая база на Render — реже упёршаяся в "
     "предел подключений.\n\n"
     "<b>Что смотреть:</b> Render → ваша база Postgres → статус. "
     "Available — живая; Suspended или Expired — работать не будет, "
     "нужна новая база и новый адрес в переменной DATABASE_URL."),
    ("too many clients",
     "Кончились свободные подключения к базе. Обычно это соседние боты "
     "на той же бесплатной базе. Помогает перезапуск сервиса, а по-"
     "хорошему — своя база."),
    ("password authentication failed",
     "Адрес живой, но пароль не подошёл: базу пересоздавали, а "
     "DATABASE_URL остался прежним. Скопируйте свежий адрес из Render "
     "целиком."),
    ("does not exist",
     "Базы с таким именем нет — вероятно, её удалили. Нужна новая и "
     "новый адрес."),
    ("name or service not known",
     "Хост не находится. Адрес устарел — возьмите новый из Render."),
    ("timeout",
     "База не отвечает вовремя. Если статус в Render — Available, "
     "попробуйте перезапустить сервис бота."),
)


def db_verdict(attempts) -> str:
    """Человеческое объяснение по тексту ошибок, если оно есть"""
    joined = " ".join(f"{how} {why}" for how, why in attempts).lower()
    for mark, text in DB_HINTS:
        if mark in joined:
            return f"💡 {text}"
    return ""


async def db_report() -> str:
    """Состояние базы одним экраном — с ответом «что делать», а не только
    «что случилось»."""
    state = await database.health()
    lines = ["🗄 <b>База данных</b>", ""]
    lines.append(f"Адрес: <code>{html.escape(database.describe_db_target())}</code>")
    lines.append(f"Связь: {database.POOL_MODE['how']}")

    if state["ok"]:
        lines.append("✅ Отвечает.")
        missing = [n for n, there in state["tables"].items() if not there]
        lines.append("⚠️ Нет таблиц: " + ", ".join(missing) if missing
                     else "Таблицы на месте.")
        if state.get("now"):
            lines.append(f"Время базы: <code>{state['now'].strftime('%d.%m %H:%M')}</code>")
    else:
        lines.append("❌ Не отвечает.")
        for how, why in state.get("attempts") or []:
            lines.append(f"• {how}: <code>{html.escape(why)}</code>")
        if not state.get("attempts"):
            lines.append(f"<code>{html.escape(state['error'])}</code>")
        verdict = db_verdict(state.get("attempts") or [])
        if verdict:
            lines += ["", verdict]

    if database.LAST_ERROR["what"]:
        when = database.LAST_ERROR["when"]
        lines += ["", "Последняя ошибка"
                  + (f" ({when.strftime('%d.%m %H:%M')} UTC)" if when else "")
                  + f":\n<code>{html.escape(database.LAST_ERROR['what'])}</code>"]
    return "\n".join(lines)


@router.message(F.text.startswith("/db"))
async def db_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    # /db заново — пересобрать подключение, не дожидаясь передеплоя. База
    # могла ожить (оплатили тариф, перезапустили), а бот держит в руках
    # старый мёртвый пул и об этом не знает.
    if len(parts) > 1 and parts[1].lower() in ("заново", "reconnect", "reset"):
        await database.reset_pool()
        await message.answer("Пересобираю подключение…\n\n" + await db_report())
        return
    await message.answer(await db_report())


@router.callback_query(F.data == "admin_db")
async def db_screen(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await call.message.answer(await db_report())


def _admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Доход", callback_data="admin_income")],
        [InlineKeyboardButton(text="🗄 База данных", callback_data="admin_db")],
        [InlineKeyboardButton(text="🔖 Шпаргалка", callback_data="admin_cheatsheet")],
        [InlineKeyboardButton(text="🔑 Пароли разделов", callback_data="admin_passwords")],
        [InlineKeyboardButton(text="👥 Посетители", callback_data="admin_visitors_0")],
        [InlineKeyboardButton(text="⇦ В главное меню", callback_data="go_home")],
    ])


@router.message(F.text == "/admin")
async def admin_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    await message.answer("🛠 <b>Служебное меню</b>", reply_markup=_admin_menu())


@router.callback_query(F.data == "admin_panel")
async def open_admin(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await call.message.answer("🛠 <b>Служебное меню</b>", reply_markup=_admin_menu())


@router.callback_query(F.data == "admin_cheatsheet")
async def show_cheatsheet(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await call.message.answer(
        CHEATSHEET,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="⇦ Назад", callback_data="admin_panel")]])
    )


@router.callback_query(F.data == "admin_passwords")
async def show_passwords(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()

    lines = ["🔑 <b>Пароли закрытых разделов</b>\n"]
    rows = []
    for key, (label, _) in PASSWORDS.items():
        value = await current_password(key)
        lines.append(f"{label}\n<code>{value}</code>\n")
        rows.append([
            InlineKeyboardButton(text=f"✏️ {label}", callback_data=f"pwedit_{key}"),
            InlineKeyboardButton(text="📤", callback_data=f"pwsend_{key}"),
        ])

    lines.append("✏️ — сменить, 📤 — прислать отдельным сообщением, "
                 "чтобы удобно переслать.")
    rows.append([InlineKeyboardButton(text="⇦ Назад", callback_data="admin_panel")])

    await call.message.answer("\n".join(lines),
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("pwsend_"))
async def send_password(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()

    key = call.data.removeprefix("pwsend_")
    if key not in PASSWORDS:
        return
    label = PASSWORDS[key][0]
    value = await current_password(key)
    # Отдельным сообщением и без разметки — так его удобно переслать целиком
    await call.message.answer(f"{label}\nПароль: {value}", parse_mode=None)


@router.callback_query(F.data.startswith("pwedit_"))
async def ask_new_password(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()

    key = call.data.removeprefix("pwedit_")
    if key not in PASSWORDS:
        return

    await state.set_state(PasswordState.waiting_new)
    await state.update_data(password_key=key)
    await call.message.answer(
        f"Пришлите новый пароль для раздела «{PASSWORDS[key][0]}».\n\n"
        f"Сравнение идёт без учёта регистра и лишних пробелов.",
        parse_mode=None,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="⛔ Отмена", callback_data="admin_passwords")]])
    )


@router.message(PasswordState.waiting_new, F.text, ~F.text.startswith("/"))
async def save_new_password(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return

    data = await state.get_data()
    key = data.get("password_key")
    await state.clear()

    new_value = message.text.strip()
    if len(new_value) < 4:
        await message.answer("Слишком короткий пароль — нужно хотя бы 4 знака.")
        return

    if await database.set_setting(key, new_value):
        await message.answer(
            f"✅ Пароль раздела «{PASSWORDS[key][0]}» изменён на:\n{new_value}",
            parse_mode=None, reply_markup=_admin_menu()
        )
    else:
        await message.answer("⚠️ Не удалось сохранить — ошибка базы.")


# =====================================================================
# 👥 ПОСЕТИТЕЛИ
# =====================================================================
# Telegram присылает имя, ник и язык в каждом апдейте — отдельного согласия
# на это нет, поэтому список видит только владелец, а любую запись можно
# удалить целиком, если человек попросит.

VISITORS_PAGE = 10
# За одно нажатие — ограниченная пачка: getChat лимитирован по частоте,
# а владелец не должен ждать ответа полминуты.
RESOLVE_BATCH = 40


def _ago(moment) -> str:
    """«3 ч назад» читается быстрее, чем дата с секундами"""
    if not moment:
        return "—"
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc) if moment.tzinfo else datetime.now()
    minutes = int((now - moment).total_seconds() // 60)
    if minutes < 1:
        return "только что"
    if minutes < 60:
        return f"{minutes} мин назад"
    if minutes < 60 * 24:
        return f"{minutes // 60} ч назад"
    return f"{minutes // 1440} дн назад"


@router.callback_query(F.data.startswith("admin_visitors_"))
async def show_visitors(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()

    page = int(call.data.removeprefix("admin_visitors_") or 0)
    total = await database.count_visitors()
    if not total:
        await call.message.answer(
            "👥 Посетителей пока нет. Записываются с момента, как это включено.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text="⇦ Назад", callback_data="admin_panel")]]))
        return

    pages = max(1, -(-total // VISITORS_PAGE))
    page = max(0, min(page, pages - 1))
    rows = await database.get_visitors(VISITORS_PAGE, page * VISITORS_PAGE)

    lines = [f"👥 <b>Посетители</b> — всего {total}"]
    if pages > 1:
        lines[0] += f", страница {page + 1} из {pages}"
    lines.append("")

    for v in rows:
        name = html.escape(v["full_name"] or "без имени")
        handle = f" @{html.escape(v['username'])}" if v["username"] else ""
        lang = f" · {v['tg_language']}" if v["tg_language"] else ""
        lines.append(
            f"<b>{name}</b>{handle}{lang}\n"
            f"   <code>{v['user_id']}</code> · действий {v['actions']} · "
            f"{_ago(v['last_seen'])}"
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅", callback_data=f"admin_visitors_{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="➡", callback_data=f"admin_visitors_{page + 1}"))

    keyboard = [nav] if pages > 1 else []
    unnamed = len(await database.get_unnamed_visitors(200))
    if unnamed:
        keyboard.append([InlineKeyboardButton(
            text=f"🔍 Определить имена ({unnamed})", callback_data="admin_resolve_names")])
    keyboard.append([InlineKeyboardButton(text="⇦ Назад", callback_data="admin_panel")])

    await call.message.answer("\n".join(lines), parse_mode="HTML",
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.message(F.text.regexp(r"^/forget(\s+\d+)?$"))
async def forget_visitor(message: Message):
    """Удаление данных конкретного человека — если он об этом попросит"""
    if not config.is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "Укажите id посетителя: /forget 123456789\n\n"
            "Удалит запись о нём и всю его историю действий безвозвратно.")
        return

    if await database.forget_visitor(int(parts[1])):
        await message.answer(f"🗑 Данные посетителя {parts[1]} удалены.")
    else:
        await message.answer("⚠️ Не удалось удалить — ошибка базы.")


@router.callback_query(F.data == "admin_resolve_names")
async def resolve_names(call: CallbackQuery, bot: Bot):
    """Дописывает имена посетителям, восстановленным из журнала кликов.

    В журнале хранились только id — имени там никогда не было. Telegram отдаёт
    его по getChat для любого, кто хоть раз обращался к боту, поэтому имена
    можно получить, не дожидаясь, пока человек зайдёт снова.
    """
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer("Запрашиваю имена…")

    ids = await database.get_unnamed_visitors(RESOLVE_BATCH)
    resolved, gone = 0, 0
    for user_id in ids:
        try:
            chat = await bot.get_chat(user_id)
        except Exception:
            # Человек заблокировал бота или удалил аккаунт — имя недоступно
            gone += 1
            continue
        full_name = " ".join(filter(None, [chat.first_name, chat.last_name])) or None
        if await database.update_visitor_identity(user_id, chat.username, full_name):
            resolved += 1
        # Пауза между запросами: Telegram ограничивает частоту обращений
        await asyncio.sleep(0.15)

    left = len(await database.get_unnamed_visitors(200))
    lines = [f"🔍 Имена получены: <b>{resolved}</b>"]
    if gone:
        lines.append(f"Недоступны: {gone} — заблокировали бота или удалили аккаунт.")
    if left:
        lines.append(f"Осталось без имени: {left}. Нажмите ещё раз, чтобы продолжить.")

    await call.message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="👥 К списку",
                                               callback_data="admin_visitors_0")]]))
