# freshness.py — когда цифры проверяли в последний раз.
#
# Справочник цен и условий устаревает молча. Сервис меняет тариф, вводит
# комиссию, перестаёт работать в стране — а у нас на экране по-прежнему
# старое число, и человек принимает по нему решение. Ошибается он, а
# отвечает за это тот, кто показал.
#
# Отсюда правило: у каждой записи есть дата проверки, и она видна
# читателю. Не «мы стараемся поддерживать актуальность», а «проверено 12
# сентября» — чтобы человек сам решил, верить ли цифре трёхмесячной
# давности.
#
# Устаревшее не прячем. Пустой экран не честнее старой цены: он просто
# не даёт ничего. Помечаем — и зовём владелицу перепроверить.
from datetime import date, datetime

FRESH_DAYS = 30                  # свежее этого — без оговорок
STALE_DAYS = 90                  # старше — предупреждаем прямо

MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def today() -> str:
    return date.today().isoformat()


def stamp(item: dict) -> dict:
    """Пометить запись сегодняшним днём. Возвращает её же."""
    item["checked"] = today()
    return item


def _parsed(item: dict):
    raw = (item or {}).get("checked") or ""
    try:
        return date.fromisoformat(raw[:10])
    except (ValueError, TypeError):
        return None


def age(item: dict):
    """Сколько дней записи. None — если дата не проставлена."""
    when = _parsed(item)
    return (date.today() - when).days if when else None


def is_stale(item: dict) -> bool:
    """Запись без даты считается устаревшей: неизвестно — значит давно."""
    days = age(item)
    return days is None or days >= STALE_DAYS


def label(item: dict) -> str:
    """Короткая подпись для читателя"""
    days = age(item)
    if days is None:
        return "⚠️ дата проверки неизвестна"
    when = _parsed(item)
    said = f"{when.day} {MONTHS[when.month]}"
    if days >= STALE_DAYS:
        return f"⚠️ не проверялось с {said}"
    if days >= FRESH_DAYS:
        return f"проверено {said}"
    return f"✓ проверено {said}"


def warning(items: list) -> str:
    """Общая оговорка под списком — если есть чему устареть"""
    old = [item for item in items if is_stale(item)]
    if not old:
        return ""
    return ("\n<i>⚠️ Часть условий не проверялась больше трёх месяцев — "
            "сверьтесь на сайте перед оплатой. Тарифы меняются без "
            "предупреждения.</i>")


def stale_report(groups: dict) -> str:
    """Что пора перепроверить — для владелицы.

    Принимает {«название раздела»: [записи]}. Показывает только то, где
    есть просроченное: напоминание обо всём сразу не читается.
    """
    lines = []
    for title, items in groups.items():
        old = [item for item in items if is_stale(item)]
        if not old:
            continue
        names = ", ".join((item.get("name") or "—")[:24] for item in old[:5])
        more = f" и ещё {len(old) - 5}" if len(old) > 5 else ""
        lines.append(f"• <b>{title}</b>: {len(old)} — {names}{more}")
    if not lines:
        return ""
    return ("🕰 <b>Пора перепроверить</b>\n\n" + "\n".join(lines) +
            "\n\n<i>Цена и правила меняются молча. Пока цифра на экране "
            "старая, ошибается читатель, а отвечаете вы.</i>")
