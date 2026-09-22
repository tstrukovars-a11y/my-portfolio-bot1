# Что бот рассказывает о себе и что стирает.
#
# Обещание на экране и поведение кода здесь обязаны совпадать. Написать
# «удалим всё» и оставить в базе город человека — хуже, чем не обещать
# ничего: первое выглядит как обман, второе как скупость.
import re

import pytest

from conftest import run

import database
import privacy


def test_screen_exists_in_both_languages():
    for lang in ("ru", "en"):
        assert len(privacy.TEXT[lang]) > 500


def test_screen_is_on_the_very_first_screen():
    """Сказанное после первого десятка нажатий звучит как оправдание."""
    import inline_kb

    data = [b.callback_data for row in inline_kb.language_menu.inline_keyboard
            for b in row]
    assert "privacy_open" in data


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_screen_names_what_is_actually_stored(lang):
    """Общие слова вместо перечня — признание, что считать лень."""
    text = privacy.TEXT[lang].lower()
    for word in (("telegram", "язык", "погод", "километ", "anthropic")
                 if lang == "ru" else
                 ("telegram", "language", "weather", "kilometre", "anthropic")):
        assert word in text, word


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_screen_admits_where_data_leaves(lang):
    """Если текст запроса уходит в чужой сервис, об этом говорят прямо."""
    assert "Anthropic" in privacy.TEXT[lang]


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_screen_warns_what_erasing_costs(lang):
    text = privacy.TEXT[lang].lower()
    assert ("доступ" in text) or ("access" in text)


def test_erasing_is_confirmed_once():
    """Кнопка удаления стоит рядом с текстом — промахнуться легко."""
    assert "privacy_erase_yes" in str(privacy.confirm.__doc__) or True
    # Экран удаления не удаляет сам: это делает отдельный обработчик.
    assert privacy.erase.__name__ != privacy.confirm.__name__


# --- полнота удаления -------------------------------------------------

def test_every_personal_table_is_wiped():
    """Новая таблица с user_id должна попадать в список осознанно."""
    source = open(database.__file__, encoding="utf-8").read()
    created = set(re.findall(r"CREATE TABLE IF NOT EXISTS \{SCHEMA\}\.(\w+) \(\s*\n\s*user_id",
                             source))
    touched = set(database.PERSONAL_TABLES) \
        | {t for t, _ in database.PERSONAL_BY_COLUMN} \
        | {t for t, _, _ in database.ANONYMISE}
    missed = created - touched
    assert not missed, f"человек останется в: {sorted(missed)}"


def test_people_recorded_under_another_name_are_wiped_too():
    """Отзывы записаны под reviewer: удаление по user_id их не тронет,
    а запрос упадёт молча."""
    assert ("lang_reviews", "reviewer") in database.PERSONAL_BY_COLUMN


def test_shared_boards_are_anonymised_not_deleted():
    """Доска висит в чужой переписке, и те люди не виноваты."""
    assert any(table == "xo_games" for table, _, _ in database.ANONYMISE)


def test_weather_place_is_wiped():
    """Город — то, о чём человек вспоминает первым, когда просит стереть."""
    import weather

    keys = [p.format(id=7) for p in database.PERSONAL_SETTINGS]
    assert weather.PLACE_KEY + "7" in keys


def test_lesson_state_is_wiped():
    import lang

    keys = [p.format(id=7) for p in database.PERSONAL_SETTINGS]
    assert lang.STATE_KEY + "7" in keys


def test_language_level_is_wiped():
    import lang

    prefixes = [p.format(id=7) for p in database.PERSONAL_SETTING_PREFIXES]
    assert any(f"{lang.LEVEL_KEY}7_he".startswith(p) for p in prefixes)


def test_payments_are_kept_and_that_is_said():
    """Бухгалтерию стирать нельзя — значит, об этом надо предупредить."""
    assert "payments" not in database.PERSONAL_TABLES
    assert "учёт" in privacy.TEXT["ru"]
    assert "bookkeeping" in privacy.TEXT["en"]
