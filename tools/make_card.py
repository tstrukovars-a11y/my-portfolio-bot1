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
    "post": (1280, 720),
    "story": (1080, 1920),
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
MINE = (154, 226, 74)
THEIRS = (92, 225, 230)

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


def watch(draw, x: int, y: int, size: int, top: str, bottom: str):
    """Экран часов, как он выглядит в игре.

    Сверху строка геймов и сетов, под ней два очка — своё и соперника,
    каждое на своей клавише. Так устроено настоящее приложение: очко
    ставится касанием цветного прямоугольника, и именно это надо
    показать, а не абстрактный счёт посередине.
    """
    draw.rounded_rectangle([x, y, x + size, y + size], radius=size // 4,
                           fill=(10, 10, 12), outline=(44, 48, 58), width=3)

    line = fitted(draw, top, "Arial Bold.ttf", size // 8, size * 0.7)
    width = draw.textlength(top, font=line)
    draw.text((x + (size - width) / 2, y + size * 0.14), top, font=line,
              fill=INK)

    # Две клавиши в ряд, с полями по краям и просветом посередине.
    pad = size * 0.09
    gap = size * 0.06
    key_w = (size - pad * 2 - gap) / 2
    key_h = size * 0.30
    key_y = y + size * 0.36

    points = [p.strip() for p in bottom.split("|")]
    if len(points) < 2:
        points = (points + ["0", "0"])[:2]

    for i, (value, colour) in enumerate(zip(points, (MINE, THEIRS))):
        left = x + pad + i * (key_w + gap)
        draw.rounded_rectangle([left, key_y, left + key_w, key_y + key_h],
                               radius=key_h // 2, fill=colour)
        face = fitted(draw, value, "Arial Bold.ttf", int(key_h * 0.62),
                      key_w * 0.7)
        width = draw.textlength(value, font=face)
        top_pad = (key_h - face.size * 1.15) / 2
        draw.text((left + (key_w - width) / 2, key_y + top_pad), value,
                  font=face, fill=(255, 255, 255))

    # Нижняя клавиша — «Отменить»: она есть на экране и объясняет, что
    # промах не страшен.
    bar_y = key_y + key_h + size * 0.08
    draw.rounded_rectangle([x + pad, bar_y, x + size - pad,
                            bar_y + size * 0.12],
                           radius=size * 0.06, fill=(40, 42, 48))
    label = fitted(draw, "Отменить", "Arial.ttf", int(size * 0.075),
                   size * 0.5)
    width = draw.textlength("Отменить", font=label)
    draw.text((x + (size - width) / 2, bar_y + size * 0.021), "Отменить",
              font=label, fill=DIM)


def card(title: str, subtitle: str = "", note: str = "",
         name: str = "card.png", face: tuple = None,
         shape: str = "post") -> str:
    size = SHAPES.get(shape, SHAPES["post"])
    tall = shape == "story"

    image = Image.new("RGB", size, BACK)
    draw = ImageDraw.Draw(image)

    # Полоса сверху вместо логотипа: узнаваемо, ничего не весит и не
    # спорит с текстом.
    draw.rectangle([0, 0, size[0], 10 if not tall else 14], fill=ACCENT)

    margin = 90 if not tall else 80
    big = font("Arial Bold.ttf", 78 if not tall else 96)
    mid = font("Arial.ttf", 40 if not tall else 46)
    small = font("Arial.ttf", 30 if not tall else 38)

    if tall:
        # В истории читают сверху вниз и большим пальцем: заголовок
        # вверху, циферблат в середине, ссылка внизу — там, где палец.
        width = size[0] - margin * 2
        y = 220
        for line in wrap(draw, title, big, width):
            draw.text((margin, y), line, font=big, fill=INK)
            y += 112

        if subtitle:
            y += 30
            for line in wrap(draw, subtitle, mid, width):
                draw.text((margin, y), line, font=mid, fill=DIM)
                y += 60

        if face:
            watch(draw, (size[0] - 520) // 2, 860, 520, face[0], face[1])

        if note:
            for i, line in enumerate(wrap(draw, note, small, width)):
                draw.text((margin, 1720 + i * 48), line, font=small,
                          fill=ACCENT)
    else:
        # Под циферблат отводим правую треть: текст в неё не заходит,
        # иначе строки ломаются об картинку.
        width = size[0] - margin * 2 - (360 if face else 0)
        y = 150
        if face:
            watch(draw, size[0] - margin - 300, 190, 300, face[0], face[1])

        for line in wrap(draw, title, big, width):
            draw.text((margin, y), line, font=big, fill=INK)
            y += 92

        if subtitle:
            y += 24
            for line in wrap(draw, subtitle, mid, width):
                draw.text((margin, y), line, font=mid, fill=DIM)
                y += 52

        if note:
            # Приписка прижата к низу: так она читается как подпись, а не
            # как продолжение мысли.
            draw.text((margin, size[1] - 90), note, font=small, fill=ACCENT)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    image.save(path, "PNG")
    return path


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print('Нужен заголовок: python3 tools/make_card.py "Текст" "Подзаголовок"')
        return 1
    title = args[0]
    subtitle = args[1] if len(args) > 1 else ""
    note = args[2] if len(args) > 2 else ""
    name = args[3] if len(args) > 3 else "card.png"
    # Пятым — строка геймов, шестым — два очка через «|»: «30|15».
    face = (args[4], args[5]) if len(args) > 5 else None
    shape = args[6] if len(args) > 6 else "post"
    print(card(title, subtitle, note, name, face, shape))
    return 0


if __name__ == "__main__":
    sys.exit(main())
