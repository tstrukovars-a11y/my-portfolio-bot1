# orders.py — заявки на рекламное сотрудничество.
# Пользователь описывает свою задачу, заявка целиком уходит владельцу бота
# в личку, решение о сотрудничестве принимается вручную.
import logging

from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import config
import database

router = Router()


class OrderStates(StatesGroup):
    choosing_need = State()
    waiting_project = State()
    waiting_audience = State()
    waiting_contact = State()
    confirming = State()


# Варианты запроса. Ключ уходит в заявку, чтобы вы сразу видели тип обращения.
NEEDS = {
    "shop_support": {"ru": "🛍 Сопровождение магазина", "en": "🛍 Store support"},
    "channel_ads": {"ru": "📢 Реклама в моём канале", "en": "📢 Ads in my channel"},
    "bot_link": {"ru": "🔗 Встроить ссылку в бота", "en": "🔗 Embed a link in a bot"},
    "bot_build": {"ru": "🤖 Нужен бот под задачу", "en": "🤖 Need a bot built"},
    "consult": {"ru": "💬 Консультация по продвижению", "en": "💬 Promotion consulting"},
}

T = {
    "intro": {
        "ru": ("📝 **Заявка на сотрудничество**\n\nОтвечу лично. Четыре коротких вопроса — "
               "чем точнее ответы, тем предметнее будет разговор.\n\nЧто вам нужно?"),
        "en": ("📝 **Partnership request**\n\nI answer personally. Four short questions — "
               "the more specific your answers, the more concrete the conversation.\n\nWhat do you need?"),
    },
    "project": {
        "ru": ("1/3 · Расскажите о проекте: название компании или канала и ссылка на него.\n\n"
               "Если ссылки нет — просто напишите, чем занимаетесь."),
        "en": ("1/3 · Tell me about the project: company or channel name and a link.\n\n"
               "No link? Just describe what you do."),
    },
    "audience": {
        "ru": ("2/3 · Кто ваша аудитория и какой результат нужен?\n\n"
               "Например: «мужчины 30–45, интерес к теннису, нужны подписчики в канал»."),
        "en": ("2/3 · Who is your audience and what outcome do you need?\n\n"
               "For example: «men 30–45, interested in tennis, need channel subscribers»."),
    },
    "contact": {
        "ru": "3/3 · Как с вами связаться? Telegram-ник, почта или телефон.",
        "en": "3/3 · How can I reach you? Telegram handle, email or phone.",
    },
    "summary": {
        "ru": "Проверьте заявку перед отправкой:\n\n{body}",
        "en": "Check the request before sending:\n\n{body}",
    },
    "sent": {
        "ru": ("✅ **Заявка отправлена.**\n\nЯ прочитаю её лично и отвечу, если задача "
               "окажется мне интересна. Спасибо, что написали."),
        "en": ("✅ **Request sent.**\n\nI read these personally and will reply if the task "
               "looks like a fit. Thank you for reaching out."),
    },
    "failed": {
        "ru": "⚠️ Не удалось отправить заявку. Попробуйте позже или напишите напрямую.",
        "en": "⚠️ Could not send the request. Please try later or contact me directly.",
    },
    "cancelled": {
        "ru": "Заявка отменена.",
        "en": "Request cancelled.",
    },
}

BTN_CANCEL = {"ru": "⛔ Отмена", "en": "⛔ Cancel"}
BTN_SEND = {"ru": "📨 Отправить заявку", "en": "📨 Send request"}
BTN_RESTART = {"ru": "↩️ Заполнить заново", "en": "↩️ Start over"}


def _t(key: str, lang: str) -> str:
    block = T[key]
    return block.get(lang, block["en"])


def _label(mapping: dict, lang: str) -> str:
    return mapping.get(lang, mapping["en"])


def _cancel_markup(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=_label(BTN_CANCEL, lang), callback_data="order_cancel")]])


def _needs_markup(lang: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=_label(meta, lang), callback_data=f"order_need_{key}")]
            for key, meta in NEEDS.items()]
    rows.append([InlineKeyboardButton(text=_label(BTN_CANCEL, lang), callback_data="order_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _summary(data: dict, lang: str) -> str:
    need = NEEDS.get(data.get("need"), {}).get(lang if lang in ("ru", "en") else "en", "—")
    if lang == "ru":
        return (f"<b>Запрос:</b> {need}\n"
                f"<b>Проект:</b> {data.get('project', '—')}\n"
                f"<b>Аудитория и цель:</b> {data.get('audience', '—')}\n"
                f"<b>Контакт:</b> {data.get('contact', '—')}")
    return (f"<b>Request:</b> {need}\n"
            f"<b>Project:</b> {data.get('project', '—')}\n"
            f"<b>Audience and goal:</b> {data.get('audience', '—')}\n"
            f"<b>Contact:</b> {data.get('contact', '—')}")


# =====================================================================
# ХОД ЗАЯВКИ
# =====================================================================

@router.callback_query(F.data == "ads_order")
async def start_order(call: CallbackQuery, state: FSMContext):
    await call.answer()
    lang = await database.get_user_language(call.from_user.id)
    await state.set_state(OrderStates.choosing_need)
    await state.update_data(order_lang=lang)
    await call.message.answer(
        _t("intro", lang), parse_mode="Markdown", reply_markup=_needs_markup(lang)
    )


@router.callback_query(F.data == "order_cancel")
async def cancel_order(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    lang = data.get("order_lang", "ru")
    await state.clear()
    await call.message.edit_text(_t("cancelled", lang))


@router.callback_query(F.data.startswith("order_need_"), OrderStates.choosing_need)
async def pick_need(call: CallbackQuery, state: FSMContext):
    await call.answer()
    need = call.data.removeprefix("order_need_")
    if need not in NEEDS:
        return

    data = await state.get_data()
    lang = data.get("order_lang", "ru")
    await state.update_data(need=need)
    await state.set_state(OrderStates.waiting_project)
    await call.message.edit_text(_t("project", lang), reply_markup=_cancel_markup(lang))


# ~F.text.startswith("/") во всех шагах: иначе состояние съест /start
@router.message(OrderStates.waiting_project, F.text, ~F.text.startswith("/"))
async def take_project(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("order_lang", "ru")
    await state.update_data(project=message.text.strip()[:500])
    await state.set_state(OrderStates.waiting_audience)
    await message.answer(_t("audience", lang), reply_markup=_cancel_markup(lang))


@router.message(OrderStates.waiting_audience, F.text, ~F.text.startswith("/"))
async def take_audience(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("order_lang", "ru")
    await state.update_data(audience=message.text.strip()[:500])
    await state.set_state(OrderStates.waiting_contact)
    await message.answer(_t("contact", lang), reply_markup=_cancel_markup(lang))


@router.message(OrderStates.waiting_contact, F.text, ~F.text.startswith("/"))
async def take_contact(message: Message, state: FSMContext):
    await state.update_data(contact=message.text.strip()[:200])
    data = await state.get_data()
    lang = data.get("order_lang", "ru")
    await state.set_state(OrderStates.confirming)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_label(BTN_SEND, lang), callback_data="order_send")],
        [InlineKeyboardButton(text=_label(BTN_RESTART, lang), callback_data="ads_order")],
        [InlineKeyboardButton(text=_label(BTN_CANCEL, lang), callback_data="order_cancel")],
    ])
    await message.answer(
        _t("summary", lang).format(body=_summary(data, lang)),
        parse_mode="HTML", reply_markup=markup
    )


@router.callback_query(F.data == "order_send", OrderStates.confirming)
async def send_order(call: CallbackQuery, state: FSMContext, bot: Bot):
    await call.answer()
    data = await state.get_data()
    lang = data.get("order_lang", "ru")
    await state.clear()

    user = call.from_user
    handle = f"@{user.username}" if user.username else "без ника"
    header = (f"🔔 <b>Новая заявка на сотрудничество</b>\n\n"
              f"<b>От:</b> {user.full_name} ({handle}, id <code>{user.id}</code>)\n\n")

    try:
        await bot.send_message(
            chat_id=config.ADMIN_ID,
            text=header + _summary(data, "ru"),
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Не удалось доставить заявку владельцу: {type(e).__name__}: {e}")
        await call.message.edit_text(_t("failed", lang))
        return

    await call.message.edit_text(_t("sent", lang), parse_mode="Markdown")
