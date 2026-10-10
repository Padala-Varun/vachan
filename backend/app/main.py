"""Vachan API: Omi webhooks, dashboard REST API and the live agent-trace stream."""
import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import scheduler
from .commands import handle_command
from .config import AGENT_NAMES, settings
from .lyzr_client import lyzr
from .memory import COMMITMENTS, TRANSCRIPTS, get_store
from .omi import WakeListener, notifier
from .pipeline import process_conversation
from .timeutil import now, parse_iso
from .trace import tracer

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = Path(os.getenv("VACHAN_FRONTEND_DIST", str(REPO_ROOT / "frontend" / "dist")))
FIXTURES_DIR = settings.fixtures_dir
STREAM_MAX_SECONDS = 120

wake_listener = WakeListener(handle_command)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_store()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Vachan", description="Your word, kept.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_origin_regex=settings.cors_origin_regex or None,
                   allow_methods=["*"], allow_headers=["*"])


def _uid(uid: str | None) -> str:
    return uid or settings.default_uid


async def _safe(coro) -> None:
    try:
        await coro
    except Exception as exc:  # already traced; keep the worker alive
        print(f"[vachan] background task failed: {exc}")


# --------------------------------------------------------------------------- Omi webhooks
@app.post("/omi/conversation")
async def omi_conversation(background: BackgroundTasks, body: dict = Body(...),
                           uid: str | None = None):
    """Omi "Conversation Creation" trigger: full transcript after a conversation ends."""
    background.add_task(_safe, process_conversation(body, _uid(uid)))
    return {"status": "accepted"}


@app.post("/omi/realtime")
async def omi_realtime(body: list | dict = Body(...), session_id: str = "default",
                       uid: str | None = None):
    """Omi "Real-time Transcript" trigger: watches for "Hey Vachan, ..." commands."""
    segments = body if isinstance(body, list) else body.get("segments", [])
    detected = await wake_listener.feed(session_id, _uid(uid), segments)
    return {"status": "ok", "wake": bool(detected)}


@app.get("/omi/setup-complete")
async def omi_setup_complete(uid: str | None = None):
    return {"is_setup_completed": True}


# --------------------------------------------------------------------------- dashboard API
def _decorate(c: dict) -> dict:
    due, current = parse_iso(c.get("due_at")), now()
    if c.get("status") == "open" and due:
        hours = (due - current).total_seconds() / 3600
        c["urgency"] = "overdue" if hours < 0 else "soon" if hours <= 24 else "later"
    else:
        c["urgency"] = "none"
    return c


@app.get("/api/health")
async def health(uid: str | None = None):
    store = get_store()
    return {
        "status": "ok",
        "uid": _uid(uid),
        "agents": {name: lyzr.mode(name) for name in AGENT_NAMES},
        "agent_errors": dict(lyzr.last_error),
        "qdrant": store.mode,
        "embedder": type(store.embedder).__name__,
        "omi": notifier.mode,
        "wake_phrases": list(settings.wake_phrases),
        "stats": store.stats(_uid(uid)),
        "scheduled_jobs": len(scheduler.upcoming_jobs()),
    }


@app.get("/api/commitments")
async def list_commitments(uid: str | None = None, status: str | None = None,
                           counterparty: str | None = None):
    items = get_store().list_commitments(_uid(uid), status=status, counterparty=counterparty)
    return [_decorate(c) for c in items]


@app.patch("/api/commitments/{cid}")
async def patch_commitment(cid: str, body: dict = Body(...), uid: str | None = None):
    store = get_store()
    allowed = {k: v for k, v in body.items() if k in {"status", "visibility", "due_at", "action"}}
    if "visibility" in allowed:
        store.set_visibility(COMMITMENTS, cid, allowed.pop("visibility"))
    record = store.update_commitment(cid, allowed, event=f"edited: {', '.join(allowed)}") \
        if allowed else store.get_commitment(cid)
    if record is None:
        raise HTTPException(404, "commitment not found")
    if record.get("status") == "open":
        scheduler.schedule_reminders(_uid(uid), record)
    else:
        scheduler.cancel_reminders(cid)
    return _decorate(record)


@app.delete("/api/commitments/{cid}")
async def delete_commitment(cid: str):
    get_store().delete_points(COMMITMENTS, [cid], reason="deleted from dashboard")
    scheduler.cancel_reminders(cid)
    return {"deleted": cid}


@app.get("/api/memories")
async def memories(uid: str | None = None, q: str | None = None,
                   conversation_id: str | None = None):
    store = get_store()
    if q:
        return store.search_transcripts(_uid(uid), q, limit=20)
    items = store.list_transcripts(_uid(uid))
    if conversation_id:
        items = sorted((m for m in items if m.get("conversation_id") == conversation_id),
                       key=lambda m: (m.get("segment_range") or [0])[0])
    return items


@app.patch("/api/memories/{mid}")
async def patch_memory(mid: str, body: dict = Body(...)):
    visibility = body.get("visibility")
    if visibility not in ("private", "shared"):
        raise HTTPException(400, "visibility must be 'private' or 'shared'")
    get_store().set_visibility(TRANSCRIPTS, mid, visibility)
    return {"id": mid, "visibility": visibility}


@app.delete("/api/memories/{mid}")
async def delete_memory(mid: str):
    get_store().delete_points(TRANSCRIPTS, [mid], reason="deleted from dashboard")
    return {"deleted": mid}


@app.post("/api/ask")
async def ask(body: dict = Body(...), uid: str | None = None):
    """Typed fallback for a voice command."""
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text is required")
    return await handle_command(_uid(uid), text, source=body.get("source", "text"))


@app.get("/api/notifications")
async def notifications():
    return list(notifier.feed)


@app.get("/api/audit")
async def audit():
    return get_store().audit_log()


@app.get("/api/traces")
async def traces(limit: int = 400):
    return list(tracer.events)[-limit:]


@app.get("/api/stream")
async def stream(request: Request):
    queue = tracer.subscribe()

    # Streams end after STREAM_MAX_SECONDS; the browser reconnects automatically and reloads
    # history. Without this, open dashboards keep the container busy forever and a redeploy
    # (single container) can't take over until every tab is closed.
    deadline = asyncio.get_running_loop().time() + STREAM_MAX_SECONDS

    async def events():
        try:
            yield "retry: 1500\n\n"
            while (not await request.is_disconnected()
                   and asyncio.get_running_loop().time() < deadline):
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(event, default=str, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            tracer.unsubscribe(queue)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --------------------------------------------------------------------------- demo helpers
def _fixtures() -> list[dict]:
    items = []
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))
        items.append({"name": path.name, "title": body.get("structured", {}).get("title", path.stem),
                      "segments": len(body.get("transcript_segments", []))})
    return items


@app.get("/api/demo/fixtures")
async def demo_fixtures():
    return _fixtures()


@app.post("/api/demo/simulate")
async def demo_simulate(background: BackgroundTasks, body: dict = Body(default={}),
                        uid: str | None = None):
    """Replay demo conversations exactly as Omi would send them (no device needed)."""
    names = body.get("fixtures") or [f["name"] for f in _fixtures()]
    paths = [FIXTURES_DIR / n for n in names if (FIXTURES_DIR / n).is_file()]
    if not paths:
        raise HTTPException(404, "no matching fixtures")

    async def replay():
        for i, path in enumerate(paths):
            if i:
                await asyncio.sleep(2.5)
            conv = json.loads(path.read_text(encoding="utf-8"))
            conv["id"] = f"{conv.get('id', path.stem)}-{uuid.uuid4().hex[:6]}"
            conv["started_at"] = now().isoformat()
            await _safe(process_conversation(conv, _uid(uid)))

    background.add_task(replay)
    return {"status": "accepted", "conversations": [p.name for p in paths]}


@app.post("/api/demo/digest")
async def demo_digest(uid: str | None = None):
    await scheduler.send_digest(_uid(uid))
    return {"status": "sent"}


@app.post("/api/demo/remind/{cid}")
async def demo_remind(cid: str, uid: str | None = None):
    await scheduler.send_reminder(_uid(uid), cid)
    return {"status": "sent"}


@app.post("/api/demo/reset")
async def demo_reset():
    get_store().reset()
    for job in scheduler.scheduler.get_jobs():
        if job.id != "nightly-digest":
            job.remove()
    tracer.events.clear()
    notifier.feed.clear()
    return {"status": "reset"}


# --------------------------------------------------------------------------- built dashboard
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        target = FRONTEND_DIST / path
        return FileResponse(target if path and target.is_file() else FRONTEND_DIST / "index.html")
