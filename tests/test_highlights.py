# Нарезки матчей. Живого матча в открытом доступе нет, нарезка есть —
# и это единственное видео, которое можно дать читателю, ничего не
# нарушая. Значит, разбирать заголовок надо без ошибок: подпись под
# чужим видео хуже отсутствия видео.
import tennis_highlights as th


def test_both_tours_write_the_title_differently():
    """У WTA игроки стоят до первой черты, у ATP — слово Highlights
    прилеплено к фамилии. Разметка одна на обоих."""
    assert th.parse(
        "Lilli Tagger vs. Harriet Dart | 2026 Guangzhou Final "
        "| WTA Match Highlights") == (
        "Lilli Tagger", "Harriet Dart", "2026 Guangzhou Final")

    assert th.parse(
        "Alexander Zverev vs Alex de Minaur Highlights "
        "| Basel 2026 Semi-Finals") == (
        "Alexander Zverev", "Alex de Minaur", "Basel 2026 Semi-Finals")


def test_a_clip_is_not_a_highlight():
    """В ленте вперемешку нарезки, шортсы и «The Guys Play Trick Or
    Treat». В канал идут только матчи."""
    assert th.parse("The Guys Play 'Trick Or Treat?' | Berrettini, Rublev") is None
    assert th.parse("Dart fires back 💥 Harriet Dart is pushing for the title") is None
    assert th.parse("Perfect way to close out the year 💜 #WTA #TorayPPO") is None


def test_the_semifinal_does_not_become_the_final():
    """«Basel 2026 Semi-Finals» кончается на «finals», и короткий ключ
    совпал бы первым: полуфинал в Базеле превращался в финал."""
    assert th.event_ru("Basel 2026 Semi-Finals") == "Базель, 1/2 финала"
    assert th.event_ru("2026 Tokyo Final") == "Токио, финал"
    assert th.event_ru("Vienna 2026 Quarter-Finals") == "Вена, 1/4 финала"
    assert th.event_ru("Paris 2026 Round of 16") == "Paris, 1/8 финала"


def test_the_year_goes_away():
    """Читатель смотрит сегодняшнюю нарезку, и «2026» сообщает ему
    только то, что сейчас 2026 год."""
    assert "2026" not in th.event_ru("Basel 2026 Semi-Finals")


def test_only_matches_with_a_known_name_go_out():
    assert th.worth_posting("Diana Shnaider", "Leylah Fernandez")
    assert th.worth_posting("Carlos Alcaraz", "Someone Unknown")
    assert not th.worth_posting("Lilli Tagger", "Harriet Dart")


def test_the_caption_names_the_players_in_russian():
    said = th.line("Diana Shnaider", "Leylah Fernandez", "2026 Tokyo Final")
    assert "Шнайдер" in said
    assert "Токио, финал" in said
