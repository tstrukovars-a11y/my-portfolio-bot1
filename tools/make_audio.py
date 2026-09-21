# tools/make_audio.py — озвучка уроков, один раз на моей машине.
#
# Слушать важнее, чем читать: в кафе и по телефону текста нет, а
# автоответчик не ждёт. Значит, у каждой фразы должен быть звук.
#
# Синтез делается здесь, а не в боте: на сервере нет ни голосов, ни права
# ходить в чужой сервис на каждое задание. Готовые файлы лежат в
# репозитории и уезжают вместе с деплоем — бот их только отправляет.
#
# Имя файла — отпечаток текста, а не сам текст: в проигрывателе Telegram
# видно имя файла, и фраза, которую нужно узнать на слух, была бы видна
# глазами.
#
# Запуск:  python3 tools/make_audio.py
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data", "lang.json")
OUT = os.path.join(HERE, "data", "audio")

# Голоса macOS. Иврит — Carmit, и это главный: ради него всё и затевалось.
VOICES = {"he": "Carmit", "fr": "Thomas", "en": "Daniel"}

# Медленнее обычного: задача — расслышать, а не угнаться. Живую скорость
# добавим отдельным файлом, когда дойдут руки.
RATE = {"he": 150, "fr": 165, "en": 165}


def digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def phrases(data: dict):
    """Всё, что должно звучать: слова, реплики и диалоги"""
    for code, lang in data.get("languages", {}).items():
        said = set()
        for topic in lang.get("topics", {}).values():
            for card in topic.get("cards", []):
                for text in [card["word"]] + [l["q"] for l in card["lines"]] \
                        + [l["a"] for l in card["lines"]]:
                    if text not in said:
                        said.add(text)
                        yield code, text
            for turn in topic.get("dialog", {}).get("turns", []):
                if turn["text"] not in said:
                    said.add(turn["text"])
                    yield code, turn["text"]


def make(code: str, text: str) -> str:
    folder = os.path.join(OUT, code)
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, digest(text) + ".m4a")
    if os.path.exists(target):
        return "уже есть"

    raw = target + ".aiff"
    try:
        subprocess.run(["say", "-v", VOICES[code], "-r", str(RATE[code]),
                        "-o", raw, text], check=True, capture_output=True)
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", raw, target],
                       check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        return f"ошибка: {e.stderr.decode('utf-8', 'ignore')[:60]}"
    finally:
        if os.path.exists(raw):
            os.remove(raw)
    return "готово"


def main():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)

    made = skipped = failed = 0
    for code, text in phrases(data):
        result = make(code, text)
        if result == "готово":
            made += 1
        elif result == "уже есть":
            skipped += 1
        else:
            failed += 1
            print(f"  {code}: {text[:30]} — {result}")
    print(f"озвучено: {made}, уже было: {skipped}, не вышло: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
