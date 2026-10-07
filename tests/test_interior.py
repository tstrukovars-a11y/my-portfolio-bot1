# Макет «картина на стене».
#
# Первый вопрос покупателя — не «что изображено», а «какая она». Размер
# в сантиметрах этого не говорит: «60 × 80» читается и как небольшая
# вещь над столом, и как холст в полстены.
#
# Проверяется здесь одно: масштаб не врёт. Макет, ошибающийся в
# размере, вреднее отсутствия макета — он отвечает на главный вопрос, и
# отвечает неправильно.
#
# Проверки идут по числам, а не по картинке. Зерно и виньетка меняют
# каждую точку кадра, и любая сверка по цвету разваливается, хотя
# масштаб цел.
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import pytest
from PIL import Image

import interior


def _art(w=900, h=1200):
    return Image.new("RGB", (w, h), (200, 180, 160))


# --- масштаб ----------------------------------------------------------

def test_the_wall_is_as_tall_as_the_ceiling():
    """Масштаб выводится из высоты потолка, а не назначается. При
    назначенном стена однажды оказывается ниже уровня, на который
    вешают картину, и верх работы уходит за край кадра."""
    wall = interior.SIZE[1] - interior.FLOOR_BAND
    assert round(wall / interior.CM) == interior.CEILING


@pytest.mark.parametrize("cm_w,cm_h", [(30, 40), (60, 80), (120, 90), (15, 20)])
def test_a_centimetre_of_work_is_a_centimetre_of_wall(cm_w, cm_h):
    """Главная проверка всего макета."""
    spot = interior.place(cm_w, cm_h)
    assert abs(spot["width"] - cm_w * interior.CM) <= 1
    assert abs(spot["height"] - cm_h * interior.CM) <= 1


def test_twice_the_size_is_twice_the_wall():
    small = interior.place(60, 40)
    big = interior.place(120, 80)
    assert abs(big["width"] - 2 * small["width"]) <= 2
    assert abs(big["height"] - 2 * small["height"]) <= 2


def test_the_work_hangs_at_eye_level():
    """Сто пятьдесят сантиметров от пола до центра — так вешают."""
    spot = interior.place(60, 80)
    centre = spot["top"] + spot["height"] / 2
    assert abs((spot["floor_y"] - centre) / interior.CM - interior.EYE) <= 1


def test_a_tall_work_is_hung_lower_not_cropped():
    """Двухметровый холст при центре на ста пятидесяти занимает от
    пятидесяти до двухсот пятидесяти — упирается в потолок. В комнате
    такую вешают ниже; обрезанный макет врёт о размере ровно в ту
    сторону, ради которой он и делается."""
    spot = interior.place(150, 200)
    assert spot["top"] >= 0, "работа ушла за верхний край"
    assert spot["top"] + spot["height"] <= spot["floor_y"], \
        "работа ушла в пол"


def test_a_work_is_centred_on_the_wall():
    spot = interior.place(60, 80)
    assert abs(spot["left"] + spot["width"] / 2 - interior.SIZE[0] / 2) <= 1


# --- подпись ----------------------------------------------------------

def test_the_caption_states_the_real_size():
    assert interior.label_of(60, 80) == "60 × 80 см"


def test_whole_numbers_lose_the_tail():
    """«60.0 × 80.0 см» выглядит как вывод программы, а не как подпись."""
    assert interior.label_of(60.0, 80.0) == "60 × 80 см"
    assert interior.label_of(24.5, 30) == "24.5 × 30 см"


# --- сама картинка ----------------------------------------------------

@pytest.mark.parametrize("palette", list(interior.PALETTES))
def test_both_rooms_render(palette):
    assert interior.hang(_art(), 50, 70, palette).size == interior.SIZE


def test_the_room_is_not_flat_colour():
    """Ровная заливка — первое, по чему картинка читается как схема.
    Настоящая стена нигде не одного цвета."""
    room = interior.hang(_art(), 60, 80)
    top = {room.getpixel((x, 20)) for x in range(0, room.width, 50)}
    assert len(top) > 5, "стена осталась плоской заливкой"


# --- фотография своей стены -------------------------------------------
#
# Нарисованная комната честна и точна, но фотографией не станет. Для
# продажи нужна настоящая, и она у художника под рукой — своя стена.

def test_the_scale_on_a_photo_comes_from_the_measurement():
    """Сантиметр работы равен сантиметру стены и на снимке: ширина
    стены в кадре — единственное, что для этого нужно знать."""
    room = Image.new("RGB", (2000, 1500), (210, 205, 200))
    # Без рамы: у неё есть внутренняя тень, и она съедает по краю холста
    # полтора десятка точек. На масштаб это не влияет — холст остаётся
    # тех же размеров, — но проверке мешает.
    out = interior.on_photo(Image.new("RGB", (100, 100), (220, 40, 40)),
                            room, 50, 50, room_width_cm=400, frame=False)
    # 50 см при 400 см на 2000 точек — это 250 точек. Ряд ищем сами:
    # работа висит не посередине кадра, а на той высоте, где её вешают.
    red = max(sum(1 for x in range(out.width)
                  if out.getpixel((x, y)) == (220, 40, 40))
              for y in range(0, out.height, 5))
    assert abs(red - 250) <= 4


def test_a_photo_without_a_measurement_is_refused():
    """Угаданный масштаб хуже отсутствующего: он выглядит как ответ."""
    room = Image.new("RGB", (800, 600), (210, 205, 200))
    with pytest.raises(ValueError):
        interior.on_photo(_art(), room, 50, 50, room_width_cm=0)


def test_a_work_bigger_than_the_wall_in_frame_is_refused():
    """Значит, снимали слишком близко — лучше сказать, чем молча
    растянуть работу на весь кадр."""
    room = Image.new("RGB", (800, 600), (210, 205, 200))
    with pytest.raises(ValueError):
        interior.on_photo(_art(), room, 300, 300, room_width_cm=200)


def test_the_work_stays_inside_the_photo():
    room = Image.new("RGB", (1600, 1200), (210, 205, 200))
    out = interior.on_photo(_art(), room, 60, 80, 300, at=(99, 99))
    assert out.size == room.size
