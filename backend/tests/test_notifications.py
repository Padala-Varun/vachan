import asyncio

import httpx

from app.commands import handle_command
from app.config import settings
from app.omi import Notifier, notifier
from app.pipeline import process_conversation

UID = "notify-user"


def run(coro):
    return asyncio.run(coro)


def test_one_notification_per_conversation(store, fixture_body):
    run(process_conversation(fixture_body("01_pitch_deck.json"), UID))
    before = len(notifier.feed)
    summary = run(process_conversation(fixture_body("02_conflict.json"), UID))
    new = list(notifier.feed)[: len(notifier.feed) - before]
    assert summary["conflicts"] and len(new) == 1
    assert new[0]["kind"] == "conflict" and new[0]["priority"] == "high"
    assert "\n" in new[0]["message"]            # clash warning + captured promises, one buzz


def test_dashboard_questions_stay_on_dashboard(store, fixture_body):
    run(process_conversation(fixture_body("01_pitch_deck.json"), UID))
    typed = run(handle_command(UID, "what do I owe Rahul?", source="dashboard"))
    spoken = run(handle_command(UID, "what do I owe Rahul?", source="voice"))
    assert typed["notification"]["channel"] == "dashboard"
    assert spoken["notification"]["channel"] != "dashboard"


def test_hourly_limit_is_respected(monkeypatch):
    monkeypatch.setattr(settings, "omi_app_id", "app")
    monkeypatch.setattr(settings, "omi_app_secret", "secret")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"status": "Ok"})

    n = Notifier(transport=httpx.MockTransport(handler))
    results = [run(n.notify("u1", f"msg {i}")) for i in range(Notifier.HOURLY_LIMIT + 2)]
    assert len(calls) == Notifier.HOURLY_LIMIT          # never asks Omi past the limit
    assert all(r["delivered"] for r in results[: Notifier.HOURLY_LIMIT])
    assert results[-1]["error"] == Notifier.LIMIT_MESSAGE


def test_omi_429_shows_friendly_message(monkeypatch):
    monkeypatch.setattr(settings, "omi_app_id", "app")
    monkeypatch.setattr(settings, "omi_app_secret", "secret")
    n = Notifier(transport=httpx.MockTransport(lambda r: httpx.Response(429, json={"detail": "Rate limit"})))
    note = run(n.notify("u1", "hello"))
    assert not note["delivered"] and note["error"] == Notifier.LIMIT_MESSAGE
