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

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "cards")

# Пропорции ленты Telegram: картинка шире экрана телефона обрезается по
# бокам, вертикальная занимает пол-экрана и раздражает. 1280×720 —
# середина, которая везде выглядит одинаково.
SIZE = (1280, 720)

# Тёмный фон: посты читают вечером и с телефона, а белый прямоугольник в
# ленте бьёт по глазам. Акцент — теннисный жёлтый, он же цвет мяча.
BACK = (14, 17, 22)
INK = (232, 234, 240)
DIM = (138, 144, 160)
ACCENT = (214, 232, 58)

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
    """Циферблат с двумя строками — тем, что показывает приложение.

    Пустая середина картинки выглядит недоделанной, а подставлять туда
    узор незачем: лучше показать сам продукт. Рисуем примитивами, без
    скриншота: скриншот часов в ленте нечитаем.
    """
    draw.rounded_rectangle([x, y, x + size, y + size], radius=size // 4,
                           fill=(26, 30, 38), outline=ACCENT, width=4)
    # Размер подбираем под строку, а не наоборот: «40 : 30» и «6 : 4»
    # разной длины, и фиксированный кегль один из них выпустит за рамку.
    big = fitted(draw, top, "Arial Bold.ttf", size // 3, size * 0.78)
    small = fitted(draw, bottom, "Arial.ttf", size // 9, size * 0.8)

    width = draw.textlength(top, font=big)
    draw.text((x + (size - width) / 2, y + size * 0.26), top, font=big,
              fill=INK)
    width = draw.textlength(bottom, font=small)
    draw.text((x + (size - width) / 2, y + size * 0.62), bottom, font=small,
              fill=DIM)


def card(title: str, subtitle: str = "", note: str = "",
         name: str = "card.png", face: tuple = None) -> str:
    image = Image.new("RGB", SIZE, BACK)
    draw = ImageDraw.Draw(image)

    # Полоса сверху вместо логотипа: узнаваемо, ничего не весит и не
    # спорит с текстом.
    draw.rectangle([0, 0, SIZE[0], 10], fill=ACCENT)

    big = font("Arial Bold.ttf", 78)
    mid = font("Arial.ttf", 40)
    small = font("Arial.ttf", 30)

    margin = 90
    # Под циферблат отводим правую треть: текст в неё не заходит, иначе
    # строки ломаются об картинку.
    width = SIZE[0] - margin * 2 - (360 if face else 0)
    y = 150

    if face:
        watch(draw, SIZE[0] - margin - 300, 190, 300, face[0], face[1])

    for line in wrap(draw, title, big, width):
        draw.text((margin, y), line, font=big, fill=INK)
        y += 92

    if subtitle:
        y += 24
        for line in wrap(draw, subtitle, mid, width):
            draw.text((margin, y), line, font=mid, fill=DIM)
            y += 52

    if note:
        # Приписка прижата к низу: так она читается как подпись, а не как
        # продолжение мысли.
        draw.text((margin, SIZE[1] - 90), note, font=small, fill=ACCENT)

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
    # Пятым и шестым — две строки циферблата: «40 : 30» и подпись.
    face = (args[4], args[5]) if len(args) > 5 else None
    print(card(title, subtitle, note, name, face))
    return 0


if __name__ == "__main__":
    sys.exit(main())
