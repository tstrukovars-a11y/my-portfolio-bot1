# urgent.py — то, что не ждёт расписания.
#
# Дайджест выходит по часам: утро, теннис, книги, ужин. Это правильно для
# постоянного потока и бесполезно для события: приложение вышло сегодня,
# а не в четверг в одиннадцать.
#
# Здесь два вида таких публикаций, и различаются они не срочностью, а
# тем, о чём говорят.
#
#   Срочное — о мире: вышло приложение, опубликована статья, случилось
#   то, ради чего читатель и подписан.
#
#   «Что нового» — о самом канале: появилась подписка на блоки, теперь
#   можно спросить «как это касается меня». Такое легко не заметить:
#   человек видит новые кнопки и не понимает, что изменилось, а чаще не
#   видит вовсе.
#
# Публикация идёт через предпросмотр. Пост в канал уходит один раз и
# правится плохо; лишние десять секунд на «посмотреть, как это выглядит»
# дешевле опечатки в заголовке.
import html
import json
import logging
import re

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, FSInputFile)

import config
import database

router = Router()

DRAFT_KEY = "urgent_draft"        # что готовится к выходу
MAX_TEXT = 3500                   # с запасом под подпись и кнопки

HEADS = {
    "news": "⚡️ <b>Срочно</b>",
    "changes": "🆕 <b>Что нового в канале</b>",
}

# Команду зовут так, как она называется в голове, а не в коде:
# «/срочно», «/срочная новость», просто «/срочная». Разницы для
# человека нет, и заставлять его вспоминать точную форму — значит
# ставить препятствие ровно там, где он торопится.
#
# Форму вырезаем целиком, вместе со словом «новость»: иначе оно уедет
# в первую строку поста и выйдет в канал как часть заголовка.
URGENT = re.compile(r"^/(?:срочно|срочная(?:\s+новость)?)\b\s*", re.I)
CHANGES = re.compile(r"^/(?:новое|что\s+нового)\b\s*", re.I)


def body_of(pattern, text: str) -> str:
    """Текст поста без команды"""
    return pattern.sub("", text or "", count=1).strip()


def parse(body: str) -> dict:
    """Разобрать черновик: текст, ссылка-кнопка, картинка.

    Формат простой, потому что писать его придётся с телефона:

        Текст поста, сколько угодно строк.
        кнопка: Поставить | https://…
        фото: data/cards/tennis_app.png
    """
    text, button, photo = [], None, None
    for line in (body or "").splitlines():
        low = line.strip().lower()
        if low.startswith("кнопка:"):
            tail = line.split(":", 1)[1]
            if "|" in tail:
                label, url = tail.split("|", 1)
                if url.strip().startswith("http"):
                    button = (label.strip()[:40], url.strip())
            continue
        if low.startswith("фото:"):
            photo = line.split(":", 1)[1].strip()
            continue
        text.append(line)
    return {"text": "\n".join(text).strip(), "button": button, "photo": photo}


def render(kind: str, draft: dict) -> str:
    """Готовый текст поста — тот же, что уйдёт в канал"""
    head = HEADS.get(kind, HEADS["news"])
    return f"{head}\n\n{draft['text']}"


def markup(draft: dict):
    if not draft.get("button"):
        return None
    label, url = draft["button"]
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=label, url=url)]])


async def publish(bot: Bot, kind: str, draft: dict) -> str:
    """Отправить в канал. Строка — для отчёта владелице."""
    import digest

    chat, thread = await digest._target()
    if not chat:
        return "канал не задан: /digest chat -100…"

    text = render(kind, draft)[:MAX_TEXT]
    photo = (draft.get("photo") or "").strip()
    try:
        if photo:
            # Картинка с подписью: подпись короче текста, поэтому длинный
            # пост уходит отдельным сообщением следом.
            if len(text) <= 1024:
                await bot.send_photo(chat, FSInputFile(photo), caption=text,
                                     message_thread_id=thread,
                                     reply_markup=markup(draft))
                return "опубликовано с картинкой"
            await bot.send_photo(chat, FSInputFile(photo),
                                 message_thread_id=thread)
        await bot.send_message(chat, text, message_thread_id=thread,
                               reply_markup=markup(draft),
                               disable_web_page_preview=not draft.get("button"))
        return "опубликовано"
    except Exception as e:
        logging.error(f"Срочная публикация не вышла: {e}")
        return f"ошибка: {e}"


# ---------------------------------------------------------------------
# КОМАНДЫ
# ---------------------------------------------------------------------

HELP = (
    "⚡️ <b>Срочная публикация</b>\n\n"
    "<code>/срочно Текст поста\n"
    "кнопка: Поставить | https://ссылка\n"
    "фото: data/cards/tennis_app.png</code>\n\n"
    "Кнопка и фото не обязательны. Бот покажет, как это будет "
    "выглядеть, и спросит подтверждение.\n\n"
    "Можно звать и полным именем: <code>/срочная новость …</code>\n\n"
    "Про изменения в самом канале — <code>/новое</code>: тот же формат, "
    "другой заголовок.")


async def _preview(message: Message, kind: str, body: str):
    draft = parse(body)
    if not draft["text"]:
        await message.answer("Нужен текст поста.\n\n" + HELP)
        return

    if draft["photo"]:
        import os
        if not os.path.exists(draft["photo"]):
            await message.answer(
                f"Файла нет: <code>{html.escape(draft['photo'])}</code>\n\n"
                f"Картинки собираются так: "
                f"<code>python3 tools/make_card.py «Заголовок» «Строка»</code>")
            return

    await database.set_setting(
        DRAFT_KEY, json.dumps({"kind": kind, **draft}, ensure_ascii=False))

    await message.answer(
        render(kind, draft), reply_markup=markup(draft),
        disable_web_page_preview=not draft["button"])
    await message.answer(
        "👆 Так это увидят в канале."
        + (f"\n📷 С картинкой: <code>{html.escape(draft['photo'])}</code>"
           if draft["photo"] else ""),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📣 Опубликовать",
                                  callback_data="urg_go")],
            [InlineKeyboardButton(text="⛔ Отмена", callback_data="urg_no")]]))


@router.message(F.text.regexp(URGENT))
async def urgent_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    body = body_of(URGENT, message.text)
    if not body:
        await message.answer(HELP)
        return
    await _preview(message, "news", body)


@router.message(F.text.regexp(CHANGES))
async def changes_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    body = body_of(CHANGES, message.text)
    if not body:
        await message.answer(
            "🆕 <b>Что нового в канале</b>\n\n"
            "<code>/новое Появилась подписка на отдельные блоки.\n"
            "кнопка: Выбрать | https://t.me/имя_бота?start=subs</code>\n\n"
            "Пишите о том, что изменилось у читателя, а не у вас: "
            "«теперь можно выбрать, что присылать» вместо «добавлен "
            "модуль подписок».")
        return
    await _preview(message, "changes", body)


@router.callback_query(F.data == "urg_go")
async def go(call: CallbackQuery, bot: Bot):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return

    raw = await database.get_setting(DRAFT_KEY)
    if not raw:
        await call.answer("Черновик потерялся — соберите заново",
                          show_alert=True)
        return
    try:
        draft = json.loads(raw)
    except ValueError:
        await call.answer("Черновик не читается", show_alert=True)
        return

    await call.answer("Публикую…")
    result = await publish(bot, draft.get("kind", "news"), draft)
    await database.set_setting(DRAFT_KEY, "")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.message.answer(f"📣 {result}")


@router.callback_query(F.data == "urg_no")
async def cancel(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await database.set_setting(DRAFT_KEY, "")
    await call.answer("Отменила")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@router.callback_query(F.data == "admin_urgent")
async def urgent_screen(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await call.message.answer(HELP)
