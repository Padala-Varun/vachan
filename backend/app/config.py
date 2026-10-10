"""Runtime configuration, loaded from backend/.env.

Every external service is optional: a missing key switches that service into a
local mode (mock agent, embedded Qdrant, dry-run notifications) so the whole
pipeline always runs end to end.
"""
import os
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


AGENT_NAMES = ("privacy_guard", "extractor", "curator", "nudger", "router", "recall")


class Settings:
    def __init__(self) -> None:
        self.data_dir = Path(_env("VACHAN_DATA_DIR", str(BACKEND_DIR / "data")))

        # Lyzr
        self.lyzr_api_key = _env("LYZR_API_KEY")
        self.lyzr_chat_url = _env(
            "LYZR_CHAT_URL", "https://agent-prod.studio.lyzr.ai/v3/inference/chat/"
        )
        self.lyzr_agent_ids = {
            name: _env(f"LYZR_{name.upper()}_AGENT_ID") for name in AGENT_NAMES
        }
        self.lyzr_timeout = float(_env("LYZR_TIMEOUT_SECONDS", "60"))

        # Qdrant: URL -> server/cloud, otherwise embedded on-disk storage
        self.qdrant_url = _env("QDRANT_URL")
        self.qdrant_api_key = _env("QDRANT_API_KEY")
        self.qdrant_path = _env("QDRANT_PATH", str(self.data_dir / "qdrant"))
        self.collection_prefix = _env("VACHAN_COLLECTION_PREFIX")
        self.embedder = _env("VACHAN_EMBEDDER", "fastembed")  # fastembed | hash
        self.embed_model = _env("VACHAN_EMBED_MODEL", "BAAI/bge-small-en-v1.5")

        # Omi
        self.omi_app_id = _env("OMI_APP_ID")
        self.omi_app_secret = _env("OMI_APP_SECRET")
        self.omi_api_base = _env("OMI_API_BASE", "https://api.omi.me")

        # App behaviour
        self.default_uid = _env("VACHAN_DEFAULT_UID", "demo-user")
        self.tz = timezone(timedelta(minutes=int(_env("VACHAN_TZ_OFFSET_MINUTES", "330"))))
        self.wake_phrases = tuple(
            p.strip().lower()
            # speech-to-text often hears "Vachan" as "Bachan"/"Vachhan"; tune per voice
            for p in _env("VACHAN_WAKE_PHRASES",
                          "hey vachan,ok vachan,vachan,bachan,vachhan,hey promise keeper").split(",")
            if p.strip()
        )
        self.command_window_seconds = float(_env("VACHAN_COMMAND_WINDOW_SECONDS", "4"))
        self.digest_hour = int(_env("VACHAN_DIGEST_HOUR", "20"))
        self.cors_origins = [
            o.strip()
            for o in _env("VACHAN_CORS_ORIGINS", "http://localhost:5173").split(",")
            if o.strip()
        ]
        # the dashboard deployed on Vercel (production and preview URLs)
        self.cors_origin_regex = _env("VACHAN_CORS_ORIGIN_REGEX", r"https://.*\.vercel\.app")
        self.fixtures_dir = Path(_env("VACHAN_FIXTURES_DIR",
                                      str(BACKEND_DIR.parent / "fixtures")))

    def agent_is_live(self, agent: str) -> bool:
        return bool(self.lyzr_api_key and self.lyzr_agent_ids.get(agent))

    @property
    def omi_enabled(self) -> bool:
        return bool(self.omi_app_id and self.omi_app_secret)


settings = Settings()
