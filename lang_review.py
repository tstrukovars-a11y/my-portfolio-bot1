# lang_review.py — проверка озвучки тем, кто говорит на языке.
#
# Огласовки иврита машина расставляет с ошибками, и это не мелочь: в уроке
# зазвучит одно слово вместо другого, а человек выучит его как верное.
# Услышать подмену может только тот, кто на языке говорит, — значит, ему
# нужен доступ, но не весь бот: проверяющий приходит по личной ссылке и
# видит ровно одно — фразы и две кнопки.
#
# Кнопок именно две. Шкала «от одного до пяти» заставляет думать, а думать
# он должен об иврите, а не об оценке. «Так звучит» или «не так» — это
# решение, которое принимается на слух за секунду.
#
# Самое ценное здесь — не «не так», а то, что идёт следом: можно записать
# голосом, как правильно. Текстом это не передать (описывать ударение
# словами — мучение), а живая запись потом и подскажет, и сама заменит
# синтезатор.
#
# Ссылка одноразовой не делается: он будет возвращаться, и каждый раз бот
# даёт ему то, чего он ещё не слышал. Новая ссылка отменяет старую —
# на случай, если та куда-то утекла.
import html
import logging
import re
import secrets
from urllib.parse import quote

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, FSInputFile)
from aiogram.dispatcher.event.bases import SkipHandler

import config
import database
import lang

router = Router()

CODE = "he"                      # проверяем иврит: остальные языки читаются ровнее
TOKEN_KEY = "lang_check_token"
CHECKER_KEY = "lang_checker_"    # + id: человек уже входил по ссылке
WAIT_KEY = "lang_check_wait_"    # + id: фраза, к которой ждём замечание

MAX_VOICES = 10                  # столько записей присылаем за раз


# ---------------------------------------------------------------------
# ДОСТУП
# ---------------------------------------------------------------------

async def token() -> str:
    """Пропуск проверяющего. Заводится сам при первом обращении."""
    value = await database.get_setting(TOKEN_KEY)
    if not value:
        value = secrets.token_urlsafe(9)
        await database.set_setting(TOKEN_KEY, value)
    return value


async def new_token() -> str:
    """Сменить пропуск: старая ссылка перестаёт работать"""
    value = secrets.token_urlsafe(9)
    await database.set_setting(TOKEN_KEY, value)
    return value


async def link() -> str:
    username = await database.get_setting("bot_username")
    if not username:
        return ""
    return f"https://t.me/{username}?start=check_{await token()}"


async def is_checker(user_id: int) -> bool:
    """Право проверять остаётся за человеком и после смены ссылки.

    Иначе смена пропуска выбрасывала бы того, ради кого всё и делалось.
    """
    return bool(await database.get_setting(CHECKER_KEY + str(user_id)))


# ---------------------------------------------------------------------
# ОЧЕРЕДЬ
# ---------------------------------------------------------------------

def spelled(phrase: str) -> str:
    """Фраза с огласовками — то, по чему синтезатор и читает.

    Проверяющему показываем обе: он слышит звук, видит написанное на
    экране и видит, что машина себе вообразила.
    """
    said = lang.spoken(CODE, phrase)
    return said if said != phrase else ""


def queue(done: set) -> list:
    """Фразы, которых он ещё не слышал. Сначала те, у которых есть звук."""
    return [p for p in lang.phrases(CODE)
            if p not in done and lang.audio_path(CODE, p)]


# ---------------------------------------------------------------------
# ЭКРАН ПРОВЕРЯЮЩЕГО
# ---------------------------------------------------------------------

HELLO = (
    "🎧 <b>Проверка озвучки</b>\n\n"
    "Спасибо, что согласились. Машина расставляет огласовки сама и "
    "иногда читает слово не тем словом — на слух это ловите только вы.\n\n"
    "Дальше будут короткие записи. Послушайте и нажмите одну из двух "
    "кнопок. Если звучит не так — можно тут же надиктовать голосом, как "
    "правильно: это полезнее любого описания словами.\n\n"
    "Можно бросить в любой момент и вернуться когда угодно — бот помнит, "
    "что вы уже слушали.")

DONE = ("🎉 Всё прослушано. Спасибо — теперь в уроках звучит то, что нужно.\n\n"
        "Если появятся новые фразы, бот их пришлёт.")


def _kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👍 Так и звучит", callback_data="chk_ok"),
         InlineKeyboardButton(text="👎 Не так", callback_data="chk_bad")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="chk_skip")]])


async def ask(message: Message, user_id: int):
    """Следующая непрослушанная фраза"""
    done = await database.reviewed_by(CODE, user_id)
    left = queue(done)
    if not left:
        await message.answer(DONE)
        return

    phrase = left[0]
    total = len(queue(set()))
    caption = [f"<b>{html.escape(phrase)}</b>"]
    marked = spelled(phrase)
    if marked:
        caption.append(f"<i>{html.escape(marked)}</i>")
    caption.append(f"\n{total - len(left) + 1} / {total}")

    await database.set_setting(WAIT_KEY + str(user_id), "")
    await message.answer_audio(
        FSInputFile(lang.audio_path(CODE, phrase)),
        title="🎧", performer=" ", caption="\n".join(caption),
        reply_markup=_kb())


@router.message(F.text.regexp(r"^/start\s+check_(\S+)"))
async def enter(message: Message):
    given = re.match(r"^/start\s+check_(\S+)", message.text or "").group(1)
    if not secrets.compare_digest(given, await token()):
        # Ссылку сменили, а старой кто-то воспользовался. Молчим о
        # причине: это не его забота, а владельца бота.
        raise SkipHandler

    await database.set_setting(CHECKER_KEY + str(message.from_user.id), "1")
    await message.answer(HELLO)
    await ask(message, message.from_user.id)


@router.message(F.text.regexp(r"^/(проверка|check)$"))
async def check_command(message: Message):
    user_id = message.from_user.id
    if config.is_admin(user_id):
        await _panel(message)
        return
    if not await is_checker(user_id):
        raise SkipHandler
    await ask(message, user_id)


# ---------------------------------------------------------------------
# ОТВЕТЫ
# ---------------------------------------------------------------------

def _current(call: CallbackQuery) -> str:
    """Фраза, о которой идёт речь: она написана в подписи под записью.

    Хранить её отдельно незачем — она уже есть в сообщении, и так не
    разъедется, если человек вернётся к старой записи выше в переписке.
    """
    caption = call.message.caption or ""
    return caption.split("\n")[0].strip()


def _name(call: CallbackQuery) -> str:
    who = call.from_user
    return " ".join(x for x in [who.first_name, who.last_name] if x) or "Проверяющий"


@router.callback_query(F.data.in_({"chk_ok", "chk_bad", "chk_skip"}))
async def verdict(call: CallbackQuery):
    user_id = call.from_user.id
    if not await is_checker(user_id):
        await call.answer()
        return

    phrase = _current(call)
    choice = call.data.split("_")[1]
    if choice == "skip":
        await call.answer("Пропускаю")
        # Пропуск тоже запоминаем, иначе бот будет предлагать одно и то
        # же по кругу, а человек — уходить.
        await database.save_review(CODE, phrase, user_id, _name(call), "skip")
    else:
        await call.answer("Записала" if choice == "ok" else "Понятно, поправим")
        await database.save_review(CODE, phrase, user_id, _name(call),
                                   "ok" if choice == "ok" else "bad")

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if choice == "bad":
        await database.set_setting(WAIT_KEY + str(user_id), phrase)
        await call.message.answer(
            "Скажите голосом, как правильно — или напишите словами. "
            "Можно и пропустить.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⏭ Дальше", callback_data="chk_next")]]))
        return

    await ask(call.message, user_id)


@router.callback_query(F.data == "chk_next")
async def skip_note(call: CallbackQuery):
    await call.answer()
    await database.set_setting(WAIT_KEY + str(call.from_user.id), "")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await ask(call.message, call.from_user.id)


@router.message(F.voice | F.audio | F.video_note)
async def voice_note(message: Message):
    """Как правильно — голосом. Ради этого всё и затевалось."""
    user_id = message.from_user.id
    phrase = await database.get_setting(WAIT_KEY + str(user_id))
    if not phrase:
        raise SkipHandler

    voice = message.voice or message.audio or message.video_note
    await database.review_note(CODE, phrase, user_id, voice_id=voice.file_id)
    await database.set_setting(WAIT_KEY + str(user_id), "")
    await message.answer("Записала ваш голос. Дальше:")
    await ask(message, user_id)


@router.message(F.text, ~F.text.startswith("/"))
async def text_note(message: Message):
    user_id = message.from_user.id
    phrase = await database.get_setting(WAIT_KEY + str(user_id))
    if not phrase:
        raise SkipHandler

    await database.review_note(CODE, phrase, user_id, note=message.text.strip())
    await database.set_setting(WAIT_KEY + str(user_id), "")
    await message.answer("Записала. Дальше:")
    await ask(message, user_id)


# ---------------------------------------------------------------------
# ЭКРАН ВЛАДЕЛИЦЫ
# ---------------------------------------------------------------------

async def report() -> str:
    rows = await database.reviews(CODE)
    total = len(queue(set()))
    if not rows:
        return ("🎧 <b>Проверка иврита</b>\n\nПока никто не слушал. "
                f"Ждут проверки {total} фраз.")

    bad = [r for r in rows if r["verdict"] == "bad"]
    ok = sum(1 for r in rows if r["verdict"] == "ok")
    who = ", ".join(sorted({r["reviewer_name"] or "?" for r in rows}))

    lines = [f"🎧 <b>Проверка иврита</b>\n",
             f"Слушал: {html.escape(who)}",
             f"Проверено {len(rows)} из {total}: {ok} верно, {len(bad)} на правку"]

    if bad:
        lines.append("\n<b>Звучит не так:</b>")
        for r in bad[:20]:
            line = f"• {html.escape(r['phrase'])}"
            if r["note"]:
                line += f" — <i>{html.escape(r['note'])}</i>"
            if r["voice_id"]:
                line += " 🎤"
            lines.append(line)
    return "\n".join(lines)


SHARE_TEXT = ("Помогите проверить, как звучит иврит в уроках — "
              "это пара минут и две кнопки")


def _share(address: str) -> str:
    """Ссылка на выбор чата: Телеграм сам вложит адрес и подпись"""
    return (f"https://t.me/share/url?url={quote(address, safe='')}"
            f"&text={quote(SHARE_TEXT, safe='')}")


def _panel_kb(link_text: str) -> InlineKeyboardMarkup:
    rows = []
    if link_text:
        rows.append([InlineKeyboardButton(text="📤 Отправить ссылку",
                                          url=_share(link_text))])
    rows.append([InlineKeyboardButton(text="🎤 Послушать замечания",
                                      callback_data="chk_voices")])
    rows.append([InlineKeyboardButton(text="🔄 Новая ссылка",
                                      callback_data="chk_newlink")])
    rows.append([InlineKeyboardButton(text="⇦ Назад", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _panel_text() -> str:
    address = await link()
    tail = (f"\n\n<b>Ссылка проверяющему:</b>\n<code>{address}</code>"
            if address else "\n\nСсылка появится, когда бот узнает своё имя.")
    return await report() + tail


async def _panel(message: Message):
    await message.answer(await _panel_text(),
                         reply_markup=_panel_kb(await link()),
                         disable_web_page_preview=True)


@router.callback_query(F.data == "admin_check")
async def panel(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    await call.message.answer(await _panel_text(),
                              reply_markup=_panel_kb(await link()),
                              disable_web_page_preview=True)


# Готовое приглашение: одна кнопка в служебном меню — и есть что
# переслать. Просить о помощи голой ссылкой неловко, а сочинять текст
# каждый раз заново — повод отложить.
INVITE = (
    "🎧 <b>Нужна пара минут вашего иврита</b>\n\n"
    "Я собрала уроки на слух: бот произносит фразу, а человек угадывает, "
    "что это. Огласовки машина расставляет сама и иногда читает слово не "
    "тем словом — заметить это может только тот, кто на иврите говорит.\n\n"
    "По ссылке — короткие записи и две кнопки: «так звучит» или «не так». "
    "Если не так, можно тут же надиктовать голосом, как правильно.\n\n"
    "Бросить можно в любой момент: бот помнит, что вы уже слушали.\n\n"
    "{link}")


@router.callback_query(F.data == "chk_send")
async def send_invite(call: CallbackQuery):
    """Карточка, которую остаётся только переслать"""
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()

    address = await link()
    if not address:
        await call.message.answer(
            "Ссылку пока не собрать: бот ещё не узнал своё имя в Телеграме. "
            "Обычно это проходит после перезапуска.")
        return

    await call.message.answer(
        INVITE.format(link=address), disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📤 Выбрать чат", url=_share(address))]]))


@router.callback_query(F.data == "chk_newlink")
async def rotate(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await new_token()
    await call.answer("Старая ссылка больше не работает")
    await call.message.answer(await _panel_text(),
                              reply_markup=_panel_kb(await link()),
                              disable_web_page_preview=True)


@router.callback_query(F.data == "chk_voices")
async def voices(call: CallbackQuery, bot: Bot):
    """Записи «как правильно» — их надо слушать, а не читать."""
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()

    rows = [r for r in await database.reviews(CODE, only_bad=True) if r["voice_id"]]
    if not rows:
        await call.message.answer("Голосовых замечаний пока нет.")
        return

    for r in rows[:MAX_VOICES]:
        try:
            await bot.send_voice(call.message.chat.id, r["voice_id"],
                                 caption=f"<b>{html.escape(r['phrase'])}</b>",
                                 parse_mode="HTML")
        except Exception as e:
            logging.warning(f"Голосовое замечание не переслалось: {e}")
            await call.message.answer(
                f"{html.escape(r['phrase'])} — запись не открывается")
    if len(rows) > MAX_VOICES:
        await call.message.answer(f"…и ещё {len(rows) - MAX_VOICES}")
