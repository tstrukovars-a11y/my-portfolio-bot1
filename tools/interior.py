# tools/interior.py — картина на стене, в настоящем масштабе.
#
# Первый вопрос покупателя — не «что изображено», а «какая она». Размер
# в сантиметрах этого не говорит: «60 × 80» одинаково читается и как
# небольшая вещь над столом, и как холст в полстены. Человек не
# представляет сантиметры, он представляет стену.
#
# Поэтому комната рисуется, а не берётся фотографией. Три причины:
#
#   Масштаб точный. В нарисованной комнате известна каждая величина:
#   высота потолка, дивана, уровень глаз. На чужой фотографии масштаб
#   можно только угадать, и ошибка пойдёт прямо в решение о покупке.
#
#   Это честно. Нарисованная комната видна как макет и никем не будет
#   принята за фотографию квартиры, которой не существует.
#
#   Это ничьё. Стоковая фотография интерьера имеет владельца и условия
#   использования, а картинка уходит в продающий пост.
#
#   python3 tools/interior.py картина.jpg --width 60 --height 80
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "interior")

SIZE = (1400, 1050)          # 4:3 — ближе всего к тому, как видят комнату

# Снизу остаётся полоса пола, остальное — стена высотой в потолок.
# Масштаб выводится из этого, а не назначается: при назначенном стена
# однажды оказывается ниже того уровня, на который вешают картину, и
# верх работы уходит за край кадра.
FLOOR_BAND = 200             # точек на пол в нижней части кадра
CEILING = 250                # высота потолка, см
CM = (SIZE[1] - FLOOR_BAND) / CEILING

# Величины настоящие, в сантиметрах. На них и держится весь смысл:
# стоит заменить их «красивыми» числами — и масштаб соврёт.
SOFA_H = 82                  # спинка дивана от пола
SOFA_W = 210
TABLE_H = 75
EYE = 150                    # центр картины вешают на уровень глаз
PLANT_H = 130

PALETTES = {
    "light": {
        "wall": (238, 234, 227), "floor": (196, 178, 156),
        "skirting": (250, 248, 245), "sofa": (168, 170, 176),
        "sofa_dark": (146, 148, 154), "wood": (150, 118, 86),
        "plant": (104, 132, 96), "pot": (176, 150, 128),
        "ink": (92, 88, 82), "shadow": (0, 0, 0, 38),
    },
    "dark": {
        "wall": (54, 52, 56), "floor": (62, 52, 44),
        "skirting": (44, 42, 46), "sofa": (78, 78, 86),
        "sofa_dark": (64, 64, 72), "wood": (92, 72, 54),
        "plant": (86, 112, 82), "pot": (108, 92, 78),
        "ink": (206, 202, 196), "shadow": (0, 0, 0, 70),
    },
}


def font(name: str, size: int):
    path = f"/System/Library/Fonts/Supplemental/{name}"
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _cm(value: float) -> int:
    return int(round(value * CM))


def _room(draw, w: int, h: int, c: dict):
    """Стена, пол, плинтус. Горизонт — на уровне глаз сидящего."""
    floor_y = h - FLOOR_BAND
    draw.rectangle([0, 0, w, floor_y], fill=c["wall"])
    draw.rectangle([0, floor_y, w, h], fill=c["floor"])
    draw.rectangle([0, floor_y - _cm(8), w, floor_y], fill=c["skirting"])
    return floor_y


def _sofa(draw, floor_y: int, centre: int, c: dict):
    """Диван — мера, по которой читается всё остальное.

    Без предмета известного размера нарисованная комната ничего не
    объясняет: стена без мебели масштаба не имеет.
    """
    half = _cm(SOFA_W) // 2
    top = floor_y - _cm(SOFA_H)
    left, right = centre - half, centre + half

    draw.rounded_rectangle([left, top, right, floor_y - _cm(12)],
                           radius=_cm(6), fill=c["sofa"])
    # Сиденье темнее спинки — иначе диван читается как прямоугольник.
    draw.rounded_rectangle([left + _cm(6), floor_y - _cm(46),
                            right - _cm(6), floor_y - _cm(14)],
                           radius=_cm(5), fill=c["sofa_dark"])
    for x in (left + _cm(14), centre - _cm(6)):
        draw.rounded_rectangle([x, top + _cm(8), x + _cm(52), top + _cm(40)],
                               radius=_cm(4), fill=c["sofa_dark"])
    for x in (left + _cm(10), right - _cm(16)):
        draw.rectangle([x, floor_y - _cm(12), x + _cm(6), floor_y],
                       fill=c["wood"])


def _plant(draw, floor_y: int, x: int, c: dict):
    pot_h = _cm(26)
    draw.polygon([(x - _cm(14), floor_y - pot_h), (x + _cm(14), floor_y - pot_h),
                  (x + _cm(10), floor_y), (x - _cm(10), floor_y)], fill=c["pot"])
    top = floor_y - pot_h
    for angle, length in ((-34, PLANT_H), (0, PLANT_H + 14), (30, PLANT_H - 18)):
        tip_x = x + _cm(angle * 0.45)
        tip_y = top - _cm(length - 26)
        draw.line([(x, top), (tip_x, tip_y)], fill=c["plant"], width=_cm(2))
        draw.ellipse([tip_x - _cm(9), tip_y - _cm(7),
                      tip_x + _cm(9), tip_y + _cm(7)], fill=c["plant"])


def hang(picture: Image.Image, width_cm: float, height_cm: float,
         palette: str = "light", frame: bool = True) -> Image.Image:
    """Повесить картину на нарисованную стену в истинном масштабе"""
    c = PALETTES.get(palette, PALETTES["light"])
    w, h = SIZE
    room = Image.new("RGB", SIZE, c["wall"])
    draw = ImageDraw.Draw(room)

    floor_y = _room(draw, w, h, c)
    centre = w // 2
    _sofa(draw, floor_y, centre, c)
    _plant(draw, floor_y, w - _cm(46), c)

    # Картина: центр на уровне глаз, ширина и высота — настоящие.
    art_w, art_h = _cm(width_cm), _cm(height_cm)
    art = picture.convert("RGB").resize((art_w, art_h), Image.LANCZOS)
    left = centre - art_w // 2
    top = floor_y - _cm(EYE) - art_h // 2

    # Высокая работа, повешенная центром на уровне глаз, упирается в
    # потолок: двухметровый холст при центре на ста пятидесяти занимает
    # от пятидесяти до двухсот пятидесяти. В комнате её вешают ниже —
    # так же поступаем и здесь, вместо того чтобы обрезать по краю
    # кадра. Обрезанный макет врёт о размере в ту же сторону, ради
    # которой он и делается.
    highest = _cm(10)
    lowest = floor_y - _cm(5) - art_h
    top = max(highest, min(top, lowest))

    # Тень кладём раньше рамы: иначе она ложится поверх картины.
    shade = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(shade).rectangle(
        [left + _cm(2), top + _cm(2), left + art_w + _cm(4),
         top + art_h + _cm(4)], fill=c["shadow"])
    room = Image.alpha_composite(room.convert("RGBA"), shade).convert("RGB")
    draw = ImageDraw.Draw(room)

    if frame:
        pad = _cm(2.5)
        draw.rectangle([left - pad, top - pad, left + art_w + pad,
                        top + art_h + pad], fill=(28, 26, 24))
    room.paste(art, (left, top))

    # Подпись с настоящими числами. Макет без них — просто картинка;
    # с ними — ответ на первый вопрос покупателя.
    label = f"{width_cm:g} × {height_cm:g} см"
    mark = font("Arial.ttf", 30)
    box = draw.textbbox((0, 0), label, font=mark)
    draw.text((centre - (box[2] - box[0]) // 2, h - _cm(26)),
              label, font=mark, fill=c["ink"])
    return room


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Картина на стене в настоящем масштабе")
    parser.add_argument("picture", help="файл с фотографией работы")
    parser.add_argument("--width", type=float, required=True,
                        help="ширина работы в сантиметрах")
    parser.add_argument("--height", type=float, required=True,
                        help="высота работы в сантиметрах")
    parser.add_argument("--palette", default="light", choices=list(PALETTES))
    parser.add_argument("--no-frame", action="store_true")
    parser.add_argument("--name", default="")
    args = parser.parse_args()

    if not os.path.exists(args.picture):
        print(f"нет файла: {args.picture}")
        return 1
    if args.width <= 0 or args.height <= 0:
        print("размеры должны быть больше нуля")
        return 1
    if args.width > CEILING or args.height > CEILING:
        print(f"работа выше потолка комнаты ({CEILING} см) — макет не нужен, "
              f"такую вещь показывают на фотографии зала")
        return 1

    os.makedirs(OUT, exist_ok=True)
    name = args.name or (os.path.splitext(os.path.basename(args.picture))[0]
                         + "_interior.png")
    path = os.path.join(OUT, name)
    hang(Image.open(args.picture), args.width, args.height,
         args.palette, not args.no_frame).save(path)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
