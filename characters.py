# characters.py — персонажи, нарисованные самим пользователем.
#
# Каждому видны только свои. Это не осторожность ради осторожности: человек,
# присылая рисунок, соглашается на своего героя в своей истории, а не на
# показ его посторонним. Поэтому и выдача картинки, и удаление проверяют
# автора, а не только номер.
#
# Рисунок хранится в базе целиком. Своего файлового хранилища у сервиса нет,
# а file_id Telegram браузеру бесполезен: страница мультфильма не умеет
# ходить в Telegram за файлами.
import html
import logging
import os

from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, BufferedInputFile)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import database
import inline_kb

router = Router()

MAX_BYTES = 4 * 1024 * 1024      # 4 МБ: больше не нужно, а базу бережём
MAX_NAME = 24


class Adding(StatesGroup):
    waiting_image = State()
    waiting_name = State()


ASK_IMAGE = {
    "ru": "🎨 <b>Свой персонаж</b>\n\nПришлите рисунок — фотографию, скан из блокнота "
          "или картинку с телефона. Дальше спрошу имя.\n\n"
          "<i>Лучше всего работает персонаж целиком, на светлом фоне.</i>",
    "en": "🎨 <b>Your own character</b>\n\nSend a drawing — a photo, a scan, or an image "
          "from your phone. I'll ask for a name next.",
    "fr": "🎨 <b>Votre personnage</b>\n\nEnvoyez un dessin — photo, scan ou image. "
          "Je demanderai ensuite un nom.",
    "he": "🎨 <b>דמות משלכם</b>\n\nשלחו ציור — תמונה, סריקה או קובץ מהטלפון. "
          "אחר כך אשאל לשם.",
}
ASK_NAME = {
    "ru": "Как его зовут? Это имя вы будете писать в своих историях.",
    "en": "What is their name? You'll use it in your stories.",
    "fr": "Comment s'appelle-t-il ? Vous l'utiliserez dans vos histoires.",
    "he": "איך קוראים לו? בשם הזה תשתמשו בסיפורים שלכם.",
}
SAVED = {
    "ru": "✅ <b>{name}</b> сохранён.\n\nТеперь просто упоминайте его в истории — "
          "и он сыграет в мультфильме.",
    "en": "✅ <b>{name}</b> saved.\n\nJust mention them in a story and they'll appear.",
    "fr": "✅ <b>{name}</b> enregistré.\n\nMentionnez-le dans une histoire.",
    "he": "✅ <b>{name}</b> נשמר.\n\nפשוט הזכירו אותו בסיפור.",
}
EMPTY = {
    "ru": "Своих персонажей пока нет.",
    "en": "No characters of your own yet.",
    "fr": "Aucun personnage pour l'instant.",
    "he": "אין עדיין דמויות משלכם.",
}
ADD = {"ru": "➕ Добавить персонажа", "en": "➕ Add a character",
       "fr": "➕ Ajouter un personnage", "he": "➕ להוסיף דמות"}
MINE = {"ru": "🎨 Мои персонажи", "en": "🎨 My characters",
        "fr": "🎨 Mes personnages", "he": "🎨 הדמויות שלי"}


async def _lang(user_id):
    return await database.get_user_language(user_id)


def _menu(lang, chars):
    rows = [[InlineKeyboardButton(text=ADD.get(lang, ADD["en"]),
                                  callback_data="char_add")]]
    for cid, name, _, _tok in chars:
        rows.append([InlineKeyboardButton(text=f"🗑 {name}",
                                          callback_data=f"char_del_{cid}")])
    rows.append([InlineKeyboardButton(text="🎬 " + ("К мультфильму" if lang == "ru"
                                                   else "To the cartoon"),
                                      callback_data="cartoon_open")])
    rows.append([InlineKeyboardButton(text=inline_kb.label(inline_kb.HOME_TEXTS, lang),
                                      callback_data="go_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "char_list")
async def show_characters(call: CallbackQuery, state: FSMContext):
    await state.clear()
    lang = await _lang(call.from_user.id)
    chars = await database.own_characters(call.from_user.id)

    if chars:
        body = "\n".join(f"• {html.escape(n)}" for _, n, _, _t in chars)
        text = (f"🎨 <b>{MINE.get(lang, MINE['en'])}</b>\n\n{body}\n\n"
                f"<i>Занято {len(chars)} из {database.MAX_OWN_CHARACTERS}. "
                f"Нажмите на имя, чтобы удалить.</i>")
    else:
        text = f"🎨 <b>{MINE.get(lang, MINE['en'])}</b>\n\n{EMPTY.get(lang, EMPTY['en'])}"

    await call.message.answer(text, reply_markup=_menu(lang, chars))
    await call.answer()


@router.callback_query(F.data == "char_add")
async def ask_image(call: CallbackQuery, state: FSMContext):
    lang = await _lang(call.from_user.id)
    await state.set_state(Adding.waiting_image)
    await call.message.answer(ASK_IMAGE.get(lang, ASK_IMAGE["en"]))
    await call.answer()


@router.message(Adding.waiting_image, F.photo | F.document)
async def take_image(message: Message, state: FSMContext, bot: Bot):
    lang = await _lang(message.from_user.id)

    if message.photo:
        file_id, mime = message.photo[-1].file_id, "image/jpeg"
    else:
        doc = message.document
        if not (doc.mime_type or "").startswith("image/"):
            await message.answer("⚠️ Это не картинка. Пришлите рисунок.")
            return
        file_id, mime = doc.file_id, doc.mime_type

    try:
        info = await bot.get_file(file_id)
        if info.file_size and info.file_size > MAX_BYTES:
            await message.answer("⚠️ Слишком большой файл. До 4 МБ.")
            return
        buffer = await bot.download_file(info.file_path)
        data = buffer.read()
    except Exception as e:
        logging.error(f"Персонаж: не скачался файл: {e}")
        await message.answer("⚠️ Не удалось забрать рисунок. Попробуйте ещё раз.")
        return

    await state.update_data(data=data, mime=mime)
    await state.set_state(Adding.waiting_name)
    await message.answer(ASK_NAME.get(lang, ASK_NAME["en"]))


@router.message(Adding.waiting_image)
async def not_an_image(message: Message):
    await message.answer("⚠️ Жду картинку — фотографию или файл-изображение.")


@router.message(Adding.waiting_name, F.text & ~F.text.startswith("/"))
async def take_name(message: Message, state: FSMContext):
    lang = await _lang(message.from_user.id)
    name = message.text.strip()[:MAX_NAME]
    if not name:
        await message.answer("⚠️ Имя пустое. Напишите, как его зовут.")
        return

    payload = await state.get_data()
    result = await database.add_own_character(
        message.from_user.id, name, "character", payload.get("data"), payload.get("mime"))
    await state.clear()

    if result == "лимит":
        await message.answer(
            f"⚠️ Больше {database.MAX_OWN_CHARACTERS} персонажей не помещается. "
            "Удалите кого-нибудь в списке.")
        return
    if result == "занято":
        await message.answer("⚠️ Персонаж с таким именем уже есть. Возьмите другое имя.")
        return
    if result != "ok":
        await message.answer("⚠️ Не удалось сохранить. Попробуйте ещё раз.")
        return

    chars = await database.own_characters(message.from_user.id)
    await message.answer(SAVED.get(lang, SAVED["en"]).format(name=html.escape(name)),
                         reply_markup=_menu(lang, chars))


@router.callback_query(F.data.startswith("char_del_"))
async def delete_character(call: CallbackQuery):
    lang = await _lang(call.from_user.id)
    try:
        char_id = int(call.data.rsplit("_", 1)[1])
    except ValueError:
        await call.answer()
        return

    # Автора проверяет сам запрос удаления: номер персонажа угадывается
    # перебором, и одной проверки на стороне кнопки было бы мало.
    ok = await database.delete_own_character(char_id, call.from_user.id)
    chars = await database.own_characters(call.from_user.id)
    body = "\n".join(f"• {html.escape(n)}" for _, n, _, _t in chars) or EMPTY.get(lang, EMPTY["en"])
    await call.message.edit_text(f"🎨 <b>{MINE.get(lang, MINE['en'])}</b>\n\n{body}",
                                 reply_markup=_menu(lang, chars))
    await call.answer("Удалён" if ok else "Не найден")
