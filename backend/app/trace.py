"""Observable agent workflow: every run and every agent step becomes an event.

Events go to an in-memory ring buffer (for page loads), to live SSE
subscribers (the dashboard's DAG view), and to traces.jsonl on disk.
"""
import asyncio
import json
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from typing import Any

from .config import settings
from .timeutil import now


def _short(value: Any, limit: int = 600) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "…"
    text = json.dumps(value, default=str, ensure_ascii=False)
    return value if len(text) <= limit else text[:limit] + "…"


class Span:
    def __init__(self) -> None:
        self.output: Any = None
        self.meta: dict = {}


class TraceBus:
    def __init__(self, capacity: int = 1000) -> None:
        self.events: deque[dict] = deque(maxlen=capacity)
        self._subscribers: set[asyncio.Queue] = set()
        self._file = settings.data_dir / "traces.jsonl"

    def emit(self, event: dict) -> dict:
        event = {"ts": now().isoformat(), **event}
        self.events.append(event)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            with self._file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, default=str, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return event

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def run_start(self, kind: str, title: str, run_id: str | None = None, **extra) -> str:
        run_id = run_id or uuid.uuid4().hex[:12]
        self.emit({"type": "run_start", "run_id": run_id, "kind": kind, "title": title, **extra})
        return run_id

    def run_end(self, run_id: str, status: str = "ok", **extra) -> None:
        self.emit({"type": "run_end", "run_id": run_id, "status": status, **extra})

    @asynccontextmanager
    async def span(self, run_id: str, step: str, *, kind: str = "agent", input: Any = None):
        """Wrap one DAG step. `kind` is agent | qdrant | local | omi."""
        span_id = uuid.uuid4().hex[:8]
        self.emit({"type": "step_start", "run_id": run_id, "span_id": span_id, "step": step,
                   "kind": kind, "input": _short(input)})
        started = time.perf_counter()
        span = Span()
        try:
            yield span
        except Exception as exc:
            self.emit({"type": "step_end", "run_id": run_id, "span_id": span_id, "step": step,
                       "kind": kind, "status": "error", "error": str(exc),
                       "latency_ms": round((time.perf_counter() - started) * 1000)})
            raise
        self.emit({"type": "step_end", "run_id": run_id, "span_id": span_id, "step": step,
                   "kind": kind, "status": "ok", "output": _short(span.output),
                   "latency_ms": round((time.perf_counter() - started) * 1000), **span.meta})


tracer = TraceBus()
