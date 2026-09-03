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
    "Michael Zheng": "Майкл Чжэн",
    "Arthur Rinderknech": "Артюр Риндеркнеш",
    "Jaume Munar": "Жауме Мунар",
    "Daniel Altmaier": "Даниэль Альтмайер",
    "Fabian Marozsan": "Фабиан Марожан",
    "Coleman Wong": "Коулман Вонг",
    "Marton Fucsovics": "Мартон Фучович",
    "Yoshihito Nishioka": "Ёсихито Нисиока",
    "Shintaro Mochizuki": "Синтаро Мотидзуки",
    "Rinky Hijikata": "Ринки Хиджиката",
    "Quentin Halys": "Кантен Али",

    # женщины, которых не хватало на «Шлеме»
    "Taylor Townsend": "Тейлор Таунсенд",
    "Sorana Cirstea": "Сорана Кырстя",
    "Diane Parry": "Диан Парри",
    "Karolina Pliskova": "Каролина Плишкова",
    "Clara Tauson": "Клара Таусон",
    "Sloane Stephens": "Слоан Стивенс",
    "Katerina Siniakova": "Катержина Синякова",
    "Elisabetta Cocciaretto": "Элизабетта Коччаретто",
    "Anastasia Zakharova": "Анастасия Захарова",
    "Maya Joint": "Майя Джойнт",
    "Ann Li": "Энн Ли",
    "Antonia Ruzic": "Антония Ружич",
    "Caty McNally": "Кэти Макналли",
    "Lucrezia Stefanini": "Лукреция Стефанини",
    "Xiyu Wang": "Ван Сиюй",
    "Zheng Qinwen": "Чжэн Циньвэнь",
    "Bu Yunchaokete": "Бу Юньчаокэтэ",
    "Botic Van De Zandschulp": "Ботик ван де Зандсхюлп",
    "Leolia Jeanjean": "Леолия Жанжан",
    "Jurij Rodionov": "Юрий Родионов",
    "Nadia Podoroska": "Надя Подороска",
    "Dane Sweeny": "Дейн Суини",
    "Tristan Schoolkate": "Тристан Скулкейт",
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


# Практическая транслитерация. Словарь покрывает первые сотни рейтинга, но
# на «Шлеме» в сетке 128 человек, и половина имён оставалась латиницей —
# в списке из восьми строк получалась каша из двух алфавитов.
#
# Правила приблизительные и местами промахиваются (Beaulieu станет
# «Беаулиеу»). Это осознанный размен: связный русский список читается
# лучше смеси, а любое имя правится строкой в _RU выше.
_PAIRS = [
    ("shch", "щ"), ("sch", "ш"), ("tsch", "ч"),
    ("cie", "си"), ("ce", "се"), ("ci", "си"), ("cy", "си"),
    ("sh", "ш"), ("ch", "ч"), ("zh", "ж"), ("kh", "х"), ("gh", "г"),
    ("ph", "ф"), ("th", "т"), ("ck", "к"), ("qu", "кв"),
    ("ee", "и"), ("oo", "у"), ("ou", "у"), ("ei", "ей"), ("ie", "ие"),
    ("ya", "я"), ("ye", "е"), ("yu", "ю"), ("yo", "ё"),
    ("ju", "ю"), ("ja", "я"), ("je", "е"),
    ("zs", "ж"), ("cz", "ч"), ("cs", "ч"), ("sz", "с"), ("rz", "ж"),
    ("a", "а"), ("b", "б"), ("c", "к"), ("d", "д"), ("e", "е"),
    ("f", "ф"), ("g", "г"), ("h", "х"), ("i", "и"), ("j", "й"),
    ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"),
    ("p", "п"), ("q", "к"), ("r", "р"), ("s", "с"), ("t", "т"),
    ("u", "у"), ("v", "в"), ("w", "в"), ("x", "кс"), ("y", "и"),
    ("z", "з"),
]
_VOWELS = "aeiouy"


def _translit_word(word: str) -> str:
    low = word.lower()
    out, i = [], 0
    while i < len(low):
        # «ts» в начале слова — «ц» (Tsitsipas), внутри — «тс» (Knutson)
        if low.startswith("ts", i):
            out.append("ц" if i == 0 else "тс")
            i += 2
            continue
        # «ie» на конце — «и» (Sophie), внутри — «ие» (Gabriela)
        if low.startswith("ie", i) and i + 2 == len(low):
            out.append("и")
            i += 2
            continue
        # начальное «e» звучит как «э»: Ella, Emma
        if i == 0 and low[0] == "e" and not low.startswith("ei"):
            out.append("э")
            i += 1
            continue
        for src, dst in _PAIRS:
            if low.startswith(src, i):
                # «y» после гласной звучит как «й»: Sweeny → Суини,
                # но Bautista-y → …й.
                if src == "y" and i and low[i - 1] in _VOWELS:
                    dst = "й"
                out.append(dst)
                i += len(src)
                break
        else:
            out.append(low[i])
            i += 1
    word_ru = "".join(out)
    return word_ru[:1].upper() + word_ru[1:]


def translit(name: str) -> str:
    """Латиница → кириллица по частям имени, с сохранением дефисов"""
    parts = []
    for chunk in name.split():
        parts.append("-".join(_translit_word(w) for w in chunk.split("-")))
    return " ".join(parts)


def ru(name: str) -> str:
    """Русское имя игрока: из словаря, а иначе транслитерацией"""
    if not name:
        return name
    clean = name.strip()
    # Своё написание перевешивает словарь: его вписали, потому что в
    # словаре было неверно или пусто.
    if clean in _OVERRIDES:
        return _OVERRIDES[clean]
    if clean in _RU:
        return _RU[clean]

    # По фамилии подставляем только тогда, когда имени и нет: «I. Swiatek»
    # или просто «Swiatek». С полным именем это подменяет человека —
    # Michael Zheng становился Чжэн Циньвэнь.
    words = clean.replace(".", ". ").split()
    initials_only = len(words) < 2 or all(
        len(w.rstrip(".")) <= 1 for w in words[:-1])
    if initials_only:
        surname = words[-1].lower().rstrip(".")
        if surname in _BY_SURNAME:
            return _BY_SURNAME[surname]
    # Уже кириллица — не трогаем
    if any("а" <= ch.lower() <= "я" or ch in "ёЁ" for ch in clean):
        return clean
    return translit(clean)


# =====================================================================
# КОГО ПОКАЗЫВАТЬ ОБЯЗАТЕЛЬНО
# =====================================================================
#
# В сетке «Шлема» полторы сотни имён, и большинство читателю ничего не
# говорит. Отбираем два круга: свои — россияне и те, кто уехал под другой
# флаг, но остался «нашим» для аудитории, — и первая двадцатка рейтинга.
#
# Источник посева и рейтинга не отдаёт, поэтому список ручной. Он
# устаревает: рейтинг меняется каждую неделю, и раз в пару месяцев сюда
# надо заглядывать. Ошибка здесь безобидна — матч просто не попадёт в
# расписание, счёт и сетка всё равно доступны по кнопке.

_NASHI = {
    # Россия
    "medvedev", "rublev", "khachanov", "safiullin", "karatsev", "kotov",
    "shevchenko", "donskoy",
    "andreeva", "shnaider", "samsonova", "alexandrova", "pavlyuchenkova",
    "kudermetova", "kalinskaya", "potapova", "rakhimova", "zakharova",
    "korneeva", "avanesyan", "blinkova", "kasatkina", "gracheva",
    # уехали под другой флаг, но для аудитории свои
    "rybakina", "putintseva", "bublik", "shapovalov", "svitolina",
    "kostyuk", "starodubtseva", "azarenka", "sabalenka",
}

# Первая двадцатка с небольшим запасом
_TOP = {
    "sinner", "alcaraz", "djokovic", "zverev", "fritz", "draper", "ruud",
    "musetti", "de minaur", "medvedev", "shelton", "rublev", "paul",
    "tsitsipas", "rune", "cerundolo", "khachanov", "humbert", "tiafoe",
    "machac", "cobolli", "lehecka", "fils", "mensik", "auger-aliassime",
    "sabalenka", "swiatek", "gauff", "pegula", "paolini", "zheng qinwen",
    "navarro", "rybakina", "badosa", "keys", "andreeva", "kasatkina",
    "haddad maia", "krejcikova", "vekic", "svitolina", "kostyuk",
    "muchova", "samsonova", "alexandrova", "shnaider", "collins",
}


# Имена, где фамилия стоит первой: сверять надо по первому слову.
_SURNAME_FIRST = {"zheng", "bu", "wang", "zhang", "li", "sun", "yuan", "shang"}


def _key(name: str) -> str:
    """Фамилия в нижнем регистре — по ней и сверяем"""
    clean = (name or "").replace(".", " ").strip().lower()
    parts = clean.split()
    if not parts:
        return ""
    # Двусоставные фамилии: «de Minaur», «Haddad Maia»
    if len(parts) >= 2 and parts[-2] in ("de", "van", "haddad", "auger", "bautista"):
        return " ".join(parts[-2:])
    # У восточных имён фамилия первая, и одной её мало: Zheng Qinwen —
    # первая ракетка, а Michael Zheng — юниор из США с той же фамилией.
    if parts[0] in _SURNAME_FIRST:
        return " ".join(parts[:2]) if len(parts) > 1 else parts[0]
    return parts[-1]


# Живой рейтинг и свои написания приезжают из базы: список в коде —
# только запасной вариант на случай, если рейтинг ещё не подтянулся.
_LIVE_TOP = set()
_OVERRIDES = {}


def set_top(names) -> int:
    """Заменить список сильнейших тем, что пришёл из рейтинга"""
    global _LIVE_TOP
    _LIVE_TOP = {_key(n) for n in names if n}
    return len(_LIVE_TOP)


def set_overrides(mapping) -> int:
    """Свои написания имён, добавленные через бота"""
    global _OVERRIDES
    _OVERRIDES = dict(mapping or {})
    return len(_OVERRIDES)


def add_nash(name: str):
    """Пополнить круг своих — например, россиянина из свежего рейтинга"""
    _NASHI.add(_key(name))


def is_nash(name: str) -> bool:
    return _key(name) in _NASHI


def is_top(name: str) -> bool:
    key = _key(name)
    return key in (_LIVE_TOP or _TOP)


def notable(name: str) -> bool:
    """Стоит ли этот матч ставить в расписание"""
    return is_nash(name) or is_top(name)
