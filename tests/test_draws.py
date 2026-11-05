"""Тесты на панель конкурса (draws.py).

Пять действий владелицы: начать, завести призы, разослать место
вручения, переписываться с призёрами, завершить фотографией. Здесь —
то, что проверяется без Telegram: имена для ссылок, подписи мест и
граница «служебное в канал не выходит».
"""

import draws


# ---------------------------------------------------------------------
# Короткое имя для ссылки по QR
# ---------------------------------------------------------------------


def test_russian_title_becomes_a_latin_slug():
    assert draws._slug("Северная Пальмира") == "severnaya-palmira"


def test_spaces_and_punctuation_become_single_dashes():
    assert draws._slug("Кубок  клуба — 2026") == "kubok-kluba-2026"


def test_a_slug_never_starts_or_ends_with_a_dash():
    got = draws._slug("  — Пальмира —  ")
    assert not got.startswith("-") and not got.endswith("-")


def test_an_empty_title_still_gives_a_usable_slug():
    """Пустое имя в ссылку попасть не должно — там будет «event»."""
    assert draws._slug("") == "event"
    assert draws._slug("!!!") == "event"


def test_a_slug_is_short_enough_for_a_link():
    assert len(draws._slug("Очень длинное название " * 10)) <= 40


# ---------------------------------------------------------------------
# Подписи мест
# ---------------------------------------------------------------------


def test_the_podium_has_medals():
    assert "🥇" in draws._place_word(1)
    assert "🥈" in draws._place_word(2)
    assert "🥉" in draws._place_word(3)


def test_the_fourth_place_has_no_medal():
    """Четвёртое не объявляется вслух, и медали у него нет."""
    word = draws._place_word(4)
    assert "🥇" not in word and "🥈" not in word and "🥉" not in word
    assert "4" in word


def test_three_places_are_announced_by_default():
    assert draws.DEFAULT_PRIZES == 3


# ---------------------------------------------------------------------
# Граница: служебное в канал не выходит
# ---------------------------------------------------------------------


def test_owner_buttons_never_work_under_a_channel_post():
    """Вся панель живёт в личке. Если кнопка окажется под постом,
    граница обязана её остановить."""
    import public
    for data in ("drnew", "draws_list", "drevent_1", "drprizes_1",
                 "drprize_1_2", "drmeet_1", "drsend_1", "drsched_1",
                 "drlaunch_1", "drtalk_1_42", "drstop_1", "drfinish_1"):
        assert not public.allowed(data), data


def test_only_the_join_button_works_in_the_channel():
    """«Участвовать» висит под постом канала — ей можно. И только ей."""
    import public
    assert public.allowed("drjoin_1")


def test_the_winner_reply_button_is_also_private():
    """Её нажимает призёр, но тоже в личке — под постом ей не место."""
    import public
    assert not public.allowed("drreply_1")


# ---------------------------------------------------------------------
# Расписание матчей
# ---------------------------------------------------------------------
#
# Заводится одним сообщением: по строке на матч. Вопрос по каждому
# уходит участникам в минуту начала, а не заранее — зритель отвечает,
# глядя на корт.

from datetime import date


DAY = date(2026, 11, 7)


def test_a_simple_line_is_parsed():
    good, bad = draws.parse_schedule("18:00 Окунев — Кураков", DAY)
    assert bad == []
    when, first, second = good[0]
    assert (when.hour, when.minute) == (18, 0)
    assert (first, second) == ("Окунев", "Кураков")


def test_several_lines_become_several_matches():
    good, _ = draws.parse_schedule(
        "18:00 Окунев — Кураков\n19:30 Новиков — Кабочкин", DAY)
    assert len(good) == 2
    assert good[1][0].hour == 19 and good[1][0].minute == 30


def test_any_dash_works():
    """Заставлять набирать длинное тире — верный способ получить
    «не разобралось» на половине списка."""
    for dash in ("—", "–", "-", "vs"):
        good, bad = draws.parse_schedule(f"18:00 Окунев {dash} Кураков", DAY)
        assert len(good) == 1, dash
        assert bad == [], dash


def test_a_dot_in_the_time_is_accepted():
    good, _ = draws.parse_schedule("18.45 Окунев — Кураков", DAY)
    assert good[0][0].minute == 45


def test_blank_lines_are_skipped_silently():
    good, bad = draws.parse_schedule(
        "\n18:00 Окунев — Кураков\n\n\n", DAY)
    assert len(good) == 1 and bad == []


def test_a_broken_line_is_reported_not_swallowed():
    """Молча проглотить строку расписания хуже, чем сказать «вот эту я
    не поняла»: матч бы просто не состоялся в конкурсе."""
    good, bad = draws.parse_schedule(
        "18:00 Окунев — Кураков\nкогда-нибудь вечером", DAY)
    assert len(good) == 1
    assert bad == ["когда-нибудь вечером"]


def test_a_line_without_a_second_name_is_rejected():
    good, bad = draws.parse_schedule("18:00 Окунев —", DAY)
    assert good == []
    assert len(bad) == 1


def test_a_bad_clock_is_rejected():
    good, bad = draws.parse_schedule("25:99 Окунев — Кураков", DAY)
    assert good == []
    assert len(bad) == 1


def test_the_answer_window_is_a_quarter_of_an_hour():
    """Зритель отвечает по ходу матча, а не до него."""
    assert draws.POLL_MINUTES == 15


# ---------------------------------------------------------------------
# Перекличка — это первый круг сетки
# ---------------------------------------------------------------------
#
# Отдельной стадии нет намеренно: пары раздаются всем, кто нажал
# «Участвовать», и не явившиеся выбывают сами. Отдельный отборочный круг
# только дублировал бы это лишним ожиданием.


def test_the_bracket_starts_from_everyone_who_joined():
    import inspect
    import draws_runner
    body = inspect.getsource(draws_runner.start_bracket)
    assert "draw_members" in body


def test_there_is_no_separate_qualifier_stage_left():
    """Мёртвый код хуже удалённого: он сбивает того, кто откроет файл
    следующим."""
    import database
    assert not hasattr(database, "draw_qualify_scores")
    assert not hasattr(draws, "QUALIFY_MINUTES")


def test_owner_control_buttons_stay_out_of_the_channel():
    import public
    for data in ("drstatus_1", "drdraw_1", "drsheet_1"):
        assert not public.allowed(data), data


# ---------------------------------------------------------------------
# Правила
# ---------------------------------------------------------------------
#
# Читают их до того, как нажмут «Участвовать», — значит, они публичны и
# выходят в канал отдельным сообщением, а не прячутся за кнопкой в боте.


def test_the_rules_name_every_rule_the_code_actually_follows():
    """Если правило есть в коде, но не в правилах, спорить будет не о чем
    и нечем."""
    rules = draws.RULES_DEFAULT
    for must in ("15 минут", "5 минут", "двух выигранных сетов",
                 "засчитывается сопернику", "больше очков в сумме",
                 "первое, второе и третье"):
        assert must in rules, must


def test_the_rules_and_the_code_agree_on_set_length():
    """Правила описывают код, код следует правилам. Разойдутся — и спор
    на площадке будет не о теннисе."""
    import draws_runner
    assert f"{draws_runner.SET_MINUTES} минут" in draws.RULES_DEFAULT
    assert f"{draws.POLL_MINUTES} минут" in draws.RULES_DEFAULT


def test_the_rules_say_the_answer_is_final_and_so_does_the_code():
    """Главное расхождение, которое пришлось чинить: правила говорили
    «менять нельзя», а база разрешала переставить голос."""
    assert "менять нельзя" in draws.RULES_DEFAULT
    import inspect
    import database
    body = inspect.getsource(database.draw_answer)
    assert "DO NOTHING" in body
    assert "DO UPDATE" not in body


def test_a_contest_cannot_be_announced_with_blanks_left():
    """Если в правилах оставлена подстановка в квадратных скобках,
    объявлять нельзя: это обещание призов без условий."""
    import inspect
    body = inspect.getsource(draws.launch)
    assert "Сначала заполните в правилах" in body


def test_the_rules_go_out_before_the_contest_post():
    """Сначала правила, следом пост с кнопкой — иначе человек нажмёт
    раньше, чем прочитает."""
    import inspect
    body = inspect.getsource(draws.launch)
    rules_at = body.index("send_message(chat, rules_text")
    post_at = min(body.index("send_photo(chat"), body.index("send_message(chat, body"))
    assert rules_at < post_at


def test_the_default_rules_are_ready_to_publish():
    """В тексте владелицы подстановок не осталось — его можно объявлять
    как есть, и проверка на скобки не должна его задерживать."""
    assert "[" not in draws.RULES_DEFAULT


def test_the_rules_fit_a_telegram_message():
    """В подпись к фотографии они не влезут — там тысяча символов, —
    поэтому и идут отдельным сообщением. Но и в него надо уложиться."""
    assert len(draws.RULES_DEFAULT) < 4096


# ---------------------------------------------------------------------
# Свой канал у конкурса
# ---------------------------------------------------------------------
#
# Ради безопасной репетиции. Настройка digest_chat одна на весь бот, и
# менять её ради теста опасно: забыли вернуть — утренний выпуск ушёл в
# закрытый канал.


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_a_contest_channel_beats_the_global_one():
    chat, thread = _run(draws.event_channel({"channel_id": -1009999}))
    assert chat == -1009999
    assert thread is None


def test_without_its_own_channel_the_digest_one_is_used(monkeypatch):
    import asyncio
    import digest
    monkeypatch.setattr(digest, "_target",
                        lambda: asyncio.sleep(0, result=(-100123, 7)))
    chat, thread = _run(draws.event_channel({"channel_id": None}))
    assert (chat, thread) == (-100123, 7)


def test_publishing_never_reaches_for_the_global_channel_directly():
    """Если где-то снова позвать digest._target() напрямую, тестовый
    конкурс уедет в «Акцент» — ровно то, от чего это и заведено."""
    import inspect
    for fn in (draws.launch, draws.finish_send):
        body = inspect.getsource(fn)
        assert "digest._target" not in body, fn.__name__
        assert "event_channel" in body, fn.__name__


def test_the_channel_button_is_owner_only():
    import public
    assert not public.allowed("drchan_1")
