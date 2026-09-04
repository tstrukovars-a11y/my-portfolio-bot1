# checklist.py — один экран «чего не хватает».
#
# Данные для этого были и раньше, но по разным командам: книги без обложек в
# одной, места без фото в другой, ссылки в третьей. Держать в голове семь
# команд, чтобы понять, что мешает публикации, — работа, которой быть не
# должно.
#
# Считаем на лету, ничего не храня: любая сохранённая сводка врёт на
# следующий день после первой же загруженной фотографии.
import html

from aiogram import Router, F
from aiogram.types import Message

import config
import database

router = Router()

MAX_NAMES = 6      # длиннее список не читается, дальше — по своей команде


def _line(title: str, missing: int, total: int, command: str) -> str:
    if not missing:
        return f"✅ {title} — всё на месте ({total})"
    return (f"⚠️ <b>{title}</b> — не хватает у {missing} из {total}\n"
            f"    {command}")


def _names(rows) -> str:
    """Первые несколько названий — чтобы было видно, о чём речь.

    У книг название во втором столбце, у мест — в третьем, у
    достопримечательностей — в четвёртом. Берём последний: он везде
    оказывается тем, что человек читает.
    """
    shown = [html.escape(str(r[-1])[:38]) for r in rows[:MAX_NAMES]]
    tail = f" и ещё {len(rows) - MAX_NAMES}" if len(rows) > MAX_NAMES else ""
    return "    " + "; ".join(shown) + tail


@router.message(F.text.startswith(("/todo", "/чего")))
async def todo(message: Message):
    """Что мешает публиковать: по разделам, с командой для починки"""
    if not config.is_admin(message.from_user.id):
        return

    lines = ["🧾 <b>Чего не хватает</b>", ""]

    # --- книги -------------------------------------------------------
    stats = await database.books_link_stats()
    no_link = await database.books_without_link()
    no_cover = await database.books_without_cover(100)
    lines.append(_line("Книги: партнёрские ссылки", len(no_link),
                       stats.get("total", 0), "<code>/book_links</code>"))
    if no_link:
        lines.append(_names(no_link))
    lines.append(_line("Книги: обложки", len(no_cover), stats.get("total", 0),
                       "<code>/book_covers</code>"))
    if no_cover:
        lines.append(_names(no_cover))
    lines.append("")

    # --- путешествия -------------------------------------------------
    places = await database.travel_without_photo(200)
    lines.append(_line("Города и места: фото", len(places),
                       await database.count_travel_places(),
                       "<code>/travel_photos</code>"))
    if places:
        lines.append(_names(places))

    spots = await database.spots_without_photo(200)
    lines.append(_line("Достопримечательности: фото", len(spots),
                       await database.count_spots(),
                       "<code>/spot_photos</code>"))
    if spots:
        lines.append(_names(spots))
    lines.append("")

    # --- картины -----------------------------------------------------
    works = await database.art_list()
    no_photo = [w for w in works if not w.get("photo_file_id")]
    if works:
        lines.append(_line("Картины: фото", len(no_photo), len(works),
                           "<code>/art_list</code>"))
        in_channel = sum(1 for w in works if w.get("channel_msg_id"))
        if in_channel < len(works):
            lines.append(f"⚠️ <b>Картины: не в канале</b> — "
                         f"{len(works) - in_channel} из {len(works)}\n"
                         f"    <code>/art_publish</code>")
        lines.append("")

    # --- очередь публикаций ------------------------------------------
    # Буфер считает то же самое с другой стороны: не «чего нет у материала»,
    # а «что из-за этого не выйдет».
    lines += ["<i>Что именно не выйдет в канал и почему — "
              "<code>/buffer</code></i>"]

    await message.answer("\n".join(lines))
