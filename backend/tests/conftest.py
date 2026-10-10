import json
import os
import sys
import tempfile
from pathlib import Path

# Isolate tests from the developer's .env: no live Lyzr/Omi/Qdrant, no model download.
_tmp = tempfile.mkdtemp(prefix="vachan-tests-")
os.environ.update({
    "VACHAN_DATA_DIR": _tmp,
    "VACHAN_EMBEDDER": "hash",
    "LYZR_API_KEY": "",
    "QDRANT_URL": "",
    "OMI_APP_ID": "",
    "OMI_APP_SECRET": "",
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402

from app.memory import HashEmbedder, MemoryStore, set_store  # noqa: E402
from app.omi import notifier  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture()
def store():
    s = MemoryStore(client=QdrantClient(":memory:"), embedder=HashEmbedder())
    set_store(s)
    notifier.feed.clear()
    return s


@pytest.fixture()
def fixture_body():
    def load(name: str) -> dict:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return load
