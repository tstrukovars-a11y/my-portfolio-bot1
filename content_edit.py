# content_edit.py — наполнить, поправить, удалить. Любой раздел.
#
# До сих пор материал правился четырьмя разными путями, и пути были
# неравны: книге можно было заменить обложку, путешествию нельзя, а
# удалить нельзя было почти ничего — только через базу руками.
#
# Отсюда и копился мусор: испорченный импортом текст оставался в
# очереди навсегда, потому что убрать его было нечем, и каждый раз он
# всплывал в «Что править» укором, на который нельзя ответить.
#
# Здесь одна дверь на все разделы: список, карточка, правка текста,
# замена фотографии, удаление с подтверждением.
#
# Удаление спрашивает подтверждение не из вежливости. Остальное здесь
# обратимо — текст можно переписать обратно, фотографию прислать
# заново. Удаление необратимо, и единственная защита от случайного
# нажатия — второе нажатие.
import html
import logging

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import config
import database

router = Router()

PER_PAGE = 8


class Editing(StatesGroup):
    text = State()
    photo = State()


def _sections_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=meta["name"],
                                  callback_data=f"ce_list_{key}_0")]
            for key, meta in database.CONTENT.items()]
    rows.append([InlineKeyboardButton(text="⇦ Назад",
                                      callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "admin_content")
async def open_content(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    lines = ["📂 <b>Материалы</b>", ""]
    for key, meta in database.CONTENT.items():
        _, total = await database.content_list(key, 0, 1)
        lines.append(f"{meta['name']}: {total}")
    lines.append("")
    lines.append("<i>Здесь можно поправить текст, заменить фотографию и "
                 "удалить то, что публиковать не нужно.</i>")
    await call.message.answer("\n".join(lines), reply_markup=_sections_kb())


@router.callback_query(F.data.startswith("ce_list_"))
async def show_list(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await state.clear()
    try:
        section, page = call.data[len("ce_list_"):].rsplit("_", 1)
        page = max(0, int(page))
    except ValueError:
        await call.answer()
        return
    if section not in database.CONTENT:
        await call.answer()
        return

    await call.answer()
    items, total = await database.content_list(section, page, PER_PAGE)
    meta = database.CONTENT[section]
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    if not items:
        await call.message.answer(
            f"{meta['name']}: пусто.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⇦ Разделы",
                                     callback_data="admin_content")]]))
        return

    rows = [[InlineKeyboardButton(
        text=f"{head[:44]}", callback_data=f"ce_open_{section}_{item_id}")]
        for item_id, head in items]

    # Листалка только там, где есть куда листать: две одинокие стрелки
    # под восемью строками читаются как поломка.
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text="←", callback_data=f"ce_list_{section}_{page - 1}"))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(
            text="→", callback_data=f"ce_list_{section}_{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⇦ Разделы",
                                      callback_data="admin_content")])

    await call.message.answer(
        f"{meta['name']} — {total}, страница {page + 1} из {pages}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


def _card_kb(section: str, item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Переписать текст",
                              callback_data=f"ce_text_{section}_{item_id}")],
        [InlineKeyboardButton(text="🖼 Заменить фотографию",
                              callback_data=f"ce_photo_{section}_{item_id}")],
        [InlineKeyboardButton(text="🗑 Удалить",
                              callback_data=f"ce_del_{section}_{item_id}")],
        [InlineKeyboardButton(text="⇦ К списку",
                              callback_data=f"ce_list_{section}_0")],
    ])


async def _show_card(message: Message, section: str, item_id: int,
                     prefix: str = ""):
    got = await database.content_get(section, item_id)
    if not got:
        await message.answer("Этого материала больше нет.")
        return
    text, photo = got
    body = (text or "").strip() or "<i>текста нет</i>"
    head = f"{prefix}<b>{database.CONTENT[section]['name']}</b> · №{item_id}\n\n"
    caption = head + html.escape(body)[:900]
    kb = _card_kb(section, item_id)

    if photo:
        try:
            await message.answer_photo(photo, caption=caption, reply_markup=kb)
            return
        except Exception as e:
            # Фотография могла устареть: file_id живёт не вечно, а
            # материал из-за этого становиться недоступным не должен.
            logging.info(f"Фото материала не показалось: {e}")
    await message.answer(caption + ("\n\n<i>Фотографии нет</i>" if not photo
                                    else ""), reply_markup=kb)


@router.callback_query(F.data.startswith("ce_open_"))
async def open_card(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    await state.clear()
    section, _, raw = call.data[len("ce_open_"):].rpartition("_")
    if section not in database.CONTENT or not raw.isdigit():
        await call.answer()
        return
    await call.answer()
    await _show_card(call.message, section, int(raw))


# --- правка текста -----------------------------------------------------

@router.callback_query(F.data.startswith("ce_text_"))
async def ask_text(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    section, _, raw = call.data[len("ce_text_"):].rpartition("_")
    if section not in database.CONTENT or not raw.isdigit():
        await call.answer()
        return
    await state.set_state(Editing.text)
    await state.update_data(section=section, item_id=int(raw))
    await call.answer()
    await call.message.answer(
        "Пришлите новый текст целиком.\n\n"
        "<i>Он заменит прежний. Первая строка — то, что видно в списке "
        "и в заголовке поста.</i>")


@router.message(Editing.text, F.text)
async def save_text(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    section, item_id = data.get("section"), data.get("item_id")
    if not section:
        return
    if await database.content_set(section, item_id, text=message.text):
        await _show_card(message, section, item_id, prefix="✅ Переписала\n\n")
    else:
        await message.answer("⚠️ Не сохранилось. Попробуйте ещё раз.")


# --- замена фотографии -------------------------------------------------

@router.callback_query(F.data.startswith("ce_photo_"))
async def ask_photo(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    section, _, raw = call.data[len("ce_photo_"):].rpartition("_")
    if section not in database.CONTENT or not raw.isdigit():
        await call.answer()
        return
    await state.set_state(Editing.photo)
    await state.update_data(section=section, item_id=int(raw))
    await call.answer()
    await call.message.answer("Пришлите фотографию картинкой, не файлом.")


@router.message(Editing.photo, F.photo)
async def save_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    section, item_id = data.get("section"), data.get("item_id")
    if not section:
        return
    if await database.content_set(section, item_id,
                                  photo=message.photo[-1].file_id):
        await _show_card(message, section, item_id, prefix="✅ Заменила\n\n")
    else:
        await message.answer("⚠️ Не сохранилось. Попробуйте ещё раз.")


@router.message(Editing.photo)
async def not_a_photo(message: Message):
    await message.answer("Нужна именно фотография — картинкой, не файлом.")


# --- удаление ----------------------------------------------------------

@router.callback_query(F.data.startswith("ce_del_"))
async def ask_delete(call: CallbackQuery):
    """Спрашиваем подтверждение не из вежливости.

    Текст можно переписать обратно, фотографию прислать заново —
    остальное здесь обратимо. Удаление необратимо, и единственная
    защита от случайного нажатия на маленьком экране — второе нажатие.
    """
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    section, _, raw = call.data[len("ce_del_"):].rpartition("_")
    if section not in database.CONTENT or not raw.isdigit():
        await call.answer()
        return
    got = await database.content_get(section, int(raw))
    head = ((got[0] or "").strip().split("\n") or [""])[0][:60] if got else ""
    await call.answer()
    await call.message.answer(
        f"🗑 Удалить без возврата?\n\n<b>{html.escape(head)}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Да, удалить",
                                  callback_data=f"ce_gone_{section}_{raw}")],
            [InlineKeyboardButton(text="⇦ Оставить",
                                  callback_data=f"ce_open_{section}_{raw}")]]))


@router.callback_query(F.data.startswith("ce_gone_"))
async def do_delete(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        await call.answer()
        return
    section, _, raw = call.data[len("ce_gone_"):].rpartition("_")
    if section not in database.CONTENT or not raw.isdigit():
        await call.answer()
        return
    if await database.content_delete(section, int(raw)):
        await call.answer("Удалено")
        await call.message.answer(
            "🗑 Удалено.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⇦ К списку",
                                     callback_data=f"ce_list_{section}_0")]]))
    else:
        await call.answer("Не вышло удалить", show_alert=True)
