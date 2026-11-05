#  draw_image.py — картинка сетки и аватарки участников.
#
#  ЗАЧЕМ АВАТАРКИ СВОИ, А НЕ ИЗ TELEGRAM. Фотографию профиля человек
#  ставил для друзей, а не для общей рассылки: увидеть своё лицо в
#  картинке, которую получили все участники, он не ожидает. Поэтому знак
#  выдаём мы — цвет и фигура, посчитанные из номера. У одного человека он
#  всегда один и тот же, так что в сетке он узнаёт себя сразу, а чужого
#  лица там нет.
#
#  ПРО ШРИФТ. Фамилии кириллицей, а готового шрифта в проекте нет:
#  tools/make_card.py берёт Arial из системных папок macOS, которых на
#  Render не существует. Поэтому ищем по цепочке и ГРОМКО пишем в лог,
#  если дошли до запасного варианта: молча нарисованные квадратики вместо
#  фамилий — худший исход.
#
#  Чтобы этого не случилось, положите свободный шрифт с кириллицей в
#  data/fonts/ (например DejaVuSans.ttf). Arial с macOS туда класть
#  нельзя — он лицензионный.

import io
import logging
import os
from pathlib import Path

FONT_DIR = Path(__file__).parent / "data" / "fonts"

# По убыванию предпочтения: своё, потом типичный Linux, потом macOS.
FONT_CANDIDATES = (
    FONT_DIR / "DejaVuSans.ttf",
    FONT_DIR / "DejaVuSans-Bold.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
)

# Двенадцать различимых цветов. Не радуга ради радуги: соседние по списку
# заметно отличаются и в мелком размере, и у людей с цветовой слепотой —
# поэтому рядом с цветом всегда стоит ещё и фигура.
PALETTE = (
    (214, 69, 65), (232, 130, 40), (221, 184, 36), (126, 173, 48),
    (46, 150, 92), (38, 150, 150), (48, 118, 196), (86, 86, 188),
    (140, 78, 180), (196, 70, 140), (120, 100, 86), (90, 100, 110),
)
SHAPES = ("circle", "square", "triangle", "diamond", "ring", "bar", "cross")

BG = (247, 247, 243)
CARD = (255, 255, 255)
LINE = (190, 192, 186)
INK = (32, 34, 30)
MUTED = (120, 124, 116)
WIN = (46, 150, 92)

_font_cache = {}
_warned = False


def _font(size: int):
    """Шрифт нужного размера. Нет ни одного — пишем в лог и рисуем тем,
    что есть у Pillow: подписи будут хуже, но картинка выйдет."""
    global _warned
    if size in _font_cache:
        return _font_cache[size]
    from PIL import ImageFont

    for path in FONT_CANDIDATES:
        try:
            if os.path.exists(path):
                _font_cache[size] = ImageFont.truetype(str(path), size)
                return _font_cache[size]
        except Exception:
            continue

    if not _warned:
        logging.error(
            "Сетка: шрифт с кириллицей не найден — фамилии могут выйти "
            "нечитаемыми. Положите DejaVuSans.ttf в data/fonts/")
        _warned = True
    try:
        _font_cache[size] = ImageFont.load_default(size)
    except TypeError:          # Pillow до 10-й: размер не принимается
        _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]


def mark_of(user_id: int):
    """(цвет, фигура) этого участника. Одинаковые у него всегда.

    Номер сначала перемешиваем, а потом уже делим. Без этого соседние
    номера давали ОДНУ И ТУ ЖЕ фигуру — делитель у них общий, — и вся
    сетка выходила с одинаковыми значками разного цвета. Множитель
    взят из Кнута, никакой магии: он просто хорошо размазывает близкие
    числа.
    """
    number = abs(int(user_id))
    mixed = (number * 2654435761) % (2 ** 32)
    return (PALETTE[mixed % len(PALETTE)],
            SHAPES[(mixed // len(PALETTE)) % len(SHAPES)])


def avatar(user_id: int, size: int = 64):
    """Кружок с фигурой — знак участника."""
    from PIL import Image, ImageDraw

    colour, shape = mark_of(user_id)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, size - 1, size - 1), fill=colour)

    pad = size * 0.3
    box = (pad, pad, size - pad, size - pad)
    white = (255, 255, 255, 235)
    if shape == "circle":
        draw.ellipse(box, fill=white)
    elif shape == "square":
        draw.rectangle(box, fill=white)
    elif shape == "triangle":
        draw.polygon([(size / 2, pad), (size - pad, size - pad),
                      (pad, size - pad)], fill=white)
    elif shape == "diamond":
        draw.polygon([(size / 2, pad), (size - pad, size / 2),
                      (size / 2, size - pad), (pad, size / 2)], fill=white)
    elif shape == "ring":
        draw.ellipse(box, outline=white, width=max(2, int(size * 0.09)))
    elif shape == "bar":
        draw.rectangle((pad, size * 0.44, size - pad, size * 0.56), fill=white)
    else:  # cross
        thick = max(2, int(size * 0.1))
        draw.rectangle((size / 2 - thick / 2, pad,
                        size / 2 + thick / 2, size - pad), fill=white)
        draw.rectangle((pad, size / 2 - thick / 2,
                        size - pad, size / 2 + thick / 2), fill=white)
    return img


def _short(name: str, limit: int = 14) -> str:
    name = (name or "").strip() or "участник"
    return name if len(name) <= limit else name[:limit - 1] + "…"


def column_titles(rounds: list) -> list:
    """Подписи колонок. Последняя — «Финал и матч за третье место»,
    потому что они и правда идут в одном окне: без подписи из четырёх
    боксов подряд не понять, кто за что играет."""
    import draw_bracket

    titles = []
    for index, participants in enumerate(rounds):
        last = index == len(rounds) - 1
        if last and len(participants) >= 4:
            titles.append("Финал и матч за третье место")
        elif last:
            titles.append("Финал")
        else:
            # По числу МЕСТ, а не живых участников. Шесть игроков в сетке
            # на восемь — это четвертьфинал с двумя проходами, а не
            # «1/3 финала», как выходило, пока считали живых.
            titles.append(draw_bracket.round_name(len(participants)))
    return titles


def render(rounds: list, names: dict, scores: dict = None,
           title: str = "Сетка розыгрыша") -> bytes:
    """PNG сетки.

    rounds — список кругов, каждый круг это список участников по местам
    (None означает пропуск круга). names — {участник: имя}, scores —
    {участник: счёт в игре}, если он уже есть.
    """
    from PIL import Image, ImageDraw

    scores = scores or {}
    rounds = [r for r in rounds if r]
    if not rounds:
        rounds = [[None, None]]

    box_w, box_h, gap_x = 230, 64, 70
    gap_y = 18
    pad = 34
    head = 92      # заголовок плюс строка с названием круга

    tallest = len(rounds[0])
    width = pad * 2 + len(rounds) * box_w + (len(rounds) - 1) * gap_x
    height = head + pad + tallest * (box_h + gap_y)

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    draw.text((pad, 22), title, font=_font(30), fill=INK)

    titles = column_titles(rounds)
    for index, name in enumerate(titles):
        draw.text((pad + index * (box_w + gap_x), head - 14), name,
                  font=_font(17), fill=MUTED)

    # Центры мест по кругам: каждый следующий круг стоит посередине между
    # двумя своими родителями — так линии сходятся, а не пересекаются
    centres = []
    def previous_len(done):
        return len(done[-1]) if done else 0

    for index, participants in enumerate(rounds):
        if index == 0:
            step = box_h + gap_y
            top = head + pad
            centres.append([top + step * i + box_h / 2
                            for i in range(len(participants))])
        elif len(participants) * 2 == previous_len(centres):
            # Обычный круг: вдвое меньше предыдущего. Каждое место встаёт
            # посередине между двумя своими родителями — так линии
            # сходятся, а не пересекаются.
            previous = centres[-1]
            centres.append([(previous[2 * i] + previous[2 * i + 1]) / 2
                            for i in range(len(participants))])
        else:
            # ПОСЛЕДНИЙ КРУГ НЕ ВДВОЕ МЕНЬШЕ: финал и матч за третье
            # место играются вместе, и мест в нём столько же, сколько в
            # полуфинале. Раскладываем их ровным столбцом по центру
            # колонки — соединять попарно здесь нечего.
            previous = centres[-1]
            span = previous[-1] - previous[0] if len(previous) > 1 else 0
            top = previous[0] + (span - (len(participants) - 1)
                                 * (box_h + gap_y)) / 2
            centres.append([top + i * (box_h + gap_y)
                            for i in range(len(participants))])

    for index, participants in enumerate(rounds):
        x = pad + index * (box_w + gap_x)
        for position, user_id in enumerate(participants):
            y = centres[index][position] - box_h / 2

            # Линия к следующему кругу — только если он вдвое меньше.
            # У последнего круга родителя нет: финал и бронза идут
            # рядом, соединять их не с чем.
            halves = (index + 1 < len(rounds)
                      and len(rounds[index + 1]) * 2 == len(participants))
            if halves:
                parent = centres[index + 1][position // 2]
                mid = x + box_w + gap_x / 2
                draw.line((x + box_w, centres[index][position],
                           mid, centres[index][position]), fill=LINE, width=2)
                draw.line((mid, centres[index][position], mid, parent),
                          fill=LINE, width=2)
                draw.line((mid, parent, x + box_w + gap_x, parent),
                          fill=LINE, width=2)

            draw.rounded_rectangle((x, y, x + box_w, y + box_h), radius=10,
                                   fill=CARD, outline=LINE, width=2)
            if user_id is None:
                draw.text((x + 18, y + box_h / 2 - 11), "проход без игры",
                          font=_font(18), fill=MUTED)
                continue

            face = avatar(user_id, 44)
            img.paste(face, (int(x + 12), int(y + 10)), face)
            draw.text((x + 68, y + 12), _short(names.get(user_id, "")),
                      font=_font(21), fill=INK)
            score = scores.get(user_id)
            draw.text((x + 68, y + 38),
                      f"розыгрыш: {score}" if score is not None else "ещё не играл",
                      font=_font(16), fill=WIN if score is not None else MUTED)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
