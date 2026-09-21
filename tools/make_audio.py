# tools/make_audio.py — озвучка уроков, один раз на моей машине.
#
# Слушать важнее, чем читать: в кафе и по телефону текста нет, а
# автоответчик не ждёт. Значит, у каждой фразы должен быть звук — и звук
# должен быть похож на человека, иначе тренируется слух не к речи, а к
# роботу, которого в жизни не встретишь.
#
# Отсюда несколько движков на выбор. Системный голос macOS («say») ничего
# не стоит и не требует ключа, но читает механически — им хорошо проверять
# содержание, а не учиться. Нейросетевые (ElevenLabs, Azure, Google) звучат
# живо, стоят копейки на нашем объёме (около 2700 знаков на все три языка)
# и требуют ключа. Какой лучше звучит на иврите — решает ухо, а не
# документация: для этого есть режим --sample.
#
# Синтез делается здесь, а не в боте: на сервере нет ни голосов, ни права
# ходить в чужой сервис на каждое задание. Готовые файлы лежат в
# репозитории и уезжают вместе с деплоем — бот их только отправляет.
#
# Имя файла — отпечаток текста, а не сам текст: в проигрывателе Telegram
# видно имя файла, и фраза, которую нужно узнать на слух, была бы видна
# глазами. Отпечаток общий с lang.py, чтобы бот и генератор не разошлись.
#
# Ключи берутся из окружения или из .env — и туда же их и надо класть,
# в переписку и в репозиторий они не попадают (.env в .gitignore).
#
#   python3 tools/make_audio.py                      — системный голос
#   python3 tools/make_audio.py --sample             — сравнить движки
#   python3 tools/make_audio.py --engine eleven      — переозвучить всё
#   python3 tools/make_audio.py --engine azure --only he --force
#   python3 tools/make_audio.py --voices eleven      — голоса в аккаунте
import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lang                                            # noqa: E402  (после sys.path)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data", "lang.json")
OUT = os.path.join(HERE, "data", "audio")
SAMPLE = os.path.join(OUT, "_sample")

digest = lang.digest          # один отпечаток на бота и на генератор


# ---------------------------------------------------------------------
# ЧТО ОЗВУЧИВАТЬ
# ---------------------------------------------------------------------

def phrases(data: dict):
    """Всё, что должно звучать. Перечень общий с ботом — см. lang.phrases."""
    for code in data.get("languages", {}):
        for text in lang.phrases(code):
            yield code, text


# ---------------------------------------------------------------------
# ДВИЖКИ
# ---------------------------------------------------------------------
#
# Каждый возвращает байты звука и своё расширение. Медленнее обычного
# везде: задача — расслышать, а не угнаться. Живую скорость добавим
# отдельным файлом, когда медленная перестанет быть трудной.

SLOW = 0.9


def _post(url: str, data: bytes, headers: dict) -> bytes:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --- macOS ------------------------------------------------------------
# Бесплатно и без ключа, но голос механический. Иврит — Carmit.

MAC_VOICES = {"he": "Carmit", "fr": "Thomas", "en": "Daniel"}
MAC_RATE = {"he": 150, "fr": 165, "en": 165}


def say_engine(code: str, text: str):
    raw = os.path.join(SAMPLE, f"_say_{digest(text)}.aiff")
    os.makedirs(os.path.dirname(raw), exist_ok=True)
    try:
        subprocess.run(["say", "-v", MAC_VOICES[code], "-r", str(MAC_RATE[code]),
                        "-o", raw, text], check=True, capture_output=True)
        with open(raw, "rb") as f:
            return f.read(), "aiff"
    finally:
        if os.path.exists(raw):
            os.remove(raw)


# --- ElevenLabs -------------------------------------------------------
# Самый простой в заведении: почта, ключ в профиле, бесплатных знаков в
# месяц хватает на несколько полных переозвучек. Голоса не привязаны к
# языку — один и тот же голос говорит на всех, поэтому имя голоса задаётся
# на язык отдельно: израильский голос на иврите звучит роднее.

ELEVEN_URL = "https://api.elevenlabs.io/v1"
ELEVEN_MODEL = os.environ.get("ELEVEN_MODEL", "eleven_multilingual_v2")
_eleven_voices = None


def _eleven_key() -> str:
    key = (os.environ.get("ELEVEN_KEY") or os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("нет ключа: положите ELEVEN_KEY в .env")
    return key


def eleven_voices() -> list:
    """Голоса аккаунта: (имя, id). Список свой у каждого — не зашиваем."""
    global _eleven_voices
    if _eleven_voices is None:
        data = _get(f"{ELEVEN_URL}/voices", {"xi-api-key": _eleven_key()})
        _eleven_voices = [(v.get("name", "?"), v.get("voice_id", "")) for v in data.get("voices", [])]
    return _eleven_voices


def _eleven_voice(code: str) -> str:
    """Голос для языка: id или имя из ELEVEN_VOICE_HE / _FR / _EN."""
    want = (os.environ.get(f"ELEVEN_VOICE_{code.upper()}") or "").strip()
    voices = eleven_voices()
    if not voices:
        raise RuntimeError("в аккаунте нет ни одного голоса")
    if want:
        for name, vid in voices:
            if want in (vid, name) or want.lower() == name.lower():
                return vid
        raise RuntimeError(f"голос {want!r} не найден: есть "
                           + ", ".join(n for n, _ in voices))
    return voices[0][1]


def eleven_engine(code: str, text: str):
    body = json.dumps({
        "text": text,
        "model_id": ELEVEN_MODEL,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": SLOW},
    }).encode("utf-8")
    audio = _post(f"{ELEVEN_URL}/text-to-speech/{_eleven_voice(code)}?output_format=mp3_44100_128",
                  body, {"xi-api-key": _eleven_key(), "Content-Type": "application/json"})
    return audio, "mp3"


# --- Azure ------------------------------------------------------------
# У Microsoft иврит живёт давно и читается уверенно — на слух это слышно
# на словах без огласовок, где остальные гадают.

AZURE_VOICES = {"he": "he-IL-HilaNeural", "fr": "fr-FR-DeniseNeural",
                "en": "en-GB-SoniaNeural"}


def azure_engine(code: str, text: str):
    key = (os.environ.get("AZURE_SPEECH_KEY") or "").strip()
    region = (os.environ.get("AZURE_SPEECH_REGION") or "westeurope").strip()
    if not key:
        raise RuntimeError("нет ключа: положите AZURE_SPEECH_KEY в .env")

    voice = os.environ.get(f"AZURE_VOICE_{code.upper()}") or AZURE_VOICES[code]
    percent = int(round((SLOW - 1) * 100))
    ssml = (f"<speak version='1.0' xml:lang='{voice[:5]}'>"
            f"<voice name='{voice}'><prosody rate='{percent:+d}%'>"
            f"{_xml(text)}</prosody></voice></speak>").encode("utf-8")

    audio = _post(f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
                  ssml, {"Ocp-Apim-Subscription-Key": key,
                         "Content-Type": "application/ssml+xml",
                         "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
                         "User-Agent": "accent-bot"})
    return audio, "mp3"


def _xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --- Google -----------------------------------------------------------

GOOGLE_VOICES = {"he": "he-IL-Wavenet-A", "fr": "fr-FR-Neural2-A",
                 "en": "en-GB-Neural2-A"}


def google_engine(code: str, text: str):
    key = (os.environ.get("GOOGLE_TTS_KEY") or "").strip()
    if not key:
        raise RuntimeError("нет ключа: положите GOOGLE_TTS_KEY в .env")

    voice = os.environ.get(f"GOOGLE_VOICE_{code.upper()}") or GOOGLE_VOICES[code]
    body = json.dumps({
        "input": {"text": text},
        "voice": {"languageCode": voice[:5], "name": voice},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": SLOW},
    }).encode("utf-8")
    answer = _post(f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}",
                   body, {"Content-Type": "application/json"})
    return base64.b64decode(json.loads(answer)["audioContent"]), "mp3"


ENGINES = {"say": say_engine, "eleven": eleven_engine,
           "azure": azure_engine, "google": google_engine}


# ---------------------------------------------------------------------
# ФАЙЛЫ
# ---------------------------------------------------------------------

def to_m4a(data: bytes, kind: str, target: str):
    """Всё сводим к одному формату: бот ищет .m4a и ничего не угадывает."""
    raw = target + "." + kind
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(raw, "wb") as f:
        f.write(data)
    try:
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", raw, target],
                       check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        subprocess.run(["ffmpeg", "-y", "-i", raw, "-c:a", "aac", target],
                       check=True, capture_output=True)
    finally:
        if os.path.exists(raw):
            os.remove(raw)


def make(engine: str, code: str, text: str, force: bool) -> str:
    target = os.path.join(OUT, code, digest(text) + ".m4a")
    if os.path.exists(target) and not force:
        return "уже есть"
    try:
        data, kind = ENGINES[engine](code, lang.spoken(code, text))
        to_m4a(data, kind, target)
    except urllib.error.HTTPError as e:
        return f"ошибка {e.code}: {e.read().decode('utf-8', 'ignore')[:120]}"
    except Exception as e:
        return f"ошибка: {str(e)[:120]}"
    return "готово"


# ---------------------------------------------------------------------
# СРАВНЕНИЕ ДВИЖКОВ
# ---------------------------------------------------------------------
#
# Какой голос лучше — вопрос к уху, а не к документации. Здесь одни и те же
# фразы читаются всеми доступными движками и складываются рядом, с
# читаемыми именами: сравнивать на слух надо, зная, что сравниваешь.

TRY = {
    "he": ["מרפאה", "סליחה?", "אני לא מבין", "עוד פעם בבקשה", "מתי אתם פתוחים?"],
    "fr": ["Je n'ai pas compris", "Vous pouvez répéter ?"],
    "en": ["I didn't catch that", "Could you say that again?"],
}


def sample(engines: list, only: str) -> int:
    codes = [only] if only else list(TRY)
    failed = 0
    for engine in engines:
        for code in codes:
            for i, text in enumerate(TRY.get(code, []), 1):
                target = os.path.join(SAMPLE, code, f"{i}-{engine}.m4a")
                try:
                    data, kind = ENGINES[engine](code, lang.spoken(code, text))
                    to_m4a(data, kind, target)
                    print(f"  {code} {i}. {engine:7} — {text}")
                except urllib.error.HTTPError as e:
                    failed += 1
                    print(f"  {code} {i}. {engine:7} — ошибка {e.code}: "
                          f"{e.read().decode('utf-8', 'ignore')[:120]}")
                except Exception as e:
                    failed += 1
                    print(f"  {code} {i}. {engine:7} — {str(e)[:120]}")
    print(f"\nПослушать: open {SAMPLE}")
    print("Один номер — одна фраза разными движками. Выбранный ставится "
          "в --engine и озвучивает всё.")
    return 1 if failed else 0


# ---------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Озвучка уроков языка")
    parser.add_argument("--engine", default=os.environ.get("AUDIO_ENGINE", "say"),
                        choices=list(ENGINES))
    parser.add_argument("--only", default="", help="только один язык: he, fr, en")
    parser.add_argument("--force", action="store_true",
                        help="переозвучить то, что уже есть")
    parser.add_argument("--sample", action="store_true",
                        help="сравнить движки на одних и тех же фразах")
    parser.add_argument("--voices", default="", choices=["", "eleven"],
                        help="показать голоса аккаунта")
    args = parser.parse_args()

    if args.voices == "eleven":
        try:
            for name, vid in eleven_voices():
                print(f"  {name:24} {vid}")
        except Exception as e:
            print(f"не вышло: {str(e)[:200]}")
            return 1
        print("\nИмя или id кладётся в ELEVEN_VOICE_HE (или _FR, _EN) в .env")
        return 0

    if args.sample:
        ready = [e for e in ENGINES if e == "say" or _has_key(e)]
        print(f"Движки с ключами: {', '.join(ready)}\n")
        return sample(ready, args.only)

    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)

    made = skipped = failed = 0
    for code, text in phrases(data):
        if args.only and code != args.only:
            continue
        result = make(args.engine, code, text, args.force)
        if result == "готово":
            made += 1
        elif result == "уже есть":
            skipped += 1
        else:
            failed += 1
            print(f"  {code}: {text[:30]} — {result}")
    print(f"движок: {args.engine}; озвучено: {made}, уже было: {skipped}, "
          f"не вышло: {failed}")
    return 1 if failed else 0


def _has_key(engine: str) -> bool:
    return bool({"eleven": os.environ.get("ELEVEN_KEY") or os.environ.get("ELEVENLABS_API_KEY"),
                 "azure": os.environ.get("AZURE_SPEECH_KEY"),
                 "google": os.environ.get("GOOGLE_TTS_KEY")}.get(engine, ""))


if __name__ == "__main__":
    sys.exit(main())
