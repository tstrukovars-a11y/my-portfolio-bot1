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

    # Размер НИКОГДА не берём больше необходимого, даже если его передали
    # снаружи. Восемь мест на двоих дают пару из двух пропусков — матч
    # без единого участника, и следующий круг получает пустое место, из
    # которого сетка уже не выбирается.
    #
    # При размере, посчитанном от числа игроков, такая пара невозможна:
    # она требовала бы, чтобы игроков было не больше половины сетки, а
    # ближайшая степень двойки берётся СВЕРХУ. Проверено перебором всех
    # составов до шестнадцати.
    needed = bracket_size(len(players))
    size = min(size, needed) if size else needed
    if size < 2:
        return []
    return [players[i] if i < len(players) else None
            for i in seed_order(size)]


def pairs(slots: list) -> list:
    """Пары круга: соседние места по двое."""
    return [(slots[i], slots[i + 1]) for i in range(0, len(slots) - 1, 2)]


def advance(pair, scores: dict, seeds: dict = None, totals: dict = None):
    """Кто проходит дальше. scores — {участник: лучший счёт} за круг.

    Правила разбора, по убыванию силы:
      1. пропуск круга — проходит тот, кто есть;
      2. сыграли оба — выше счёт;
      3. сыграл один — он и проходит, даже с единицей: явка важнее;
      4. не сыграл никто — ВЫБЫВАЮТ ОБА. Место в следующем круге
         остаётся пустым и работает там как пропуск: соперник проходит
         без игры;
      5. счёт равный — выше СУММА попыток за круг (totals);
      6. и она равная — верхний посев.

    ПОЧЕМУ СУММА, А НЕ ПОСЕВ СРАЗУ. Посев у нас задаётся тем, кто раньше
    ответил на прогнозы, — это совсем другое действие и другой день.
    Человек отыграл круг и проиграл бы за то, что когда-то нажал кнопку
    позже: обидно и несправедливо. Сумма попыток — тоже игра, просто
    другая её сторона. Посев остаётся на самый край, когда по игре
    неразличимо вообще ничем.

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
        return None          # не явился никто — дальше не идёт никто
    if sb is None:
        return a
    if sa is None:
        return b
    if sa != sb:
        return a if sa > sb else b

    # Лучший результат совпал — смотрим, кто наиграл больше за круг
    totals = totals or {}
    ta, tb = totals.get(a, 0), totals.get(b, 0)
    if ta != tb:
        return a if ta > tb else b
    return _better_seed(a, b, seeds)


def _better_seed(a, b, seeds):
    """Чей посев выше. Нет данных — первый по порядку в паре."""
    if not seeds:
        return a
    return a if seeds.get(a, 10 ** 6) <= seeds.get(b, 10 ** 6) else b


def next_round(slots: list, scores: dict, seeds: dict = None,
               totals: dict = None) -> list:
    """Места следующего круга из мест текущего."""
    return [advance(p, scores, seeds, totals) for p in pairs(slots)]


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


def loser(pair, winner):
    """Второй из пары. None, если пара неполная."""
    a, b = pair
    if a is None or b is None:
        return None
    return b if winner == a else a


def last_round_no(size: int) -> int:
    """Номер последнего круга. Финал и матч за третье место идут в ОДНОМ
    окне, поэтому последний круг держит четыре места, а не два: иначе
    вечер растягивался бы на лишний круг ради одной бронзы."""
    return rounds_left(size)


def step(slots: list, round_no: int, size: int, scores: dict,
         seeds: dict = None, totals: dict = None):
    """Следующий круг либо итоговые места.

    Возвращает (места следующего круга, призовые места). Одно из двух
    всегда пустое: круг либо продолжается, либо закончился.

    Полуфинал отдаёт ЧЕТЫРЕ места, а не два: победители становятся
    финалистами, проигравшие — парой за третье место, и оба матча
    играются в одном окне.
    """
    last = last_round_no(size)
    current = pairs(slots)

    # Последний круг: пара финала и пара за третье место
    if round_no >= last:
        if len(slots) == 2:
            return [], places(slots, None, scores, seeds, totals)
        if len(slots) >= 4:
            return [], places(slots[:2], (slots[2], slots[3]), scores,
                              seeds, totals)
        return [], []

    winners = [advance(p, scores, seeds, totals) for p in current]

    # Полуфинал — следом последний круг, значит добавляем проигравших
    if round_no == last - 1 and len(winners) == 2:
        beaten = [loser(p, w) for p, w in zip(current, winners)]
        return winners + beaten, []

    return winners, []


def places(final_slots: list, third_place, scores: dict,
           seeds: dict = None, totals: dict = None) -> list:
    """Итоговые места по порядку: первое, второе, третье, четвёртое.

    Третье берётся матчем проигравших в полуфинале, который идёт в одном
    окне с финалом. Иначе бронзу пришлось бы присуждать «по счёту в
    полуфинале», а это сравнение результатов против разных соперников.

    ЧЕТВЁРТОЕ ВОЗВРАЩАЕТСЯ ТОЖЕ, хотя в объявлении его нет. Человек
    дошёл до последнего круга и проиграл один матч — ему полагается
    утешительный приз, брелок или наклейки. Объявлять четвёртое место
    незачем: это звучит как «почти», а вот пригласить за призом лично —
    совсем другое дело. Сколько мест попадает в объявление, решает
    draw_events.prizes.
    """
    if len(final_slots) != 2:
        return []
    champion = advance((final_slots[0], final_slots[1]), scores, seeds, totals)
    runner_up = loser((final_slots[0], final_slots[1]), champion)
    out = [champion, runner_up]
    if third_place:
        third = advance(third_place, scores, seeds, totals)
        out.append(third)
        out.append(loser(third_place, third))
    return [x for x in out if x is not None]


def announced(all_places: list, prizes: int = 3):
    """(кого объявляем, кого зовём за призом молча)"""
    return all_places[:prizes], all_places[prizes:]
