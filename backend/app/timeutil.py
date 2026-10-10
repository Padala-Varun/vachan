"""Time helpers: ISO parsing and resolving spoken deadlines ("by Thursday morning")."""
import re
from datetime import datetime, time, timedelta

from .config import settings

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DEFAULT_DUE_TIME = time(18, 0)
PARTS_OF_DAY = {"morning": time(10, 0), "noon": time(12, 0), "afternoon": time(15, 0),
                "evening": time(18, 0), "eod": time(18, 0), "tonight": time(21, 0),
                "night": time(21, 0)}


def now() -> datetime:
    return datetime.now(settings.tz)


def parse_iso(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=settings.tz)
    return dt


def to_local(dt: datetime) -> datetime:
    return dt.astimezone(settings.tz)


def day_bounds(dt: datetime) -> tuple[datetime, datetime]:
    local = to_local(dt)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _clock_time(text: str) -> time | None:
    m = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", text, re.I)
    if not m:
        return None
    hour, minute = int(m.group(1)) % 12, int(m.group(2) or 0)
    if m.group(3).lower().startswith("p"):
        hour += 12
    return time(hour, minute)


def resolve_due(text: str, reference: datetime) -> datetime | None:
    """Resolve the first deadline phrase in `text` relative to `reference`."""
    lowered = text.lower()
    ref = to_local(reference)
    day: datetime | None = None

    if re.search(r"\b(today|tonight|end of (the )?day|eod)\b", lowered):
        day = ref
    elif "day after tomorrow" in lowered:
        day = ref + timedelta(days=2)
    elif "tomorrow" in lowered:
        day = ref + timedelta(days=1)
    elif re.search(r"\b(end of (the )?week|this weekend)\b", lowered):
        day = ref + timedelta(days=(4 - ref.weekday()) % 7)
    elif "next week" in lowered:
        day = ref + timedelta(days=7 - ref.weekday())
    else:
        for i, name in enumerate(WEEKDAYS):
            m = re.search(rf"\b(next\s+)?{name}\b", lowered)
            if m:
                if m.group(1):  # "next Friday" = Friday of next calendar week
                    delta = 7 - ref.weekday() + i
                else:
                    delta = (i - ref.weekday()) % 7 or 7
                day = ref + timedelta(days=delta)
                break
        else:
            m = re.search(r"\bin\s+(\d+|a|an|two|three)\s+(hour|day)s?\b", lowered)
            if m:
                n = {"a": 1, "an": 1, "two": 2, "three": 3}.get(m.group(1)) or int(m.group(1))
                if m.group(2) == "hour":
                    return ref + timedelta(hours=n)
                day = ref + timedelta(days=n)

    clock = _clock_time(lowered)
    if day is None:
        if clock is None:
            return None
        day = ref if clock > ref.time() else ref + timedelta(days=1)

    if clock is None:
        clock = next((t for word, t in PARTS_OF_DAY.items() if re.search(rf"\b{word}\b", lowered)),
                     DEFAULT_DUE_TIME)
    return day.replace(hour=clock.hour, minute=clock.minute, second=0, microsecond=0)


def add_when(value):
    """Replace every `due_at` in a payload with a ready-to-read `when` + `overdue`.

    LLMs miscount weekdays from ISO dates ("Sat" for a Thursday), so agents
    that write for humans (Nudger, Recall) never see the raw date at all.
    """
    if isinstance(value, list):
        return [add_when(v) for v in value]
    if isinstance(value, dict):
        out = {k: add_when(v) for k, v in value.items() if k not in ("due_at", "due_ts")}
        if "due_at" in value:
            due = parse_iso(value.get("due_at"))
            out["when"] = humanize_due(due)
            out["overdue"] = bool(due and due < now() and value.get("status", "open") == "open")
        return out
    return value


def humanize_due(dt: datetime | None, reference: datetime | None = None) -> str:
    if dt is None:
        return "no deadline"
    ref = to_local(reference or now())
    local = to_local(dt)
    days = (local.date() - ref.date()).days
    clock = local.strftime("%I:%M %p").lstrip("0")
    if days == 0:
        return f"today {clock}"
    if days == 1:
        return f"tomorrow {clock}"
    if 1 < days < 7:
        return f"{local.strftime('%A')} {clock}"
    return local.strftime("%d %b %I:%M %p")
