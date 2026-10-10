from datetime import datetime

import pytest

from app.config import settings
from app.lyzr_client import AgentError, extract_json
from app.mock_agents import extractor, router
from app.omi import parse_conversation
from app.privacy import mask_pii, prepass
from app.timeutil import resolve_due

MONDAY = datetime(2026, 10, 12, 9, 30, tzinfo=settings.tz)


def test_mask_pii_covers_indian_formats():
    text = "Call 98765 43210 or mail a.b@x.com, aadhaar 1234 5678 9012, PAN ABCDE1234F"
    masked = mask_pii(text)
    assert "98765" not in masked and "a.b@x.com" not in masked
    assert "[PHONE]" in masked and "[EMAIL]" in masked
    assert "[AADHAAR]" in masked and "[PAN]" in masked


def test_off_the_record_is_dropped():
    segs = [
        {"idx": 0, "text": "Fine. Off the record, the CTO is quitting. Back on the record."},
        {"idx": 1, "text": "Off the record again: secret plan"},
        {"idx": 2, "text": "still secret"},
        {"idx": 3, "text": "ok back on the record, I'll send it Friday"},
    ]
    kept, report = prepass(segs)
    joined = " ".join(s["text"] for s in kept)
    assert "CTO" not in joined and "secret" not in joined
    assert "Fine" in joined and "send it Friday" in joined
    assert report["off_record_segments"] == 4


@pytest.mark.parametrize("phrase,expected", [
    ("by Thursday evening", datetime(2026, 10, 15, 18, 0)),
    ("tomorrow morning", datetime(2026, 10, 13, 10, 0)),
    ("on Thursday at 6 pm", datetime(2026, 10, 15, 18, 0)),
    ("next Monday", datetime(2026, 10, 19, 18, 0)),
    ("tonight", datetime(2026, 10, 12, 21, 0)),
])
def test_resolve_due(phrase, expected):
    assert resolve_due(phrase, MONDAY).replace(tzinfo=None) == expected


def test_next_weekday_means_next_calendar_week():
    saturday = datetime(2026, 10, 10, 12, 0, tzinfo=settings.tz)
    assert resolve_due("by next Friday", saturday).day == 16
    assert resolve_due("by Friday", saturday).day == 16


def test_resolve_due_none_without_deadline():
    assert resolve_due("I'll look into it", MONDAY) is None


def test_extract_json_variants():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here you go: {"a": "x \\" }", "b": [1]} hope it helps') == \
        {"a": 'x " }', "b": [1]}
    with pytest.raises(AgentError):
        extract_json("no json here")


def test_reply_contract_rejects_wrong_schema():
    from app.lyzr_client import validate_reply
    with pytest.raises(AgentError, match="segments"):
        validate_reply("privacy_guard", {"tweet": "x", "title": "sensitive"})
    assert validate_reply("recall", {"answer": "ok"}) == {"answer": "ok"}


def test_mock_extractor_owner_and_counterparty(fixture_body):
    conv = parse_conversation(fixture_body("01_pitch_deck.json"))
    out = extractor({"conversation_started_at": MONDAY.isoformat(),
                     "segments": conv["segments"]})["commitments"]
    mine = [c for c in out if c["owner"] == "me"]
    theirs = [c for c in out if c["owner"] == "other"]
    assert any("pitch deck" in c["action"] and c["counterparty"] == "Rahul" for c in mine)
    assert any("investors" in c["action"] for c in theirs)


def test_generic_speaker_gets_addressed_name(fixture_body):
    conv = parse_conversation(fixture_body("02_conflict.json"))
    assert {s["speaker"] for s in conv["segments"] if not s["is_user"]} == {"Priya"}


def test_mock_router_intents():
    people = ["Rahul", "Priya"]
    assert router({"command": "what do I owe Rahul this week?", "known_people": people}) \
        ["counterparty"] == "Rahul"
    assert router({"command": "forget what I said about the loan"})["intent"] == "forget"
    assert router({"command": "I sent the deck to Rahul", "known_people": people})["intent"] \
        == "mark_done"
