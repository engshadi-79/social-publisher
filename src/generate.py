"""يحوّل طلب توليد (من اللوحة) إلى مسودات في queue.yaml.

الطلب: content/generate_request.yaml
  id, count, start ("YYYY-MM-DD HH:MM"), topic_id أو topic_text, platforms (اختياري)
النتيجة: مسودات approved:false + content/generate_log.json (تُعرض في اللوحة).
"""
import json
import re
import sys
from datetime import timedelta

import yaml

import generator
from config import ROOT, QUEUE_PATH
from queue_io import fatal, load_queue, load_brand, parse_when, validate
from config import TOPICS_PATH

REQUEST = ROOT / "content" / "generate_request.yaml"
LOG = ROOT / "content" / "generate_log.json"
DEFAULT_PLATFORMS = ["facebook", "instagram", "threads"]


def load_topic(req: dict) -> dict:
    tid = req.get("topic_id")
    if tid and TOPICS_PATH.exists():
        data = yaml.safe_load(TOPICS_PATH.read_text(encoding="utf-8")) or {}
        for t in data.get("topics") or []:
            if str(t.get("id")) == str(tid):
                return t
        raise generator.GeneratorError(f"الموضوع {tid} غير موجود في topics.yaml")
    text = (req.get("topic_text") or "").strip()
    if not text:
        raise generator.GeneratorError("لم يُحدَّد موضوع")
    return {"id": "", "name": text, "description": "", "audience": "", "tone": "", "hashtags_fixed": []}


def build_prompt(topic: dict, count: int, brand: dict, recent: list[str]) -> str:
    fixed = " ".join(topic.get("hashtags_fixed") or []) or "(لا يوجد)"
    avoid = "، ".join(recent[-15:]) or "(لا يوجد)"
    return f"""أنت كاتب محتوى عربي محترف لحساب «{brand.get('name', '')}» على وسائل التواصل.
اكتب {count} منشورات مختلفة تماماً عن الموضوع: «{topic['name']}».
وصف الموضوع: {topic.get('description') or 'غير محدد'}
الجمهور: {topic.get('audience') or 'عام'}
النبرة: {topic.get('tone') or 'ودّية ومباشرة'}
هاشتاجات ثابتة للموضوع: {fixed}
عناوين سبق نشرها (لا تكررها): {avoid}

قواعد صارمة:
- العربية الفصحى المبسّطة. معلومات صحيحة ومفيدة، بلا ادعاءات طبية أو مالية أو سياسية ولا أرقام مختلقة.
- ابحث في الويب الآن عن الهاشتاجات العربية الرائجة حالياً والمرتبطة فعلاً بالموضوع، واستعمل 2 إلى 3 منها،
  مع 2 إلى 3 هاشتاجات متخصصة، مع الثابتة. لا تستعمل ترنداً لا علاقة له بالمنشور.
- لكل منشور هذه الحقول بالضبط:
  "title": عنوان قصير يظهر على الصورة (حتى 60 حرفاً)،
  "body": سطر صغير تحت العنوان (حتى 110 أحرف، أو فارغ)،
  "photo_query": 2 إلى 4 كلمات إنجليزية لصورة فوتوغرافية حقيقية مناسبة (بلا وجوه إن أمكن)،
  "text_long": نص كامل لفيسبوك وإنستغرام وتيليجرام مع الهاشتاجات في آخره (حتى 900 حرف)،
  "text_short": نص قصير لثريدز مع 2 إلى 3 هاشتاجات (حتى 380 حرفاً).
أخرج مصفوفة JSON فقط بلا أي شرح قبلها أو بعدها."""


def make_entries(items: list[dict], req: dict, topic: dict, existing_ids: set[str]) -> list[dict]:
    start = parse_when(req["start"])
    platforms = req.get("platforms") or DEFAULT_PLATFORMS
    out = []
    for i, it in enumerate(items):
        when = start + timedelta(days=i)
        pid, n = f"{when:%Y-%m-%d}-g1", 1
        while pid in existing_ids:
            n += 1
            pid = f"{when:%Y-%m-%d}-g{n}"
        existing_ids.add(pid)
        long_t, short_t = str(it.get("text_long", "")).strip(), str(it.get("text_short", "")).strip()
        texts = {"facebook": long_t, "instagram": long_t, "telegram": long_t, "threads": short_t or long_t}
        entry = {
            "id": pid, "approved": False, "publish_at": f"{when:%Y-%m-%d %H:%M}",
            "template": req.get("template") or "photo",
        }
        if topic.get("id"):
            entry["topic"] = topic["id"]
        entry["image"] = {"title": str(it.get("title", "")).strip(), "body": str(it.get("body", "")).strip(),
                          "photo_query": str(it.get("photo_query", "")).strip(), "seed": 1 + (i * 7) % 90}
        entry["platforms"] = {p: texts[p][:480] if p == "threads" else texts[p] for p in platforms if texts.get(p)}
        out.append(entry)
    return out


def write_log(**kw):
    LOG.write_text(json.dumps(kw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not REQUEST.exists():
        print("لا يوجد طلب توليد")
        return 0
    req = yaml.safe_load(REQUEST.read_text(encoding="utf-8")) or {}
    rid = str(req.get("id", ""))
    try:
        count = max(1, min(int(req.get("count", 1)), 7))
        topic = load_topic(req)
        queue = load_queue()
        recent = [p["image"]["title"] for p in queue if isinstance(p.get("image"), dict) and p["image"].get("title")]
        text, method = generator.generate_text(build_prompt(topic, count, load_brand(), recent))
        items = generator.extract_json(text)
        if not isinstance(items, list) or not items:
            raise generator.GeneratorError("قائمة المنشورات فارغة")
        entries = make_entries(items[:count], req, topic, {p["id"] for p in queue})
        entries = [e for e in entries if e["image"]["title"] and e["platforms"]]
        if not entries:
            raise generator.GeneratorError("لم يصلح أي منشور مولَّد")
        errors = fatal(validate(queue + entries))
        if errors:
            raise generator.GeneratorError("فشل التحقق: " + "؛ ".join(errors)[:300])
        block = yaml.safe_dump(entries, allow_unicode=True, sort_keys=False, width=1000)
        current = QUEUE_PATH.read_text(encoding="utf-8") if QUEUE_PATH.exists() else ""
        current = re.sub(r"^\[\]\s*$", "", current, flags=re.M)
        if current and not current.endswith("\n"):
            current += "\n"
        QUEUE_PATH.write_text(current + block, encoding="utf-8")
        write_log(id=rid, ok=True, count=len(entries), topic=topic["name"], method=method,
                  message=f"وُلِّدت {len(entries)} مسودات عن «{topic['name']}»")
        print(f"تم: {len(entries)} مسودات — {method}")
    except Exception as e:  # noqa: BLE001
        write_log(id=rid, ok=False, count=0, topic=req.get("topic_text") or str(req.get("topic_id", "")),
                  message=f"فشل التوليد: {str(e)[:400]}")
        print("فشل:", e)
    REQUEST.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
