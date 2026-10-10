"""Send Omi-shaped webhooks to a running Vachan backend, no Omi device needed.

Examples
  python scripts/simulate_omi.py fixtures/01_pitch_deck.json
  python scripts/simulate_omi.py fixtures/*.json --delay 8
  python scripts/simulate_omi.py --say "Hey Vachan, what do I owe Rahul this week?"

Conversation fixtures get a fresh `started_at` (now) so deadlines like
"Thursday" resolve relative to the moment you run the demo.
"""
import argparse
import glob
import json
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx

IST = timezone(timedelta(hours=5, minutes=30))


def send_conversation(client: httpx.Client, base: str, uid: str, path: str) -> None:
    with open(path, encoding="utf-8") as fh:
        body = json.load(fh)
    started = datetime.now(IST)
    body.setdefault("id", str(uuid.uuid4()))
    body["id"] = f"{body['id']}-{uuid.uuid4().hex[:6]}"
    body["started_at"] = started.isoformat()
    body["created_at"] = started.isoformat()
    last = max((s.get("end") or 0 for s in body.get("transcript_segments", [])), default=0)
    body["finished_at"] = (started + timedelta(seconds=last)).isoformat()
    resp = client.post(f"{base}/omi/conversation", params={"uid": uid}, json=body)
    title = body.get("structured", {}).get("title", path)
    print(f"-> conversation  {title!r:45} {resp.status_code} {resp.text}")


def send_realtime(client: httpx.Client, base: str, uid: str, text: str) -> None:
    session = f"sim-{uuid.uuid4().hex[:8]}"
    words = text.split()
    # Omi streams speech in small batches; split the utterance in two to mimic that.
    half = max(1, len(words) // 2)
    t = 0.0
    for chunk in (" ".join(words[:half]), " ".join(words[half:])):
        if not chunk:
            continue
        seg = {"text": chunk, "speaker": "SPEAKER_00", "speakerId": 0, "is_user": True,
               "start": t, "end": t + 1.5}
        t += 1.6
        resp = client.post(f"{base}/omi/realtime", params={"uid": uid, "session_id": session},
                           json=[seg])
        print(f"-> realtime      {chunk!r:45} {resp.status_code} {resp.text}")
        time.sleep(0.4)
    print("  (the command runs after a short pause; watch the dashboard / phone)")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fixtures", nargs="*", help="conversation JSON files (globs ok)")
    parser.add_argument("--say", help="simulate a spoken 'Hey Vachan ...' command")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--uid", default="demo-user")
    parser.add_argument("--delay", type=float, default=3.0, help="seconds between conversations")
    args = parser.parse_args()

    files = [f for pattern in args.fixtures for f in sorted(glob.glob(pattern))]
    if not files and not args.say:
        parser.print_help()
        return 1
    with httpx.Client(timeout=30) as client:
        for i, path in enumerate(files):
            if i:
                time.sleep(args.delay)
            send_conversation(client, args.url.rstrip("/"), args.uid, path)
        if args.say:
            if files:
                time.sleep(args.delay)
            send_realtime(client, args.url.rstrip("/"), args.uid, args.say)
    return 0


if __name__ == "__main__":
    sys.exit(main())
