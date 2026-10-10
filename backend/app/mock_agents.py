"""Deterministic stand-ins for the Lyzr agents.

Used when an agent ID is not configured, and as an automatic fallback if a live
Lyzr call fails, so a demo never dies on a network hiccup. Each function takes
the same JSON payload the real agent receives and returns the same JSON shape
(see app/agents/*.md for the contracts).
"""
import re
from collections import Counter
from datetime import timedelta

from .timeutil import day_bounds, humanize_due, now, parse_iso, resolve_due

HEALTH = re.compile(r"\b(diagnos\w*|medicine|medication|therapy|therapist|surgery|blood "
                    r"pressure|diabetes|depression|anxiety|hospital|prescription)\b", re.I)
FINANCE = re.compile(r"(?:₹|rs\.?|inr|\$)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|lakh|lakhs|crore))?"
                     r"|\b\d[\d,]*\s?(?:rupees|lakh|lakhs|crore)\b", re.I)
FINANCE_WORDS = re.compile(r"\b(loan|salary|debt|emi|bank balance|credit score)\b", re.I)
PERSONAL = re.compile(r"\b(mom|dad|wife|husband|girlfriend|boyfriend|family|feel|feeling|upset)\b",
                      re.I)

PROMISE = re.compile(
    r"\b(?:i'll|i will|i'm going to|i am going to|i promise to|i promise i'll|i can(?!'t| not)|"
    r"let me|i shall|i'll make sure to|i'll try to)\s+(?P<rest>[^.?!]+)", re.I)
DEADLINE_TAIL = re.compile(
    r"\s*,?\s*\b(?:by|before|on|for|until|first thing|latest by)?\s*(?:next\s+|this\s+)?"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|today|tonight|"
    r"eod|end of (?:the )?(?:day|week)|next week|day after tomorrow|in \w+ (?:hours?|days?))\b.*$",
    re.I)
CLOCK_TAIL = re.compile(r"\s*\b(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)\b.*$", re.I)
SOFT = re.compile(r"\b(try|maybe|probably|might)\b", re.I)


def _clean_text(text: str) -> str:
    return text.replace("’", "'").replace("‘", "'")


# --------------------------------------------------------------------------- privacy guard
def privacy_guard(payload: dict) -> dict:
    out = []
    for seg in payload.get("segments", []):
        text = seg["text"]
        sensitivity = "public"
        if PERSONAL.search(text):
            sensitivity = "personal"
        if HEALTH.search(text) or FINANCE_WORDS.search(text) or FINANCE.search(text):
            sensitivity = "sensitive"
        text = HEALTH.sub("[HEALTH]", text)
        text = FINANCE.sub("[FINANCE]", text)
        out.append({"idx": seg["idx"], "text": text, "sensitivity": sensitivity})
    return {"segments": out}


# --------------------------------------------------------------------------- extractor
def _other_party(segments: list[dict]) -> str | None:
    names = Counter(s.get("speaker") for s in segments if not s.get("is_user") and s.get("speaker"))
    return names.most_common(1)[0][0] if names else None


def extractor(payload: dict) -> dict:
    started = parse_iso(payload.get("conversation_started_at")) or now()
    segments = payload.get("segments", [])
    other = _other_party(segments)
    commitments = []
    for seg in segments:
        text = _clean_text(seg["text"])
        for m in PROMISE.finditer(text):
            rest = m.group("rest").strip()
            sentence = m.group(0)
            action = CLOCK_TAIL.sub("", DEADLINE_TAIL.sub("", rest)).strip(" ,")
            action = re.sub(r"^(?:try to|make sure to|definitely|also)\s+", "", action, flags=re.I)
            if len(action.split()) < 2:
                continue
            if seg.get("is_user"):
                owner, counterparty = "me", other
                if counterparty:
                    action = re.sub(r"\byour\b", f"{counterparty}'s", action, flags=re.I)
                    action = re.sub(r"\byou\b", counterparty, action, flags=re.I)
            else:
                owner, counterparty = "other", seg.get("speaker")
            due = resolve_due(sentence, started)
            confidence = 0.9 if due else 0.65
            if SOFT.search(sentence):
                confidence -= 0.2
            commitments.append({
                "owner": owner,
                "counterparty": counterparty,
                "action": action[0].upper() + action[1:],
                "due_at": due.isoformat() if due else None,
                "quote": sentence.strip(),
                "confidence": round(confidence, 2),
                "segment_idx": seg["idx"],
            })
    return {"commitments": commitments}


# --------------------------------------------------------------------------- curator
def curator(payload: dict) -> dict:
    decisions = []
    for item in payload.get("new", []):
        due = parse_iso(item.get("due_at"))
        cp = (item.get("counterparty") or "").lower()
        action, target, reason = "create", None, "New promise."
        for s in item.get("similar", []):
            same_person = (s.get("counterparty") or "").lower() == cp
            if not same_person or s.get("owner") != item.get("owner") or s.get("status") != "open":
                continue
            s_due = parse_iso(s.get("due_at"))
            if s.get("score", 0) >= 0.9 and s_due == due:
                action, target, reason = "skip", s["id"], "Already remembered."
                break
            if s.get("score", 0) >= 0.8:
                action, target, reason = "update", s["id"], "Same promise, new deadline."
                break

        conflict_with, conflict_reason = [], ""
        if item.get("owner") == "me" and due and action != "skip":
            mine = [d for d in item.get("same_day", [])
                    if d.get("owner") == "me" and d["id"] != target]
            clashes = [d for d in mine if (dd := parse_iso(d.get("due_at")))
                       and abs((dd - due).total_seconds()) <= 2 * 3600]
            if clashes:
                conflict_with = [d["id"] for d in clashes]
                c = clashes[0]
                conflict_reason = (f"Clashes with '{c['action']}' for {c.get('counterparty')} "
                                   f"around the same time.")
            elif len(mine) >= 2:
                conflict_with = [d["id"] for d in mine]
                conflict_reason = f"Overloaded: {len(mine) + 1} promises due the same day."
        decisions.append({
            "tmp_id": item["tmp_id"], "action": action, "target_id": target,
            "conflict": bool(conflict_with), "conflict_with": conflict_with,
            "reason": conflict_reason or reason,
        })
    return {"decisions": decisions}


# --------------------------------------------------------------------------- nudger
def _when(c: dict) -> str:
    """Payloads carry a pre-phrased `when` (see timeutil.add_when); fall back to due_at."""
    return c.get("when") or humanize_due(parse_iso(c.get("due_at")))


def _short(c: dict) -> str:
    who = c.get("counterparty") or "someone"
    when = _when(c)
    if c.get("owner") == "me":
        return f"{c['action']} ({who}, {when})"
    return f"{who} owes you: {c['action']} ({when})"


def nudger(payload: dict) -> dict:
    notes = []
    for ev in payload.get("events", []):
        kind = ev.get("type")
        if kind == "captured":
            items = ev.get("commitments", [])
            head = "; ".join(_short(c) for c in items[:2])
            more = f" +{len(items) - 2} more" if len(items) > 2 else ""
            notes.append({"message": f"🤝 Noted: {head}{more}", "priority": "low"})
        elif kind == "conflict":
            c, others = ev["commitment"], ev.get("with", [])
            other = others[0] if others else {}
            when = _when(c)
            if other:
                msg = (f"⚠️ {when}: '{c['action']}' clashes with '{other.get('action')}'. "
                       f"Give {c.get('counterparty') or 'them'} a heads-up or move one?")
            else:
                msg = f"⚠️ {ev.get('reason', 'Conflict detected')} Consider rescheduling."
            notes.append({"message": msg, "priority": "high"})
        elif kind == "reminder":
            c = ev["commitment"]
            notes.append({"message": f"⏰ Due {_when(c)}: "
                                     f"{c['action']} for {c.get('counterparty') or 'someone'}.",
                          "priority": "normal"})
        elif kind == "digest":
            due, overdue = ev.get("due_tomorrow", []), ev.get("overdue", [])
            parts = []
            if overdue:
                parts.append(f"{len(overdue)} overdue ({overdue[0]['action']})")
            if due:
                parts.append(f"{len(due)} due tomorrow ({due[0]['action']})")
            notes.append({"message": "🌙 " + ("; ".join(parts) or "All promises on track!"),
                          "priority": "normal"})
    return {"notifications": notes}


# --------------------------------------------------------------------------- router
def _time_range(text: str) -> tuple[str | None, str | None]:
    t, ref = text.lower(), now()
    if "today" in t or "tonight" in t:
        start, end = day_bounds(ref)
    elif "tomorrow" in t:
        start, end = day_bounds(ref + timedelta(days=1))
    elif "next week" in t:
        start = day_bounds(ref + timedelta(days=7 - ref.weekday()))[0]
        end = start + timedelta(days=7)
    elif "week" in t:  # "this week" = the next 7 days, which is what people mean when asking
        start = day_bounds(ref)[0]
        end = start + timedelta(days=8)
    else:
        return None, None
    return start.isoformat(), end.isoformat()


def router(payload: dict) -> dict:
    command = _clean_text(payload.get("command", "")).strip()
    lowered = command.lower()
    if re.search(r"\b(forget|delete|erase|remove)\b", lowered):
        intent = "forget"
    elif re.search(r"\b(done|finished|completed|did it|i sent|i've sent|i have sent|"
                   r"i submitted|i paid|i called|i reviewed)\b", lowered):
        intent = "mark_done"
    elif re.search(r"\b(remind me|i promised|note that|remember that|add)\b", lowered):
        intent = "add"
    elif lowered:
        intent = "recall"
    else:
        intent = "unknown"

    counterparty = next((p for p in payload.get("known_people", [])
                         if re.search(rf"\b{re.escape(p.lower())}\b", lowered)), None)
    if counterparty is None:
        m = re.search(r"\b(?:to|owe|from|with|for|about)\s+([A-Z][a-z]+)", command)
        counterparty = m.group(1) if m else None

    owner = None
    if re.search(r"\b(i owe|did i promise|i promised|my promises)\b", lowered):
        owner = "me"
    elif re.search(r"\b(owes? me|promised me|promise me)\b", lowered):
        owner = "other"

    query = re.sub(r"^(what|which|did|do|does|tell me|show me|remind me|forget|please)\b\s*", "",
                   lowered).strip(" ?.") or lowered
    time_from, time_to = _time_range(lowered)
    return {"intent": intent, "query": query, "counterparty": counterparty, "owner": owner,
            "time_from": time_from, "time_to": time_to}


# --------------------------------------------------------------------------- recall
def recall(payload: dict) -> dict:
    items = payload.get("commitments", [])
    if not items:
        convo = payload.get("conversations", [])
        if convo:
            return {"answer": f"I found a related conversation: \"{convo[0]['text'][:120]}\""}
        return {"answer": "I couldn't find any promise matching that."}
    items = sorted(items, key=lambda c: not c.get("overdue"))  # overdue first, else keep order
    parts = [_short(c) + (" (overdue!)" if c.get("overdue") else "") for c in items[:3]]
    extra = f" and {len(items) - 3} more" if len(items) > 3 else ""
    return {"answer": "You have: " + "; ".join(parts) + extra + "."}


MOCKS = {
    "privacy_guard": privacy_guard,
    "extractor": extractor,
    "curator": curator,
    "nudger": nudger,
    "router": router,
    "recall": recall,
}
