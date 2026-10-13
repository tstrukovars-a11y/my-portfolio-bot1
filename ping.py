# ping.py — жив ли бот и узнаёт ли он вас.
#
# Каждая служебная команда начинается с «вы владелец?», и при
# несовпадении обработчик молча выходит. Снаружи это неотличимо от
# мёртвого бота: в обоих случаях тишина.
#
# Разница при этом огромная. Мёртвый бот чинят перезапуском, неузнанного
# владельца — одной переменной окружения, и пока их не различить,
# чинится наугад то одно, то другое.
#
# Поэтому здесь одна команда, которая отвечает всем и всегда. Она ничего
# не показывает из чужого: свой номер человек и так знает, а состояние
# базы говорит только «отвечает» или «нет».
import html
import os

from aiogram import Router, F
from aiogram.types import Message

import config
import database

router = Router()


@router.message(F.text.regexp(r"^/(пинг|ping|я)\b"))
async def ping(message: Message):
    """Ответ приходит всегда — в этом весь смысл команды"""
    user = message.from_user
    lines = ["🤖 <b>Бот жив</b>", ""]
    lines.append(f"Ваш номер: <code>{user.id}</code>")

    if not config.ADMIN_ID:
        # Самый коварный случай: бот работает, команды есть, и ни одна
        # не отвечает. Переменная окружения потерялась — об этом надо
        # сказать прямо, иначе её будут искать неделю.
        lines.append("")
        lines.append("⚠️ <b>Владелец не задан вовсе.</b> Служебные команды "
                     "не работают ни у кого.")
        lines.append("На Render: Environment → <code>ADMIN_ID</code> или "
                     "<code>ORGANIZER_TELEGRAM_ID</code> → ваш номер выше.")
    elif config.is_admin(user.id):
        lines.append("Вы — владелец: служебные команды работают.")
    else:
        lines.append(f"Владелец — другой номер (<code>{config.ADMIN_ID}</code>). "
                     f"Служебные команды вам не отвечают.")

    state = await database.health()
    lines.append("")
    if state.get("ok"):
        lines.append("База: отвечает")
    else:
        lines.append("⚠️ <b>База не отвечает</b> — ни настройки, ни "
                     "расписание публикаций не читаются.")
        if state.get("error"):
            lines.append(f"<code>{html.escape(str(state['error'])[:160])}</code>")

    where = os.environ.get("RENDER_EXTERNAL_URL", "")
    if not where:
        lines.append("")
        lines.append("⚠️ Адрес службы не задан — Telegram шлёт обновления "
                     "в никуда.")

    chat = message.chat.type
    if chat != "private":
        lines.append("")
        lines.append("<i>Это общий чат. Служебные команды здесь не "
                     "выполняются — только в личке.</i>")

    await message.answer("\n".join(lines))
