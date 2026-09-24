# tools/make_card.py — картинка к посту, собранная на своей машине.
#
# Пост со ссылкой Telegram показывает мелким превью из App Store: чужая
# иконка, чужой шрифт, обрезанный текст. Своя картинка занимает в ленте
# втрое больше места и говорит то, что нужно вам.
#
# Рисуем локально, а не в чужом сервисе: текст на картинке — часть
# редакционной работы, и отдавать его наружу ради шаблона незачем.
#
#   python3 tools/make_card.py "Заголовок" "Подзаголовок" "Приписка"
import os
import sys

from PIL import Image, ImageDraw, ImageFont

# Эмодзи в этих шрифтах нет: вместо смайлика рисуется пустой квадрат.
# В подписи к карточке они и не нужны — их место в тексте поста.

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "cards")

# Два формата, и они не взаимозаменяемы.
#
# Пост в ленте: картинка шире экрана обрезается по бокам, вертикальная
# занимает пол-экрана и раздражает. 1280×720 везде выглядит одинаково.
#
# История: экран телефона целиком, 9:16. Горизонтальная картинка в
# истории превращается в полоску посередине с пустотой сверху и снизу —
# её пролистывают, не дочитав.
SHAPES = {
    "post": (1280, 720),      # горизонтальная, для ссылок и превью
    "feed": (1080, 1350),     # вертикальная в ленте: занимает втрое больше
    "story": (1080, 1920),    # история, экран телефона целиком
}

# Раскладка вертикальных: доли высоты, а не пиксели. 4:5 и 9:16
# отличаются на шестьсот точек, и подписанные вручную координаты
# развалились бы на одном из них.
TALL = {
    "feed": {"sign": 0.055, "title": 0.105, "watch": 0.44,
             "size": 0.46, "cta": 0.855},
    # История: сверху Telegram рисует аватар, имя и время, снизу — поле
    # ответа и вложенную ссылку. Всё, что попадёт в эти полосы, читатель
    # не увидит вовсе. Поэтому содержимое живёт между ними, а не по
    # краям картинки.
    "story": {"sign": 0.135, "title": 0.185, "watch": 0.45,
              "size": 0.50, "cta": 0.735},
}
SIZE = SHAPES["post"]

# Тёмный фон: посты читают вечером и с телефона, а белый прямоугольник в
# ленте бьёт по глазам. Акцент — теннисный жёлтый, он же цвет мяча.
BACK = (14, 17, 22)
INK = (232, 234, 240)
DIM = (138, 144, 160)
ACCENT = (214, 232, 58)

# Цвета с настоящего экрана приложения: своё очко — зелёное, чужое —
# голубое. Карточка должна показывать то, что человек увидит на часах,
# иначе она обещает одно, а он получает другое.
MINE = (154, 226, 74)        # своё очко
THEIRS = (92, 225, 230)      # очко соперника
FRESH = (240, 50, 80)        # «Новая игра» — единственная красная
MUTED = (40, 42, 48)         # «Отменить»
GHOST = (26, 28, 33)         # «Считать без бота», приглушённая

# Подписи на самом экране часов. В английской рекламе русские кнопки
# выглядят чужими: человек решает, что приложение не для него.
LABELS = {
    "ru": ("Отменить", "Новая игра", "Считать без бота"),
    "en": ("Undo", "New game", "Count without bot"),
    "fr": ("Annuler", "Nouvelle partie", "Compter sans bot"),
}

FONTS = "/System/Library/Fonts/Supplemental/"


def font(name: str, size: int):
    try:
        return ImageFont.truetype(os.path.join(FONTS, name), size)
    except OSError:
        return ImageFont.load_default()


def wrap(draw, text: str, typeface, width: int) -> list:
    """Разбить строку по словам под заданную ширину"""
    words, lines, row = text.split(), [], ""
    for word in words:
        trial = f"{row} {word}".strip()
        if draw.textlength(trial, font=typeface) <= width:
            row = trial
        else:
            if row:
                lines.append(row)
            row = word
    if row:
        lines.append(row)
    return lines


def fitted(draw, text: str, name: str, start: int, limit: float):
    """Шрифт, при котором строка помещается в отведённую ширину"""
    size = start
    while size > 10:
        typeface = font(name, size)
        if draw.textlength(text, font=typeface) <= limit:
            return typeface
        size -= 2
    return font(name, 10)


def key(draw, box, colour, text, typeface, ink=(255, 255, 255)):
    """Клавиша с подписью по центру"""
    left, top, right, bottom = box
    height = bottom - top
    draw.rounded_rectangle(box, radius=height / 2, fill=colour)
    width = draw.textlength(text, font=typeface)
    draw.text((left + (right - left - width) / 2,
               top + (height - typeface.size * 1.2) / 2),
              text, font=typeface, fill=ink)


def watch(draw, x: int, y: int, size: int, top: str, bottom: str,
          lang: str = "ru"):
    """Экран часов целиком, со всеми клавишами.

    Цвета не украшение, а смысл: зелёная — своё очко, голубая — чужое,
    красная — начать заново. Выкинуть красную, как я сделала в первой
    версии, значит сломать схему: остаются две холодные клавиши и серый
    низ, и экран выглядит плоским, хотя в жизни он яркий.
    """
    draw.rounded_rectangle([x, y, x + size, y + size], radius=size // 4,
                           fill=(8, 8, 10), outline=(48, 52, 62), width=3)

    line = fitted(draw, top, "Arial Bold.ttf", int(size * 0.105), size * 0.66)
    width = draw.textlength(top, font=line)
    draw.text((x + (size - width) / 2, y + size * 0.10), top, font=line,
              fill=INK)

    pad = size * 0.08
    gap = size * 0.05
    key_w = (size - pad * 2 - gap) / 2
    key_h = size * 0.24
    key_y = y + size * 0.27

    points = [p.strip() for p in bottom.split("|")]
    points = (points + ["0", "0"])[:2]
    for i, (value, colour) in enumerate(zip(points, (MINE, THEIRS))):
        left = x + pad + i * (key_w + gap)
        face = fitted(draw, value, "Arial Bold.ttf", int(key_h * 0.66),
                      key_w * 0.62)
        key(draw, [left, key_y, left + key_w, key_y + key_h], colour,
            value, face)

    # Три полосы под очками — ровно как на часах.
    # Три полосы должны уложиться до скругления: нижняя иначе уезжает
    # в угол и выглядит обрезанной.
    bar_h = size * 0.10
    step = bar_h + size * 0.032
    small = font("Arial.ttf", int(size * 0.072))
    names = LABELS.get(lang, LABELS["ru"])
    rows = list(zip(names, (MUTED, FRESH, GHOST),
                    (DIM, (255, 255, 255), (96, 100, 112))))
    for i, (label, colour, ink) in enumerate(rows):
        bar_y = key_y + key_h + size * 0.045 + i * step
        key(draw, [x + pad, bar_y, x + size - pad, bar_y + bar_h],
            colour, label, small, ink)


def pill(draw, x: int, y: int, text: str, size: int, colour=FRESH):
    """Кнопка-призыв на самой карточке: глаз цепляется за цвет раньше,
    чем читает буквы, и понимает, что действие бесплатное."""
    typeface = font("Arial Bold.ttf", size)
    width = draw.textlength(text, font=typeface)
    pad_x, pad_y = size * 0.9, size * 0.55
    draw.rounded_rectangle(
        [x, y, x + width + pad_x * 2, y + size * 1.2 + pad_y * 2],
        radius=(size * 1.2 + pad_y * 2) / 2, fill=colour)
    draw.text((x + pad_x, y + pad_y), text, font=typeface,
              fill=(255, 255, 255))
    return y + size * 1.2 + pad_y * 2


def card(title: str, subtitle: str = "", note: str = "",
         name: str = "card.png", face: tuple = None,
         shape: str = "post", lang: str = "ru", author: str = "") -> str:
    """Рекламная карточка: заголовок, экран приложения и призыв.

    Note здесь — текст на красной кнопке, а не подпись мелким шрифтом:
    карточка должна звать, а не сообщать.
    """
    size = SHAPES.get(shape, SHAPES["post"])
    tall = shape in TALL
    plan = TALL.get(shape, TALL["story"])

    image = Image.new("RGB", size, BACK)
    draw = ImageDraw.Draw(image)

    # Полоса сверху — из цветов приложения, а не одна жёлтая: она задаёт
    # палитру раньше, чем глаз дойдёт до экрана часов.
    band = 14 if tall else 10
    parts = [MINE, THEIRS, FRESH]
    step = size[0] / len(parts)
    for i, colour in enumerate(parts):
        draw.rectangle([i * step, 0, (i + 1) * step, band], fill=colour)

    margin = 80 if tall else 90
    big = font("Arial Bold.ttf", 96 if tall else 80)
    mid = font("Arial.ttf", 46 if tall else 38)

    # Подпись автора — над заголовком и вразрядку. Это не «ещё одно
    # приложение»: у него есть человек, и человек хочет, чтобы его имя
    # читали раньше, чем описание.
    if author:
        # Вразрядку — только короткое имя. Двойная подпись «как знают
        # там и как знают здесь» с промежутками расползается на всю
        # ширину и перестаёт читаться как имя.
        sign = font("Arial Bold.ttf", 28 if tall else 24)
        text = author.upper()
        if len(text) <= 22:
            text = " ".join(text)
        draw.text((margin, size[1] * plan["sign"] if tall else 70),
                  text, font=sign, fill=ACCENT)

    if tall:
        width = size[0] - margin * 2
        y = size[1] * plan["title"]
        for line in wrap(draw, title, big, width):
            draw.text((margin, y), line, font=big, fill=INK)
            y += big.size * 1.16

        if subtitle:
            y += 26
            for line in wrap(draw, subtitle, mid, width):
                draw.text((margin, y), line, font=mid, fill=DIM)
                y += mid.size * 1.3

        if face:
            screen = int(size[0] * plan["size"])
            watch(draw, (size[0] - screen) // 2, int(size[1] * plan["watch"]),
                  screen, face[0], face[1], lang)

        if note:
            pill(draw, margin, int(size[1] * plan["cta"]), note, 46)
    else:
        screen = 420 if face else 0
        width = size[0] - margin * 2 - (screen + 40 if face else 0)
        y = 150
        if face:
            watch(draw, size[0] - margin - screen, 160, screen,
                  face[0], face[1], lang)

        for line in wrap(draw, title, big, width):
            draw.text((margin, y), line, font=big, fill=INK)
            y += 94

        if subtitle:
            y += 20
            for line in wrap(draw, subtitle, mid, width):
                draw.text((margin, y), line, font=mid, fill=DIM)
                y += 52

        if note:
            pill(draw, margin, size[1] - 150, note, 42)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    image.save(path, "PNG")
    return path


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Карточка к посту")
    parser.add_argument("--title", required=True)
    parser.add_argument("--sub", default="")
    parser.add_argument("--cta", default="", help="текст на красной кнопке")
    parser.add_argument("--name", default="card.png")
    parser.add_argument("--score", default="", help="строка геймов: «4 : 3»")
    parser.add_argument("--points", default="", help="очки через |: «30|15»")
    parser.add_argument("--shape", default="post", choices=list(SHAPES))
    parser.add_argument("--lang", default="ru", choices=list(LABELS))
    parser.add_argument("--author", default="")
    args = parser.parse_args()

    face = (args.score, args.points) if args.score and args.points else None
    print(card(args.title, args.sub, args.cta, args.name, face,
               args.shape, args.lang, args.author))
    return 0


if __name__ == "__main__":
    sys.exit(main())
