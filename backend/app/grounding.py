"""Deterministic checks on the Extractor's output.

LLMs are unreliable at weekday arithmetic ("Thursday evening" said on a
Monday) and sometimes return "you" as the other person. Both facts are
recoverable from the transcript itself, so we verify them in code:

- the deadline is re-resolved from the exact words the agent quoted;
  the agent's own date is kept only when the quote has no deadline phrase
- a pronoun counterparty is replaced with the real speaker's name
"""
import re
from collections import Counter
from datetime import datetime, timedelta

from .timeutil import parse_iso, resolve_due, to_local

PRONOUNS = {"", "you", "me", "i", "myself", "yourself", "user", "the user", "someone", "them"}


def calendar(reference: datetime) -> dict:
    """Date hints sent to the Extractor so it never has to count weekdays."""
    local = to_local(reference)
    days = {(local + timedelta(days=d)).strftime("%A"): (local + timedelta(days=d)).date().isoformat()
            for d in range(1, 8)}
    return {"today": local.strftime("%A %d %B %Y"), "next_7_days": days}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def due_from_quote(quote: str, action: str, reference: datetime) -> datetime | None:
    """Resolve the deadline in `quote`; with several, pick the sentence closest to `action`."""
    sentences = [s for s in re.split(r"(?<=[.!?;])\s+", quote or "") if s.strip()]
    dated = [(s, d) for s in sentences if (d := resolve_due(s, reference))]
    if not dated:
        return None
    action_words = _words(action)
    return max(dated, key=lambda sd: len(_words(sd[0]) & action_words))[1]


DUPLICATE_MIN_SCORE = 0.85   # bge-small: unrelated promises score 0.5-0.65, restatements 0.85+
CLASH_WINDOW_HOURS = 2


def check_decisions(new_items: list[dict], decisions: dict[str, dict]) -> tuple[dict[str, dict], list[dict]]:
    """Guardrails on the Curator's decisions, checked against what Qdrant actually returned.

    - "skip"/"update" must point at a genuinely similar promise to the same person;
      otherwise the agent invented a duplicate and the promise is created.
    - two of the user's promises within CLASH_WINDOW_HOURS are always a conflict,
      even if the agent missed it (the agent can still add subtler conflicts).
    """
    corrections = []
    checked = {}
    for item in new_items:
        d = dict(decisions.get(item["tmp_id"]) or {"tmp_id": item["tmp_id"], "action": "create"})
        action = d.get("action", "create")
        if action in ("skip", "update"):
            similar = {s["id"]: s for s in item.get("similar", [])}
            target = similar.get(d.get("target_id")) or next(iter(item.get("similar", [])), None)
            same_person = target and (target.get("counterparty") or "").lower() == \
                (item.get("counterparty") or "").lower()
            if not target or (target.get("score") or 0) < DUPLICATE_MIN_SCORE or not same_person:
                corrections.append({"action": item["action"], "agent_said": action,
                                    "verified": "create",
                                    "why": "no matching promise exists in memory"})
                d.update(action="create", target_id=None)
            else:
                d["target_id"] = target["id"]

        due = parse_iso(item.get("due_at"))
        if item.get("owner") == "me" and due and d.get("action") != "skip":
            window = CLASH_WINDOW_HOURS * 3600
            clashes = [s for s in item.get("same_day", [])
                       if s.get("owner") == "me" and s["id"] != d.get("target_id")
                       and (sd := parse_iso(s.get("due_at"))) and abs((sd - due).total_seconds()) <= window]
            missed = [s for s in clashes if s["id"] not in (d.get("conflict_with") or [])]
            if missed:
                agent_flagged = bool(d.get("conflict"))
                corrections.append({"action": item["action"],
                                    "agent_said": "partial conflict" if agent_flagged else "no conflict",
                                    "verified": "conflict", "with": [s["action"] for s in missed]})
                d["conflict"] = True
                d["conflict_with"] = list(dict.fromkeys((d.get("conflict_with") or []) + [s["id"] for s in missed]))
                if not agent_flagged:
                    first = missed[0]
                    d["reason"] = f"Same time as '{first['action']}' for {first.get('counterparty') or 'someone'}."
        checked[item["tmp_id"]] = d
    return checked, corrections


WEEKDAY_WORDS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
                 "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4,
                 "saturday": 5, "sat": 5, "sunday": 6, "sun": 6}


def _due_dates(value) -> list[datetime]:
    if isinstance(value, list):
        return [d for v in value for d in _due_dates(v)]
    if isinstance(value, dict):
        found = [d for v in value.values() for d in _due_dates(v)]
        if (due := parse_iso(value.get("due_at"))):
            found.append(due)
        return found
    return []


STOPWORDS = {"the", "a", "an", "to", "for", "of", "with", "and", "by", "on", "at", "you", "your", "me",
              "my", "i", "is", "it", "noted", "due", "from", "pm", "am", "s"}


def _promises(value) -> list[dict]:
    """Every dict in a payload that describes a dated promise."""
    if isinstance(value, list):
        return [p for v in value for p in _promises(v)]
    if isinstance(value, dict):
        found = [p for v in value.values() for p in _promises(v)]
        if value.get("action") and parse_iso(value.get("due_at")):
            found.append(value)
        return found
    return []


def _days_allowed(dates: set, today) -> tuple[set, set]:
    relative = set()
    if today in dates:
        relative |= {"today", "tonight"}
    if today + timedelta(days=1) in dates:
        relative.add("tomorrow")
    return {d.weekday() for d in dates}, relative


def _day_words_ok(message: str, events: list[dict], reference: datetime) -> bool:
    """True if every weekday / today / tomorrow in `message` matches the promise it describes.

    The message is split into clauses; a clause is checked against the promise whose
    action it shares the most words with (or against all deadlines if none match).
    """
    today = to_local(reference).date()
    promises = _promises(events)
    all_dates = {to_local(d).date() for d in _due_dates(events)}
    for clause in re.split(r"[;&|.,]|\band\b|\bwhile\b|\bclashes with\b|\bvs\b", message.lower()):
        words = re.findall(r"[a-z]+", clause)
        weekdays = {WEEKDAY_WORDS[w] for w in words if w in WEEKDAY_WORDS}
        relative = {w for w in words if w in ("today", "tonight", "tomorrow")}
        if not weekdays and not relative:
            continue
        clause_words = set(words) - STOPWORDS
        scored = [(len(clause_words & (_words(p["action"]) - STOPWORDS)), p) for p in promises]
        best_score = max((s for s, _ in scored), default=0)
        dates = ({to_local(parse_iso(p["due_at"])).date() for s, p in scored if s == best_score}
                 if best_score else all_dates)
        ok_weekdays, ok_relative = _days_allowed(dates, today)
        if not (weekdays <= ok_weekdays and relative <= ok_relative):
            return False
    return True


def check_notifications(notes: list[dict], events: list[dict], fallback, reference: datetime) -> tuple[list[dict], list[dict]]:
    """Replace any notification whose day words contradict the real deadlines.

    `fallback(events)` must return {"notifications": [...]} worded from the true dates.
    """
    corrections = []
    aligned = len(notes) == len(events)
    checked = []
    for i, note in enumerate(notes):
        scope = [events[i]] if aligned else events
        if _day_words_ok(note.get("message", ""), scope, reference):
            checked.append(note)
            continue
        replacement = (fallback(scope).get("notifications") or [note])[0]
        corrections.append({"agent_wrote": note.get("message"), "sent_instead": replacement["message"]})
        checked.append({**replacement, "priority": note.get("priority", replacement.get("priority"))})
    return checked, corrections


def ground_commitments(items: list[dict], segments: list[dict], reference: datetime) -> tuple[list[dict], list[dict]]:
    """Fix dates and people in place. Returns (items, corrections) for the trace."""
    by_idx = {s["idx"]: s for s in segments}
    others = Counter(s["speaker"] for s in segments if not s["is_user"])
    main_other = others.most_common(1)[0][0] if others else None
    corrections = []
    for c in items:
        seg = by_idx.get(c.get("segment_idx"))
        counterparty = (c.get("counterparty") or "").strip()
        if counterparty.lower() in PRONOUNS:
            fixed = seg["speaker"] if (c.get("owner") == "other" and seg and not seg["is_user"]) else main_other
            if fixed and fixed != counterparty:
                corrections.append({"action": c.get("action"), "field": "counterparty",
                                    "agent": counterparty or None, "verified": fixed})
                c["counterparty"] = fixed

        # "call you" reads wrong on a dashboard: name the person and start with a capital
        if c.get("owner") == "me" and c.get("counterparty") and c.get("action"):
            cp = c["counterparty"]
            c["action"] = re.sub(r"\byou\b", cp, re.sub(r"\byour\b", f"{cp}'s", c["action"], flags=re.I),
                                 flags=re.I)
        if c.get("action"):
            c["action"] = c["action"][0].upper() + c["action"][1:]

        resolved = due_from_quote(c.get("quote") or "", c.get("action") or "", reference)
        if resolved:
            agent_due = parse_iso(c.get("due_at"))
            if agent_due != resolved:
                corrections.append({"action": c.get("action"), "field": "due_at",
                                    "agent": c.get("due_at"), "verified": resolved.isoformat(),
                                    "from": c.get("quote")})
            c["due_at"] = resolved.isoformat()
    return items, corrections
