# Розыгрыш: приём счёта. Сама игра живёт в браузере, на сервер приходит
# только число — и именно его мог бы прислать кто угодно, поэтому
# проверяем отказы, а не удачный путь.
import hashlib
import hmac
import json
import time
import urllib.parse

from conftest import run

import rally

TOKEN = "123456:TESTTOKEN"


def signed(user_id=777, name="Татьяна"):
    data = {"auth_date": str(int(time.time())),
            "user": json.dumps({"id": user_id, "first_name": name},
                               ensure_ascii=False)}
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(data)


def _saves(monkeypatch, box):
    import asyncio

    import database

    async def save(user_id, name, score):
        box.update(user_id=user_id, name=name, score=score)
        return 1, score

    monkeypatch.setattr(database, "save_rally_score", save)


def test_honest_score_is_accepted(monkeypatch):
    box = {}
    _saves(monkeypatch, box)
    body = json.dumps({"initData": signed(), "score": 14}).encode()
    code, result = run(rally.handle_score(body, TOKEN))
    assert code == 200 and result["status"] == "ok"
    assert box["score"] == 14 and box["user_id"] == 777


def test_forged_signature_is_refused():
    body = json.dumps({"initData": signed()[:-4] + "0000", "score": 999}).encode()
    code, _ = run(rally.handle_score(body, TOKEN))
    assert code == 403


def test_score_out_of_range_is_refused(monkeypatch):
    _saves(monkeypatch, {})
    body = json.dumps({"initData": signed(), "score": 10 ** 6}).encode()
    code, _ = run(rally.handle_score(body, TOKEN))
    assert code == 400


def test_broken_json_is_refused():
    code, _ = run(rally.handle_score(b"{not json", TOKEN))
    assert code == 400


def test_no_external_address_means_no_button(monkeypatch):
    """Telegram открывает мини-приложения только по https."""
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    assert rally.game_url() == ""
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://bot.onrender.com")
    assert rally.game_url() == "https://bot.onrender.com/rally"


def test_page_is_real_html():
    page = rally.page()
    assert b"<canvas" in page and b"rally/score" in page


# --- отправка в чужой чат ---------------------------------------------

def test_inline_offers_all_three(settings):
    """В чужой чат уходит поле крестиков и ссылки на остальные игры."""
    import xo
    settings["bot_username"] = "accent_hub_bot"

    got = {}

    class Query:
        async def answer(self, results=None, **kw):
            got["results"] = results

    run(xo.offer_games(Query()))
    titles = [r.title for r in got["results"]]
    assert len(titles) == 3
    assert any("Розыгрыш" in t for t in titles)
    assert any("Все игры" in t for t in titles)


def test_inline_without_bot_name_keeps_only_the_board(settings):
    """Ссылка в никуда хуже отсутствующей карточки."""
    import xo

    got = {}

    class Query:
        async def answer(self, results=None, **kw):
            got["results"] = results

    run(xo.offer_games(Query()))
    assert len(got["results"]) == 1


def test_rally_payload_opens_the_game():
    import common
    assert common.DEEP_LINKS.get("rally") == "rally_open"
