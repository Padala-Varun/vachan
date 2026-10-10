"""Deterministic privacy pre-pass.

Runs locally before any text leaves the machine: masks structured PII and
drops everything said "off the record". The Privacy Guard agent then handles
the fuzzy cases (health, finance, third-party secrets).
"""
import re
from collections import Counter

PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("AADHAAR", re.compile(r"\b\d{4}[ -]\d{4}[ -]\d{4}\b")),
    ("PHONE", re.compile(r"(?:\+?91[ -]?)?\b[6-9]\d{4}[ -]?\d{5}\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("OTP", re.compile(r"\b(?:otp|pin|password|passcode)\b\W*(?:is\s*)?\w+", re.I)),
]

OFF_RECORD = re.compile(r"\boff\s+the\s+record\b", re.I)
ON_RECORD = re.compile(r"\b(?:back\s+on\s+(?:the\s+)?record|on\s+the\s+record\s+again)\b", re.I)


def mask_pii(text: str, counts: Counter | None = None) -> str:
    for label, pattern in PII_PATTERNS:
        def _sub(match: re.Match, label: str = label) -> str:
            if counts is not None:
                counts[label] += 1
            return f"[{label}]"

        text = pattern.sub(_sub, text)
    return text


def apply_off_record(segments: list[dict]) -> tuple[list[dict], int]:
    """Remove speech between "off the record" and "back on the record".

    Text before the trigger phrase in the same segment is kept, as is text
    after the resume phrase. Returns the kept segments and how many segments
    were touched by the off-record window.
    """
    kept: list[dict] = []
    off = False
    touched = 0
    for seg in segments:
        text = seg["text"]
        pieces: list[str] = []
        pos = 0
        seg_touched = off
        while pos <= len(text):
            if not off:
                m = OFF_RECORD.search(text, pos)
                if not m:
                    pieces.append(text[pos:])
                    break
                pieces.append(text[pos:m.start()])
                off, seg_touched, pos = True, True, m.end()
            else:
                m = ON_RECORD.search(text, pos)
                if not m:
                    break
                off, pos = False, m.end()
        if seg_touched:
            touched += 1
        cleaned = " ".join(p.strip(" ,.") for p in pieces if p.strip(" ,.")).strip()
        if cleaned:
            kept.append({**seg, "text": cleaned})
    return kept, touched


def prepass(segments: list[dict]) -> tuple[list[dict], dict]:
    kept, off_record = apply_off_record(segments)
    counts: Counter = Counter()
    masked = [{**seg, "text": mask_pii(seg["text"], counts)} for seg in kept]
    report = {"pii_masked": dict(counts), "off_record_segments": off_record}
    return masked, report
