# players_ru.py — русские написания имён теннисистов.
#
# Источник расписания англоязычный, а канал русский. Автоматическая
# транслитерация тут не годится совсем: Swiatek она превращает в
# «Свиатек», хотя по-русски Швёнтек, а Tsitsipas — в «Тситсипас».
# Поэтому словарь, а не правило.
#
# Незнакомое имя остаётся латиницей. Непереведённое видно и чинится
# добавлением строки; неверно переведённое выглядит как знание и живёт
# годами.

_RU = {
    # мужчины
    "Jannik Sinner": "Янник Синнер",
    "Carlos Alcaraz": "Карлос Алькарас",
    "Novak Djokovic": "Новак Джокович",
    "Alexander Zverev": "Александр Зверев",
    "Daniil Medvedev": "Даниил Медведев",
    "Andrey Rublev": "Андрей Рублёв",
    "Karen Khachanov": "Карен Хачанов",
    "Stefanos Tsitsipas": "Стефанос Циципас",
    "Taylor Fritz": "Тейлор Фриц",
    "Casper Ruud": "Каспер Рууд",
    "Holger Rune": "Хольгер Руне",
    "Alex de Minaur": "Алекс де Минор",
    "Grigor Dimitrov": "Григор Димитров",
    "Hubert Hurkacz": "Хуберт Хуркач",
    "Tommy Paul": "Томми Пол",
    "Ben Shelton": "Бен Шелтон",
    "Frances Tiafoe": "Фрэнсис Тиафо",
    "Lorenzo Musetti": "Лоренцо Музетти",
    "Ugo Humbert": "Юго Умбер",
    "Felix Auger-Aliassime": "Феликс Оже-Альяссим",
    "Sebastian Korda": "Себастьян Корда",
    "Matteo Berrettini": "Маттео Берреттини",
    "Rafael Nadal": "Рафаэль Надаль",
    "Stan Wawrinka": "Стан Вавринка",
    "Gael Monfils": "Гаэль Монфис",
    "Denis Shapovalov": "Денис Шаповалов",
    "Alexander Bublik": "Александр Бублик",
    "Jack Draper": "Джек Дрейпер",
    "Arthur Fils": "Артюр Фис",
    "Jakub Mensik": "Якуб Меншик",
    "Tomas Machac": "Томаш Махач",
    "Flavio Cobolli": "Флавио Коболли",
    "Nuno Borges": "Нуну Боржеш",
    "Alejandro Tabilo": "Алехандро Табило",
    "Sebastian Baez": "Себастьян Баэс",
    "Francisco Cerundolo": "Франсиско Серундоло",
    "Roberto Bautista Agut": "Роберто Баутиста Агут",
    "Daniel Evans": "Дэниел Эванс",
    "Adrian Mannarino": "Адриан Маннарино",
    "Marin Cilic": "Марин Чилич",

    # женщины
    "Aryna Sabalenka": "Арина Соболенко",
    "Iga Swiatek": "Ига Швёнтек",
    "Coco Gauff": "Коко Гауфф",
    "Elena Rybakina": "Елена Рыбакина",
    "Jessica Pegula": "Джессика Пегула",
    "Jasmine Paolini": "Жасмин Паолини",
    "Qinwen Zheng": "Чжэн Циньвэнь",
    "Emma Navarro": "Эмма Наварро",
    "Daria Kasatkina": "Дарья Касаткина",
    "Barbora Krejcikova": "Барбора Крейчикова",
    "Danielle Collins": "Даниэль Коллинз",
    "Beatriz Haddad Maia": "Беатрис Хаддад Майя",
    "Madison Keys": "Мэдисон Киз",
    "Paula Badosa": "Паула Бадоса",
    "Mirra Andreeva": "Мирра Андреева",
    "Diana Shnaider": "Диана Шнайдер",
    "Liudmila Samsonova": "Людмила Самсонова",
    "Ekaterina Alexandrova": "Екатерина Александрова",
    "Anastasia Pavlyuchenkova": "Анастасия Павлюченкова",
    "Veronika Kudermetova": "Вероника Кудерметова",
    "Elina Svitolina": "Элина Свитолина",
    "Marta Kostyuk": "Марта Костюк",
    "Victoria Azarenka": "Виктория Азаренко",
    "Karolina Muchova": "Каролина Мухова",
    "Marketa Vondrousova": "Маркета Вондроушова",
    "Petra Kvitova": "Петра Квитова",
    "Ons Jabeur": "Онс Жабер",
    "Leylah Fernandez": "Лейла Фернандес",
    "Naomi Osaka": "Наоми Осака",
    "Venus Williams": "Винус Уильямс",
    "Anna Kalinskaya": "Анна Калинская",
    "Donna Vekic": "Донна Векич",
    "Yulia Putintseva": "Юлия Путинцева",
    "Magdalena Frech": "Магдалена Фрех",
    "Linda Noskova": "Линда Носкова",
    "Katie Boulter": "Кэти Боултер",
    "Emma Raducanu": "Эмма Радукану",
    "Sofia Kenin": "София Кенин",
    "Maria Sakkari": "Мария Саккари",
    "Belinda Bencic": "Белинда Бенчич",
    "Eva Lys": "Ева Лис",
    "Alina Korneeva": "Алина Корнеева",
    "Yuliia Starodubtseva": "Юлия Стародубцева",
    "Anna Bondar": "Анна Бондар",
    "Robin Montgomery": "Робин Монтгомери",
    "Elina Avanesyan": "Элина Аванесян",
    "Anastasia Potapova": "Анастасия Потапова",
    "Polina Kudermetova": "Полина Кудерметова",
    "Kamilla Rakhimova": "Камилла Рахимова",
    "Erika Andreeva": "Эрика Андреева",

    # мужчины, которых не хватало
    "Corentin Moutet": "Корантен Муте",
    "Mattia Bellucci": "Маттиа Беллуччи",
    "Jan-Lennard Struff": "Ян-Леннард Штруфф",
    "Zizou Bergs": "Зизу Бергс",
    "Carlos Taberner": "Карлос Табернер",
    "Filip Misolic": "Филип Мизолич",
    "Francisco Comesana": "Франсиско Комесанья",
    "Roman Safiullin": "Роман Сафиуллин",
    "Pavel Kotov": "Павел Котов",
    "Aslan Karatsev": "Аслан Карацев",
    "Jacob Fearnley": "Джейкоб Фирнли",
    "Learner Tien": "Лернер Тьен",
    "Joao Fonseca": "Жоао Фонсека",
    "Alexei Popyrin": "Алексей Попырин",
    "Matteo Arnaldi": "Маттео Арнальди",
    "Luciano Darderi": "Лучано Дардери",
    "Gabriel Diallo": "Габриэль Диалло",
    "Brandon Nakashima": "Брэндон Накашима",
    "Alex Michelsen": "Алекс Микельсен",
    "Tallon Griekspoor": "Таллон Грикспор",
    "Botic van de Zandschulp": "Ботик ван де Зандсхюлп",
}

# По фамилии — на случай, когда источник отдаёт имя иначе («I. Swiatek»,
# «Swiatek I.»). Собирается из основного словаря, чтобы не расходиться.
_BY_SURNAME = {}
for _en, _ru in _RU.items():
    _BY_SURNAME.setdefault(_en.split()[-1].lower(), _ru)


# Турниры. Крупные переводим, остальные оставляем как есть: названия
# небольших турниров по-русски пишут кто во что горазд, и выдумывать
# ещё один вариант незачем.
_EVENTS = {
    "Australian Open": "Australian Open",
    "Roland Garros": "Ролан Гаррос",
    "French Open": "Ролан Гаррос",
    "Wimbledon": "Уимблдон",
    "US Open": "US Open",
    "ATP Finals": "Итоговый турнир ATP",
    "WTA Finals": "Итоговый турнир WTA",
    "Davis Cup": "Кубок Дэвиса",
    "Billie Jean King Cup": "Кубок Билли Джин Кинг",
    "Indian Wells": "Индиан-Уэллс",
    "Miami Open": "Майами",
    "Monte Carlo": "Монте-Карло",
    "Madrid Open": "Мадрид",
    "Italian Open": "Рим",
    "Canadian Open": "Канада",
    "Cincinnati": "Цинциннати",
    "Shanghai": "Шанхай",
    "Paris Masters": "Париж",
    "Dubai": "Дубай",
    "Doha": "Доха",
    "Stuttgart": "Штутгарт",
    "Halle": "Галле",
    "Queen\'s Club": "Куинс",
    "Eastbourne": "Истборн",
    "Washington": "Вашингтон",
    "Tokyo": "Токио",
    "Beijing": "Пекин",
    "Vienna": "Вена",
    "Basel": "Базель",
}


def event(name: str) -> str:
    """Русское название турнира либо исходное"""
    if not name:
        return ""
    clean = name.strip()
    if clean in _EVENTS:
        return _EVENTS[clean]
    for en, ru_name in _EVENTS.items():
        if en.lower() in clean.lower():
            return ru_name
    return clean


# Стадии турнира. Источник пишет их по-английски и вперемешку
# («Quarterfinals», «QF», «Round of 16»), приводим к одному виду.
_ROUNDS = {
    "final": "финал",
    "f": "финал",
    "semifinal": "1/2 финала",
    "semifinals": "1/2 финала",
    "sf": "1/2 финала",
    "quarterfinal": "1/4 финала",
    "quarterfinals": "1/4 финала",
    "qf": "1/4 финала",
    "round of 16": "1/8 финала",
    "r16": "1/8 финала",
    "round of 32": "1/16 финала",
    "r32": "1/16 финала",
    "round of 64": "1/32 финала",
    "r64": "1/32 финала",
    "round of 128": "1/64 финала",
    "r128": "1/64 финала",
    "1st round": "1-й круг",
    "first round": "1-й круг",
    "2nd round": "2-й круг",
    "second round": "2-й круг",
    "3rd round": "3-й круг",
    "third round": "3-й круг",
    "round robin": "групповой этап",
    # так их пишет ESPN на «Шлемах»
    "round 1": "1-й круг",
    "round 2": "2-й круг",
    "round 3": "3-й круг",
    "round 4": "1/8 финала",
    "quarterfinal": "1/4 финала",
    "semifinal": "1/2 финала",
    "qualifying 1st round": "квалификация, 1-й круг",
    "qualifying 2nd round": "квалификация, 2-й круг",
    "qualifying 3rd round": "квалификация, 3-й круг",
    "qualifying final": "квалификация, решающий круг",
    "qualifying": "квалификация",
    "qualification": "квалификация",
}


def rnd(name: str) -> str:
    """Русское название стадии либо исходное"""
    if not name:
        return ""
    return _ROUNDS.get(name.strip().lower(), name.strip())


def ru(name: str) -> str:
    """Русское имя игрока либо исходное, если такого в словаре нет"""
    if not name:
        return name
    clean = name.strip()
    if clean in _RU:
        return _RU[clean]
    surname = clean.replace(".", " ").split()[-1].lower() if clean else ""
    return _BY_SURNAME.get(surname, clean)
