from __future__ import annotations

import re
from datetime import datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

from bot import texts
from bot.config import DEFAULT_REMIND_BEFORE, MAX_REMINDER_OFFSETS

_CUSTOM_OFFSET_RE = re.compile(
    r"(?i)^\s*(?:за\s+)?(\d+)\s*"
    r"(хв|хвилин[аиу]?|мин|минут[аы]?|год|годин[аиу]?|час[аиу]?|д(?:ень|ні|нів)?|дн|тиж(?:день|ні)?|недел[юяи]?)\s*$"
)


def is_url(value: str) -> bool:
    value = value.strip()
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def parse_time_hhmm(value: str) -> str | None:
    value = value.strip().lower().replace(".", ":")
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", value)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}"


def parse_digest_time(value: str) -> str | None:
    return parse_time_hhmm(value)


def parse_due(value: str, tz: ZoneInfo, now: datetime | None = None) -> datetime | None:
    text = value.strip().lower()
    if not text:
        return None
    now = now or datetime.now(tz)

    if text.startswith("завтра"):
        rest = text[len("завтра") :].strip()
        base = now + timedelta(days=1)
        if not rest:
            return base.replace(hour=9, minute=0, second=0, microsecond=0)
        t = parse_time_hhmm(rest)
        if t:
            h, m = map(int, t.split(":"))
            return base.replace(hour=h, minute=m, second=0, microsecond=0)
        return None

    if text.startswith("сьогодні") or text.startswith("сегодня"):
        rest = text.split(maxsplit=1)[1] if " " in text else ""
        t = parse_time_hhmm(rest) if rest else None
        if t:
            h, m = map(int, t.split(":"))
            return now.replace(hour=h, minute=m, second=0, microsecond=0)
        return None

    # dd.mm[.[yyyy]] [HH:MM]
    m = re.fullmatch(
        r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?:\s+(\d{1,2})[:.](\d{2}))?",
        text,
    )
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        if year < 100:
            year += 2000
        hour = int(m.group(4)) if m.group(4) else 9
        minute = int(m.group(5)) if m.group(5) else 0
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=tz)
        except ValueError:
            return None
        if not m.group(3) and dt < now - timedelta(days=1):
            try:
                dt = dt.replace(year=year + 1)
            except ValueError:
                pass
        return dt

    try:
        dt = date_parser.parse(text, dayfirst=True, fuzzy=True)
    except (ValueError, OverflowError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    else:
        dt = dt.astimezone(tz)
    return dt


def parse_offset_text(value: str) -> int | None:
    value = value.strip().lower()
    if value in {"у строк", "в срок", "0"}:
        return 0
    m = _CUSTOM_OFFSET_RE.match(value)
    if not m:
        return None
    amount = int(m.group(1))
    unit = m.group(2)
    if unit.startswith(("хв", "мин")):
        return amount
    if unit.startswith(("год", "час")):
        return amount * 60
    if unit.startswith(("д", "дн")):
        return amount * 1440
    if unit.startswith(("тиж", "недел")):
        return amount * 10080
    return None


def normalize_offsets(offsets: list[int] | None, *, has_due: bool) -> list[int]:
    if not has_due:
        return []
    if not offsets:
        return [DEFAULT_REMIND_BEFORE]
    uniq = sorted({max(0, int(x)) for x in offsets})
    return uniq[:MAX_REMINDER_OFFSETS]


def to_iso(dt: datetime) -> str:
    return dt.astimezone(ZoneInfo("UTC")).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def from_iso(value: str, tz: ZoneInfo) -> datetime:
    raw = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(tz)


def format_dt(dt: datetime | None, tz: ZoneInfo) -> str:
    if dt is None:
        return "—"
    local = dt.astimezone(tz)
    return local.strftime("%d.%m.%Y %H:%M")


def format_dt_iso(value: str | None, tz: ZoneInfo) -> str:
    if not value:
        return "—"
    return format_dt(from_iso(value, tz), tz)


def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def task_card_html(task, offsets: list[int], tz: ZoneInfo, author: str | None = None) -> str:
    status = "✔ зроблено" if task.status == "done" else "⏳ відкрито"
    lines = [
        f"<b>{escape_html(task.title)}</b>",
        f"Статус: {status}",
    ]
    if task.description:
        lines.append(escape_html(task.description))
    if task.link:
        lines.append(f'<a href="{escape_html(task.link)}">посилання</a>')
    if task.due_at:
        lines.append(f"Строк: {format_dt_iso(task.due_at, tz)}")
        lines.append(f"Нагадати: {texts.format_offsets(offsets)}")
    if author:
        lines.append(f"Автор: {escape_html(author)}")
    lines.append(f"#{task.id}")
    return "\n".join(lines)


def schedule_card_html(item, offsets: list[int], tz: ZoneInfo) -> str:
    lines = [f"<b>{escape_html(item.title)}</b>"]
    if item.kind == "weekly":
        day = texts.WEEKDAYS_FULL[item.weekday or 0]
        time_part = item.start_time or "??:??"
        if item.end_time:
            time_part = f"{time_part}–{item.end_time}"
        lines.append(f"Щотижня: {day}, {time_part}")
    else:
        lines.append(f"Подія: {format_dt_iso(item.starts_at, tz)}")
        if item.ends_at:
            lines.append(f"До: {format_dt_iso(item.ends_at, tz)}")
    if item.description:
        lines.append(escape_html(item.description))
    if item.link:
        lines.append(f'<a href="{escape_html(item.link)}">посилання</a>')
    lines.append(f"Нагадати: {texts.format_offsets(offsets)}")
    lines.append(f"#{item.id}")
    return "\n".join(lines)


def next_weekly_occurrence(
    weekday: int,
    start_time: str,
    tz: ZoneInfo,
    now: datetime | None = None,
) -> datetime:
    """weekday: 0=Mon .. 6=Sun; start_time HH:MM."""
    now = now or datetime.now(tz)
    h, m = map(int, start_time.split(":"))
    # Python weekday: Mon=0
    days_ahead = (weekday - now.weekday()) % 7
    candidate = now.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(
        days=days_ahead
    )
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def occurrence_for_schedule(item, tz: ZoneInfo, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now(tz)
    if item.kind == "once":
        if not item.starts_at:
            return None
        return from_iso(item.starts_at, tz)
    if item.weekday is None or not item.start_time:
        return None
    # For reminder checks we need the occurrence that is currently relevant:
    # today's if not yet passed relative to remind window, else next week.
    h, m = map(int, item.start_time.split(":"))
    today = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if now.weekday() == item.weekday:
        return today
    return next_weekly_occurrence(item.weekday, item.start_time, tz, now)
