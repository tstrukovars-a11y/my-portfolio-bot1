# Сетка дня и отчёт об ошибке.
#
# Молчащий выпуск — самая дорогая поломка канала: пост не вышел, а
# причина лежала в логах Render, куда никто не ходит. Здесь проверяется
# то, что делает причину видимой.
import digest


def test_the_grid_names_every_slot():
    """Свой список названий был копией SLOT_TITLES, и новый слот в нём
    не появлялся — в сетке дня светилось служебное «art»."""
    source = open("digest.py", encoding="utf-8").read()
    body = source[source.index("for at, slot, _ in SCHEDULE:"):]
    body = body[:body.index("lines.append(\"\")")]
    assert "SLOT_TITLES.items()" in body, "сетка снова со своим списком"
    for _, slot, _ in digest.SCHEDULE:
        assert slot in digest.SLOT_TITLES, slot


def test_a_failed_slot_reports_where_it_broke():
    """«string index out of range» встречается в сотне мест: имя ошибки
    без места — не отчёт, а намёк."""
    source = open("digest.py", encoding="utf-8").read()
    body = source[source.index("async def _try_slot"):]
    body = body[:body.index("async def refresh_bot_name")]
    assert "extract_tb" in body and "lineno" in body
    assert "digest_last_error" in body


def test_the_manual_slot_answers_instead_of_staying_silent():
    """Владелица нажала и ждёт ответа, а получала его только в логах."""
    source = open("digest.py", encoding="utf-8").read()
    body = source[source.index('if command == "slot"'):]
    body = body[:body.index('if command == "tz"')]
    assert "_try_slot" in body
    assert "await publish_slot(bot" not in body, \
        "ручной выпуск снова зовёт слот напрямую и глотает ошибку"


def test_the_scheduler_also_records_the_place():
    source = open("digest.py", encoding="utf-8").read()
    body = source[source.index("Ошибка планировщика дайджеста"):]
    assert "extract_tb" in body[:900]


# --- дубль в группу ----------------------------------------------------
#
# Пост в канале есть, в группе его нет, и заметить это можно, только
# зайдя в группу и вспомнив, что там чего-то не хватает. Молчащая
# поломка хуже громкой ровно на то время, за которое её находят.

def test_a_failed_mirror_is_reported_to_the_owner():
    source = open("digest.py", encoding="utf-8").read()
    body = source[source.index("async def _mirror("):]
    body = body[:body.index("async def _ad_block")]
    assert "config.ADMIN_ID" in body, "о непрошедшем дубле знают только логи"
    assert "/id" in body, "не сказано, чем чинить"


def test_the_complaint_is_not_repeated_for_every_post():
    """Сломанная тема иначе напишет по сообщению на каждую публикацию."""
    source = open("digest.py", encoding="utf-8").read()
    body = source[source.index("async def _mirror("):]
    body = body[:body.index("async def _ad_block")]
    assert "mirror_fail_" in body


def test_a_fixed_mirror_forgets_the_old_complaint():
    """Иначе следующая поломка покажется повтором и промолчит."""
    source = open("digest.py", encoding="utf-8").read()
    body = source[source.index("async def _mirror("):]
    body = body[:body.index("async def _ad_block")]
    assert 'set_setting(f"mirror_fail_{section}", "")' in body


# --- дослать то, что не доехало ----------------------------------------
#
# Дубль делается в момент публикации, и пост, вышедший до того, как тема
# была задана, задним числом туда не попадёт. Переиздавать его ради
# этого — значит получить вторую копию в канале: читатель увидит одно и
# то же дважды, а виновата настройка, о которой он не знает.

def _remirror_body():
    source = open("digest.py", encoding="utf-8").read()
    body = source[source.index("async def remirror"):]
    return body[:body.index('@router.message(F.text.startswith("/digest"))')]


def test_there_is_a_way_to_resend_without_republishing():
    body = _remirror_body()
    assert "_mirror(" in body
    assert "publish_slot" not in body, "это переиздание, а не досылка"


def test_it_names_the_sections_it_knows():
    """«Раздел не тот» без списка возможных — загадка вместо ответа."""
    assert _remirror_body().count("SECTION_ALIASES") >= 2


def test_it_explains_where_to_take_the_post_number():
    assert "Копировать ссылку" in _remirror_body()


def test_paintings_are_among_the_sections_it_accepts():
    import digest
    assert digest.SECTION_ALIASES.get("картины") == "art"
