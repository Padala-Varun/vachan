"""Conversation pipeline: the multi-agent DAG run for every Omi conversation.

  privacy_prepass (local) -> Privacy Guard (Lyzr) -> store transcript (Qdrant)
    -> Commitment Extractor (Lyzr) -> verify dates/people (local)
    -> retrieve similar + same-day (Qdrant)
    -> Memory Curator / Conflict Detector (Lyzr) -> write commitments (Qdrant)
    -> Nudger (Lyzr) -> Omi notification + reminder scheduling

Agents share state through Qdrant: the curator sees what earlier
conversations stored, and the recall agent later reads what the curator wrote.
"""
import re

from .grounding import calendar, check_decisions, check_notifications, ground_commitments
from .lyzr_client import lyzr
from .memory import get_store
from .mock_agents import nudger as local_nudger
from .omi import notifier, parse_conversation
from .privacy import prepass
from .scheduler import schedule_reminders
from .timeutil import add_when, day_bounds, now, parse_iso
from .trace import tracer

SENSITIVITY_RANK = {"public": 0, "personal": 1, "sensitive": 2}
SENSITIVE_TAGS = re.compile(r"\[(HEALTH|FINANCE|ADDRESS|PRIVATE|CARD|AADHAAR|PAN|OTP)\]")
MIN_CONFIDENCE = 0.6
CHUNK_SEGMENTS = 6

known_uids: set[str] = set()


def _chunks(segments: list[dict]) -> list[dict]:
    chunks = []
    for i in range(0, len(segments), CHUNK_SEGMENTS):
        group = segments[i:i + CHUNK_SEGMENTS]
        chunks.append({
            "text": "\n".join(f"{s['speaker']}: {s['text']}" for s in group),
            "speakers": sorted({s["speaker"] for s in group}),
            "sensitivity": max((s.get("sensitivity", "public") for s in group),
                               key=SENSITIVITY_RANK.get),
            "segment_range": [group[0]["idx"], group[-1]["idx"]],
        })
    return chunks


def _brief(c: dict) -> dict:
    return {k: c.get(k) for k in ("id", "owner", "counterparty", "action", "due_at", "status")}


async def nudge(uid: str, events: list[dict], *, run_id: str, private: bool = False) -> list[dict]:
    """Ask the Nudger to phrase events, then push them. Private events never reach an LLM."""
    if not events:
        return []
    payload = {"now": now().isoformat(), "events": add_when(events)}
    async with tracer.span(run_id, "nudger", input=payload) as span:
        if private:
            result, backend = local_nudger(payload), "local (private)"
        else:
            result, backend = await lyzr.run("nudger", payload, uid=uid, session_id=run_id)
        span.output, span.meta["backend"] = result, backend
    if not private:
        # guardrail: a notification must never name the wrong day
        async with tracer.span(run_id, "verify_notifications", kind="local",
                               input={"notifications": len(result.get("notifications", []))}) as span:
            notes, corrections = check_notifications(
                result.get("notifications", []), events,
                lambda evs: local_nudger({"now": payload["now"], "events": add_when(evs)}), now())
            result = {**result, "notifications": notes}
            span.output = {"corrections": corrections} if corrections else "all days and times confirmed"
    sent = []
    async with tracer.span(run_id, "omi_notify", kind="omi",
                           input={"count": len(result.get("notifications", []))}) as span:
        notes = result.get("notifications", [])
        for i, note in enumerate(notes):
            kind = events[i]["type"] if len(notes) == len(events) else events[0]["type"]
            sent.append(await notifier.notify(uid, note["message"], kind=kind,
                                              priority=note.get("priority", "normal"),
                                              run_id=run_id))
        span.output, span.meta["backend"] = [n["message"] for n in sent], notifier.mode
    return sent


async def process_conversation(body: dict, uid: str) -> dict:
    store = get_store()
    known_uids.add(uid)
    conv = parse_conversation(body)
    run_id = tracer.run_start("conversation", conv["title"], conversation_id=conv["id"], uid=uid,
                              segments=len(conv["segments"]))
    summary = {"run_id": run_id, "conversation_id": conv["id"], "created": [], "updated": [],
               "skipped": 0, "conflicts": [], "privacy": {}}
    if conv["discarded"] or not conv["segments"]:
        tracer.run_end(run_id, "skipped", reason="empty or discarded conversation")
        return summary
    try:
        # 1. deterministic local redaction: nothing below sees raw PII
        async with tracer.span(run_id, "privacy_prepass", kind="local",
                               input={"segments": len(conv["segments"])}) as span:
            segments, report = prepass(conv["segments"])
            span.output = report
        summary["privacy"] = report

        # 2. Privacy Guard agent: contextual redaction + sensitivity labels
        guard_in = {"segments": [{k: s[k] for k in ("idx", "speaker", "is_user", "text")}
                                 for s in segments]}
        async with tracer.span(run_id, "privacy_guard", input=guard_in) as span:
            guarded, backend = await lyzr.run("privacy_guard", guard_in, uid=uid, session_id=run_id)
            span.output, span.meta["backend"] = guarded, backend
        by_idx = {g["idx"]: g for g in guarded.get("segments", []) if "idx" in g}
        for seg in segments:
            g = by_idx.get(seg["idx"], {})
            seg["text"] = g.get("text") or seg["text"]
            seg["sensitivity"] = g.get("sensitivity") if g.get("sensitivity") in SENSITIVITY_RANK \
                else "personal"
            # a redacted health/finance/ID detail is sensitive, whatever label the model chose
            if SENSITIVE_TAGS.search(seg["text"]):
                seg["sensitivity"] = "sensitive"

        # 3. long-term transcript memory
        chunks = _chunks(segments)
        async with tracer.span(run_id, "qdrant_store_transcript", kind="qdrant",
                               input={"chunks": len(chunks)}) as span:
            ids = store.add_transcript_chunks(uid, conv["id"], conv["started_at"], chunks)
            span.output = {"collection": "transcripts", "points": len(ids),
                           "private": sum(c["sensitivity"] == "sensitive" for c in chunks)}

        # 4. extract commitments
        offset = now().strftime("%z")
        extract_in = {"conversation_started_at": conv["started_at"].isoformat(),
                      "timezone": f"{offset[:3]}:{offset[3:]}",
                      "calendar": calendar(conv["started_at"]),
                      "segments": [{k: s[k] for k in ("idx", "speaker", "is_user", "text")}
                                   for s in segments]}
        async with tracer.span(run_id, "extractor", input=extract_in) as span:
            extracted, backend = await lyzr.run("extractor", extract_in, uid=uid, session_id=run_id)
            span.output, span.meta["backend"] = extracted, backend
        found = [c for c in extracted.get("commitments", [])
                 if c.get("action") and (c.get("confidence") or 1) >= MIN_CONFIDENCE]

        # 4b. verify dates and people against the transcript (LLMs miscount weekdays)
        async with tracer.span(run_id, "verify_extraction", kind="local",
                               input={"candidates": len(found)}) as span:
            found, corrections = ground_commitments(found, segments, conv["started_at"])
            span.output = {"corrections": corrections} if corrections else "all dates and people confirmed"
        if not found:
            tracer.run_end(run_id, "ok", **_counts(summary))
            return summary

        # 5. retrieve memory context for every candidate (semantic + temporal)
        seg_sensitivity = {s["idx"]: s["sensitivity"] for s in segments}
        new_items = []
        async with tracer.span(run_id, "qdrant_retrieve_context", kind="qdrant",
                               input={"candidates": len(found)}) as span:
            for i, c in enumerate(found):
                due = parse_iso(c.get("due_at"))
                similar = store.search_commitments(
                    uid, store.commitment_text({**c, "owner": c.get("owner", "me")}), limit=5,
                    shared_only=True)
                same_day = [x for x in store.same_day_commitments(uid, due)
                            if x.get("visibility") != "private"] if due else []
                # earlier candidates from this same conversation also count
                for prev in new_items:
                    p_due = parse_iso(prev["due_at"])
                    if due and p_due and day_bounds(p_due) == day_bounds(due):
                        same_day.append({"id": prev["tmp_id"], **{k: prev[k] for k in (
                            "owner", "counterparty", "action", "due_at")}})
                new_items.append({
                    "tmp_id": f"new-{i}",
                    "owner": c.get("owner", "me"), "counterparty": c.get("counterparty"),
                    "action": c["action"], "due_at": due.isoformat() if due else None,
                    "similar": [{**_brief(s), "score": s.get("score")} for s in similar],
                    "same_day": [{k: x.get(k) for k in ("id", "owner", "counterparty",
                                                        "action", "due_at")} for x in same_day],
                })
            span.output = {"similar_hits": sum(len(n["similar"]) for n in new_items),
                           "same_day_hits": sum(len(n["same_day"]) for n in new_items)}

        # 6. curator decides create / update / skip and flags conflicts
        curator_in = {"new": new_items}
        async with tracer.span(run_id, "curator", input=curator_in) as span:
            decided, backend = await lyzr.run("curator", curator_in, uid=uid, session_id=run_id)
            span.output, span.meta["backend"] = decided, backend
        decisions = {d.get("tmp_id"): d for d in decided.get("decisions", [])}

        # 6b. guardrails: verify every decision against what Qdrant actually returned
        async with tracer.span(run_id, "verify_decisions", kind="local",
                               input={"decisions": len(decisions)}) as span:
            decisions, corrections = check_decisions(new_items, decisions)
            span.output = {"corrections": corrections} if corrections else "all decisions confirmed"

        # 7. write the decisions back to Qdrant
        tmp_to_id: dict[str, str] = {}
        written: list[tuple[dict, dict]] = []
        async with tracer.span(run_id, "qdrant_write_commitments", kind="qdrant",
                               input={"decisions": len(decisions)}) as span:
            for item, c in zip(new_items, found):
                d = decisions.get(item["tmp_id"], {"action": "create"})
                private = seg_sensitivity.get(c.get("segment_idx")) == "sensitive"
                if d.get("action") == "skip":
                    summary["skipped"] += 1
                    continue
                if d.get("action") == "update" and d.get("target_id") \
                        and store.get_commitment(d["target_id"]):
                    record = store.update_commitment(
                        d["target_id"], {"due_at": item["due_at"], "action": item["action"],
                                         "quote": c.get("quote"), "status": "open"},
                        event=f"updated from conversation {conv['id']}")
                    summary["updated"].append(record)
                else:
                    record = store.add_commitment(uid, {
                        **item, "quote": c.get("quote"), "confidence": c.get("confidence"),
                        "source_conversation_id": conv["id"],
                        "visibility": "private" if private else "shared"})
                    summary["created"].append(record)
                tmp_to_id[item["tmp_id"]] = record["id"]
                written.append((record, d))
            for record, d in written:
                if d.get("conflict"):
                    ids = [tmp_to_id.get(x, x) for x in d.get("conflict_with", [])]
                    record.update(store.update_commitment(
                        record["id"], {"conflict_with": ids, "conflict_reason": d.get("reason")},
                        event="conflict flagged") or {})
                    summary["conflicts"].append(record)
            span.output = _counts(summary)

        # 8. nudges + reminders
        captured = summary["created"] + summary["updated"]
        shared = [_brief(c) for c in captured if c.get("visibility") != "private"]
        private = [_brief(c) for c in captured if c.get("visibility") == "private"]
        events = [{"type": "conflict", "commitment": _brief(c), "reason": c.get("conflict_reason"),
                   "with": [_brief(x) for x in map(store.get_commitment, c["conflict_with"]) if x]}
                  for c in summary["conflicts"] if c.get("visibility") != "private"]
        if shared:
            events.append({"type": "captured", "commitments": shared})
        await nudge(uid, events, run_id=run_id)
        if private:
            await nudge(uid, [{"type": "captured", "commitments": private}], run_id=run_id,
                        private=True)
        for c in captured:
            schedule_reminders(uid, c)

        tracer.run_end(run_id, "ok", **_counts(summary))
        return summary
    except Exception as exc:
        tracer.run_end(run_id, "error", error=str(exc))
        raise


def _counts(summary: dict) -> dict:
    return {"created": len(summary["created"]), "updated": len(summary["updated"]),
            "skipped": summary["skipped"], "conflicts": len(summary["conflicts"])}
