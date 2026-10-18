"""قراءة الطابور والحالة والتحقق من الصحة."""
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml

from config import (BRAND_PATH, LIMITS, PLATFORMS, QUEUE_PATH, STATE_PATH,
                    TEMPLATES, TIMEZONE)

TZ = ZoneInfo(TIMEZONE)


class QueueError(Exception):
    pass


def load_brand() -> dict:
    return yaml.safe_load(BRAND_PATH.read_text(encoding="utf-8"))


def load_queue(path=QUEUE_PATH) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else []
    return data or []


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8") or "{}")
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")


def parse_when(value) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.strptime(str(value).strip(), "%Y-%m-%d %H:%M")
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)


def now_local() -> datetime:
    return datetime.now(TZ)


def validate(queue: list[dict]) -> list[str]:
    """يرجع قائمة بالأخطاء (فارغة = سليم)."""
    errors: list[str] = []
    if not isinstance(queue, list):
        return ["queue.yaml يجب أن يكون قائمة منشورات"]
    seen = set()
    for i, p in enumerate(queue):
        tag = f"[#{i + 1} {p.get('id', '؟') if isinstance(p, dict) else '؟'}]"
        if not isinstance(p, dict):
            errors.append(f"{tag} العنصر ليس كائناً")
            continue
        pid = p.get("id")
        if not pid or not re.fullmatch(r"[\w\-]+", str(pid)):
            errors.append(f"{tag} id مفقود أو يحوي رموزاً غير مسموحة")
        elif pid in seen:
            errors.append(f"{tag} id مكرر")
        seen.add(pid)
        if not isinstance(p.get("approved"), bool):
            errors.append(f"{tag} approved يجب أن تكون true/false")
        try:
            parse_when(p.get("publish_at"))
        except Exception:
            errors.append(f"{tag} publish_at بصيغة خاطئة (المطلوب: YYYY-MM-DD HH:MM)")
        if p.get("template") not in TEMPLATES:
            errors.append(f"{tag} قالب غير صالح: {p.get('template')} (المتاح: {', '.join(TEMPLATES)})")
        img = p.get("image")
        if not isinstance(img, dict) or not img.get("title"):
            errors.append(f"{tag} image.title مطلوب")
        elif not img.get("visual_prompt"):
            errors.append(f"{tag} image.visual_prompt مفقود (سيُستعمل خلفية متدرجة فقط)")
        plats = p.get("platforms")
        if not isinstance(plats, dict) or not plats:
            errors.append(f"{tag} platforms فارغة")
            continue
        for name, text in plats.items():
            if name not in PLATFORMS:
                errors.append(f"{tag} منصة غير معروفة: {name}")
            elif not isinstance(text, str) or not text.strip():
                errors.append(f"{tag} نص {name} فارغ")
            elif len(text) > LIMITS[name]:
                errors.append(f"{tag} نص {name} {len(text)} حرفاً > الحد {LIMITS[name]}")
    # التحذير بشأن visual_prompt ليس فشلاً قاطعاً
    return errors


def fatal(errors: list[str]) -> list[str]:
    return [e for e in errors if "visual_prompt مفقود" not in e]
