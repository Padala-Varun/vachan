"""Voice commands ("Hey Vachan, ..."): the Router agent delegates to a specialist."""
import re
import uuid

from .lyzr_client import lyzr
from .memory import get_store
from .omi import notifier
from .pipeline import known_uids, process_conversation
from .scheduler import cancel_reminders
from .timeutil import add_when, now, parse_iso
from .trace import tracer

# Calibrated on bge-small: unrelated promises score 0.50-0.65, the intended one 0.80+.
MARK_DONE_MIN_SCORE = 0.75
MARK_DONE_MIN_SCORE_FOR_PERSON = 0.6   # lower bar once results are filtered to one person


def _brief(c: dict) -> dict:
    return {k: c.get(k) for k in ("owner", "counterparty", "action", "due_at", "status")}


async def handle_command(uid: str, text: str, source: str = "text") -> dict:
    store = get_store()
    known_uids.add(uid)
    run_id = tracer.run_start("command", text, uid=uid, source=source)
    try:
        router_in = {"command": text, "now": now().isoformat(),
                     "known_people": store.counterparties(uid)}
        async with tracer.span(run_id, "router", input=router_in) as span:
            route, backend = await lyzr.run("router", router_in, uid=uid, session_id=run_id)
            # a person named in the command is never lost, even if the agent drops it
            if not route.get("counterparty"):
                named = [p for p in router_in["known_people"]
                         if re.search(rf"\b{re.escape(p)}\b", text, re.I)]
                if len(named) == 1:
                    route["counterparty"] = named[0]
            span.output, span.meta["backend"] = route, backend

        intent = route.get("intent", "unknown")
        handler = {"recall": _recall, "mark_done": _mark_done, "forget": _forget,
                   "add": _add}.get(intent, _unknown)
        result = await handler(uid, text, route, run_id)
        # Spoken to Omi -> answer on the phone. Asked on the dashboard -> the answer is
        # already on screen, so don't spend one of Omi's 10 notifications per hour.
        note = await notifier.notify(uid, result["answer"], kind=intent, run_id=run_id,
                                     push=source == "voice")
        tracer.run_end(run_id, "ok", intent=intent)
        return {"run_id": run_id, "intent": intent, "route": route, **result,
                "notification": note}
    except Exception as exc:
        tracer.run_end(run_id, "error", error=str(exc))
        raise


async def _recall(uid: str, text: str, route: dict, run_id: str) -> dict:
    store = get_store()
    time_from, time_to = parse_iso(route.get("time_from")), parse_iso(route.get("time_to"))
    query = route.get("query") or text
    async with tracer.span(run_id, "qdrant_recall", kind="qdrant", input=route) as span:
        commitments = store.search_commitments(
            uid, query, limit=8, status=["open", "done"], counterparty=route.get("counterparty"),
            shared_only=True, due_from=time_from, due_to=time_to)
        if route.get("owner") in ("me", "other"):
            commitments = [c for c in commitments if c.get("owner") == route["owner"]]
        conversations = store.search_transcripts(uid, query, limit=3, shared_only=True)
        span.output = {"commitments": len(commitments), "conversations": len(conversations)}
    recall_in = {"question": text, "now": now().isoformat(),
                 "commitments": add_when([_brief(c) for c in sorted(
                     commitments, key=lambda c: c.get("due_ts") or float("inf"))]),
                 "conversations": [{"started_at": c.get("started_at"), "text": c.get("text")}
                                   for c in conversations]}
    async with tracer.span(run_id, "recall", input=recall_in) as span:
        answer, backend = await lyzr.run("recall", recall_in, uid=uid, session_id=run_id)
        span.output, span.meta["backend"] = answer, backend
    return {"answer": answer.get("answer") or "I couldn't find anything about that.",
            "matches": commitments}


async def _mark_done(uid: str, text: str, route: dict, run_id: str) -> dict:
    store = get_store()
    async with tracer.span(run_id, "qdrant_mark_done", kind="qdrant", input=route) as span:
        hits = store.search_commitments(uid, route.get("query") or text, limit=3, status="open",
                                        counterparty=route.get("counterparty"))
        bar = MARK_DONE_MIN_SCORE_FOR_PERSON if route.get("counterparty") else MARK_DONE_MIN_SCORE
        best = hits[0] if hits and hits[0].get("score", 0) >= bar else None
        if best:
            store.update_commitment(best["id"], {"status": "done"}, event=f"done via {text!r}")
            cancel_reminders(best["id"])
        span.output = {"matched": best and _brief(best), "score": best and best.get("score")}
    if not best:
        return {"answer": "I couldn't tell which promise you finished. Try naming the person.",
                "matches": hits}
    who = best.get("counterparty") or "them"
    return {"answer": f"✅ Promise kept: {best['action']} ({who}). Nice!", "matches": [best]}


async def _forget(uid: str, text: str, route: dict, run_id: str) -> dict:
    store = get_store()
    query = re.sub(r"^(about|what i said about|everything about)\s+", "",
                   route.get("query") or text).strip()
    async with tracer.span(run_id, "qdrant_forget", kind="qdrant", input={"query": query}) as span:
        removed = store.forget(uid, query)
        for item in removed.get("commitments", []):
            cancel_reminders(item["id"])
        span.output = {k: len(v) for k, v in removed.items()}
    total = sum(len(v) for v in removed.values())
    answer = (f"🗑️ Forgotten: {total} memories about \"{query}\" were permanently deleted."
              if total else f"I had nothing stored about \"{query}\".")
    return {"answer": answer, "removed": removed}


async def _add(uid: str, text: str, route: dict, run_id: str) -> dict:
    sentence = re.sub(r"^(please\s+)?(remind me( that)?|note that|remember that)\s*", "", text,
                      flags=re.I).strip()
    body = {"id": f"voice-{uuid.uuid4().hex[:8]}", "started_at": now().isoformat(),
            "structured": {"title": "Voice note"},
            "transcript_segments": [{"text": sentence, "speaker": "SPEAKER_00",
                                     "speaker_name": "You", "is_user": True}]}
    if route.get("counterparty"):
        body["transcript_segments"].append({"text": f"(talking with {route['counterparty']})",
                                            "speaker_name": route["counterparty"],
                                            "is_user": False})
    async with tracer.span(run_id, "pipeline", kind="local", input={"text": sentence}) as span:
        # the command's own reply is the single notification, so the inner run stays quiet
        summary = await process_conversation(body, uid, push=False)
        span.output = {"created": len(summary["created"]), "run_id": summary["run_id"]}
    if summary["created"] or summary["updated"]:
        c = (summary["created"] or summary["updated"])[0]
        answer = f"📝 Got it: {c['action']}."
        if summary["conflicts"]:
            answer += f" ⚠️ Heads up: {summary['conflicts'][0].get('conflict_reason')}"
        return {"answer": answer, "matches": [c]}
    return {"answer": "I heard you, but couldn't find a promise in that.", "matches": []}


async def _unknown(uid: str, text: str, route: dict, run_id: str) -> dict:
    return {"answer": "Try: \"what do I owe Rahul?\", \"I sent the deck\", or "
                      "\"forget what I said about the loan\".", "matches": []}
