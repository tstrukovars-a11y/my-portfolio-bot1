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
}

# По фамилии — на случай, когда источник отдаёт имя иначе («I. Swiatek»,
# «Swiatek I.»). Собирается из основного словаря, чтобы не расходиться.
_BY_SURNAME = {}
for _en, _ru in _RU.items():
    _BY_SURNAME.setdefault(_en.split()[-1].lower(), _ru)


def ru(name: str) -> str:
    """Русское имя игрока либо исходное, если такого в словаре нет"""
    if not name:
        return name
    clean = name.strip()
    if clean in _RU:
        return _RU[clean]
    surname = clean.replace(".", " ").split()[-1].lower() if clean else ""
    return _BY_SURNAME.get(surname, clean)
