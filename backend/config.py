import os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "storage", "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "storage", "outputs")
TRAINING_DIR = os.path.join(BASE_DIR, "storage", "training")
DECODED_DIR = os.path.join(BASE_DIR, "storage", "decoded")
DB_PATH = os.path.join(BASE_DIR, "storage", "tasks.db")
DEPLOY_TIME_FILE = os.path.join(BASE_DIR, "storage", "deploy_time")

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
MAX_UPLOAD_SIZE = 1 * 1024 * 1024 * 1024

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a", ".wma"}

MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))
MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", str(max(1, MAX_WORKERS - 1))))

SOURCE_FILE_CACHE_LIMIT = int(os.getenv("SOURCE_FILE_CACHE_LIMIT", str(1024 * 1024 * 1024)))

MOBILE_MODE = os.getenv("MOBILE_MODE", "").lower() in ("1", "true", "yes")


def _init_deploy_time():
    now = datetime.now(timezone.utc).isoformat()
    if os.path.exists(DEPLOY_TIME_FILE):
        try:
            with open(DEPLOY_TIME_FILE, "r") as f:
                content = f.read().strip()
            datetime.fromisoformat(content)
            return
        except (ValueError, OSError):
            pass
    with open(DEPLOY_TIME_FILE, "w") as f:
        f.write(now)


os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TRAINING_DIR, exist_ok=True)
os.makedirs(DECODED_DIR, exist_ok=True)
_init_deploy_time()
