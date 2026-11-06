#  surfaces.py — покрытие корта по названию турнира.
#
#  ЗАЧЕМ. В истории личных встреч покрытие — половина смысла: победа над
#  тем же соперником на грунте и на траве говорят о разном. У источника
#  табло этого поля нет совсем.
#
#  ОТКУДА БЕРЁМ. Из справочника ниже. Покрытия крупных турниров не
#  меняются годами, и выписать их можно уверенно. Чего в справочнике
#  нет — возвращаем None и спрашиваем у владелицы: придуманное покрытие
#  хуже отсутствующего, потому что выглядит как факт.
#
#  ОСТОРОЖНО СО ШТУТГАРТОМ. Он есть у обоих туров и покрытия у них
#  РАЗНЫЕ: у мужчин трава, у женщин грунт в зале. Поэтому поиск
#  принимает тур, а не только название.

HARD = "хард"
CLAY = "грунт"
GRASS = "трава"

# Ключ — кусок названия в нижнем регистре, какой приходит от источника.
# Проверяется вхождением: «Rolex Paris Masters» находится по «paris».
COMMON = {
    # Шлемы
    "australian open": HARD,
    "roland garros": CLAY,
    "french open": CLAY,
    "wimbledon": GRASS,
    "us open": HARD,

    # Мастерсы и тысячники
    "indian wells": HARD,
    "miami": HARD,
    "monte-carlo": CLAY,
    "monte carlo": CLAY,
    "madrid": CLAY,
    "internazionali": CLAY,
    "rome": CLAY,
    "roma": CLAY,
    "toronto": HARD,
    "montreal": HARD,
    "canadian open": HARD,
    "national bank open": HARD,
    "cincinnati": HARD,
    "shanghai": HARD,
    "paris": HARD,          # Rolex Paris Masters — зал
    "turin": HARD,
    "nitto atp finals": HARD,
    "wta finals": HARD,

    # Грунт
    "barcelona": CLAY,
    "munich": CLAY,
    "estoril": CLAY,
    "geneva": CLAY,
    "hamburg": CLAY,
    "bastad": CLAY,
    "gstaad": CLAY,
    "kitzbuhel": CLAY,
    "umag": CLAY,
    "rio": CLAY,
    "buenos aires": CLAY,
    "santiago": CLAY,
    "cordoba": CLAY,
    "marrakech": CLAY,
    "charleston": CLAY,
    "strasbourg": CLAY,
    "rabat": CLAY,
    "parma": CLAY,
    "bucharest": CLAY,

    # Трава
    "halle": GRASS,
    "queen": GRASS,
    # «london» ключом не ставим: под него попал бы любой лондонский
    # турнир, включая зальные. Куинс и так находится по «queen».
    "hertogenbosch": GRASS,
    "eastbourne": GRASS,
    "mallorca": GRASS,
    "newport": GRASS,
    "birmingham": GRASS,
    "nottingham": GRASS,
    "berlin": GRASS,

    # Хард
    "doha": HARD,
    "dubai": HARD,
    "acapulco": HARD,
    "delray beach": HARD,
    "dallas": HARD,
    "los cabos": HARD,
    "winston-salem": HARD,
    "atlanta": HARD,
    "washington": HARD,
    "tokyo": HARD,
    "beijing": HARD,
    "china open": HARD,
    "astana": HARD,
    "vienna": HARD,
    "basel": HARD,
    "antwerp": HARD,
    "metz": HARD,
    "stockholm": HARD,
    "adelaide": HARD,
    "brisbane": HARD,
    "auckland": HARD,
    "montpellier": HARD,
    "rotterdam": HARD,
    "marseille": HARD,
    "rio open": CLAY,
    "guadalajara": HARD,
    "monterrey": HARD,
    "cleveland": HARD,
    "san diego": HARD,
    "ningbo": HARD,
    "zhengzhou": HARD,
    "wuhan": HARD,
    "seoul": HARD,
    "osaka": HARD,
    "linz": HARD,
    "cluj": HARD,
}

# Турниры, которые есть у обоих туров с РАЗНЫМ покрытием.
BY_TOUR = {
    "stuttgart": {"atp": GRASS, "wta": CLAY},
    "s-hertogenbosch": {"atp": GRASS, "wta": GRASS},
}


def of(tournament: str, tour: str = None):
    """Покрытие по названию турнира. None — не знаем, и врать не будем.

    Сначала турниры с разным покрытием у туров, потом общий справочник.
    Поиск вхождением: названия от источника бывают с приставками вроде
    «Rolex» и «presented by».
    """
    name = (tournament or "").strip().lower()
    if not name:
        return None

    for key, by_tour in BY_TOUR.items():
        if key in name:
            return by_tour.get((tour or "").lower())

    # Длинные ключи проверяем раньше: «rio open» должен победить «rio»,
    # а «us open» не должен срабатывать внутри «australian open».
    for key in sorted(COMMON, key=len, reverse=True):
        if key in name:
            return COMMON[key]
    return None


def known() -> int:
    """Сколько турниров в справочнике — для отчёта владелице."""
    return len(COMMON) + len(BY_TOUR)
