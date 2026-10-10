"""Deploy the Vachan API to Modal.

    cd backend
    modal deploy modal_app.py

Runs as exactly ONE always-warm container: the wake-phrase listener, the
reminder scheduler and the live trace stream keep state in memory, so every
request must reach the same process. Promises and memories live in Qdrant
Cloud; the audit log and traces persist on a Modal Volume.

Secrets come from backend/.env at deploy time (Secret.from_dotenv), so keys
are never committed.
"""
from pathlib import Path

import modal

BACKEND = Path(__file__).resolve().parent
REPO = BACKEND.parent

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements(str(BACKEND / "requirements.txt"))
    .env({"FASTEMBED_CACHE_PATH": "/models", "VACHAN_DATA_DIR": "/data",
          "VACHAN_FIXTURES_DIR": "/root/fixtures", "VACHAN_EMBEDDER": "fastembed",
          "VACHAN_FRONTEND_DIST": "/root/frontend/dist"})
    # bake the embedding model into the image so cold starts never download it
    .run_commands('python -c "from fastembed import TextEmbedding; TextEmbedding(\'BAAI/bge-small-en-v1.5\')"')
    .add_local_dir(str(REPO / "fixtures"), "/root/fixtures")
    # the built dashboard (npm run build), served from the same URL as the API
    .add_local_dir(str(REPO / "frontend" / "dist"), "/root/frontend/dist")
    .add_local_python_source("app")
)

data = modal.Volume.from_name("vachan-data", create_if_missing=True)
app = modal.App("vachan")


@app.function(
    image=image,
    secrets=[modal.Secret.from_dotenv(BACKEND)],
    volumes={"/data": data},
    min_containers=1,       # always warm: Omi webhooks and reminders never hit a cold start
    max_containers=1,       # single process: in-memory state stays consistent
    cpu=1.0,
    memory=1024,
    timeout=24 * 60 * 60,
)
@modal.concurrent(max_inputs=100)
@modal.asgi_app(label="vachan-api")
def api():
    from app.main import app as fastapi_app

    return fastapi_app
