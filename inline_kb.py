# inline_kb.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

language_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
     InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
    [InlineKeyboardButton(text="🇫🇷 Français", callback_data="lang_fr"),
     InlineKeyboardButton(text="🇮🇱 עברית", callback_data="lang_he")]
])

def get_main_menu(lang):
    titles = {
        "ru": ["🏆 Блок 1: Спорт и путешествия", "🎨 Блок 2: Творчество", "🧠 Блок 3: Интеллект и карьера", "🤖 Блок 4: Нейросеть Claude", "💼 Профили: HH & LinkedIn", "🎮 Интерактив: Игра"],
        "en": ["🏆 Block 1: Sports & Travel", "🎨 Block 2: Creativity", "🧠 Block 3: Intellect & Career", "🤖 Block 4: Claude AI", "💼 Profiles: HH & LinkedIn", "🎮 Interactive: Game"],
        "fr": ["🏆 Bloc 1 : Sport & Voyage", "🎨 Bloc 2 : Créativité", "🧠 Bloc 3 : Intellect & Carrière", "🤖 Bloc 4 : IA Claude", "💼 Profils : HH & LinkedIn", "🎮 Interactif: Jeu"],
        "he": ["בלוק 1: ספורט וטיולים 🏆", "בלוק 2: יצירתיות 🎨", "בלוק 3: אינטלקט וקריירה 🧠", "בלוק 4: בינה מלאכותית קלוד 🤖", "פרופילים: HH & LinkedIn 💼", "משחק אינטראקטיבי 🎮"]
    }
    m = titles.get(lang, titles["en"])
    # Тексты для кнопки VPN на 4 языках
    vpn_titles = {
        "ru": "🔌 Premium VPN",
        "en": "🔌 Premium VPN Service",
        "fr": "🔌 Service VPN Premium",
        "he": "🔌 שירות VPN פרימיום"
    }
    v_title = vpn_titles.get(lang, vpn_titles["en"])

    # Тексты для кнопки аналитики на 4 языках
    analytics_titles = {
        "ru": "📊 Бизнес-аналитика (Real-Time)",
        "en": "📊 Business Analytics (Real-Time)",
        "fr": "📊 Analyses Commerciales",
        "he": "📊 אנליטיקה עסקית"
    }
    a_title = analytics_titles.get(lang, analytics_titles["en"])

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=m[0], callback_data="menu_sport")],
        [InlineKeyboardButton(text=m[1], callback_data="menu_creative")],
        [InlineKeyboardButton(text=m[2], callback_data="menu_intellect")],
        [InlineKeyboardButton(text=m[3], callback_data="menu_claude")],
        [InlineKeyboardButton(text=m[4], callback_data="menu_profiles")],
        [InlineKeyboardButton(text=m[5], callback_data="menu_game")],
        [InlineKeyboardButton(text=v_title, callback_data="menu_vpn")],
        [InlineKeyboardButton(text=a_title, callback_data="menu_analytics")]  # Кнопка Аналитики
    ])

def get_sport_menu(lang):
    titles = {
        "ru": ["🎵 Музыка", "🌍 Путешествия", "🎾 Большой теннис", "🏇 Конный спорт", "🏌 Гольф", "🥎 Падел", "🏓 Настольный теннис", "📰 Новости", "⇦ В главное меню"],
        "en": ["🎵 Music", "🌍 Travel", "🎾 Tennis", "🏇 Equestrian", "🏌 Golf", "🥎 Padel", "🏓 Table Tennis", "📰 News", "⇦ Main Menu"],
        "fr": ["🎵 Musique", "🌍 Voyage", "🎾 Tennis", "🏇 Équitation", "🏌 Golf", "🥎 Padel", "🏓 Tennis de Table", "📰 Actualités", "⇦ Menu Principal"],
        "he": ["מוזיקה 🎵", "נסיעות 🌍", "טניס 🎾", "רכיבה על סוסים 🏇", "גולף 🏌", "פאדל 🥎", "טניס שולחן 🏓", "חדשות 📰", "⇦ לתפריט הראשי"]
    }
    m = titles.get(lang, titles["en"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=m[0], callback_data="sport_music")],
        [InlineKeyboardButton(text=m[1], callback_data="sport_travel")],
        [InlineKeyboardButton(text=m[2], callback_data="sport_tennis")],
        [InlineKeyboardButton(text=m[3], callback_data="sport_horse")],
        [InlineKeyboardButton(text=m[4], callback_data="sport_golf")],
        [InlineKeyboardButton(text=m[5], callback_data="sport_padel")],
        [InlineKeyboardButton(text=m[6], callback_data="sport_table_tennis")],
        [InlineKeyboardButton(text=m[7], callback_data="sport_news")],
        [InlineKeyboardButton(text=m[8], callback_data="go_home")]
    ])

def get_music_main_menu(lang):
    titles = {
        "ru": {"perf": "🎹 Мой репертуар", "comp": "📜 Топ-10 композиторов", "back": "🔙 Назад"},
        "en": {"perf": "🎹 My Repertoire", "comp": "📜 Top 10 Composers", "back": "🔙 Back"},
        "fr": {"perf": "🎹 Mon Répertoire", "comp": "📜 Top 10", "back": "🔙 Retour"},
        "he": {"perf": "רפרטואר הביצוע שלי 🎹", "comp": "טופ 10 מלחינים 📜", "back": "חזרה 🔙"}
    }
    t = titles.get(lang, titles["en"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["perf"], callback_data="music_my_perf")],
        [InlineKeyboardButton(text=t["comp"], callback_data="music_composers_hub")],
        [InlineKeyboardButton(text=t["back"], callback_data="menu_sport")]
    ])

def get_music_back_button(lang, target_callback="sport_music"):
    back_texts = {"ru": "⇦ Назад", "en": "⇦ Back", "fr": "⇦ Retour", "he": "⇦ חזרה"}
    text = back_texts.get(lang, back_texts["en"])
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=target_callback)]])

def get_travel_main_menu(lang):
    geo = "🗺 География визитов" if lang == "ru" else "🗺 Geography of Visits"
    tool = "🧮 Travel Toolkit" if lang == "ru" else "🧮 Travel Toolkit"
    back = "🔙 Назад" if lang == "ru" else "🔙 Back"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=geo, callback_data="travel_geography")],
        [InlineKeyboardButton(text=tool, callback_data="travel_toolkit")],
        [InlineKeyboardButton(text=back, callback_data="menu_sport")]
    ])

def get_tennis_main_menu(lang):
    g = "🗺 Мой опыт и база" if lang == "ru" else "🗺 Experience & Clubs"
    l = "🏆 Турниры & Стримы" if lang == "ru" else "🏆 Live Tournaments"
    s = "🛍 Реферальный Pro-Shop" if lang == "ru" else "🛍 Referral Pro-Shop"
    t = "🔒 Теория и Лайфхаки" if lang == "ru" else "🔒 Tennis Theory"
    b = "🔙 Назад" if lang == "ru" else "🔙 Back"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=g, callback_data="tennis_geography")],
        [InlineKeyboardButton(text=l, callback_data="tennis_live_matches")],
        [InlineKeyboardButton(text=s, callback_data="tennis_shop_referral")],
        [InlineKeyboardButton(text=t, callback_data="tennis_premium_theory")],
        [InlineKeyboardButton(text=b, callback_data="menu_sport")]
    ])

def get_horse_main_menu(lang):
    r = "🌾 Опыт верховой езды" if lang == "ru" else "🌾 Riding Experience"
    a = "📊 Аналитика скачек" if lang == "ru" else "📊 Race Analytics"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=r, callback_data="horse_riding_experience")],
        [InlineKeyboardButton(text=a, callback_data="horse_racing_analytics")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_sport")]
    ])

def get_golf_main_menu(lang):
    ru = "📖 Правила и этикет" if lang == "ru" else "📖 Rules & Etiquette"
    pl = "🏆 Мои игры и поля" if lang == "ru" else "🏆 My Games"
    jo = "👥 Закрытое сообщество" if lang == "ru" else "👥 Private Community"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ru, callback_data="golf_rules")],
        [InlineKeyboardButton(text=pl, callback_data="golf_places")],
        [InlineKeyboardButton(text=jo, callback_data="golf_join_community")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_sport")]
    ])

def get_news_main_menu(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 РФ" if lang=="ru" else "🇷🇺 Russia", callback_data="news_sub_ru"),
         InlineKeyboardButton(text="🇮🇱 Израиль" if lang=="ru" else "🇮🇱 Israel", callback_data="news_sub_il")],
        [InlineKeyboardButton(text="🇫🇷 Франция" if lang=="ru" else "🇫🇷 France", callback_data="news_sub_fr"),
         InlineKeyboardButton(text="🇺🇸 США" if lang=="ru" else "🇺🇸 USA", callback_data="news_sub_us")],
        [InlineKeyboardButton(text="📊 ROI-Отчеты" if lang=="ru" else "📊 ROI Reports", callback_data="news_sub_analytics")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_sport")]
    ])

def get_profiles_menu(lang):
    b0 = "🎯 Стратегическая архитектура" if lang == "ru" else "🎯 Strategic Architecture"
    b1 = "🏛 Банки" if lang == "ru" else "🏛 Banking"
    b2 = "📦 Логистика" if lang == "ru" else "📦 Logistics"
    b3 = "🚜 АПК" if lang == "ru" else "🚜 Agriculture"
    b4 = "✈ Машиностроение" if lang == "ru" else "✈ Manufacturing"
    short_cv = "📄 Краткая версия резюме" if lang == "ru" else "📄 Resume (Short Version)"
    full_info = "🌐 Подробнее обо мне и проектах" if lang == "ru" else "🌐 Full Portfolio & Projects"

    ck = [
        [InlineKeyboardButton(text=b0, callback_data="p_universal")],
        [InlineKeyboardButton(text=b1, callback_data="sub_bank")],
        [InlineKeyboardButton(text=b2, callback_data="sub_logistics")],
        [InlineKeyboardButton(text=b3, callback_data="sub_agro")],
        [InlineKeyboardButton(text=b4, callback_data="sub_production")],
        [InlineKeyboardButton(text="🌐 LinkedIn", url="https://www.linkedin.com/in/tatiana-malakhova-017a9b256/")],
        [InlineKeyboardButton(text=short_cv, url="https://drive.google.com/file/d/1m8z9MlA8g-NT1yP9KAhGbrKDymY4HpLN/view")],
        [InlineKeyboardButton(text=full_info, url="https://project7216905.tilda.ws/page74075639html")]
    ]
    if lang == "ru":
        ck.append([InlineKeyboardButton(text="💼 HeadHunter", url="https://hh.ru/resume/6d545f57ff100284c10039ed1f4d624f737135")])
    else:
        ck.append([InlineKeyboardButton(text="📄 Download CV", url="https://drive.google.com/file/d/1m8z9MlA8g-NT1yP9KAhGbrKDymY4HpLN/view")])
    ck.append([InlineKeyboardButton(text="⇦ Назад", callback_data="go_home")])
    return InlineKeyboardMarkup(inline_keyboard=ck)

def get_bank_submenu(exclude_prj=None):
    kb = [
        ("p_sb_dist", "🟢 Сбер: Платформа Дистрибуции"),
        ("p_sb_risk", "🟢 Сбер: Платформа сложных сделок"),
        ("p_sb_cash", "🟢 Сбер: Стресс-тестирование CashFlow"),
        ("p_sb_ml", "🟢 Сбер: ML-андеррайтинг недвижимости"),
        ("p_rsb", "🔵 Банк Русский Стандарт")
    ]
    buttons = [[InlineKeyboardButton(text=tx, callback_data=cb)] for cb, tx in kb if cb != exclude_prj]
    buttons.append([InlineKeyboardButton(text="🔙 Назад к секторам", callback_data="menu_profiles")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_logistics_submenu(exclude_prj=None):
    kb = [
        ("p_lg_sms", "📲 SPSR: СМС и Push"),
        ("p_lg_cust", "📲 SPSR: Автоматизация таможни"),
        ("p_lg_fts", "📲 SPSR: Отчетность ФТС"),
        ("p_lg_fulfill", "📲 SPSR: Фулфилмент"),
        ("p_lg_acq", "📲 SPSR: Мобильный эквайринг"),
        ("p_lg_unit", "📲 SPSR: Unit-экономика"),
        ("p_ev_adm", "📱 Евросеть: Администрирование"),
        ("p_ev_pro", "📱 Евросеть: Про-Сервис")
    ]
    buttons = [[InlineKeyboardButton(text=tx, callback_data=cb)] for cb, tx in kb if cb != exclude_prj]
    buttons.append([InlineKeyboardButton(text="🔙 Назад к секторам", callback_data="menu_profiles")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_agro_submenu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌾 АГРОЭКО: Инвест-проекты", callback_data="p_agroeco")],
        [InlineKeyboardButton(text="🔙 Назад к секторам", callback_data="menu_profiles")]
    ])

def get_production_submenu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙ ВАСО: Модернизация SAP ERP", callback_data="p_vaso_sap")],
        [InlineKeyboardButton(text="⚙ ВАСО: Модернизация 1C", callback_data="p_vaso_1c")],
        [InlineKeyboardButton(text="🔙 Назад к секторам", callback_data="menu_profiles")]
    ])

def get_composers_grid_menu(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎹 И.С. Бах" if lang=="ru" else "🎹 J.S. Bach", callback_data="comp_detail_bach")],
        [InlineKeyboardButton(text="✨ В.А. Моцарт" if lang=="ru" else "✨ W.A. Mozart", callback_data="comp_detail_mozart")],
        [InlineKeyboardButton(text="⚡ Л. Бетховен" if lang=="ru" else "⚡ L. Beethoven", callback_data="comp_detail_beethoven")],
        [InlineKeyboardButton(text="🎼 Ф. Шопен" if lang=="ru" else "🎼 F. Chopin", callback_data="comp_detail_chopin")],
        [InlineKeyboardButton(text="🎭 П.И. Чайковский" if lang=="ru" else "🎭 P.I. Tchaikovsky", callback_data="comp_detail_tchaikovsky")],
        [InlineKeyboardButton(text="🔥 С. Рахманинов" if lang=="ru" else "🔥 S. Rachmaninoff", callback_data="comp_detail_rachmaninoff")],
        [InlineKeyboardButton(text="🍃 А. Вивальди" if lang=="ru" else "🍃 A. Vivaldi", callback_data="comp_detail_vivaldi")],
        [InlineKeyboardButton(text="🌊 К. Дебюсси" if lang=="ru" else "🌊 C. Debussy", callback_data="comp_detail_debussy")],
        [InlineKeyboardButton(text="🎯 И. Брамс" if lang=="ru" else "🎯 J. Brahms", callback_data="comp_detail_brahms")],
        [InlineKeyboardButton(text="👑 Г.Ф. Гендель" if lang=="ru" else "👑 G.F. Handel", callback_data="comp_detail_handel")],
        [InlineKeyboardButton(text="⇦ Назад", callback_data="sport_music")]
    ])

def get_travel_back_button(lang, target):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⇦ Назад", callback_data=target)]])

def get_tennis_shop_action_menu(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 Открыть Pro-Shop", url="https://t.me")],
        [InlineKeyboardButton(text="⇦ Назад", callback_data="sport_tennis")]
    ])

def get_tennis_live_action_menu(lang):
    channel_text = "📺 Канал с трансляциями" if lang == "ru" else "📺 Live Streams Channel"
    back_text = "⇦ Назад" if lang == "ru" else "⇦ Back"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=channel_text, url="https://t.me/playintennisagain")],
        [InlineKeyboardButton(text=back_text, callback_data="sport_tennis")]
    ])

def get_tennis_pay_action_menu(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оформить подписку", callback_data="tennis_buy_subscription")],
        [InlineKeyboardButton(text="⇦ Назад", callback_data="sport_tennis")]
    ])

def get_horse_channel_action_menu(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Перейти в канал", url="https://t.me")],
        [InlineKeyboardButton(text="🤖 AI-Робот Маркет", callback_data="horse_ai_bot_market")],
        [InlineKeyboardButton(text="⇦ Назад", callback_data="sport_horse")]
    ])

def get_horse_bot_action_menu(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Купить робота", callback_data="horse_buy_robot_click")],
        [InlineKeyboardButton(text="⇦ Назад", callback_data="sport_horse")]
    ])

def get_golf_join_action_menu(lang):
    join_text = "⛳ Вступить в канал" if lang == "ru" else "⛳ Join the channel"
    back_text = "⇦ Назад" if lang == "ru" else "⇦ Back"
    # Ссылка-приглашение выдаётся не сразу: сначала блок1 спрашивает пароль,
    # поэтому здесь именно callback, а не url.
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=join_text, callback_data="golf_join_request")],
        [InlineKeyboardButton(text=back_text, callback_data="sport_golf")]
    ])

def get_game_menu(lang):
    back_texts = {"ru": "⇦ В главное меню", "en": "⇦ Main Menu", "fr": "⇦ Menu Principal", "he": "⇦ לתפריט הראשי"}
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=back_texts.get(lang, back_texts["en"]), callback_data="go_home")]
    ])

# =======================================================
# ДОПИСАНО: НАБОР МЕНЮ ДЛЯ БЛОКА 2 (ТВОРЧЕСТВО)
# =======================================================
def get_creative_menu(lang):
    p = "🎨 Картины и Арт-Хаб" if lang == "ru" else "🎨 Paintings & Art Hub"
    a = "👗 Ателье и Fashion" if lang == "ru" else "👗 Atelier & Fashion"
    c = "🍳 Кулинария" if lang == "ru" else "🍳 Haute Cuisine"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=p, callback_data="creative_paintings")],
        [InlineKeyboardButton(text=a, callback_data="creative_atelier")],
        [InlineKeyboardButton(text=c, callback_data="creative_culinary")],
        [InlineKeyboardButton(text="⇦ В главное меню" if lang == "ru" else "⇦ Main Menu", callback_data="go_home")]
    ])

def get_art_hub_main_menu(lang):
    g = "🖼 Моя галерея" if lang == "ru" else "🖼 My Gallery"
    s = "💰 Подписки и цены" if lang == "ru" else "💰 Subs & Prices"
    c = "📅 Календарь выставок" if lang == "ru" else "📅 Exhibition Calendar"
    f = "📝 Подать анкету автора" if lang == "ru" else "📝 Submit Artwork Form"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=g, callback_data="art_my_portfolio")],
        [InlineKeyboardButton(text=s, callback_data="art_subscriptions_prices")],
        [InlineKeyboardButton(text=c, callback_data="art_exhibitions_calendar")],
        [InlineKeyboardButton(text=f, callback_data="art_start_application_form")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_creative")]
    ])

def get_art_subs_markup(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Купить подписку" if lang == "ru" else "💳 Buy Subscription", callback_data="art_fsm_initiate_flow")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="creative_paintings")]
    ])

def get_art_form_trigger_markup(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Заполнить анкету" if lang == "ru" else "🚀 Fill Form", callback_data="art_fsm_initiate_flow")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="creative_paintings")]
    ])

def get_creative_atelier_menu(lang):
    c = "🧥 Моя капсульная коллекция" if lang == "ru" else "🧥 My Capsule Collection"
    h = "📜 История моды" if lang == "ru" else "📜 Fashion History"
    b = "🤝 B2B Интеграция бренда" if lang == "ru" else "🤝 B2B Brand Integration"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c, callback_data="atelier_my_collection")],
        [InlineKeyboardButton(text=h, callback_data="atelier_fashion_history")],
        [InlineKeyboardButton(text=b, callback_data="atelier_b2b_integration_form")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_creative")]
    ])

def get_atelier_b2b_action_menu(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать подачу заявки" if lang == "ru" else "🚀 Start B2B Form", callback_data="atelier_fsm_b2b_initiate")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="creative_atelier")]
    ])

def get_creative_culinary_menu(lang):
    b = "🎬 Видеорецепты" if lang == "ru" else "🎬 Video Recipes"
    m = "📖 Рецепты" if lang == "ru" else "📖 Recipes"
    d = "💪 Полезное" if lang == "ru" else "💪 Healthy"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=b, callback_data="culinary_cat_video")],
        [InlineKeyboardButton(text=m, callback_data="culinary_cat_recipes")],
        [InlineKeyboardButton(text=d, callback_data="culinary_cat_useful")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_creative")]
    ])

# =======================================================
# ДОПИСАНО: НАБОР МЕНЮ ДЛЯ БЛОКА 3 (ИНТЕЛЛЕКТ И КАРЬЕРА)
# =======================================================
def get_intellect_menu(lang):
    d = "📖 Дневник Директора" if lang == "ru" else "📖 Director's Diary"
    g = "🧬 Генетика и Наука" if lang == "ru" else "🧬 Genetics & Science"
    p = "🧩 Головоломки" if lang == "ru" else "🧩 Puzzles"
    b = "📚 Моя библиотека" if lang == "ru" else "📚 My Library"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=d, callback_data="menu_diary")],
        [InlineKeyboardButton(text=g, callback_data="intellect_genetics")],
        [InlineKeyboardButton(text=p, callback_data="intellect_puzzle")],
        [InlineKeyboardButton(text=b, callback_data="intellect_books")],
        [InlineKeyboardButton(text="⇦ В главное меню" if lang == "ru" else "⇦ Main Menu", callback_data="go_home")]
    ])

def get_diary_menu(lang):
    b = "💼 Бизнес-кейсы (ROI)" if lang == "ru" else "💼 Business Cases"
    e = "🏗 Инженерные лоты" if lang == "ru" else "🏗 Engineering Logs"
    p = "🧩 Перейти к задачам" if lang == "ru" else "🧩 Go to Puzzles"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=b, callback_data="diary_business")],
        [InlineKeyboardButton(text=e, callback_data="diary_engineering")],
        [InlineKeyboardButton(text=p, callback_data="intellect_puzzle")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_intellect")]
    ])

def get_genetics_hub_menu(lang):
    k = "📚 База знаний канала" if lang == "ru" else "📚 Channel knowledge base"
    n = "🌍 Новости генетики" if lang == "ru" else "🌍 Genetics news"
    o = "🧪 Заказать исследование" if lang == "ru" else "🧪 Order research"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=k, callback_data="genetics_channel_base")],
        [InlineKeyboardButton(text=n, callback_data="genetics_news")],
        [InlineKeyboardButton(text=o, callback_data="genetics_order")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_intellect")]
    ])

def get_books_shelf_menu(lang):
    b = "📈 Бизнес и Лидерство" if lang == "ru" else "📈 Business & Leadership"
    h = "🔭 Кругозор и Наука" if lang == "ru" else "🔭 Horizon & Science"
    t = "🛠 Полезный инструментарий" if lang == "ru" else "🛠 Strategy & Tools"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=b, callback_data="books_view_business")],
        [InlineKeyboardButton(text=h, callback_data="books_view_horizon")],
        [InlineKeyboardButton(text=t, callback_data="books_view_tools")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_intellect")]
    ])

def get_claude_pay_menu(lang):
    # Запасное меню оплаты/подписки для премиум-блоков
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оформить Premium" if lang == "ru" else "💳 Unlock Premium", callback_data="start_solving_puzzles")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_intellect")]
    ])

# КНОПКИ ВЫХОДА ИЗ ЧАТА CLAUDE (REPLY)
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

reply_exit_ru = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🛑 Покинуть чат с ИИ")]], resize_keyboard=True)
reply_exit_en = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🛑 Exit AI Chat")]], resize_keyboard=True)
reply_exit_fr = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🛑 Quitter le chat IA")]], resize_keyboard=True)
reply_exit_he = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🛑 צา מצ'אט AI")]], resize_keyboard=True)

# КНОПКИ ПОДТВЕРЖДЕНИЯ ДВУХЭТАПНОГО ВЫХОДА (REPLY)
confirm_exit_ru = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="⚠ Да, выйти в главное меню")],
    [KeyboardButton(text="🔙 Продолжить общение с Claude")]
], resize_keyboard=True)

confirm_exit_en = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="⚠ Yes, return to main menu")],
    [KeyboardButton(text="🔙 Continue chatting with Claude")]
], resize_keyboard=True)

confirm_exit_fr = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="⚠ Oui, retourner au menu")],
    [KeyboardButton(text="🔙 Continuer à discuter avec Claude")]
], resize_keyboard=True)

confirm_exit_he = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="⚠ כן, לחזור לתפריט הראשי")],
    [KeyboardButton(text="🔙 המשך לשוחח עם קלוד")]
], resize_keyboard=True)
