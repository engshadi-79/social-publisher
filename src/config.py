"""إعدادات مركزية للمشروع."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TIMEZONE = "Asia/Hebron"
GRAPH_VERSION = "v21.0"          # نسخة Graph API (فيسبوك/إنستغرام) — تُغيَّر هنا فقط
THREADS_VERSION = "v1.0"
MAX_ATTEMPTS = 3
PLATFORM_DELAY_SEC = 5           # فاصل بين المنصات

QUEUE_PATH = ROOT / "content" / "queue.yaml"
STATE_PATH = ROOT / "content" / "state.json"
MEDIA_DIR = ROOT / "content" / "media"
TOPICS_PATH = ROOT / "content" / "topics.yaml"
BRAND_PATH = ROOT / "brand" / "brand.yaml"
TEMPLATES_DIR = ROOT / "templates"
OUT_DIR = ROOT / "out"

# اسم القالب -> (العرض، الارتفاع)
TEMPLATES = {
    "quote": (1080, 1080),
    "announcement": (1080, 1350),
    "tip": (1080, 1350),
    "story": (1080, 1920),
    "split": (1080, 1350),
    "photo": (1080, 1350),
    "infographic": (1080, 1350),
}

PLATFORMS = ("facebook", "instagram", "threads", "telegram")
LIMITS = {"threads": 500, "instagram": 2200, "facebook": 63000, "telegram": 4096}
