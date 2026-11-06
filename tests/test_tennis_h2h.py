"""Тесты на личные встречи перед матчем (tennis_h2h.py).

Статистику присылает владелица: у источника табло истории встреч нет, а
выдумывать её запрещено тем же правилом, по которому отложено движение
по рейтингу. Значит, главное здесь — чтобы присланное попало в пост без
искажений, а неправдоподобное не попало вовсе.
"""

import tennis_h2h as h2h


# ---------------------------------------------------------------------
# Разбор заголовка матча
# ---------------------------------------------------------------------


def test_names_are_split_on_a_long_dash():
    assert h2h._names("Рублёв — Алькарас") == ("Рублёв", "Алькарас")


def test_names_survive_a_short_dash():
    """Заголовок приходит из разных мест, и тире в нём не всегда одно."""
    assert h2h._names("Рублёв - Алькарас") == ("Рублёв", "Алькарас")


def test_a_title_without_a_dash_does_not_crash():
    assert h2h._names("матч") == ("матч", "")


# ---------------------------------------------------------------------
# Текст про встречи
# ---------------------------------------------------------------------


def _block(**fields):
    return h2h._stats_block("Рублёв", "Алькарас", fields)


def test_no_meetings_is_said_plainly():
    """«Личные встречи: 0» — отписка. Человек хочет прочесть фразу."""
    assert _block(meetings=0) == "Играют между собой впервые."


def test_score_is_counted_from_one_number():
    """Второе число считает бот: два введённых могли бы противоречить
    друг другу, и в посте оказалось бы 3:3 из четырёх встреч."""
    text = _block(meetings=4, wins_first=1)
    assert "Личные встречи: 4" in text
    assert "Счёт — 1:3" in text


def test_the_leader_is_named_after_a_colon():
    """Фамилии нельзя склонять автоматически, поэтому имя ставится после
    двоеточия, а не в середину фразы."""
    assert "впереди: Алькарас" in _block(meetings=4, wins_first=1)
    assert "впереди: Рублёв" in _block(meetings=4, wins_first=3)


def test_an_even_score_names_nobody():
    text = _block(meetings=4, wins_first=2)
    assert "поровну" in text
    assert "впереди" not in text


def test_surfaces_and_years_appear_when_given():
    text = _block(meetings=2, wins_first=1, surfaces="хард, грунт",
                  years="2024, 2025")
    assert "Покрытия: хард, грунт" in text
    assert "Годы: 2024, 2025" in text


def test_skipped_fields_leave_no_empty_lines():
    text = _block(meetings=2, wins_first=1, surfaces=None, years=None)
    assert "Покрытия" not in text
    assert "Годы" not in text


def test_the_note_goes_last():
    text = _block(meetings=2, wins_first=1, note="Оба идут без поражений.")
    assert text.rstrip().endswith("Оба идут без поражений.")


def test_html_in_the_note_is_escaped():
    """Владелица пишет текст руками, и «<» в нём не должен ронять пост."""
    text = _block(meetings=1, wins_first=1, note="матч <b>года")
    assert "&lt;b&gt;" in text


# ---------------------------------------------------------------------
# Что уходит в канал
# ---------------------------------------------------------------------


# ОТДЕЛЬНОГО ПОСТА «ПЕРЕД МАТЧЕМ» НЕТ, и тесты на него удалены вместе
# с ним. Он был лишним: статистика нужна тому, кто за матчем следит, и
# он получает её в уведомлении о подписке. Пост в канал повторял бы то
# же самое тем, кто этот матч смотреть не собирался.


def test_publishing_is_gone_for_good():
    """Мёртвая кнопка хуже отсутствующей: она нажимается и молчит."""
    assert not hasattr(h2h, "preview_text")
    assert not hasattr(h2h, "publish")
    import pathlib
    source = pathlib.Path("tennis_h2h.py").read_text()
    assert "h2hgo_" not in source, "кнопка ссылается на удалённый обработчик"


# ---------------------------------------------------------------------
# Пропуск необязательного
# ---------------------------------------------------------------------


def test_dashes_and_words_both_mean_skip():
    for word in ("-", "–", "—", "нет", "Пропустить", " далее "):
        assert h2h._skipped(word), word


def test_a_real_answer_is_not_a_skip():
    assert not h2h._skipped("хард, грунт")
    assert not h2h._skipped("2024")


# ---------------------------------------------------------------------
# Граница «служебное не выходит в канал»
# ---------------------------------------------------------------------


def test_filling_buttons_are_not_allowed_under_channel_posts():
    """Диалог заполнения живёт только в личке у владелицы. Если такая
    кнопка однажды окажется под постом, граница её не пропустит."""
    import public
    assert not public.allowed("h2hfill_atp_123")
    assert not public.allowed("h2hgo_atp_123")


def test_there_is_a_ceiling_on_meetings():
    """Защита не от злого умысла, а от опечатки: «44» вместо «4» уехало
    бы в канал как факт."""
    assert 0 < h2h.MAX_MEETINGS <= 100


# ---------------------------------------------------------------------
# Откуда берётся пара фамилий
# ---------------------------------------------------------------------
#
# Кнопка «заполнить встречи» стоит теперь в двух разных сообщениях: в
# запросе статистики и в карточке подписки. Разбор по номеру абзаца
# работал только в первом.


def test_the_pair_is_found_wherever_it_stands():
    text = ("🔔 Напоминание включено\n\n"
            "Шелтон — Шубладзе · Париж\n"
            "Начало в 18:00.")
    assert h2h._title_from(text) == "Шелтон — Шубладзе · Париж"


def test_the_pair_is_found_in_the_stats_request():
    text = ("📊 Статистики по этому матчу нет\n\n"
            "Жабин — Петров\n\n"
            "Заполните личные встречи.")
    assert h2h._title_from(text) == "Жабин — Петров"


def test_a_short_dash_also_counts():
    assert h2h._title_from("Жабин - Петров") == "Жабин - Петров"


def test_text_without_a_pair_gives_nothing():
    assert h2h._title_from("Просто сообщение") == ""
    assert h2h._title_from("") == ""


def test_a_dangling_dash_is_not_a_pair():
    assert h2h._title_from("Начало — ") == ""


# ---------------------------------------------------------------------
# История, которую бот копит сам
# ---------------------------------------------------------------------
#
# У источника истории встреч нет: он отдаёт сегодняшнее табло и забывает
# о нём через день. Поэтому каждый завершённый матч записывается парой
# игроков — строка «Шелтон — Шубладзе» не даёт спросить «все матчи этой
# пары», а пара даёт.

import datetime


def test_initials_and_case_do_not_split_one_person():
    assert h2h.normalize("Б. Шелтон") == h2h.normalize("ШЕЛТОН")
    assert h2h.normalize("Шелтон") == "шелтон"


def test_yo_and_ye_are_the_same_person():
    """«Алёна» и «Алена» в источниках встречаются обе."""
    assert h2h.normalize("Алёна") == h2h.normalize("Алена")


def test_the_pair_is_the_same_in_both_directions():
    assert h2h.pair_key("Шелтон", "Крыстя") == h2h.pair_key("Крыстя", "Шелтон")


def test_an_empty_name_does_not_crash():
    assert h2h.normalize("") == ""
    assert h2h.normalize(None) == ""


def _meeting(winner, surface=None, year=2025):
    return {"winner": winner, "score": "6:4 6:3", "tournament": "Рим",
            "surface": surface, "played_on": datetime.date(year, 5, 12)}


def test_wins_are_counted_for_the_first_name():
    history = [_meeting("шелтон"), _meeting("крыстя"), _meeting("шелтон")]
    got = h2h.summarize(history, "Шелтон", "Крыстя")
    assert got["meetings"] == 3
    assert got["wins_first"] == 2


def test_surfaces_are_listed_without_repeats():
    history = [_meeting("шелтон", "грунт"), _meeting("крыстя", "грунт"),
               _meeting("шелтон", "хард")]
    assert h2h.summarize(history, "Шелтон", "Крыстя")["surfaces"] == "грунт, хард"


def test_unknown_surfaces_are_simply_absent():
    """Пустое поле честнее выдуманного: выдуманное выглядит как факт."""
    history = [_meeting("шелтон"), _meeting("крыстя")]
    assert h2h.summarize(history, "Шелтон", "Крыстя")["surfaces"] is None


def test_years_are_sorted_and_unique():
    history = [_meeting("шелтон", year=2025), _meeting("крыстя", year=2023),
               _meeting("шелтон", year=2025)]
    assert h2h.summarize(history, "Шелтон", "Крыстя")["years"] == "2023, 2025"


def test_the_summary_feeds_the_same_block_as_manual_stats():
    """Текст один и тот же, откуда бы ни пришли числа — иначе читатель
    увидит два разных формата на соседних матчах."""
    history = [_meeting("шелтон", "грунт")]
    got = h2h.summarize(history, "Шелтон", "Крыстя")
    text = h2h._stats_block("Шелтон", "Крыстя", got)
    assert "Личные встречи: 1" in text
    assert "впереди: Шелтон" in text


# ---------------------------------------------------------------------
# Заполнять может только владелица
# ---------------------------------------------------------------------


def test_the_fill_button_is_added_only_for_the_owner():
    """Кнопка не показывается читателю вовсе — это служебное действие."""
    import inspect
    import tennis_alerts
    body = inspect.getsource(tennis_alerts._confirm)
    assert "config.is_admin(user_id)" in body
    assert body.index("config.is_admin(user_id)") < body.index("h2hfill_")


def test_the_handler_checks_again_on_its_own():
    """Вторая проверка в обработчике: кнопку можно нажать и по старому
    сообщению, и из пересланного — доверять её наличию нельзя."""
    import inspect
    assert "config.is_admin(call.from_user.id)" in inspect.getsource(
        h2h.start_filling)


def test_filling_never_works_from_a_channel_post():
    import public
    assert not public.allowed("h2hfill_atp_1")
