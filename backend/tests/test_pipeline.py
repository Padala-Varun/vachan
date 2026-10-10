import asyncio

from app.commands import handle_command
from app.omi import WakeListener, notifier
from app.pipeline import process_conversation
from app.trace import tracer

UID = "test-user"


def run(coro):
    return asyncio.run(coro)


def test_conversation_creates_commitments_and_traces(store, fixture_body):
    summary = run(process_conversation(fixture_body("01_pitch_deck.json"), UID))
    actions = [c["action"] for c in summary["created"]]
    assert any("pitch deck" in a for a in actions)
    assert store.stats(UID)["commitments"] == len(summary["created"]) >= 2

    steps = [e["step"] for e in tracer.events
             if e.get("run_id") == summary["run_id"] and e["type"] == "step_end"]
    for step in ("privacy_prepass", "privacy_guard", "qdrant_store_transcript", "extractor",
                 "qdrant_retrieve_context", "curator", "qdrant_write_commitments", "nudger"):
        assert step in steps
    assert notifier.feed, "a notification should be produced"


def test_privacy_nothing_sensitive_reaches_qdrant(store, fixture_body):
    run(process_conversation(fixture_body("01_pitch_deck.json"), UID))
    run(process_conversation(fixture_body("03_sensitive.json"), UID))
    stored = " ".join(t["text"] for t in store.list_transcripts(UID))
    assert "98765" not in stored and "CTO" not in stored
    assert "blood pressure" not in stored and "20,000" not in stored
    loan = [c for c in store.list_commitments(UID) if "loan" in c["action"].lower()]
    assert loan and loan[0]["visibility"] == "private"


def test_conflict_detected_across_conversations(store, fixture_body):
    run(process_conversation(fixture_body("01_pitch_deck.json"), UID))
    summary = run(process_conversation(fixture_body("02_conflict.json"), UID))
    assert summary["conflicts"], "Thursday 6 PM PR review should clash with the deck"
    assert any(n["kind"] == "conflict" and n["priority"] == "high" for n in notifier.feed)


def test_duplicate_conversation_is_skipped(store, fixture_body):
    body = fixture_body("01_pitch_deck.json")
    first = run(process_conversation(body, UID))
    second = run(process_conversation(body, UID))
    assert second["skipped"] == len(first["created"])
    assert store.stats(UID)["commitments"] == len(first["created"])


def test_voice_commands_recall_done_forget(store, fixture_body):
    run(process_conversation(fixture_body("01_pitch_deck.json"), UID))
    run(process_conversation(fixture_body("03_sensitive.json"), UID))

    recall = run(handle_command(UID, "what do I owe Rahul?"))
    assert recall["intent"] == "recall" and "deck" in recall["answer"].lower()
    # private commitments never feed the recall agent
    assert all(m.get("visibility") != "private" for m in recall["matches"])

    done = run(handle_command(UID, "I sent the pitch deck to Rahul"))
    assert done["intent"] == "mark_done"
    deck = [c for c in store.list_commitments(UID) if "pitch deck" in c["action"]][0]
    assert deck["status"] == "done"

    forgot = run(handle_command(UID, "forget the pay back loan Arjun"))
    assert forgot["intent"] == "forget"
    assert not [c for c in store.list_commitments(UID) if "loan" in c["action"].lower()]
    assert store.audit_log()[0]["action"] == "delete"


def test_wake_listener_collects_command_across_batches():
    heard = []

    async def handler(uid, text, source):
        heard.append((uid, text, source))

    async def scenario():
        listener = WakeListener(handler, window=0.05)
        await listener.feed("s1", "u1", [{"text": "random chatter", "start": 0}])
        await listener.feed("s1", "u1", [{"text": "Hey Vachan, what do I owe", "start": 1}])
        await listener.feed("s1", "u1", [{"text": "Rahul this week?", "start": 2}])
        await listener.feed("s1", "u1", [{"text": "Rahul this week?", "start": 2}])  # duplicate
        await asyncio.sleep(0.2)

    run(scenario())
    assert heard == [("u1", "what do I owe Rahul this week?", "voice")]
