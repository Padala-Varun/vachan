"""Time-based nudges: reminders before each deadline and a nightly digest."""
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import settings
from .timeutil import day_bounds, now, parse_iso

REMINDER_LEADS = {"24h": timedelta(hours=24), "2h": timedelta(hours=2)}

scheduler = AsyncIOScheduler(timezone="UTC")


def schedule_reminders(uid: str, commitment: dict) -> int:
    """(Re)schedule reminders for one commitment; returns how many were scheduled."""
    cancel_reminders(commitment["id"])
    due = parse_iso(commitment.get("due_at"))
    if not due or commitment.get("status", "open") != "open" or commitment.get("owner") != "me":
        return 0
    count = 0
    for lead, delta in REMINDER_LEADS.items():
        run_at = due - delta
        if run_at > now():
            scheduler.add_job(send_reminder, "date", run_date=run_at,
                              args=[uid, commitment["id"]], id=f"{commitment['id']}:{lead}",
                              replace_existing=True, misfire_grace_time=600)
            count += 1
    return count


def cancel_reminders(commitment_id: str) -> None:
    for lead in REMINDER_LEADS:
        job = scheduler.get_job(f"{commitment_id}:{lead}")
        if job:
            job.remove()


def upcoming_jobs() -> list[dict]:
    return [{"id": j.id, "run_at": j.next_run_time.isoformat() if j.next_run_time else None}
            for j in scheduler.get_jobs()]


async def send_reminder(uid: str, commitment_id: str) -> None:
    from .memory import get_store
    from .pipeline import nudge
    from .trace import tracer

    c = get_store().get_commitment(commitment_id)
    if not c or c.get("status") != "open":
        return
    run_id = tracer.run_start("reminder", f"Reminder: {c['action']}", uid=uid)
    await nudge(uid, [{"type": "reminder", "commitment": c}], run_id=run_id,
                private=c.get("visibility") == "private")
    tracer.run_end(run_id, "ok")


async def send_digest(uid: str | None = None) -> None:
    from .memory import get_store
    from .pipeline import known_uids, nudge
    from .trace import tracer

    store = get_store()
    for target in ([uid] if uid else sorted(known_uids | {settings.default_uid})):
        current = now()
        open_items = store.list_commitments(target, status="open")
        if not open_items:
            continue
        tomorrow_start, tomorrow_end = day_bounds(current + timedelta(days=1))
        overdue = [c for c in open_items if (d := parse_iso(c.get("due_at"))) and d < current]
        due_tomorrow = [c for c in open_items
                        if (d := parse_iso(c.get("due_at"))) and tomorrow_start <= d < tomorrow_end]
        run_id = tracer.run_start("digest", "Nightly digest", uid=target)
        shared = lambda items: [c for c in items if c.get("visibility") != "private"]  # noqa: E731
        await nudge(target, [{"type": "digest", "overdue": shared(overdue),
                              "due_tomorrow": shared(due_tomorrow)}], run_id=run_id)
        tracer.run_end(run_id, "ok", overdue=len(overdue), due_tomorrow=len(due_tomorrow))


def start(uid_hint: str | None = None) -> None:
    from .memory import get_store

    if not scheduler.running:
        scheduler.start()
    scheduler.add_job(send_digest, "cron", hour=settings.digest_hour, minute=0,
                      timezone=settings.tz, id="nightly-digest", replace_existing=True)
    uid = uid_hint or settings.default_uid
    for c in get_store().list_commitments(uid, status="open"):
        schedule_reminders(uid, c)


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
