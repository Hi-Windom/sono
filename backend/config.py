import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "storage", "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "storage", "outputs")
TRAINING_DIR = os.path.join(BASE_DIR, "storage", "training")
DECODED_DIR = os.path.join(BASE_DIR, "storage", "decoded")
DB_PATH = os.path.join(BASE_DIR, "storage", "tasks.db")
DEPLOY_TIME_FILE = os.path.join(BASE_DIR, "storage", "deploy_time")


def _safe_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        logger.warning(
            f"环境变量 {name} 值 '{raw}' 不是有效整数，使用默认值 {default}"
        )
        return default


HOST = os.getenv("HOST", "0.0.0.0")
PORT = _safe_int_env("PORT", 8000)
MAX_UPLOAD_SIZE = 1 * 1024 * 1024 * 1024

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a", ".wma"}

MAX_WORKERS = _safe_int_env("MAX_WORKERS", 4)
_default_concurrent = max(1, MAX_WORKERS - 1)
MAX_CONCURRENT_TASKS = _safe_int_env("MAX_CONCURRENT_TASKS", _default_concurrent)

SOURCE_FILE_CACHE_LIMIT = _safe_int_env("SOURCE_FILE_CACHE_LIMIT", 1024 * 1024 * 1024)

MOBILE_MODE = os.getenv("MOBILE_MODE", "").lower() in ("1", "true", "yes")

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-key-change-in-production")


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
