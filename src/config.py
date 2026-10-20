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
    "carousel": (1080, 1350),
    "reel": (1080, 1920),       # فيديو عمودي
}

# أنماط الكاروسيل: لكلٍّ لغة بصرية مختلفة بنيوياً لا لوناً فقط.
# بلا صور: blueprint مخطط هندسي · editorial مجلّة · terminal نافذة كود
#          poster ملصق لوني · sticky ورقة ملصقة · duo لوحان بشريط جانبي
CAROUSEL_STYLES_FLAT = ("blueprint", "editorial", "terminal", "poster", "sticky", "duo")
# بصور حقيقية: magazine غلاف مجلّة · polaroid صورة فورية · collage قصاصات
#              duotone صورة بلونين · window بطاقة بنافذة · filmstrip شريط فيلم
CAROUSEL_STYLES_PHOTO = ("magazine", "polaroid", "collage", "duotone", "window", "filmstrip")
CAROUSEL_STYLES = CAROUSEL_STYLES_FLAT + CAROUSEL_STYLES_PHOTO

PLATFORMS = ("facebook", "instagram", "threads", "linkedin", "telegram")
LIMITS = {"threads": 500, "instagram": 2200, "facebook": 63000, "telegram": 4096,
          "linkedin": 3000}
