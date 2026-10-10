"""Qdrant memory layer: the single source of truth for Vachan.

Collections
- transcripts: redacted conversation chunks (semantic + time-range recall)
- commitments: every promise made or received, with status/deadline payload

Embeddings are computed locally (fastembed), so raw text is never sent to an
embedding API. Points marked `visibility=private` are never included in any
prompt sent to an LLM agent.
"""
import hashlib
import json
import math
import re
import threading
import uuid
from datetime import datetime
from typing import Iterable

from qdrant_client import QdrantClient, models

from .config import settings
from .timeutil import day_bounds, now, parse_iso

# An optional prefix keeps separate data sets (e.g. a demo recording) in the same cluster.
TRANSCRIPTS = f"{settings.collection_prefix}transcripts"
COMMITMENTS = f"{settings.collection_prefix}commitments"
VECTOR_SIZE = 384

KEYWORD_FIELDS = {
    TRANSCRIPTS: ["uid", "conversation_id", "visibility", "sensitivity"],
    COMMITMENTS: ["uid", "status", "counterparty_key", "owner", "visibility",
                  "source_conversation_id"],
}
FLOAT_FIELDS = {TRANSCRIPTS: ["started_ts"], COMMITMENTS: ["due_ts", "created_ts"]}


# --------------------------------------------------------------------------- embeddings
class HashEmbedder:
    """Dependency-free bag-of-words embedder used in tests and offline fallback."""

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * VECTOR_SIZE
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vec[h % VECTOR_SIZE] += 1.0 if (h >> 9) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class FastEmbedder:
    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding

        self.model = TextEmbedding(model_name=model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self.model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self.model.query_embed(text))).tolist()


# --------------------------------------------------------------------------- store
class MemoryStore:
    def __init__(self, client: QdrantClient | None = None, embedder=None) -> None:
        self._lock = threading.RLock()
        self.client = client or self._make_client()
        self.embedder = embedder or self._make_embedder()
        self.mode = "cloud" if settings.qdrant_url else "local"
        self.audit_file = settings.data_dir / "audit.jsonl"
        self.ensure_collections()

    @staticmethod
    def _make_client() -> QdrantClient:
        if settings.qdrant_url:
            return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        return QdrantClient(path=settings.qdrant_path)

    @staticmethod
    def _make_embedder():
        if settings.embedder == "hash":
            return HashEmbedder()
        try:
            return FastEmbedder(settings.embed_model)
        except Exception as exc:  # pragma: no cover - depends on model download
            print(f"[memory] fastembed unavailable ({exc}); falling back to hash embedder")
            return HashEmbedder()

    def ensure_collections(self) -> None:
        with self._lock:
            for name in (TRANSCRIPTS, COMMITMENTS):
                if not self.client.collection_exists(name):
                    self.client.create_collection(
                        name,
                        vectors_config=models.VectorParams(size=VECTOR_SIZE,
                                                           distance=models.Distance.COSINE),
                    )
                if self.mode == "cloud":
                    for field in KEYWORD_FIELDS[name]:
                        self.client.create_payload_index(name, field, models.PayloadSchemaType.KEYWORD)
                    for field in FLOAT_FIELDS[name]:
                        self.client.create_payload_index(name, field, models.PayloadSchemaType.FLOAT)

    def reset(self) -> None:
        with self._lock:
            for name in (TRANSCRIPTS, COMMITMENTS):
                if self.client.collection_exists(name):
                    self.client.delete_collection(name)
        self.ensure_collections()

    # ------------------------------------------------------------------ filters
    @staticmethod
    def _filter(uid: str, *, status: str | Iterable[str] | None = None,
                counterparty: str | None = None, visibility: str | None = None,
                time_field: str | None = None, time_from: datetime | None = None,
                time_to: datetime | None = None, extra: list | None = None) -> models.Filter:
        must: list = [models.FieldCondition(key="uid", match=models.MatchValue(value=uid))]
        if status:
            values = [status] if isinstance(status, str) else list(status)
            must.append(models.FieldCondition(key="status", match=models.MatchAny(any=values)))
        if counterparty:
            must.append(models.FieldCondition(key="counterparty_key",
                                              match=models.MatchValue(value=counterparty.lower())))
        if visibility:
            must.append(models.FieldCondition(key="visibility",
                                              match=models.MatchValue(value=visibility)))
        if time_field and (time_from or time_to):
            must.append(models.FieldCondition(key=time_field, range=models.Range(
                gte=time_from.timestamp() if time_from else None,
                lt=time_to.timestamp() if time_to else None)))
        return models.Filter(must=must + (extra or []))

    @staticmethod
    def _record(point) -> dict:
        record = dict(point.payload or {})
        record["id"] = str(point.id)
        if getattr(point, "score", None) is not None:
            record["score"] = round(point.score, 4)
        return record

    # ------------------------------------------------------------------ transcripts
    def add_transcript_chunks(self, uid: str, conversation_id: str, started_at: datetime,
                              chunks: list[dict]) -> list[str]:
        """chunks: [{text, speakers, sensitivity, segment_range}]"""
        if not chunks:
            return []
        vectors = self.embedder.embed([c["text"] for c in chunks])
        ids, points = [], []
        for chunk, vector in zip(chunks, vectors):
            pid = str(uuid.uuid4())
            ids.append(pid)
            sensitivity = chunk.get("sensitivity", "public")
            points.append(models.PointStruct(id=pid, vector=vector, payload={
                "uid": uid,
                "conversation_id": conversation_id,
                "text": chunk["text"],
                "speakers": chunk.get("speakers", []),
                "segment_range": chunk.get("segment_range"),
                "sensitivity": sensitivity,
                "visibility": "private" if sensitivity == "sensitive" else "shared",
                "started_at": started_at.isoformat(),
                "started_ts": started_at.timestamp(),
            }))
        with self._lock:
            self.client.upsert(TRANSCRIPTS, points=points)
        return ids

    def search_transcripts(self, uid: str, query: str, *, limit: int = 5,
                           shared_only: bool = False, time_from: datetime | None = None,
                           time_to: datetime | None = None) -> list[dict]:
        flt = self._filter(uid, visibility="shared" if shared_only else None,
                           time_field="started_ts", time_from=time_from, time_to=time_to)
        with self._lock:
            res = self.client.query_points(TRANSCRIPTS, query=self.embedder.embed_query(query),
                                           query_filter=flt, limit=limit, with_payload=True)
        return [self._record(p) for p in res.points]

    def list_transcripts(self, uid: str, limit: int = 200) -> list[dict]:
        with self._lock:
            points, _ = self.client.scroll(TRANSCRIPTS, scroll_filter=self._filter(uid),
                                           limit=limit, with_payload=True)
        records = [self._record(p) for p in points]
        return sorted(records, key=lambda r: r.get("started_ts", 0), reverse=True)

    # ------------------------------------------------------------------ commitments
    @staticmethod
    def commitment_text(c: dict) -> str:
        """Text embedded for a commitment; also used as the query when deduplicating."""
        who = "I promised" if c.get("owner") == "me" else "promised to me by"
        return f"{c.get('action', '')} — {who} {c.get('counterparty') or 'someone'}"

    def add_commitment(self, uid: str, data: dict) -> dict:
        due = parse_iso(data.get("due_at"))
        created = now()
        counterparty = (data.get("counterparty") or "").strip()
        payload = {
            "uid": uid,
            "owner": data.get("owner", "me"),
            "counterparty": counterparty or None,
            "counterparty_key": counterparty.lower() or None,
            "action": data["action"].strip(),
            "due_at": due.isoformat() if due else None,
            "due_ts": due.timestamp() if due else None,
            "status": data.get("status", "open"),
            "visibility": data.get("visibility", "shared"),
            "quote": data.get("quote"),
            "confidence": data.get("confidence"),
            "source_conversation_id": data.get("source_conversation_id"),
            "conflict_with": data.get("conflict_with", []),
            "conflict_reason": data.get("conflict_reason"),
            "history": [{"at": created.isoformat(), "event": "created"}],
            "created_at": created.isoformat(),
            "created_ts": created.timestamp(),
        }
        pid = str(uuid.uuid4())
        vector = self.embedder.embed([self.commitment_text(payload)])[0]
        with self._lock:
            self.client.upsert(COMMITMENTS, points=[models.PointStruct(id=pid, vector=vector,
                                                                       payload=payload)])
        return {**payload, "id": pid}

    def get_commitment(self, cid: str) -> dict | None:
        with self._lock:
            points = self.client.retrieve(COMMITMENTS, ids=[cid], with_payload=True)
        return self._record(points[0]) if points else None

    def update_commitment(self, cid: str, fields: dict, event: str | None = None) -> dict | None:
        current = self.get_commitment(cid)
        if current is None:
            return None
        fields = dict(fields)
        if "due_at" in fields:
            due = parse_iso(fields["due_at"])
            fields["due_at"] = due.isoformat() if due else None
            fields["due_ts"] = due.timestamp() if due else None
        if event:
            fields["history"] = current.get("history", []) + [{"at": now().isoformat(),
                                                               "event": event}]
        with self._lock:
            self.client.set_payload(COMMITMENTS, payload=fields, points=[cid])
        return {**current, **fields}

    def search_commitments(self, uid: str, query: str, *, limit: int = 5,
                           status: str | Iterable[str] | None = None,
                           counterparty: str | None = None, shared_only: bool = False,
                           due_from: datetime | None = None,
                           due_to: datetime | None = None) -> list[dict]:
        flt = self._filter(uid, status=status, counterparty=counterparty,
                           visibility="shared" if shared_only else None,
                           time_field="due_ts", time_from=due_from, time_to=due_to)
        with self._lock:
            res = self.client.query_points(COMMITMENTS, query=self.embedder.embed_query(query),
                                           query_filter=flt, limit=limit, with_payload=True)
        return [self._record(p) for p in res.points]

    def list_commitments(self, uid: str, *, status: str | Iterable[str] | None = None,
                         counterparty: str | None = None, due_from: datetime | None = None,
                         due_to: datetime | None = None, limit: int = 500) -> list[dict]:
        flt = self._filter(uid, status=status, counterparty=counterparty,
                           time_field="due_ts", time_from=due_from, time_to=due_to)
        with self._lock:
            points, _ = self.client.scroll(COMMITMENTS, scroll_filter=flt, limit=limit,
                                           with_payload=True)
        records = [self._record(p) for p in points]
        return sorted(records, key=lambda r: (r.get("due_ts") is None, r.get("due_ts") or 0))

    def same_day_commitments(self, uid: str, due: datetime) -> list[dict]:
        start, end = day_bounds(due)
        return self.list_commitments(uid, status="open", due_from=start, due_to=end)

    def counterparties(self, uid: str) -> list[str]:
        names = {c["counterparty"] for c in self.list_commitments(uid) if c.get("counterparty")}
        return sorted(names)

    # ------------------------------------------------------------------ privacy controls
    def set_visibility(self, collection: str, pid: str, visibility: str) -> None:
        with self._lock:
            self.client.set_payload(collection, payload={"visibility": visibility}, points=[pid])
        self.audit("visibility", {"collection": collection, "id": pid, "visibility": visibility})

    def delete_points(self, collection: str, ids: list[str], reason: str) -> None:
        if not ids:
            return
        with self._lock:
            self.client.delete(collection, points_selector=models.PointIdsList(points=ids))
        self.audit("delete", {"collection": collection, "ids": ids, "reason": reason})

    # Calibrated on bge-small: unrelated memories score 0.50-0.65 against a query, so a
    # hit must clear FORGET_MIN_SCORE *and* be close to the best hit in its collection.
    FORGET_MIN_SCORE = 0.65
    FORGET_MARGIN = 0.05

    def forget(self, uid: str, query: str, *, limit: int = 10) -> dict:
        """Semantic delete: remove the memories that clearly match `query`."""
        vector = self.embedder.embed_query(query)
        removed: dict[str, list[dict]] = {}
        for collection in (TRANSCRIPTS, COMMITMENTS):
            with self._lock:
                res = self.client.query_points(collection, query=vector,
                                               query_filter=self._filter(uid), limit=limit,
                                               with_payload=True,
                                               score_threshold=self.FORGET_MIN_SCORE)
            hits = [self._record(p) for p in res.points]
            if hits:
                floor = hits[0]["score"] - self.FORGET_MARGIN
                hits = [h for h in hits if h["score"] >= floor]
            self.delete_points(collection, [h["id"] for h in hits], reason=f"forget: {query}")
            removed[collection] = [{"id": h["id"], "score": h.get("score"),
                                    "text": h.get("text") or h.get("action")} for h in hits]
        return removed

    def audit(self, action: str, details: dict) -> None:
        entry = {"at": now().isoformat(), "action": action, **details}
        self.audit_file.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def audit_log(self, limit: int = 100) -> list[dict]:
        if not self.audit_file.exists():
            return []
        lines = self.audit_file.read_text(encoding="utf-8").splitlines()[-limit:]
        return [json.loads(line) for line in reversed(lines) if line.strip()]

    def stats(self, uid: str) -> dict:
        with self._lock:
            return {
                "transcripts": self.client.count(TRANSCRIPTS, count_filter=self._filter(uid)).count,
                "commitments": self.client.count(COMMITMENTS, count_filter=self._filter(uid)).count,
            }


_store: MemoryStore | None = None


def get_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store


def set_store(store: MemoryStore) -> None:
    global _store
    _store = store
