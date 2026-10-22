"""قراءة الطابور والحالة والتحقق من الصحة."""
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml

import accounts as _acc
from config import (BRAND_PATH, CAROUSEL_STYLES, INFOGRAPHIC_STYLES, REEL_STYLES, TOPICS_PATH, LIMITS, PLATFORMS, QUEUE_PATH,
                    STATE_PATH, TEMPLATES, TIMEZONE)

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


def load_topic_ids() -> set[str]:
    if not TOPICS_PATH.exists():
        return set()
    data = yaml.safe_load(TOPICS_PATH.read_text(encoding="utf-8")) or {}
    return {str(t["id"]) for t in (data.get("topics") or []) if isinstance(t, dict) and t.get("id")}


def validate(queue: list[dict]) -> list[str]:
    """يرجع قائمة بالأخطاء (فارغة = سليم)."""
    errors: list[str] = []
    if not isinstance(queue, list):
        return ["queue.yaml يجب أن يكون قائمة منشورات"]
    seen = set()
    topic_ids = load_topic_ids()
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
        if isinstance(img, dict) and img.get("hue") is not None and not (isinstance(img["hue"], int) and 0 <= img["hue"] < 360):
            errors.append(f"{tag} image.hue يجب أن يكون عدداً بين 0 و359")
        if not isinstance(img, dict) or not img.get("title"):
            errors.append(f"{tag} image.title مطلوب")
        elif p.get("template") == "infographic" and str(img.get("style", "") or "").strip() and str(img["style"]).strip().lower() not in INFOGRAPHIC_STYLES:
            errors.append(f"{tag} نمط إنفوجرافك غير معروف: {img['style']} (المتاح: {', '.join(INFOGRAPHIC_STYLES)})")
        elif p.get("template") == "carousel":
            sl = img.get("slides")
            style = str(img.get("style", "") or "").strip()
            if style and style.lower() not in CAROUSEL_STYLES:
                errors.append(f"{tag} نمط كاروسيل غير معروف: {style} (المتاح: {', '.join(CAROUSEL_STYLES)})")
            if not (isinstance(sl, list) and 3 <= len(sl) <= 10):
                errors.append(f"{tag} الكاروسيل يحتاج image.slides من 3 إلى 10 شرائح")
            else:
                for n, s_ in enumerate(sl, 1):
                    if not (isinstance(s_, dict) and str(s_.get("title", "")).strip()):
                        errors.append(f"{tag} الشريحة {n} بلا عنوان")
                    elif len(str(s_["title"])) > 120 or len(str(s_.get("body", ""))) > 260:
                        errors.append(f"{tag} الشريحة {n}: العنوان أو النص أطول من المسموح")
                    elif len(s_.get("points") or []) > 5:
                        errors.append(f"{tag} الشريحة {n}: أكثر من 5 نقاط")
        elif p.get("template") == "reel" and str(img.get("style", "") or "").strip() and str(img["style"]).strip().lower() not in REEL_STYLES:
            errors.append(f"{tag} نمط ريل غير معروف: {img['style']} (المتاح: {', '.join(REEL_STYLES)})")
        elif p.get("template") == "reel":
            sc = img.get("scenes")
            if not (isinstance(sc, list) and 3 <= len(sc) <= 8):
                errors.append(f"{tag} الريل يحتاج image.scenes من 3 إلى 8 مشاهد")
            else:
                for n, s_ in enumerate(sc, 1):
                    if not (isinstance(s_, dict) and str(s_.get("title", "")).strip()):
                        errors.append(f"{tag} المشهد {n} بلا عنوان")
                    elif len(str(s_["title"])) > 70 or len(str(s_.get("body", ""))) > 150:
                        errors.append(f"{tag} المشهد {n}: العنوان أطول من 70 حرفاً أو النص من 150 "
                                      f"(الفيديو يُقرأ في ثوانٍ، فالنص القصير شرط لا تحسين)")
                    elif not (1.5 <= float(s_.get("seconds") or 3.6) <= 8):
                        errors.append(f"{tag} المشهد {n}: مدّة خارج المدى المسموح (1.5 إلى 8 ثوانٍ)")
        elif p.get("template") == "infographic":
            pts = img.get("points")
            if not (isinstance(pts, list) and 2 <= len(pts) <= 6 and all(isinstance(x, str) and x.strip() for x in pts)):
                errors.append(f"{tag} قالب infographic يحتاج image.points من 2 إلى 6 نقاط نصية")
            elif any(len(x) > 90 for x in pts):
                errors.append(f"{tag} نقطة في image.points أطول من 90 حرفاً")
        elif not (img.get("visual_prompt") or img.get("photo_query")):
            errors.append(f"{tag} image.visual_prompt مفقود (سيُستعمل خلفية متدرجة فقط)")
        if topic_ids and p.get("topic") not in topic_ids:
            # المسودة لا توقف النشر؛ أما المنشور المعتمد خارج القائمة فيُرفض
            note = "" if p.get("approved") is True else " (مسودة)"
            errors.append(f"{tag} الموضوع «{p.get('topic')}» خارج القائمة المسموحة في topics.yaml ({', '.join(sorted(topic_ids))}){note}")
        plats = p.get("platforms")
        if not isinstance(plats, dict) or not plats:
            errors.append(f"{tag} platforms فارغة")
            continue
        tg = p.get("targets")
        if tg is not None:
            known = _acc.load_accounts()
            if not isinstance(tg, dict):
                errors.append(f"{tag} targets يجب أن تكون قاموساً (منصة ← قائمة حسابات)")
            else:
                for plat, ids in tg.items():
                    for i in (ids or []):
                        if i not in known:
                            errors.append(f"{tag} حساب غير معروف في targets: {i} (انظر content/accounts.yaml)")
                        elif known[i].platform != plat:
                            errors.append(f"{tag} الحساب {i} ليس لمنصة {plat}")
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
    return [e for e in errors if "visual_prompt مفقود" not in e and not e.endswith("(مسودة)")]
