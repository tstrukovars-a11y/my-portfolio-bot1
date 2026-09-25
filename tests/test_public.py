# Граница между каналом и личкой.
#
# Кнопка под постом приходит вместе с самим постом: call.message — это
# опубликованное сообщение. Обработчик делает привычное
# message.answer(...) — и меню печатается в «Акценте» у всех на виду.
#
# Так и случилось: кнопка «Как это касается меня» под утренним выпуском
# развернула список разборов прямо в канале. А шаг разбора идёт через
# edit_text и delete — то есть любой читатель мог переписать или стереть
# опубликованный выпуск.
#
# Здесь проверяется обратное правило: в общем чате запрещено всё, кроме
# названного поимённо. Обработчик, написанный завтра, должен оказаться
# закрытым по умолчанию.
import pytest

from conftest import run

import config
import public


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class Button:
    def __init__(self, text, callback_data=None, url=None):
        self.text = text
        self.callback_data = callback_data
        self.url = url


class Bot:
    def __init__(self, closed=False):
        self.sent = []
        self.closed = closed

    async def send_message(self, chat, text, **kw):
        if self.closed:
            raise RuntimeError("bot can't initiate conversation with a user")
        self.sent.append({"chat": chat, "text": text,
                          "markup": kw.get("reply_markup")})


class Post:
    """Сообщение, под которым стоит кнопка.

    Повторяет то, чем обработчики пользуются на живом посте: если
    оставить здесь один answer, проверка запретов окажется проверкой
    того, что метода нет, а не того, что он закрыт.
    """

    def __init__(self, chat_type="channel", markup=None, chat_id=-100123):
        self.chat = type("C", (), {"type": chat_type, "id": chat_id})()
        self.reply_markup = markup
        self.said = []
        self.redrawn = 0

    async def answer(self, text="", **kw):
        self.said.append(text)

    reply = answer_photo = answer_document = answer
    edit_text = answer

    async def delete(self):
        self.said.append("<удалено>")

    async def forward(self, *a, **kw):
        self.said.append("<переслано>")

    async def copy_to(self, *a, **kw):
        self.said.append("<скопировано>")

    async def pin(self, *a, **kw):
        self.said.append("<закреплено>")

    async def edit_reply_markup(self, **kw):
        self.redrawn += 1


class Call:
    def __init__(self, data, chat_type="channel", markup=None,
                 user_id=777, bot=None, message=True):
        self.data = data
        self.message = Post(chat_type, markup) if message else None
        self.from_user = type("U", (), {"id": user_id})()
        self.bot = bot or Bot()
        self.popups = []

    async def answer(self, text="", **kw):
        self.popups.append(text)


def run_guard(call):
    """Прогнать нажатие через границу. Список — что дошло до обработчика."""
    reached = []

    async def handler(event, data):
        reached.append(event)
        return "отработал"

    run(public.keep_private(handler, call, {}))
    return reached


# --- в канале работает только названное поимённо ----------------------

def test_the_menu_does_not_open_in_the_channel():
    """То, с чего всё началось: список разборов печатался в «Акценте»."""
    call = Call("eco_open")
    assert not run_guard(call), "обработчик запустился под постом"
    assert not call.message.said, "в канал всё-таки написали"


def test_a_reader_cannot_rewrite_the_post():
    """Шаг разбора идёт через edit_text по call.message — то есть по
    опубликованному выпуску. Обработчик не должен получить его в руки."""
    assert not run_guard(Call("tre_e_t1_n1"))


@pytest.mark.parametrize("data", [
    "admin_urgent", "urg_go", "subs_open", "go_home", "crs_a_1",
    "pay_ok_5", "tree_open", "trd_e_t1", "mine_open",
])
def test_everything_personal_stays_out_of_the_channel(data):
    assert not run_guard(Call(data))


@pytest.mark.parametrize("data", ["vote_morning_12", "pz_7_2", "xo_5_4"])
def test_buttons_meant_for_the_post_keep_working(data):
    """Отклик и задача дня отвечают окошком и правят свою же разметку —
    в чужой чат они не пишут, и ломать их нельзя."""
    assert run_guard(Call(data)), f"{data} перестала работать под постом"


def test_the_inline_game_is_not_touched():
    """Инлайн-поле живёт в чужом чате, своего чата у него нет: утечь
    ответу некуда. Игра в чатах без приложений — сама суть затеи."""
    assert run_guard(Call("xoi_4", message=False))


def test_in_private_everything_works_as_before():
    assert run_guard(Call("eco_open", chat_type="private"))


def test_a_new_handler_is_closed_by_default():
    """Главное свойство: запрещено всё, кроме названного. Иначе завтра
    появится ещё одна кнопка и утечёт так же, как дерево."""
    assert not run_guard(Call("whatever_new_feature_2027"))


# --- человек получает то, за чем шёл ----------------------------------

def test_the_person_gets_the_same_button_in_private():
    markup = Markup([[Button("📊 Как это касается меня", "eco_open")]])
    call = Call("eco_open", markup=markup)
    run_guard(call)

    assert len(call.bot.sent) == 1
    sent = call.bot.sent[0]
    assert sent["chat"] == 777, "написали не тому человеку"
    button = sent["markup"].inline_keyboard[0][0]
    assert button.callback_data == "eco_open"
    assert button.text == "📊 Как это касается меня", \
        "в личке кнопка должна выглядеть так же, иначе человек её не узнает"


def test_the_person_is_told_where_it_opened():
    call = Call("eco_open")
    run_guard(call)
    assert call.popups and "личке" in call.popups[0]


def test_a_stranger_who_never_wrote_to_the_bot_is_told_how():
    """Telegram не даёт боту написать первым. Человек должен понять,
    почему ничего не произошло."""
    call = Call("eco_open", bot=Bot(closed=True))
    run_guard(call)
    assert call.popups and "Напишите" in call.popups[0]


def test_the_label_falls_back_when_the_button_is_gone():
    call = Call("eco_open", markup=Markup([[Button("Другое", "other")]]))
    run_guard(call)
    assert call.bot.sent[0]["markup"].inline_keyboard[0][0].text == "Открыть"


# --- команды в общем чате ---------------------------------------------

class Msg:
    def __init__(self, text, chat_type="supergroup", user_id=777):
        self.text = text
        self.chat = type("C", (), {"type": chat_type, "id": -100999})()
        self.from_user = type("U", (), {"id": user_id})()
        self.bot = Bot()


def run_commands(message):
    reached = []

    async def handler(event, data):
        reached.append(event)

    run(public.commands_stay_private(handler, message, {}))
    return reached


def test_a_stranger_cannot_open_the_menu_in_the_group(monkeypatch):
    """В группе-дубле команда разворачивает разделы бота у всех на виду."""
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    assert not run_commands(Msg("/меню"))


def test_service_does_not_show_even_for_the_owner(monkeypatch):
    """Право набрать команду и право показать ответ при всех — разные
    вещи. Ответ печатается в том же чате, где стоят читатели."""
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    assert not run_commands(Msg("/продажи", user_id=1))
    assert not run_commands(Msg("/срочно Текст", user_id=1))
    assert not run_commands(Msg("/digest chat -100123", user_id=1))


def test_the_owner_gets_the_chat_number_in_private(monkeypatch):
    """Чат ей нужен не для команды, а для номера: без него не подключить."""
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    message = Msg("/digest chat", user_id=1)
    run_commands(message)
    sent = message.bot.sent[0]
    assert sent["chat"] == 1, "номер ушёл не ей"
    assert "-100999" in sent["text"], "номера чата в подсказке нет"


def test_ordinary_talk_in_the_group_is_untouched(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    assert run_commands(Msg("просто сообщение"))


def test_private_commands_are_untouched(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    assert run_commands(Msg("/меню", chat_type="private"))


# --- правило не обойти по забывчивости --------------------------------
#
# Список разрешённых кнопок — договорённость: тот, кто завтра добавит в
# задачу дня строчку message.answer(...), напишет в канал, и список ему
# не помешает. Договорённость держится на памяти, а память и подвела.

def guarded_call(data="pz_7_2"):
    """Разрешённая кнопка — ровно в том виде, в каком её получит код"""
    call = Call(data)
    return call, public.narrowed(call)


@pytest.mark.parametrize("method", [
    "answer", "reply", "edit_text", "delete", "answer_photo",
    "forward", "copy_to", "pin",
])
def test_an_allowed_button_still_cannot_write_to_the_channel(method):
    """Не «не должен писать», а «не может написать». Разница видна ровно
    тогда, когда кто-то забудет правило — то есть однажды обязательно."""
    call, narrowed = guarded_call()
    with pytest.raises(public.PublicWrite):
        run(getattr(narrowed.message, method)("текст"))
    assert not call.message.said, "запрет сработал уже после записи"


def test_the_counter_on_the_button_keeps_working():
    """На ней держатся отклик под новостью и счётчик ответов — это
    часть самого поста, а не ответ в чужой чат."""
    call, narrowed = guarded_call()
    run(narrowed.message.edit_reply_markup(reply_markup=None))
    assert call.message.redrawn == 1


def test_the_popup_is_not_a_message_to_the_chat():
    """call.answer — окошко у того, кто нажал: его никто другой не
    видит, и закрывать его незачем."""
    call, narrowed = guarded_call()
    run(narrowed.answer("Верно!"))
    assert call.popups == ["Верно!"]


def test_the_handler_cannot_reach_the_channel_through_the_bot():
    """Обойти урезанный пост можно было бы через bot.send_message
    с номером канала."""
    _, narrowed = guarded_call()
    with pytest.raises(public.PublicWrite):
        run(narrowed.bot.send_message(-100123, "текст в канал"))


def test_writing_to_the_person_is_untouched():
    """Разбор задачи уходит в личку — ради этого всё и делается."""
    call, narrowed = guarded_call()
    run(narrowed.bot.send_message(777, "Разбор задачи"))
    assert call.bot.sent[0]["chat"] == 777


def test_an_attempt_to_write_does_not_break_the_channel():
    """Обработчик упал на запрете — читатель видит окошко, канал чист."""
    async def careless(event, data):
        await event.message.answer("Меню для всех")

    call = Call("pz_7_2")
    run(public.keep_private(careless, call, {}))
    assert not call.message.said, "в канал всё-таки написали"
    assert call.popups, "человек не понял, что произошло"


# --- граница включена --------------------------------------------------

def test_the_guard_is_actually_registered():
    """Модуль без регистрации в диспетчере — просто файл в папке."""
    source = open("main.py", encoding="utf-8").read()
    assert "public.keep_private" in source
    assert "public.commands_stay_private" in source


def test_the_guard_runs_before_the_gate():
    """Иначе обработчик успеет написать в канал до проверки."""
    source = open("main.py", encoding="utf-8").read()
    assert source.index("public.keep_private") < \
           source.index("growth.gate_middleware")
