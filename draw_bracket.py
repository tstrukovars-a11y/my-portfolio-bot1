#  draw_bracket.py — олимпийская сетка для розыгрыша призов.
#
#  ЗАЧЕМ ОНА ВООБЩЕ. Вопросы на мероприятии угадывают многие: при трёх
#  вопросах и полусотне зрителей «угадал всё» наберётся у шестерых-восьми,
#  а призов три. Делить три приза между восемью нельзя, и сетка — честный
#  и зрелищный способ получить ровно первое, второе и третье место.
#
#  ПОЧЕМУ ИГРУ НЕ ПЕРЕДЕЛЫВАЕМ В ПАРНУЮ. Игра одиночная, и это сетке не
#  мешает: оба в паре играют внутри окна круга, выше счёт — тот прошёл.
#  Парная игра потребовала бы, чтобы двое были за телефоном в одну и ту
#  же минуту, — а это главная причина, по которой вечерние круги
#  разваливаются: с мероприятия уходят.
#
#  ЗДЕСЬ ТОЛЬКО АРИФМЕТИКА. Ни базы, ни Telegram: посев, пропуски круга,
#  пары и продвижение считаются чистыми функциями, и проверить их можно
#  до единой строчки SQL.

# Больше шестнадцати участников плей-офф на вечернем мероприятии не
# бывает: это четыре круга, то есть минимум сорок минут игры после
# окончания матчей. Упрёмся — лучше отсечь по таблице, чем разводить
# пять кругов и неявки.
MAX_PLAYERS = 16


def bracket_size(players: int) -> int:
    """Ближайшая сверху степень двойки: 6 участников -> сетка на 8."""
    if players < 2:
        return 0
    size = 2
    while size < players:
        size *= 2
    return size


def seed_order(size: int) -> list:
    """Порядок посевов по позициям сетки.

    Строится удвоением: пара к первому — последний, и каждая следующая
    половина зеркалит предыдущую. Для восьми выходит
    [0, 7, 3, 4, 1, 6, 2, 5] — первый и второй посевы оказываются в
    разных половинах и встретиться могут только в финале.
    """
    if size < 2:
        return [0] if size == 1 else []
    order = [0, 1]
    while len(order) < size:
        mirror = [len(order) * 2 - 1 - x for x in order]
        merged = []
        for a, b in zip(order, mirror):
            merged += [a, b]
        order = merged
    return order


def seed_slots(players: list, size: int = None) -> list:
    """Разложить участников по местам сетки. None — пропуск круга.

    Участники приходят отсортированными: лучший первым. Пропуски
    достаются верхним посевам — так принято везде, и спорить с этим не
    будут: сильнейший по таблице получает преимущество, а не случайный.
    """
    if not players:
        return []
    size = size or bracket_size(len(players))
    if size < 2:
        return []
    return [players[i] if i < len(players) else None
            for i in seed_order(size)]


def pairs(slots: list) -> list:
    """Пары круга: соседние места по двое."""
    return [(slots[i], slots[i + 1]) for i in range(0, len(slots) - 1, 2)]


def advance(pair, scores: dict, seeds: dict = None):
    """Кто проходит дальше. scores — {участник: счёт} за этот круг.

    Правила разбора, по убыванию силы:
      1. пропуск круга — проходит тот, кто есть;
      2. сыграли оба — выше счёт;
      3. сыграл один — он и проходит, даже с единицей: явка важнее;
      4. не сыграл никто — проходит верхний посев. Снимать обоих нельзя,
         иначе в следующем круге окажется пустое место, и сетка
         развалится;
      5. счёт равный — тоже верхний посев.

    Явка решает намеренно: круги короткие, и «пришёл и сыграл» — это
    ровно то, чего мы просим от участника.
    """
    a, b = pair
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a

    sa, sb = scores.get(a), scores.get(b)
    if sa is None and sb is None:
        return _better_seed(a, b, seeds)
    if sb is None:
        return a
    if sa is None:
        return b
    if sa == sb:
        return _better_seed(a, b, seeds)
    return a if sa > sb else b


def _better_seed(a, b, seeds):
    """Чей посев выше. Нет данных — первый по порядку в паре."""
    if not seeds:
        return a
    return a if seeds.get(a, 10 ** 6) <= seeds.get(b, 10 ** 6) else b


def next_round(slots: list, scores: dict, seeds: dict = None) -> list:
    """Места следующего круга из мест текущего."""
    return [advance(p, scores, seeds) for p in pairs(slots)]


def rounds_left(size: int) -> int:
    """Сколько кругов осталось сыграть в сетке такого размера."""
    rounds, n = 0, size
    while n > 1:
        n //= 2
        rounds += 1
    return rounds


def round_name(remaining: int) -> str:
    """Название круга по числу оставшихся участников"""
    return {2: "Финал", 4: "Полуфинал", 8: "Четвертьфинал"}.get(
        remaining, f"1/{remaining // 2} финала")


def places(final_slots: list, third_place, scores: dict,
           seeds: dict = None) -> list:
    """Итоговые три места.

    Третье берётся отдельным матчем проигравших в полуфинале — иначе
    бронзу пришлось бы присуждать «по счёту в полуфинале», а это сравнение
    результатов, полученных против разных соперников.
    """
    if len(final_slots) != 2:
        return []
    champion = advance((final_slots[0], final_slots[1]), scores, seeds)
    runner_up = final_slots[1] if champion == final_slots[0] else final_slots[0]
    out = [champion, runner_up]
    if third_place:
        out.append(advance(third_place, scores, seeds))
    return [x for x in out if x is not None]
