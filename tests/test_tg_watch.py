# Слежение за чужим публичным каналом. Ботом вступить в чужой канал
# нельзя — читаем веб-превью t.me/s/<имя>, которое сервер отдаёт кому
# угодно.
import tg_watch as w


PAGE = '''
<div class="tgme_widget_message_wrap">
 <div class="tgme_widget_message " data-post="formulatx/942">
  <div class="tgme_widget_message_text js-message_text" dir="auto">
   &#9200;Рады сообщить, что до турнира остался месяц!<br/><br/>Списки
   игроков готовы, расписание составлено.
  </div>
 </div>
</div>
<div class="tgme_widget_message_wrap">
 <div class="tgme_widget_message " data-post="formulatx/950">
  <div class="tgme_widget_message_text js-message_text" dir="auto">
   Диана - Чемпионка Токио! Поздравляем!
  </div>
 </div>
</div>
<div class="tgme_widget_message_wrap">
 <div class="tgme_widget_message " data-post="someoneelse/1">
  <div class="tgme_widget_message_text js-message_text" dir="auto">Чужое</div>
 </div>
</div>
'''


def test_posts_are_read_from_the_preview():
    got = w.parse(PAGE, "formulatx")
    assert [n for n, _ in got] == [942, 950], "номера постов не те"
    assert "Списки" in got[0][1]
    assert "<br" not in got[0][1], "разметка осталась в тексте"
    assert "&#9200;" not in got[0][1], "html-мнемоники не раскрыты"


def test_a_neighbour_channel_does_not_leak_in():
    """На странице канала попадаются пересланные и чужие блоки. Берём
    только то, что подписано нашим именем."""
    assert all("Чужое" not in text for _, text in w.parse(PAGE, "formulatx"))


def test_the_rosters_post_is_marked():
    """Ради этого всё и затевалось: пост про составы не должен
    потеряться среди расписаний и опросов."""
    assert w.is_important("Списки игроков готовы, расписание составлено")
    assert w.is_important("САША БУБЛИК И КАРЕН ХАЧАНОВ ПРИМУТ УЧАСТИЕ")
    assert w.is_important("Объявляем состав команды «Львы»")
    assert not w.is_important("Совсем скоро")
    assert not w.is_important("Сегодня поздравляем с Днём рождения")


def test_the_card_carries_a_link_to_the_post():
    said = w.card("formulatx", 942, "Списки игроков готовы")
    assert "https://t.me/formulatx/942" in said
    assert "Похоже на состав" in said, "важный пост не помечен"

    plain = w.card("formulatx", 949, "Совсем скоро")
    assert "Новое у" in plain
