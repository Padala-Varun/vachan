"""Check every Lyzr agent configured in backend/.env with a realistic sample.

Run from the repo root:
  backend\\.venv\\Scripts\\python scripts/check_lyzr.py            (all agents)
  backend\\.venv\\Scripts\\python scripts/check_lyzr.py extractor  (one agent)
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import AGENT_NAMES, settings  # noqa: E402
from app.grounding import calendar, ground_commitments  # noqa: E402
from app.timeutil import add_when, parse_iso  # noqa: E402
from app.lyzr_client import AgentError, LyzrClient, extract_json, validate_reply  # noqa: E402

NOW = "2026-10-12T09:30:00+05:30"
SAMPLES = {
    "privacy_guard": {"segments": [
        {"idx": 0, "speaker": "You", "is_user": True, "text": "Thanks Arjun, I'll pay back the 20,000 rupee loan by Friday."},
        {"idx": 1, "speaker": "Arjun", "is_user": False, "text": "Is your dad's new blood pressure medicine helping?"},
    ]},
    "extractor": {"conversation_started_at": NOW, "timezone": "+05:30",
                  "calendar": calendar(parse_iso(NOW)), "segments": [
        {"idx": 0, "speaker": "You", "is_user": True, "text": "Thanks Rahul. I'll send you the updated pitch deck by Thursday evening."},
        {"idx": 1, "speaker": "Rahul", "is_user": False, "text": "Perfect. I'll share the investor list with you tomorrow morning."},
    ]},
    "curator": {"new": [{
        "tmp_id": "new-0", "owner": "me", "counterparty": "Priya", "action": "Review Priya's PR",
        "due_at": "2026-10-15T18:00:00+05:30", "similar": [],
        "same_day": [{"id": "c1", "owner": "me", "counterparty": "Rahul",
                      "action": "Send Rahul the pitch deck", "due_at": "2026-10-15T18:00:00+05:30"}]}]},
    "nudger": {"now": NOW, "events": [{"type": "captured", "commitments": [
        {"owner": "me", "counterparty": "Rahul", "action": "Send Rahul the pitch deck",
         "due_at": "2026-10-15T18:00:00+05:30", "status": "open"}]}]},
    "router": {"command": "what do I owe Rahul this week?", "now": NOW, "known_people": ["Rahul", "Priya"]},
    "recall": {"question": "what do I owe Rahul this week?", "now": NOW, "conversations": [],
               "commitments": [{"owner": "me", "counterparty": "Rahul", "action": "Send Rahul the pitch deck",
                                "due_at": "2026-10-15T18:00:00+05:30", "status": "open"}]},
}


SAMPLES["nudger"] = add_when(SAMPLES["nudger"])
SAMPLES["recall"] = add_when(SAMPLES["recall"])


async def check(client: LyzrClient, agent: str) -> bool:
    if not settings.lyzr_agent_ids.get(agent):
        print(f"  SKIP  {agent:14} no LYZR_{agent.upper()}_AGENT_ID in backend/.env")
        return True
    started = time.time()
    try:
        raw = await client._call_lyzr(agent, json.dumps(SAMPLES[agent]), "vachan-check", "check")
        result = validate_reply(agent, extract_json(raw))
    except (AgentError, Exception) as exc:  # noqa: BLE001 - report anything
        print(f"  FAIL  {agent:14} {exc}")
        if "raw" in locals():
            print(f"        reply was: {raw[:300]}")
        return False
    print(f"  PASS  {agent:14} {time.time() - started:4.1f}s  {json.dumps(result, ensure_ascii=False)[:160]}")
    if agent == "extractor":
        sample = SAMPLES["extractor"]
        _, fixes = ground_commitments(result["commitments"], sample["segments"], parse_iso(NOW))
        for c in result["commitments"]:
            print(f"        {c['owner']:5} {str(c.get('counterparty')):6} {c['action'][:40]:40} {c.get('due_at')}")
        for f in fixes:
            print(f"        corrected {f['field']}: agent said {f['agent']} -> {f['verified']}")
        print("        expected: deck -> 2026-10-15T18:00, investor list (Rahul) -> 2026-10-13T10:00")
    return True


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not settings.lyzr_api_key:
        print("LYZR_API_KEY is empty in backend/.env")
        return 1
    agents = sys.argv[1:] or list(AGENT_NAMES)
    client = LyzrClient()
    print(f"Checking {len(agents)} agent(s) at {settings.lyzr_chat_url}\n")
    results = [await check(client, a) for a in agents]
    print("\nAll good." if all(results) else "\nFix the FAIL lines above (see docs/LYZR_SETUP.md).")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
