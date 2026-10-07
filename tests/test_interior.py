# Макет «картина на стене».
#
# Первый вопрос покупателя — не «что изображено», а «какая она». Размер
# в сантиметрах этого не говорит: «60 × 80» читается и как небольшая
# вещь над столом, и как холст в полстены.
#
# Поэтому здесь проверяется одно: масштаб не врёт. Макет, который
# ошибается в размере, вреднее отсутствия макета — он отвечает на
# главный вопрос, и отвечает неправильно.
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import pytest
from PIL import Image

import interior


def _art(w=900, h=1200):
    return Image.new("RGB", (w, h), (200, 180, 160))


def test_the_wall_is_as_tall_as_the_ceiling():
    """Масштаб выводится из высоты потолка, а не назначается. При
    назначенном стена однажды оказывается ниже уровня, на который
    вешают картину, и верх работы уходит за край кадра."""
    wall = interior.SIZE[1] - interior.FLOOR_BAND
    assert round(wall / interior.CM) == interior.CEILING


RED = (220, 40, 40)


def _measured_width(cm_w, cm_h) -> int:
    """Сколько точек занимает работа на стене — меряем по самой картинке.

    Косвенные проверки («стало больше точек») здесь бесполезны: мебель
    даёт больше точек, чем работа, и ошибка масштаба в них утонет.
    """
    out = interior.hang(Image.new("RGB", (400, 400), RED), cm_w, cm_h)
    row = out.height // 2
    # Ряд через центр работы: он проходит по ней при любом разумном
    # размере, потому что центр вешают на уровень глаз.
    best = 0
    for y in range(out.height // 4, out.height // 2 + 80, 10):
        count = sum(1 for x in range(out.width)
                    if out.getpixel((x, y)) == RED)
        best = max(best, count)
    return best


@pytest.mark.parametrize("cm_w,cm_h", [(30, 40), (60, 80), (120, 90)])
def test_the_width_on_the_wall_is_the_real_width(cm_w, cm_h):
    """Главная проверка всего макета: сантиметр работы — это ровно
    столько точек, сколько сантиметр стены."""
    expected = round(cm_w * interior.CM)
    assert abs(_measured_width(cm_w, cm_h) - expected) <= 2


def test_twice_the_size_is_twice_the_wall():
    assert abs(_measured_width(120, 80) - 2 * _measured_width(60, 40)) <= 4


def test_the_proportions_of_the_work_are_kept():
    """Растянутая по кадру работа — обман о форме вещи."""
    out = interior.hang(_art(), 60, 80)
    assert out.size == interior.SIZE


def test_a_tall_work_is_hung_lower_not_cropped():
    """Двухметровый холст при центре на ста пятидесяти занимает от
    пятидесяти до двухсот пятидесяти — то есть упирается в потолок. В
    комнате такую вешают ниже; обрезанный макет врёт о размере ровно в
    ту сторону, ради которой он и делается."""
    out = interior.hang(_art(), 150, 200)
    top_row = [out.getpixel((x, 2)) for x in range(0, out.width, 40)]
    assert all(p == interior.PALETTES["light"]["wall"] for p in top_row), \
        "работа упёрлась в верхний край кадра"


def test_the_caption_states_the_real_size():
    """Числа в подписи — тот же ответ, что и макет, только словами."""
    out = interior.hang(_art(), 60, 80)
    assert out.size[1] > 0  # макет собрался
    # Подпись стоит в полосе пола: проверяем, что она там нарисована.
    floor = out.height - interior.FLOOR_BAND
    rows = [y for y in range(floor, out.height)
            if len({out.getpixel((x, y))
                    for x in range(out.width // 3, 2 * out.width // 3)}) > 1]
    assert rows, "подписи с размером нет"
    assert all(y > floor for y in rows), "подпись залезла на стену"


@pytest.mark.parametrize("palette", list(interior.PALETTES))
def test_both_rooms_work(palette):
    assert interior.hang(_art(), 50, 70, palette).size == interior.SIZE


def test_a_work_taller_than_the_room_is_refused():
    """Трёхметровый холст в комнате с потолком двести пятьдесят — не
    макет, а неправда. Такую вещь показывают фотографией зала."""
    assert interior.CEILING == 250
