# tools/nikud.py — огласовки для иврита, чтобы синтезатор не гадал.
#
# Иврит пишут без огласовок, и одно написание читается по-разному: מרפאה
# — это и «поликлиника», и «она лечит». Человек различает их по смыслу,
# синтезатор — угадывает, и на слух это слышно сразу. Проблема общая для
# всех движков, дорогих и дешёвых: она не в голосе, а в написании.
#
# Значит, лечить надо до озвучки. Здесь фразы уходят в «Накдан» — это
# израильский бесплатный огласовщик от Dicta (Бар-Илан), тот самый, что
# стоит на nakdanpro.dicta.org.il, — и возвращаются с огласовками.
# Результат ложится в data/lang.json, в раздел "voice": на экране фраза
# остаётся как была, меняется только чтение.
#
# Автоматика ошибается на пару слов из десятка, поэтому перед записью всё
# показывается списком, а спорные места (где Накдан сам не уверен или
# предлагает много вариантов) помечены «?». Их стоит показать тому, кто
# говорит на иврите: одна неверная огласовка — и в уроке звучит другое
# слово, а человек учит его как правильное.
#
#   python3 tools/nikud.py            — показать, ничего не меняя
#   python3 tools/nikud.py --write    — записать в lang.json
import argparse
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lang                                            # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data", "lang.json")

API = "https://nakdan-5-3.loadbalancer.dicta.org.il/api"
MARKS = re.compile(r"[֑-ֽֿ-ׇ]")     # огласовки и ударения


def bare(text: str) -> str:
    """Текст без огласовок — то, что видно на экране"""
    return MARKS.sub("", text).replace("|", "")


def nakdan(text: str):
    """(огласованная фраза, сколько слов под вопросом). Слова — по одному."""
    body = json.dumps({"task": "nakdan", "data": text, "genre": "modern",
                       "addmorph": False, "keepqq": False,
                       "nodageshdefmem": False, "patachma": False,
                       "keepmetagim": True}).encode("utf-8")
    req = urllib.request.Request(API, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        words = json.loads(resp.read().decode("utf-8"))

    out, doubt = [], 0
    for word in words:
        if word.get("sep"):
            out.append(word["word"])
            continue
        options = word.get("options") or []
        if not options:
            out.append(word["word"])
            continue
        out.append(options[0].replace("|", ""))
        # Накдан честно говорит, когда не уверен. Одной неуверенности мало:
        # он не уверен в двух словах из трёх, и метка «проверить всё» не
        # значит ничего. Считаем спорным слово, где он и не уверен, и
        # вариантов у него больше пяти.
        if not word.get("fconfident") and len(options) > 5:
            doubt += 1
    return "".join(out), doubt


def main() -> int:
    parser = argparse.ArgumentParser(description="Огласовки для ивритских фраз")
    parser.add_argument("--write", action="store_true",
                        help="записать в lang.json (иначе только показать)")
    args = parser.parse_args()

    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)

    sys.path.insert(0, os.path.join(HERE, "tools"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "make_audio", os.path.join(HERE, "tools", "make_audio.py"))
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)

    voice, doubtful = {}, []
    for code, text in tool.phrases(data):
        if code != "he":
            continue
        try:
            marked, doubt = nakdan(text)
        except Exception as e:
            print(f"  {text} — не вышло: {str(e)[:80]}")
            continue

        # Огласовки добавляют знаки, но не меняют букв. Если изменились —
        # Накдан вернул другое слово, и записывать это нельзя.
        if bare(marked) != text:
            print(f"  ! {text} → {marked} — текст изменился, пропускаю")
            continue

        if marked != text:
            voice[text] = marked
        if doubt:
            doubtful.append((doubt, text, marked))
        print(f"  {'?' if doubt else ' '} {text:28} → {marked}")

    if doubtful:
        print("\nПоказать знающему иврит — здесь Накдан выбирал наугад:")
        for _, text, marked in sorted(doubtful, reverse=True):
            print(f"  {text:28} → {marked}")
    print(f"\nогласовано: {len(voice)}, под вопросом: {len(doubtful)}")
    if not args.write:
        print("Записать: python3 tools/nikud.py --write")
        return 0

    data["languages"]["he"]["voice"] = voice
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("Записано. Переозвучить: python3 tools/make_audio.py --only he --force")
    return 0


if __name__ == "__main__":
    sys.exit(main())
