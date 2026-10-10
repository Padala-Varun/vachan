"""Regression tests built from real (wrong) Extractor replies seen on Lyzr."""
from datetime import datetime

from app.config import settings
from app.grounding import calendar, check_decisions, check_notifications, ground_commitments

MONDAY = datetime(2026, 10, 12, 9, 30, tzinfo=settings.tz)
SEGMENTS = [
    {"idx": 0, "speaker": "You", "is_user": True,
     "text": "Thanks Rahul. I'll send you the updated pitch deck by Thursday evening."},
    {"idx": 1, "speaker": "Rahul", "is_user": False,
     "text": "Perfect. I'll share the investor list with you tomorrow morning."},
]


def test_wrong_weekday_and_pronoun_are_corrected():
    llm = [
        {"owner": "me", "counterparty": "Rahul", "action": "Send the updated pitch deck to Rahul",
         "due_at": "2026-10-12T18:00:00+05:30", "segment_idx": 0,
         "quote": "I'll send you the updated pitch deck by Thursday evening."},
        {"owner": "other", "counterparty": "you", "action": "Share the investor list with me",
         "due_at": "2026-10-13T10:00:00+05:30", "segment_idx": 1,
         "quote": "I'll share the investor list with you tomorrow morning."},
    ]
    items, corrections = ground_commitments(llm, SEGMENTS, MONDAY)
    assert items[0]["due_at"] == "2026-10-15T18:00:00+05:30"   # Thursday, not Monday
    assert items[1]["counterparty"] == "Rahul"
    assert items[1]["due_at"] == "2026-10-13T10:00:00+05:30"   # already right: untouched
    assert {c["field"] for c in corrections} == {"due_at", "counterparty"}


def test_quote_with_two_deadlines_picks_matching_sentence():
    saturday = datetime(2026, 10, 10, 19, 30, tzinfo=settings.tz)
    quote = "Sure Priya, I'll review your PR on Thursday at 6 pm. I'll also call Arjun on Sunday."
    llm = [{"owner": "me", "counterparty": "Arjun", "action": "Call Arjun", "due_at": None,
            "segment_idx": 0, "quote": quote}]
    items, _ = ground_commitments(llm, [{"idx": 0, "speaker": "You", "is_user": True, "text": quote}],
                                  saturday)
    assert items[0]["due_at"].startswith("2026-10-11T18:00")


def test_pronouns_in_my_promise_become_names():
    llm = [{"owner": "me", "counterparty": "Arjun", "action": "Call you about your results",
            "due_at": None, "segment_idx": 0, "quote": "I'll call you"}]
    items, _ = ground_commitments(llm, SEGMENTS, MONDAY)
    assert items[0]["action"] == "Call Arjun about Arjun's results"


def test_agent_date_kept_when_quote_has_no_deadline():
    llm = [{"owner": "me", "counterparty": "Rahul", "action": "Send the deck",
            "due_at": "2026-10-20T12:00:00+05:30", "segment_idx": 0, "quote": "I'll send it then."}]
    items, corrections = ground_commitments(llm, SEGMENTS, MONDAY)
    assert items[0]["due_at"] == "2026-10-20T12:00:00+05:30" and not corrections


def test_invented_duplicate_is_overruled():
    # live Curator said "skip, duplicate" although Qdrant returned no similar promise
    items = [{"tmp_id": "new-0", "owner": "me", "counterparty": "Rahul", "action": "Send the deck",
              "due_at": "2026-10-15T18:00:00+05:30", "similar": [], "same_day": []}]
    checked, corrections = check_decisions(items, {"new-0": {"tmp_id": "new-0", "action": "skip"}})
    assert checked["new-0"]["action"] == "create" and corrections


def test_real_duplicate_is_kept():
    items = [{"tmp_id": "new-0", "owner": "me", "counterparty": "Rahul", "action": "Send the deck",
              "due_at": None, "same_day": [],
              "similar": [{"id": "c1", "score": 0.97, "counterparty": "Rahul", "owner": "me"}]}]
    checked, corrections = check_decisions(items, {"new-0": {"tmp_id": "new-0", "action": "skip"}})
    assert checked["new-0"]["action"] == "skip" and not corrections


def test_missed_time_clash_is_flagged():
    items = [{"tmp_id": "new-1", "owner": "me", "counterparty": "Priya", "action": "Book the team dinner",
              "due_at": "2026-10-15T18:00:00+05:30", "similar": [],
              "same_day": [{"id": "c1", "owner": "me", "counterparty": "Rahul", "action": "Send the deck",
                            "due_at": "2026-10-15T18:30:00+05:30"},
                           {"id": "c2", "owner": "other", "counterparty": "Priya", "action": "Fix tests",
                            "due_at": "2026-10-15T18:00:00+05:30"}]}]
    checked, _ = check_decisions(items, {"new-1": {"tmp_id": "new-1", "action": "create", "conflict": False}})
    d = checked["new-1"]
    assert d["conflict"] and d["conflict_with"] == ["c1"] and "Send the deck" in d["reason"]


def test_notification_with_wrong_day_is_replaced():
    saturday = datetime(2026, 10, 10, 19, 30, tzinfo=settings.tz)
    events = [{"type": "captured", "commitments": [
        {"owner": "me", "counterparty": "Rahul", "action": "Send the deck", "due_at": "2026-10-15T18:00:00+05:30"},
        {"owner": "other", "counterparty": "Rahul", "action": "Share the investor list",
         "due_at": "2026-10-11T10:00:00+05:30"}]}]
    good = {"message": "Noted: deck to Rahul Thu 6 PM, investor list from Rahul tomorrow 10 AM"}
    bad = {"message": "Noted: deck to Rahul Thu 6 PM & investor list from Rahul Fri 10 AM"}
    fallback = lambda evs: {"notifications": [{"message": "FALLBACK", "priority": "low"}]}  # noqa: E731
    notes, fixes = check_notifications([good], events, fallback, saturday)
    assert notes == [good] and not fixes
    notes, fixes = check_notifications([bad], events, fallback, saturday)
    assert notes[0]["message"] == "FALLBACK" and fixes[0]["agent_wrote"] == bad["message"]
    # the day is valid for *a* promise in the message, but not for the one it describes
    mixed = {"message": "Noted: send pitch deck to Rahul Thu 6 PM & share investor list Thu 10 AM."}
    notes, fixes = check_notifications([mixed], events, fallback, saturday)
    assert notes[0]["message"] == "FALLBACK"


def test_calendar_maps_weekdays_to_dates():
    cal = calendar(MONDAY)
    assert cal["today"] == "Monday 12 October 2026"
    assert cal["next_7_days"]["Thursday"] == "2026-10-15"
    assert cal["next_7_days"]["Monday"] == "2026-10-19"
