# block5_game.py
import logging
from aiogram import Router, F
from aiogram.types import (CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, InputMediaPhoto)
from aiogram.exceptions import TelegramBadRequest
import config
import database
import inline_kb

router = Router()

# Полноценная локализация бизнес-квиза на 4 языка
GAME_TEXTS = {
    "ru": {
        "intro": "🎮 **Интерактив**\n\nЗдесь три занятия:\n\n🧩 **Бизнес-квиз** — три реальные ситуации из топ-менеджмента.\n🏎 **Гонка** — ночной город, три полосы, встречный поток.\n🎬 **Мультфильм** — вы пишете историю, бот её снимает.\n\nВыбирайте:",
        "btn_start": "🧩 Бизнес-квиз",
        "q1": "❓ **Ситуация 1**: Ключевой разработчик за день до релиза заявляет, что уходит к конкурентам на х2 оклад. Ваши действия?",
        "q1_a": "🤝 Предложить контр-оффер х2.5",
        "q1_b": "🛑 Заблокировать доступы, дожать релиз силами команды",
        "q1_c": "💬 Поговорить лично, договориться на бонус за передачу дел",
        "q2": "❓ **Ситуация 2**: Заказчик требует бесплатно добавить в проект функцию, которой не было в ТЗ, угрожая расторгнуть контракт. Что делать?",
        "q2_a": "📉 Сделать бесплатно ради сохранения отношений",
        "q2_b": "📝 Показать ТЗ и выставить доп. счет за аудит изменений",
        "q2_c": "⚖ Передать дело юристам и готовиться к суду",
        "q3": "❓ **Ситуация 3**: Бюджет проекта урезан на 30%, но сроки и объем остались прежними. Ваша стратегия?",
        "q3_a": "🔥 Заставить команду работать сверхурочно",
        "q3_b": "✂ Сократить второстепенные фичи (MVP) и согласовать это",
        "q3_c": "📉 Нанять дешевых фрилансеров на часть задач",
        "result": "🏆 **Тест завершен!**\n\nВаш результат: {score} из 9 баллов.\n\n🤖 *Управленческий вердикт*: Вы отлично ориентируетесь в кризисных ситуациях и принимаете взвешенные ROI-решения!"
    },
    "en": {
        "intro": "🎮 **Interactive**\n\nThree things here:\n\n🧩 **Business quiz** — three real situations from top management.\n🏎 **Race** — a neon night city, three lanes, oncoming traffic.\n🎬 **Cartoon** — you write a story, the bot films it.\n\nTake your pick:",
        "btn_start": "🧩 Business quiz",
        "q1": "❓ **Situation 1**: A key developer announces a day before the release that they are leaving for a competitor for x2 salary. Your actions?",
        "q1_a": "🤝 Offer a counter-offer x2.5",
        "q1_b": "🛑 Block access, push release with the remaining team",
        "q1_c": "💬 Talk personally, agree on a bonus for handover",
        "q2": "❓ **Situation 2**: The client demands a free feature not in the scope, threatening to terminate the contract. What to do?",
        "q2_a": "📉 Do it for free to maintain relationships",
        "q2_b": "📝 Show the Scope of Work and issue an invoice for change",
        "q2_c": "⚖ Hand over to lawyers and prepare for court",
        "q3": "❓ **Situation 3**: Project budget cut by 30%, deadlines and scope remain unchanged. Strategy?",
        "q3_a": "🔥 Force the team to work overtime",
        "q3_b": "✂ Cut secondary features (MVP) and re-negotiate",
        "q3_c": "📉 Hire cheap freelancers for part of the tasks",
        "result": "🏆 **Quiz completed!**\n\nYour score: {score} out of 9.\n\n🤖 *Management Verdict*: You navigate crises well and make balanced, high-ROI business decisions!"
    },
    "fr": {
        "intro": "🎮 **Interactif**\n\nTrois choses ici :\n\n🧩 **Quiz business** — trois situations réelles de top management.\n🏎 **Course** — ville de nuit, trois voies, trafic venant en face.\n🎬 **Dessin animé** — vous écrivez, le bot filme.\n\nChoisissez :",
        "btn_start": "🧩 Quiz business",
        "q1": "❓ **Situation 1** : Un développeur clé démissionne la veille de la livraison pour un salaire x2 chez un concurrent. Que faites-vous ?",
        "q1_a": "🤝 Faire une contre-offre x2.5",
        "q1_b": "🛑 Bloquer les accès, livrer avec l'équipe restante",
        "q1_c": "💬 Négocier une prime pour la passation des dossiers",
        "q2": "❓ **Situation 2** : Le client exige une fonctionnalité gratuite non prévue, menaçant de résilier le contrat. Que faire ?",
        "q2_a": "📉 Le faire gratuitement pour préserver la relation",
        "q2_b": "📝 Montrer le contrat et facturer un supplément",
        "q2_c": "⚖ Transmettre aux avocats",
        "q3": "❓ **Situation 3** : Budget réduit de 30%, délais et périmètre inchangés. Votre stratégie ?",
        "q3_a": "🔥 Forcer l'équipe à faire des heures supplémentaires",
        "q3_b": "✂ Réduire les fonctionnalités secondaires (MVP)",
        "q3_c": "📉 Recruter des freelances bon marché",
        "result": "🏆 **Quiz terminé !**\n\nVotre score : {score} sur 9.\n\n🤖 *Verdict* : Vous gérez efficacement les crises et prenez des décisions rentables !"
    },
    "he": {
        "intro": "🎮 **אינטראקטיבי**\n\nשלושה דברים כאן:\n\n🧩 **קוויז עסקי** — שלושה מצבים אמיתיים מהניהול הבכיר.\n🏎 **מרוץ** — עיר לילה, שלושה נתיבים, תנועה נגדית.\n🎬 **סרטון** — אתם כותבים סיפור, הבוט מצלם.\n\nבחרו:",
        "btn_start": "🧩 קוויז עסקי",
        "q1": "❓ **מצב 1**: מפתח מפתח מודיע יום לפני השחרור שהוא עוזב למתחרה עבור שכר כפול. מה עושים?",
        "q1_a": "🤝 הצע הצעה נגדית פי 2.5",
        "q1_b": "🛑 חסום גישה, דחף שחרור עם הצוות הנותר",
        "q1_c": "💬 שוחח אישית, הסכם על בונוס עבור העברת תפקיד",
        "q2": "❓ **מצב 2**: הלקוח דורש תכונה בחינם שלא בחוזה, ומאיים לבטל אותו. מה לעשות?",
        "q2_a": "📉 עשה זאת בחינם כדי לשמור על יחסים",
        "q2_b": "📝 הצג את החוזה והוצא חשבונית נוספת",
        "q2_c": "⚖ העבר לטיפול משפטי והיערך לבית המשפט",
        "q3": "❓ **מצב 3**: תקציב הפרויקט קוצץ ב-30%, לוחות הזמנים נותרו בעינם. אסטרטגיה?",
        "q3_a": "🔥 הכרח את הצוות לעבוד שעות נוספות",
        "q3_b": "✂ קצץ בתכונות משניות (MVP) ונהל מו''מ מחדש",
        "q3_c": "📉 שכור פרילנסרים זולים לחלק מהמשימות",
        "result": "🏆 **הבוחן הסתיים!**\n\nהציון שלך: {score} מתוך 9.\n\n🤖 *פסק דין ניהולי*: אתה מנווט היטב במשברים ומקבל החלטות עסקיות שקולות!"
    }
}

@router.callback_query(F.data == "menu_game")
async def start_game_block(call: CallbackQuery):
    try:
        lang = await database.get_user_language(call.from_user.id)
    except Exception:
        lang = "ru"
    t = GAME_TEXTS.get(lang, GAME_TEXTS["en"])
    
    cartoon_titles = {"ru": "\U0001F3AC Мультфильм по описанию", "en": "\U0001F3AC Cartoon from a description",
                      "fr": "\U0001F3AC Dessin animé sur description", "he": "\U0001F3AC סרטון לפי תיאור"}
    chars_titles = {"ru": "🎨 Мои персонажи", "en": "🎨 My characters",
                    "fr": "🎨 Mes personnages", "he": "🎨 הדמויות שלי"}
    race_titles = {"ru": "🏎 Гонка", "en": "🏎 Race", "fr": "🏎 Course", "he": "🏎 מרוץ"}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_start"], callback_data="game_step1")],
        [InlineKeyboardButton(text=race_titles.get(lang, race_titles["en"]),
                              callback_data="race_open")],
        [InlineKeyboardButton(text=cartoon_titles.get(lang, cartoon_titles["en"]),
                              callback_data="cartoon_open")],
        [InlineKeyboardButton(text=chars_titles.get(lang, chars_titles["en"]),
                              callback_data="char_list")],
        [InlineKeyboardButton(text=inline_kb.label(inline_kb.HOME_TEXTS, lang), callback_data="go_home")]
    ])
    # Свою картинку раздел ставит сам: раньше он лишь переписывал подпись,
    # и наверху оставался снимок предыдущего экрана.
    try:
        await call.message.edit_media(
            media=InputMediaPhoto(media=config.GAME_BANNER, caption=t["intro"],
                                  parse_mode="Markdown"),
            reply_markup=kb)
    except TelegramBadRequest:
        await call.message.edit_caption(caption=t["intro"], reply_markup=kb,
                                        parse_mode="Markdown")
    await call.answer()

@router.callback_query(F.data == "game_step1")
async def game_q1(call: CallbackQuery):
    try:
        lang = await database.get_user_language(call.from_user.id)
    except Exception:
        lang = "ru"
    t = GAME_TEXTS.get(lang, GAME_TEXTS["en"])
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["q1_a"], callback_data="game_q2_1")],
        [InlineKeyboardButton(text=t["q1_b"], callback_data="game_q2_2")],
        [InlineKeyboardButton(text=t["q1_c"], callback_data="game_q2_3")]
    ])
    await call.message.edit_caption(caption=t["q1"], reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@router.callback_query(F.data.startswith("game_q2_"))
async def game_q2(call: CallbackQuery):
    current_score = int(call.data.split("_")[-1])
    try:
        lang = await database.get_user_language(call.from_user.id)
    except Exception:
        lang = "ru"
    t = GAME_TEXTS.get(lang, GAME_TEXTS["en"])
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["q2_a"], callback_data=f"game_q3_{current_score + 1}")],
        [InlineKeyboardButton(text=t["q2_b"], callback_data=f"game_q3_{current_score + 3}")],
        [InlineKeyboardButton(text=t["q2_c"], callback_data=f"game_q3_{current_score + 2}")]
    ])
    await call.message.edit_caption(caption=t["q2"], reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@router.callback_query(F.data.startswith("game_q3_"))
async def game_q3(call: CallbackQuery):
    current_score = int(call.data.split("_")[-1])
    try:
        lang = await database.get_user_language(call.from_user.id)
    except Exception:
        lang = "ru"
    t = GAME_TEXTS.get(lang, GAME_TEXTS["en"])
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["q3_a"], callback_data=f"game_end_{current_score + 1}")],
        [InlineKeyboardButton(text=t["q3_b"], callback_data=f"game_end_{current_score + 3}")],
        [InlineKeyboardButton(text=t["q3_c"], callback_data=f"game_end_{current_score + 2}")]
    ])
    await call.message.edit_caption(caption=t["q3"], reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@router.callback_query(F.data.startswith("game_end_"))
async def game_end(call: CallbackQuery):
    final_score = int(call.data.split("_")[-1])
    try:
        lang = await database.get_user_language(call.from_user.id)
    except Exception:
        lang = "ru"
    t = GAME_TEXTS.get(lang, GAME_TEXTS["en"])
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=inline_kb.label(inline_kb.HOME_TEXTS, lang), callback_data="go_home")]
    ])
    await call.message.edit_caption(caption=t["result"].format(score=final_score), reply_markup=kb, parse_mode="Markdown")
    await call.answer()
