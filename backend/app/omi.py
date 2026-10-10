"""Omi integration: webhook payload parsing, wake-phrase listener, push notifications.

Docs: https://docs.omi.me/doc/developer/apps/Integrations
      https://docs.omi.me/doc/developer/apps/Notifications
"""
import asyncio
import json
import re
import uuid
from collections import deque
from typing import Awaitable, Callable

import httpx

from .config import settings
from .timeutil import now, parse_iso
from .trace import tracer

GENERIC_SPEAKER = re.compile(r"^speaker[\s_-]*\d+$", re.I)
ADDRESSED_NAME = re.compile(
    r"\b(?i:thanks|thank you|hey|hi|hello|ok|okay|sure|bye|see you|sounds good|listen)[,!]?\s+"
    r"([A-Z][a-z]{2,})\b")


def _addressed_name(segments: list[dict]) -> str | None:
    for seg in segments:
        if seg.get("is_user"):
            m = ADDRESSED_NAME.search(seg.get("text", ""))
            if m and m.group(1).lower() not in {"vachan", "omi"}:
                return m.group(1)
    return None


def parse_conversation(body: dict) -> dict:
    """Normalise an Omi "conversation created" payload (or a simulator payload)."""
    raw_segments = body.get("transcript_segments") or body.get("segments") or []
    segments = []
    for seg in raw_segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        is_user = bool(seg.get("is_user"))
        speaker = seg.get("speaker_name") or ("You" if is_user else seg.get("speaker")) \
            or f"Speaker {seg.get('speakerId', '?')}"
        segments.append({"idx": len(segments), "speaker": speaker, "is_user": is_user,
                         "text": text, "start": seg.get("start"), "end": seg.get("end")})

    # Omi labels unknown voices SPEAKER_01; use the name the user addresses them by.
    name = _addressed_name(segments)
    if name:
        for seg in segments:
            if not seg["is_user"] and GENERIC_SPEAKER.match(str(seg["speaker"])):
                seg["speaker"] = name

    structured = body.get("structured") or {}
    return {
        "id": str(body.get("id") or uuid.uuid4()),
        "started_at": parse_iso(body.get("started_at") or body.get("created_at")) or now(),
        "title": structured.get("title") or "Conversation",
        "segments": segments,
        "discarded": bool(body.get("discarded")),
    }


# --------------------------------------------------------------------------- notifications
class Notifier:
    """Sends Omi push notifications; always mirrors them to the dashboard's phone feed."""

    # Omi allows each app 10 phone notifications per user per hour.
    HOURLY_LIMIT = 10
    LIMIT_MESSAGE = "Phone limit reached (Omi allows 10 notifications an hour), so it's shown here instead."

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.feed: deque[dict] = deque(maxlen=200)
        self._transport = transport
        self._file = settings.data_dir / "notifications.jsonl"
        self._sent: dict[str, deque[float]] = {}

    @property
    def mode(self) -> str:
        return "omi" if settings.omi_enabled else "dry-run"

    def _under_limit(self, uid: str) -> bool:
        window = self._sent.setdefault(uid, deque())
        cutoff = now().timestamp() - 3600
        while window and window[0] < cutoff:
            window.popleft()
        return len(window) < self.HOURLY_LIMIT

    async def _push(self, uid: str, message: str) -> tuple[bool, str | None]:
        if not self._under_limit(uid):
            return False, self.LIMIT_MESSAGE
        url = f"{settings.omi_api_base}/v2/integrations/{settings.omi_app_id}/notification"
        try:
            async with httpx.AsyncClient(timeout=15, transport=self._transport) as client:
                resp = await client.post(
                    url, params={"uid": uid, "message": message},
                    headers={"Authorization": f"Bearer {settings.omi_app_secret}",
                             "Content-Type": "application/json"})
        except httpx.HTTPError as exc:
            return False, str(exc)
        self._sent[uid].append(now().timestamp())
        if resp.status_code == 429:
            return False, self.LIMIT_MESSAGE
        if resp.status_code >= 300:
            return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
        return True, None

    async def notify(self, uid: str, message: str, *, kind: str = "info",
                     priority: str = "normal", run_id: str | None = None,
                     push: bool = True) -> dict:
        """Record a nudge on the dashboard and, if `push`, send it to the phone via Omi."""
        delivered, error = False, None
        channel = self.mode if push else "dashboard"
        if push and settings.omi_enabled:
            delivered, error = await self._push(uid, message)
        note = {"id": uuid.uuid4().hex[:10], "at": now().isoformat(), "uid": uid,
                "message": message, "kind": kind, "priority": priority,
                "channel": channel, "delivered": delivered, "error": error, "run_id": run_id}
        self.feed.appendleft(note)
        tracer.emit({"type": "notification", **note})
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            with self._file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(note, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return note


notifier = Notifier()


# --------------------------------------------------------------------------- realtime
CommandHandler = Callable[[str, str, str], Awaitable[object]]


class WakeListener:
    """Watches Omi real-time transcript batches for "Hey Vachan, <command>".

    Segments after the wake phrase are collected until the speaker pauses for
    `command_window_seconds`, then the command is handed to the Router.
    """

    def __init__(self, handler: CommandHandler, window: float | None = None) -> None:
        self.handler = handler
        self.window = window if window is not None else settings.command_window_seconds
        phrases = sorted(settings.wake_phrases, key=len, reverse=True)
        self.pattern = re.compile(r"\b(?:" + "|".join(re.escape(p) for p in phrases) + r")\b[\s,.!:]*",
                                  re.I)
        self.sessions: dict[str, dict] = {}

    async def feed(self, session_id: str, uid: str, segments: list[dict]) -> list[str]:
        state = self.sessions.setdefault(session_id, {"seen": set(), "capture": None,
                                                      "timer": None, "uid": uid})
        detected = []
        for seg in segments:
            text = (seg.get("text") or "").strip()
            key = (seg.get("start"), text)
            if not text or key in state["seen"]:
                continue
            state["seen"].add(key)
            if state["capture"] is not None:
                state["capture"].append(text)
                continue
            m = self.pattern.search(text)
            if m:
                state["capture"] = [text[m.end():].strip()]
                detected.append(text)
        if state["capture"] is not None:
            if state["timer"]:
                state["timer"].cancel()
            state["timer"] = asyncio.create_task(self._flush_later(session_id))
        return detected

    async def _flush_later(self, session_id: str) -> None:
        await asyncio.sleep(self.window)
        await self.flush(session_id)

    async def flush(self, session_id: str) -> str | None:
        state = self.sessions.get(session_id)
        if not state or state["capture"] is None:
            return None
        command = " ".join(p for p in state["capture"] if p).strip(" ,.")
        state["capture"], state["timer"] = None, None
        if command:
            await self.handler(state["uid"], command, "voice")
        return command or None
