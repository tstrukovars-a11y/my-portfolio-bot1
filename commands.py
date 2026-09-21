# commands.py — список команд бота, собранный из самого кода.
#
# Список, написанный руками, врёт через неделю: команды добавляются,
# переименовываются и исчезают, а шпаргалка остаётся прежней. Поэтому
# читаем исходники и достаём то, на что действительно повешены
# обработчики.
#
# Разбор простой: нас интересуют три способа, которыми в проекте
# объявлены команды, — F.text == "/x", F.text.startswith("/x") и
# F.text.regexp(r"^/x"). Всё, что не подошло, просто не попадёт в список:
# ошибочно показать несуществующую команду хуже, чем не показать редкую.
import html
import os
import re

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)

import config

router = Router()

HERE = os.path.dirname(os.path.abspath(__file__))

PATTERNS = (
    re.compile(r'F\.text\s*==\s*["\'](/[^"\']+)["\']'),
    re.compile(r'F\.text\.startswith\(\s*["\'](/[^"\']+)["\']'),
    # Вид startswith(("/todo", "/чего")): несколько написаний одной команды.
    re.compile(r'F\.text\.startswith\(\s*\(\s*["\'](/[^"\']+)["\']'),
    re.compile(r'F\.text\.regexp\(\s*r["\']\^(/[a-zA-Zа-яёА-ЯЁ_]+)'),
    # Вид «^/(доход|income)»: команда с синонимами. Берём первый вариант —
    # он основной, остальные обычно английские дубли.
    re.compile(r'F\.text\.regexp\(\s*r["\']\^/\(([^)|]+)'),
)

# Порядок — как в работе: сначала то, чем пользуются каждый день.
GROUPS = (
    ("digest", "📣 Канал и публикации"),
    ("books_seed", "📚 Книги"),
    ("book_find", "🔍 Поиск книг"),
    ("tennis_alerts", "🎾 Теннис"),
    ("tennis_rank", "🎾 Рейтинг"),
    ("checklist", "💰 Деньги и что не готово"),
    ("advcake", "🤝 Партнёрская сеть"),
    ("invite_card", "📨 Приглашения"),
    ("growth", "📈 Рост канала"),
    ("banners", "🖼 Картинки разделов"),
    ("avatars", "🖼 Аватарки каналов"),
    ("weather", "🌦 Погода"),
    ("admin", "🛠 Служебное"),
    ("commands", "⌨️ Справка"),
    ("art_shop", "🎨 Картины"),
    ("xo", "🎮 Игры"),
    ("lang", "🗣 Языки"),
    ("puzzle_daily", "🧩 Головоломки"),
    ("travel_spots", "🌍 Места"),
    ("travel_channel", "🌍 Канал путешествий"),
    ("genetics", "🧬 Генетика"),
    ("planner", "🗓 Календарь"),
)

# Команды, которые не команды: их вводят читатели или это служебные
# маршруты сервера.
HIDDEN = {"/start", "/cancel"}

_cache = None


def _from_file(name: str) -> list:
    path = os.path.join(HERE, f"{name}.py")
    try:
        with open(path, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return []

    found = []
    for pattern in PATTERNS:
        for command in pattern.findall(source):
            command = command.split()[0].strip()
            if not command.startswith("/"):
                command = "/" + command
            if command in HIDDEN or command in found:
                continue
            found.append(command)
    return sorted(found)


def collect() -> list:
    """[(заголовок, [команды])] — то, что реально объявлено в коде"""
    global _cache
    if _cache is not None:
        return _cache

    out = []
    for module, title in GROUPS:
        commands = _from_file(module)
        if commands:
            out.append((title, commands))
    _cache = out
    return out


def text() -> str:
    lines = ["⌨️ <b>Команды бота</b>", ""]
    total = 0
    for title, commands in collect():
        lines.append(f"<b>{title}</b>")
        lines.append(" ".join(f"<code>{html.escape(c)}</code>" for c in commands))
        lines.append("")
        total += len(commands)
    lines.append(f"<i>Всего {total}. Список собран из кода, "
                 f"поэтому не расходится с тем, что бот умеет.</i>")
    return "\n".join(lines)


@router.message(F.text.regexp(r"^/(команды|commands)"))
async def commands_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    await message.answer(text())


@router.callback_query(F.data == "admin_commands")
async def commands_screen(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await call.message.answer(text())
