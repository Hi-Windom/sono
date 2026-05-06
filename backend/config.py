import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "storage", "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "storage", "outputs")
TRAINING_DIR = os.path.join(BASE_DIR, "storage", "training")  # AI训练素材独立存储路径
DB_PATH = os.path.join(BASE_DIR, "storage", "tasks.db")

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
MAX_UPLOAD_SIZE = 200 * 1024 * 1024

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a", ".wma"}

MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))  # 增加线程数避免检测任务阻塞

SOURCE_FILE_CACHE_LIMIT = int(os.getenv("SOURCE_FILE_CACHE_LIMIT", str(1024 * 1024 * 1024)))

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TRAINING_DIR, exist_ok=True)  # 创建训练素材目录
