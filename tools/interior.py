# tools/interior.py — картина на стене, в настоящем масштабе.
#
# Первый вопрос покупателя — не «что изображено», а «какая она». Размер
# в сантиметрах этого не говорит: «60 × 80» одинаково читается и как
# небольшая вещь над столом, и как холст в полстены. Человек не
# представляет сантиметры, он представляет стену.
#
# Комната рисуется здесь, а не берётся готовой фотографией:
#
#   Масштаб точный. В нарисованной комнате известна каждая величина:
#   высота потолка, дивана, уровень глаз. На чужой фотографии масштаб
#   можно только угадать, и ошибка пойдёт прямо в решение о покупке.
#
#   Это ничьё. Стоковая фотография интерьера имеет владельца и условия
#   использования, а картинка уходит в продающий пост.
#
# Первая версия рисовала плоскими заливками, и это не годилось: под
# продажу живописи нужна комната, а не схема комнаты. Поэтому здесь
# свет, мягкие тени, перспектива пола, глубина резкости и зерно —
# то, из чего складывается ощущение снимка.
#
# Главное при этом не изменилось: сантиметр работы — это ровно столько
# же точек, сколько сантиметр стены.
#
#   python3 tools/interior.py картина.jpg --width 60 --height 80
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

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
EYE = 150                    # центр картины вешают на уровень глаз
PLANT_H = 130

# Свет падает слева сверху — как из окна, которого в кадре нет. От него
# зависят и градиент стены, и сторона, куда ложатся тени: разойдутся —
# и комната развалится на отдельные предметы.
LIGHT = (0.26, 0.10)

PALETTES = {
    "light": {
        "wall": (226, 221, 213), "wall_lit": (247, 244, 238),
        "floor": (158, 126, 92), "floor_far": (120, 94, 68),
        "plank": (139, 110, 80),
        "skirting": (242, 239, 233), "sofa": (178, 176, 170),
        "sofa_dark": (151, 149, 144), "wood": (120, 92, 64),
        "plant": (96, 122, 88), "plant_dark": (74, 96, 70),
        "pot": (166, 142, 120),
        "ink": (104, 99, 92), "frame": (38, 34, 30),
    },
    "dark": {
        "wall": (48, 46, 50), "wall_lit": (78, 75, 79),
        "floor": (62, 50, 40), "floor_far": (42, 34, 28),
        "plank": (54, 44, 36),
        "skirting": (38, 36, 40), "sofa": (72, 71, 78),
        "sofa_dark": (58, 57, 64), "wood": (74, 58, 44),
        "plant": (74, 98, 72), "plant_dark": (56, 76, 56),
        "pot": (96, 82, 70),
        "ink": (188, 184, 178), "frame": (24, 22, 20),
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


def _mix(a, b, t: float):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


# ---------------------------------------------------------------------
# СВЕТ И ПОВЕРХНОСТИ
# ---------------------------------------------------------------------

def _lit_wall(size, c: dict) -> Image.Image:
    """Стена со светом из-за кадра.

    Ровная заливка — первое, по чему картинка читается как схема:
    настоящая стена нигде не одного цвета. Пятно света делаем большим и
    мягким, иначе оно само бросается в глаза.
    """
    w, h = size
    wall = Image.new("RGB", size, c["wall"])

    # Круговой градиент Pillow отдаёт в маленьком размере — растягиваем:
    # так он и получается достаточно размытым.
    glow = Image.radial_gradient("L").resize((w * 2, h * 2), Image.BICUBIC)
    glow = Image.eval(glow, lambda v: 255 - v)      # ярко в центре
    left = int(w * LIGHT[0] - w)
    top = int(h * LIGHT[1] - h)
    mask = Image.new("L", size, 0)
    mask.paste(glow, (left, top))

    return Image.composite(Image.new("RGB", size, c["wall_lit"]), wall, mask)


def _floor(room: Image.Image, floor_y: int, c: dict):
    """Пол в перспективе: доски сходятся к точке за кадром.

    Горизонтальных полос достаточно для схемы и мало для комнаты: пол
    читается плоским, и вся глубина пропадает вместе с ним.
    """
    w, h = room.size
    draw = ImageDraw.Draw(room)
    draw.rectangle([0, floor_y, w, h], fill=c["floor"])

    # Дальний край темнее ближнего — так ложится свет на горизонтальную
    # поверхность, и так она отделяется от стены.
    depth = h - floor_y
    for i in range(depth):
        t = 1 - i / max(1, depth)
        draw.line([(0, floor_y + i), (w, floor_y + i)],
                  fill=_mix(c["floor"], c["floor_far"], t ** 1.6))

    # Стыки досок: к дальнему краю сходятся, у ближнего расходятся.
    #
    # Поперечных линий здесь быть не должно: вместе с продольными они
    # дают сетку, и пол читается плиткой. Доска идёт от стены к зрителю
    # одной линией — этого хватает, чтобы появилась глубина.
    vanish = w // 2
    for step in range(-9, 10):
        far = vanish + step * _cm(26)
        near = vanish + step * _cm(26) * 2.3
        draw.line([(far, floor_y), (near, h)], fill=c["plank"], width=2)

    # Отсвет стены у плинтуса: пол блестит, и у самой стены он светлее.
    # Без этого стена и пол стыкуются как два куска бумаги.
    for i in range(_cm(16)):
        t = i / _cm(16)
        draw.line([(0, floor_y + i), (w, floor_y + i)],
                  fill=_mix(_mix(c["floor"], c["wall"], 0.30),
                            c["floor_far"], t))


def _soft_shadow(size, box, blur: int, strength: int,
                 offset=(0, 0)) -> Image.Image:
    """Мягкая тень прямоугольника — слоем, а не заливкой.

    Резкая тень выглядит хуже, чем её отсутствие: глаз читает её как
    вторую фигуру, а не как тень.
    """
    layer = Image.new("L", size, 0)
    ImageDraw.Draw(layer).rectangle(
        [box[0] + offset[0], box[1] + offset[1],
         box[2] + offset[0], box[3] + offset[1]], fill=strength)
    return layer.filter(ImageFilter.GaussianBlur(blur))


def _grain(room: Image.Image, sigma: float = 5.0) -> Image.Image:
    """Зерно поверх всего.

    Ровные заливки без зерна — главная примета рисунка. Одно это
    сближает картинку со снимком сильнее, чем любая добавленная мебель.
    """
    noise = Image.effect_noise(room.size, sigma).convert("RGB")
    return Image.blend(room, noise, 0.055)


def _vignette(room: Image.Image, strength: float = 0.30) -> Image.Image:
    w, h = room.size
    mask = Image.radial_gradient("L").resize((int(w * 1.45), int(h * 1.45)),
                                             Image.BICUBIC)
    mask = mask.crop(((mask.width - w) // 2, (mask.height - h) // 2,
                      (mask.width - w) // 2 + w, (mask.height - h) // 2 + h))
    mask = Image.eval(mask, lambda v: int(v * strength))
    return Image.composite(Image.new("RGB", room.size, (0, 0, 0)), room,
                           mask)


# ---------------------------------------------------------------------
# ПРЕДМЕТЫ
# ---------------------------------------------------------------------

def _sofa(draw, floor_y: int, centre: int, c: dict):
    """Диван — мера, по которой читается всё остальное.

    Без предмета известного размера нарисованная комната ничего не
    объясняет: стена без мебели масштаба не имеет.
    """
    half = _cm(SOFA_W) // 2
    top = floor_y - _cm(SOFA_H)
    left, right = centre - half, centre + half

    draw.rounded_rectangle([left, top, right, floor_y - _cm(12)],
                           radius=_cm(7), fill=c["sofa"])
    # Верх спинки ловит свет, низ уходит в тень — без этого диван
    # остаётся прямоугольником.
    for i in range(_cm(26)):
        t = i / _cm(26)
        draw.line([(left + _cm(2), top + i), (right - _cm(2), top + i)],
                  fill=_mix(_mix(c["sofa"], (255, 255, 255), 0.12),
                            c["sofa"], t))
    draw.rounded_rectangle([left + _cm(6), floor_y - _cm(46),
                            right - _cm(6), floor_y - _cm(14)],
                           radius=_cm(6), fill=c["sofa_dark"])
    for x in (left + _cm(16), centre + _cm(4)):
        draw.rounded_rectangle([x, top + _cm(9), x + _cm(50), top + _cm(41)],
                               radius=_cm(5), fill=c["sofa_dark"])
    for x in (left + _cm(10), right - _cm(16)):
        draw.rectangle([x, floor_y - _cm(12), x + _cm(6), floor_y],
                       fill=c["wood"])


def _plant(draw, floor_y: int, x: int, c: dict):
    """Растение у стены — второй предмет известного роста.

    Круглый лист на палке читается как леденец: у настоящего листа
    есть длина и направление, и держится он не в точке, а вдоль стебля.
    Поэтому лист — вытянутый многоугольник по дуге стебля.
    """
    pot_h = _cm(26)
    draw.polygon([(x - _cm(14), floor_y - pot_h), (x + _cm(14), floor_y - pot_h),
                  (x + _cm(9), floor_y), (x - _cm(9), floor_y)], fill=c["pot"])
    draw.line([(x - _cm(13), floor_y - pot_h), (x + _cm(13), floor_y - pot_h)],
              fill=_mix(c["pot"], (255, 255, 255), 0.3), width=3)

    top = floor_y - pot_h
    leaves = ((-30, PLANT_H - 10, c["plant_dark"]),
              (-11, PLANT_H + 20, c["plant"]),
              (10, PLANT_H + 6, c["plant"]),
              (28, PLANT_H - 26, c["plant_dark"]))
    for angle, length, colour in leaves:
        tip_x = x + _cm(angle * 0.62)
        tip_y = top - _cm(length - 26)
        mid_x = (x + tip_x) // 2 + _cm(angle * 0.12)
        mid_y = (top + tip_y) // 2
        draw.line([(x, top), (mid_x, mid_y), (tip_x, tip_y)],
                  fill=colour, width=max(2, _cm(0.9)), joint="curve")
        # Лист вдоль последней трети стебля, а не шариком на конце.
        base_x = mid_x + (tip_x - mid_x) // 3
        base_y = mid_y + (tip_y - mid_y) // 3
        side = _cm(5.5)
        draw.polygon([(tip_x, tip_y),
                      (base_x + side, (base_y + tip_y) // 2),
                      (base_x, base_y),
                      (base_x - side, (base_y + tip_y) // 2)], fill=colour)


def _furniture(room: Image.Image, floor_y: int, c: dict) -> Image.Image:
    """Мебель рисуем отдельным слоем и слегка расфокусируем.

    Съёмка интерьера с картиной всегда наводится на картину: мебель
    уходит в нерезкость. Это и делает кадр снимком — и заодно убирает
    то, в чём нарисованные предметы выдают себя, линию и угол.
    """
    layer = Image.new("RGBA", room.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    _sofa(draw, floor_y, room.width // 2, c)
    _plant(draw, floor_y, room.width - _cm(46), c)

    # Тень от мебели на пол и стену — предметы должны стоять, а не
    # висеть в воздухе.
    shade = _soft_shadow(room.size,
                         (room.width // 2 - _cm(SOFA_W) // 2 - _cm(6),
                          floor_y - _cm(SOFA_H),
                          room.width // 2 + _cm(SOFA_W) // 2 + _cm(6),
                          floor_y + _cm(10)), blur=_cm(9), strength=70,
                         offset=(_cm(5), _cm(3)))
    room = Image.composite(Image.new("RGB", room.size, (0, 0, 0)), room, shade)

    layer = layer.filter(ImageFilter.GaussianBlur(2.4))
    return Image.alpha_composite(room.convert("RGBA"), layer).convert("RGB")


def _framed(art: Image.Image, c: dict, frame: bool) -> Image.Image:
    """Работа в раме: фаска и внутренняя тень дают толщину.

    Картина, вставленная в кадр без этого, выглядит наклейкой — она
    лежит на стене, а не висит перед ней.
    """
    if not frame:
        return art
    pad = max(6, _cm(2.6))
    w, h = art.size
    panel = Image.new("RGB", (w + pad * 2, h + pad * 2), c["frame"])
    draw = ImageDraw.Draw(panel)
    light = _mix(c["frame"], (255, 255, 255), 0.42)
    dark = _mix(c["frame"], (0, 0, 0), 0.5)
    # Свет слева сверху: там фаска светлая, справа снизу — тёмная.
    draw.line([(0, 0), (panel.width - 1, 0)], fill=light, width=2)
    draw.line([(0, 0), (0, panel.height - 1)], fill=light, width=2)
    draw.line([(panel.width - 1, 0), (panel.width - 1, panel.height - 1)],
              fill=dark, width=2)
    draw.line([(0, panel.height - 1), (panel.width - 1, panel.height - 1)],
              fill=dark, width=2)
    panel.paste(art, (pad, pad))

    inner = Image.new("L", panel.size, 0)
    ImageDraw.Draw(inner).rectangle([pad - 1, pad - 1, pad + w, pad + h],
                                    outline=120, width=max(2, pad // 3))
    inner = inner.filter(ImageFilter.GaussianBlur(max(1, pad // 3)))
    return Image.composite(Image.new("RGB", panel.size, (0, 0, 0)),
                           panel, inner)


# ---------------------------------------------------------------------
# СБОРКА
# ---------------------------------------------------------------------

def label_of(width_cm: float, height_cm: float) -> str:
    """Подпись с настоящими числами — тот же ответ, что и макет, словами"""
    return f"{width_cm:g} × {height_cm:g} см"


def place(width_cm: float, height_cm: float) -> dict:
    """Где и какого размера работа окажется на стене — в точках.

    Вынесено из отрисовки намеренно. Масштаб — единственное, ради чего
    макет существует, и проверять его надо числами, а не разглядыванием
    готовой картинки: зерно и виньетка меняют каждую точку, и любая
    проверка по цвету после них разваливается, хотя масштаб цел.
    """
    floor_y = SIZE[1] - FLOOR_BAND
    art_w, art_h = _cm(width_cm), _cm(height_cm)
    top = floor_y - _cm(EYE) - art_h // 2

    # Высокая работа, повешенная центром на уровне глаз, упирается в
    # потолок: двухметровый холст при центре на ста пятидесяти занимает
    # от пятидесяти до двухсот пятидесяти. В комнате её вешают ниже —
    # так же поступаем и здесь, вместо того чтобы обрезать по краю
    # кадра. Обрезанный макет врёт о размере в ту же сторону, ради
    # которой он и делается.
    top = max(_cm(10), min(top, floor_y - _cm(5) - art_h))

    return {"left": SIZE[0] // 2 - art_w // 2, "top": top,
            "width": art_w, "height": art_h, "floor_y": floor_y}


def hang(picture: Image.Image, width_cm: float, height_cm: float,
         palette: str = "light", frame: bool = True) -> Image.Image:
    """Повесить картину на стену комнаты в истинном масштабе"""
    c = PALETTES.get(palette, PALETTES["light"])
    w, h = SIZE
    floor_y = h - FLOOR_BAND

    room = _lit_wall(SIZE, c)
    _floor(room, floor_y, c)
    draw = ImageDraw.Draw(room)
    draw.rectangle([0, floor_y - _cm(8), w, floor_y], fill=c["skirting"])
    draw.line([(0, floor_y - _cm(8)), (w, floor_y - _cm(8))],
              fill=_mix(c["skirting"], (255, 255, 255), 0.5), width=2)
    room = _furniture(room, floor_y, c)

    # Картина: центр на уровне глаз, ширина и высота — настоящие.
    centre = w // 2
    spot = place(width_cm, height_cm)
    art_w, art_h = spot["width"], spot["height"]
    left, top = spot["left"], spot["top"]
    art = picture.convert("RGB").resize((art_w, art_h), Image.LANCZOS)

    panel = _framed(art, c, frame)
    px = left - (panel.width - art_w) // 2
    py = top - (panel.height - art_h) // 2

    # Тень падает вправо и вниз — туда же, куда от мебели.
    shade = _soft_shadow(SIZE, (px, py, px + panel.width, py + panel.height),
                         blur=_cm(4), strength=92,
                         offset=(_cm(2.4), _cm(2.8)))
    room = Image.composite(Image.new("RGB", SIZE, (0, 0, 0)), room, shade)
    room.paste(panel, (px, py))

    room = _vignette(_grain(room))

    # Подпись с настоящими числами. Макет без них — просто картинка;
    # с ними — ответ на первый вопрос покупателя.
    draw = ImageDraw.Draw(room)
    label = label_of(width_cm, height_cm)
    mark = font("Arial.ttf", 30)
    box = draw.textbbox((0, 0), label, font=mark)
    tx, ty = centre - (box[2] - box[0]) // 2, h - _cm(26)
    # Тёмная подложка под подписью: пол теперь неровный, и текст на нём
    # местами пропадал.
    draw.text((tx + 1, ty + 1), label, font=mark, fill=(0, 0, 0))
    draw.text((tx, ty), label, font=mark, fill=(246, 243, 238))
    return room


def on_photo(picture: Image.Image, room: Image.Image, width_cm: float,
             height_cm: float, room_width_cm: float, at=(50, 42),
             frame: bool = True) -> Image.Image:
    """Повесить работу на фотографию настоящей стены.

    Нарисованная комната честна и точна, но фотографией не станет —
    это предел рисования геометрией. Настоящая комната получается
    только из настоящего снимка, и у художника он всегда под рукой:
    своя стена.

    Масштаб берётся из одного измерения. Нужно знать, сколько
    сантиметров стены попало в кадр по ширине: рулетка вдоль стены,
    одно число — и сантиметр работы снова равен сантиметру стены.
    Угадывать это по фотографии нельзя, поэтому число спрашиваем.
    """
    if room_width_cm <= 0:
        raise ValueError("ширина стены в кадре должна быть больше нуля")

    room = room.convert("RGB")
    per_cm = room.width / room_width_cm
    art_w = max(1, int(round(width_cm * per_cm)))
    art_h = max(1, int(round(height_cm * per_cm)))
    if art_w >= room.width or art_h >= room.height:
        raise ValueError("работа больше, чем попавший в кадр кусок стены — "
                         "отойдите дальше и снимите ещё раз")

    art = picture.convert("RGB").resize((art_w, art_h), Image.LANCZOS)
    panel = _framed(art, PALETTES["light"], frame)

    cx = int(room.width * at[0] / 100) - panel.width // 2
    cy = int(room.height * at[1] / 100) - panel.height // 2
    cx = max(0, min(cx, room.width - panel.width))
    cy = max(0, min(cy, room.height - panel.height))

    # Тень по месту: на снимке она и отличает повешенную работу от
    # наклеенной поверх картинки.
    blur = max(3, int(per_cm * 3))
    shade = _soft_shadow(room.size,
                         (cx, cy, cx + panel.width, cy + panel.height),
                         blur=blur, strength=96,
                         offset=(int(per_cm * 2), int(per_cm * 2.4)))
    room = Image.composite(Image.new("RGB", room.size, (0, 0, 0)), room, shade)
    room.paste(panel, (cx, cy))
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
    parser.add_argument("--room", default="",
                        help="фотография своей стены вместо нарисованной")
    parser.add_argument("--room-width", type=float, default=0,
                        help="сколько сантиметров стены попало в кадр по "
                             "ширине — одно измерение рулеткой")
    parser.add_argument("--at", default="50,42",
                        help="куда вешать на фотографии: проценты «x,y»")
    args = parser.parse_args()

    if not os.path.exists(args.picture):
        print(f"нет файла: {args.picture}")
        return 1
    if args.width <= 0 or args.height <= 0:
        print("размеры должны быть больше нуля")
        return 1
    os.makedirs(OUT, exist_ok=True)
    name = args.name or (os.path.splitext(os.path.basename(args.picture))[0]
                         + "_interior.png")
    path = os.path.join(OUT, name)

    if args.room:
        if not os.path.exists(args.room):
            print(f"нет файла комнаты: {args.room}")
            return 1
        if args.room_width <= 0:
            print("нужно знать, сколько сантиметров стены в кадре: "
                  "--room-width 320\n\n"
                  "Измерьте рулеткой стену по ширине кадра. Без этого "
                  "масштаб можно только угадать, а угаданный масштаб "
                  "хуже отсутствующего.")
            return 1
        try:
            x, _, y = args.at.partition(",")
            where = (float(x), float(y or 42))
        except ValueError:
            print("положение задаётся как «50,42» — проценты по ширине и высоте")
            return 1
        try:
            on_photo(Image.open(args.picture), Image.open(args.room),
                     args.width, args.height, args.room_width, where,
                     not args.no_frame).save(path)
        except ValueError as e:
            print(e)
            return 1
        print(path)
        return 0

    if args.width > CEILING or args.height > CEILING:
        print(f"работа выше потолка комнаты ({CEILING} см) — макет не нужен, "
              f"такую вещь показывают на фотографии зала")
        return 1

    hang(Image.open(args.picture), args.width, args.height,
         args.palette, not args.no_frame).save(path)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
