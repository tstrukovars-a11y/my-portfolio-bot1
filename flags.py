# flags.py — флаг страны по её названию.
#
# Флаг не хранится в базе вместе с местом: это оформление, а не данные.
# Храни мы его строкой, смена вида потребовала бы переписать восемьдесят
# записей вместо одной строки здесь.
#
# Ключ — русское название, потому что именно оно лежит в country_ru и
# приходит из разбора списка. Английское поддержано вторым слоем: раздел
# показывает его англоязычным посетителям.

_BY_RU = {
    "Австрия": "🇦🇹", "Беларусь": "🇧🇾", "Великобритания": "🇬🇧",
    "Германия": "🇩🇪", "Греция": "🇬🇷", "Грузия": "🇬🇪", "Египет": "🇪🇬",
    "Израиль": "🇮🇱", "Испания": "🇪🇸", "Италия": "🇮🇹", "Кипр": "🇨🇾",
    "Латвия": "🇱🇻", "Литва": "🇱🇹", "Лихтенштейн": "🇱🇮", "Монако": "🇲🇨",
    "Нидерланды": "🇳🇱", "Норвегия": "🇳🇴", "ОАЭ": "🇦🇪", "Польша": "🇵🇱",
    "Португалия": "🇵🇹", "Россия": "🇷🇺", "США": "🇺🇸", "Таиланд": "🇹🇭",
    "Турция": "🇹🇷", "Украина": "🇺🇦", "Финляндия": "🇫🇮", "Франция": "🇫🇷",
    "Хорватия": "🇭🇷", "Черногория": "🇲🇪", "Чехия": "🇨🇿", "Швейцария": "🇨🇭",
    "Швеция": "🇸🇪", "Эстония": "🇪🇪", "Япония": "🇯🇵",
}

# Олимпийские трёхбуквенные коды → ISO-2. ESPN отдаёт страну теннисиста
# только картинкой: .../countries/500/esp.png. Само эмодзи собираем из
# двух букв, поэтому здесь нужны лишь те коды, где ИОК расходится с ISO
# (chi — Чили, а не Китай; ger — Германия; sui — Швейцария).
_IOC = {
    "and": "AD", "arg": "AR", "arm": "AM", "aus": "AU", "aut": "AT",
    "bel": "BE", "bih": "BA", "blr": "BY", "bol": "BO", "bra": "BR",
    "bul": "BG", "can": "CA", "chi": "CL", "chn": "CN", "col": "CO",
    "cro": "HR", "cze": "CZ", "den": "DK", "egy": "EG", "esp": "ES",
    "est": "EE", "fin": "FI", "fra": "FR", "gbr": "GB", "geo": "GE",
    "ger": "DE", "gre": "GR", "hkg": "HK", "hun": "HU", "ina": "ID",
    "ind": "IN", "ita": "IT", "jpn": "JP", "kaz": "KZ", "kor": "KR",
    "lat": "LV", "ltu": "LT", "mex": "MX", "mkd": "MK", "mon": "MC",
    "ned": "NL", "nor": "NO", "par": "PY", "per": "PE", "phi": "PH",
    "pol": "PL", "por": "PT", "rom": "RO", "rsa": "ZA", "rus": "RU",
    "ser": "RS", "slo": "SI", "sui": "CH", "svk": "SK", "swe": "SE",
    "tha": "TH", "tpo": "TW", "tun": "TN", "tur": "TR", "ukr": "UA",
    "uru": "UY", "usa": "US", "uzb": "UZ",
    # встречаются реже, но встречаются
    "alg": "DZ", "bah": "BS", "bar": "BB", "civ": "CI", "cyp": "CY",
    "dom": "DO", "ecu": "EC", "irl": "IE", "isl": "IS", "isr": "IL",
    "jam": "JM", "ksa": "SA", "kuw": "KW", "lux": "LU", "mar": "MA",
    "mas": "MY", "mda": "MD", "mlt": "MT", "nzl": "NZ", "pak": "PK",
    "pur": "PR", "qat": "QA", "sen": "SN", "sgp": "SG", "sri": "LK",
    "tto": "TT", "uae": "AE", "ven": "VE", "vie": "VN", "zim": "ZW",
}


def by_code(code: str) -> str:
    """Флаг по коду страны (ИОК или ISO-2). Незнакомый код — пустая строка."""
    if not code:
        return ""
    clean = code.strip().lower()
    iso = _IOC.get(clean, clean.upper() if len(clean) == 2 else "")
    if len(iso) != 2 or not iso.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in iso.upper())


_BY_EN = {
    "Austria": "🇦🇹", "Belarus": "🇧🇾", "United Kingdom": "🇬🇧", "Germany": "🇩🇪",
    "Greece": "🇬🇷", "Georgia": "🇬🇪", "Egypt": "🇪🇬", "Israel": "🇮🇱",
    "Spain": "🇪🇸", "Italy": "🇮🇹", "Cyprus": "🇨🇾", "Latvia": "🇱🇻",
    "Lithuania": "🇱🇹", "Liechtenstein": "🇱🇮", "Monaco": "🇲🇨",
    "Netherlands": "🇳🇱", "Norway": "🇳🇴", "Poland": "🇵🇱", "Portugal": "🇵🇹",
    "Russia": "🇷🇺", "United States": "🇺🇸", "Thailand": "🇹🇭", "Turkey": "🇹🇷",
    "Ukraine": "🇺🇦", "Finland": "🇫🇮", "France": "🇫🇷", "Croatia": "🇭🇷",
    "Montenegro": "🇲🇪", "Czechia": "🇨🇿", "Switzerland": "🇨🇭", "Sweden": "🇸🇪",
    "Estonia": "🇪🇪", "Japan": "🇯🇵",
}


def flag(country_ru: str = "", country_en: str = "") -> str:
    """Флаг либо пустая строка. Неизвестная страна остаётся без флага —
    это заметно и чинится добавлением строки, а подставленный наугад
    чужой флаг незаметен и живёт годами."""
    return _BY_RU.get((country_ru or "").strip()) or \
        _BY_EN.get((country_en or "").strip()) or ""


def with_flag(country_ru: str = "", country_en: str = "", label: str = None) -> str:
    """«🇫🇷 Франция». Без флага — просто название, без лишнего пробела."""
    name = label if label is not None else (country_ru or country_en or "")
    mark = flag(country_ru, country_en)
    return f"{mark} {name}".strip() if mark else name
