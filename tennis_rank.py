# tennis_rank.py — рейтинг тура и свои написания имён, без правки кода.
#
# Раньше «первая двадцатка» лежала списком в исходнике и устаревала: рейтинг
# меняется каждую неделю, а деплой ради двух фамилий никто делать не станет.
# ESPN отдаёт полторы сотни мест обоих туров и обновляет их еженедельно —
# берём оттуда.
#
# «Свои» тоже вычисляются сами: по флагу, а для уехавших — по месту
# рождения, которое ESPN отдаёт вместе с рейтингом. Рыбакина играет за
# Казахстан, но родилась в Москве, и для аудитории она своя. Ручной список
# в players_ru остался запасным — на тех, кого рейтинг не застал.
import asyncio
import logging

import httpx
from aiogram import Router, F, Bot
from aiogram.types import Message

import config
import database
import players_ru

router = Router()

URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/rankings"
HEADERS = {"User-Agent": "Mozilla/5.0"}
KEEP = 60                 # столько мест храним: с запасом на травмы и откаты
NOTABLE_PLACE = 25        # кого считаем сильнейшими для анонса
REFRESH_HOURS = 24 * 7    # ESPN обновляет раз в неделю, чаще незачем
RUSSIAN_FLAGS = {"rus", "russia"}


async def _fetch(tour: str):
    """[(место, имя, страна)] либо пусто"""
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            response = await client.get(URL.format(tour=tour), headers=HEADERS)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logging.error(f"Рейтинг {tour} не скачался: {e}")
        return []

    out = []
    for section in data.get("rankings") or []:
        for row in section.get("ranks") or []:
            place = row.get("current")
            athlete = row.get("athlete") or {}
            name = athlete.get("displayName")
            if not place or not name or place > KEEP:
                continue

            # В рейтинге флаг приходит строкой-адресом, в табло — объектом.
            # Терпим оба вида, иначе обновление падает при смене формата.
            flag = athlete.get("flag")
            href = flag if isinstance(flag, str) else (flag or {}).get("href") or ""
            country = href.rsplit("/", 1)[-1].split(".")[0] if href else ""

            # Место рождения выдаёт уехавших: Рыбакина играет за Казахстан,
            # но родилась в Москве, и для аудитории она своя.
            born = ((athlete.get("birthPlace") or {}).get("summary") or "")
            if "russia" in born.lower():
                country = country or "rus"
                out.append((int(place), name, "rus"))
                continue
            out.append((int(place), name, country))
    return out


async def refresh() -> str:
    """Скачать рейтинг обоих туров и применить его на месте"""
    saved = 0
    for tour in ("atp", "wta"):
        rows = await _fetch(tour)
        if rows:
            saved += await database.save_ranking(tour, rows)
    if not saved:
        return "рейтинг недоступен — оставила прежний"
    await apply()
    return f"рейтинг обновлён: {saved} мест"


async def apply() -> str:
    """Поднять рейтинг и свои написания из базы в память процесса"""
    pairs = await database.ranking_names(NOTABLE_PLACE)
    top = players_ru.set_top([name for name, _ in pairs])

    # Россиян из рейтинга добавляем в круг своих автоматически: список
    # фамилий в коде так не надо править после каждого новичка.
    ours = 0
    for name, country in pairs:
        if (country or "").lower() in RUSSIAN_FLAGS:
            players_ru.add_nash(name)
            ours += 1

    names = players_ru.set_overrides(await database.player_names())
    return f"в анонсе: {top} сильнейших (из них наших {ours}), своих имён {names}"


async def scheduler():
    """Раз в неделю подтягивает свежий рейтинг"""
    await asyncio.sleep(120)
    while True:
        try:
            logging.info(f"Теннис: {await refresh()}")
        except Exception as e:
            logging.error(f"Обновление рейтинга сорвалось: {e}")
        await asyncio.sleep(REFRESH_HOURS * 3600)


# =====================================================================
# КОМАНДЫ
# =====================================================================

@router.message(F.text.startswith("/tennis_rank"))
async def rank_command(message: Message):
    if not config.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) > 1 and parts[1].lower() in ("обновить", "refresh"):
        await message.answer("⏳ Тяну рейтинг…")
        await message.answer(f"✅ {await refresh()}\n{await apply()}")
        return

    updated = await database.ranking_updated()
    lines = ["🎾 <b>Рейтинг для анонсов</b>", ""]
    lines.append(f"Обновлён: {updated:%d.%m %H:%M}" if updated
                 else "Ещё не загружался.")
    lines.append(f"В анонс идут первые {NOTABLE_PLACE} мест и все свои.")
    for tour in ("atp", "wta"):
        rows = await database.ranking_top(tour, 10)
        if rows:
            lines += ["", f"<b>{tour.upper()}</b>"]
            lines += [f"{p}. {players_ru.ru(n)}" for p, n in rows]
    lines += ["", "Обновить сейчас: <code>/tennis_rank обновить</code>",
              "Поправить имя: <code>/tennis_name Dane Sweeny = Дейн Суини</code>"]
    await message.answer("\n".join(lines))


@router.message(F.text.startswith("/tennis_name"))
async def name_command(message: Message):
    """Своё написание имени: то, чего нет в словаре или написано неверно"""
    if not config.is_admin(message.from_user.id):
        return
    body = message.text.split(maxsplit=1)
    if len(body) < 2 or "=" not in body[1]:
        await message.answer(
            "Нужно так: <code>/tennis_name Dane Sweeny = Дейн Суини</code>\n\n"
            "Слева — как пишет источник (латиницей), справа — как надо "
            "по-русски. Посмотреть, как бот пишет сейчас: "
            "<code>/tennis_who Dane Sweeny</code>")
        return
    en, ru = body[1].split("=", 1)
    if not await database.set_player_name(en.strip(), ru.strip()):
        await message.answer("❌ Не сохранилось")
        return
    players_ru.set_overrides(await database.player_names())
    await message.answer(f"✅ {en.strip()} → {ru.strip()}")


@router.message(F.text.startswith("/tennis_who"))
async def who_command(message: Message):
    """Как бот напишет это имя и попадёт ли матч в анонс"""
    if not config.is_admin(message.from_user.id):
        return
    body = message.text.split(maxsplit=1)
    if len(body) < 2:
        await message.answer("Например: <code>/tennis_who Elena Rybakina</code>")
        return
    name = body[1].strip()
    await message.answer(
        f"<b>{name}</b>\n"
        f"По-русски: {players_ru.ru(name)}\n"
        f"Свой: {'да' if players_ru.is_nash(name) else 'нет'}\n"
        f"В первых {NOTABLE_PLACE}: {'да' if players_ru.is_top(name) else 'нет'}\n"
        f"Попадёт в анонс: "
        f"{'да' if players_ru.notable(name) else 'нет — только в сетку'}")
