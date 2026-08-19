# admin.py — служебный раздел владельца бота: шпаргалка по хэштегам и командам,
# управление паролями закрытых разделов.
#
# Всё здесь видно только пользователю с ORGANIZER_TELEGRAM_ID. Кнопка в главном
# меню другим просто не рисуется, а каждый обработчик проверяет права заново —
# кнопку можно подделать, callback приходит от кого угодно.
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

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
    "<code>/admin</code> — это меню\n\n"
    "<i>Видно только вам.</i>"
)


def _admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔖 Шпаргалка", callback_data="admin_cheatsheet")],
        [InlineKeyboardButton(text="🔑 Пароли разделов", callback_data="admin_passwords")],
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
