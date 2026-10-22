"""يحوّل طلب توليد (من اللوحة) إلى مسودات في queue.yaml.

الطلب: content/generate_request.yaml
  id, count, start ("YYYY-MM-DD HH:MM"), topic_id أو topic_text, platforms (اختياري)
النتيجة: مسودات approved:false + content/generate_log.json (تُعرض في اللوحة).
"""
import json
import re
import sys
from datetime import timedelta

import urllib.request
import xml.etree.ElementTree as ET

import yaml

import generator
from config import ROOT, QUEUE_PATH
from queue_io import fatal, load_queue, load_brand, parse_when, validate
from config import TOPICS_PATH, INFOGRAPHIC_STYLES, CAROUSEL_STYLES_FLAT, HUES

REQUEST = ROOT / "content" / "generate_request.yaml"
LOG = ROOT / "content" / "generate_log.json"
DEFAULT_PLATFORMS = ["facebook", "instagram", "threads", "linkedin"]


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


TREND_GEOS = ["PS", "SA", "JO", "EG", "AE"]


def fetch_trends() -> list[str]:
    """ترند Google الحالي (RSS عام بلا مفتاح). عند أي فشل يرجع قائمة فارغة."""
    seen, out = set(), []
    for geo in TREND_GEOS:
        try:
            req = urllib.request.Request(f"https://trends.google.com/trending/rss?geo={geo}",
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                root = ET.fromstring(r.read())
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                if title and title not in seen:
                    seen.add(title)
                    out.append(title)
        except Exception:  # noqa: BLE001
            continue
    return out[:60]


def build_prompt(topic: dict, count: int, brand: dict, recent: list[str], trends: list[str], style: str = "photo", slides_n: int = 7) -> str:
    fixed = " ".join(topic.get("hashtags_fixed") or []) or "(لا يوجد)"
    avoid = "، ".join(recent[-15:]) or "(لا يوجد)"
    trend_txt = "، ".join(trends) if trends else "(غير متاح الآن)"
    if style == "carousel":
        n = max(5, min(int(slides_n or 7), 10))
        style_fields = (f'  "slides": مصفوفة من {n} شرائح لكاروسيل إنستغرام بأسلوب «دراسة حالة/دليل عملي»، كل شريحة كائن فيه: '
                        '"kicker" (سطر صغير فوق العنوان مثل: المشكلة، الفكرة، الخطوة الأولى، الخلاصة)، "title" (عنوان قوي حتى 70 حرفاً)، '
                        '"body" (جملة أو جملتان حتى 180 حرفاً، أو فارغ)، "points" (قائمة حتى 3 نقاط قصيرة حتى 60 حرفاً لكل نقطة، أو فارغة)، "photo_query" (2 إلى 4 كلمات إنجليزية للبحث عن صورة فوتوغرافية حقيقية تمثّل فكرة هذه الشريحة تحديداً: شيء ملموس مرئي لا مفهوم مجرد).\n'
                        '    الشريحة الأولى غلاف: عنوان جاذب وجملة تحته و3 نقاط في "points" تلخّص الوعد. الشرائح الوسطى: فكرة واحدة لكل شريحة بتسلسل منطقي. '
                        'الأخيرة: سؤال تفاعلي للمتابع في "title" ودعوة لحفظ المنشور والتعليق في "body".\n'
                        '  "photo_query": 2 إلى 4 كلمات إنجليزية تمثّل موضوع المنشور كله (تُستعمل للشريحة التي بلا كلمات خاصة)،\n  "visual_prompt": "" (اتركه فارغاً)،\n'
                        '  ملاحظة: "title" و"body" الخارجيان للمنشور ككل: "title" هو عنوان الغلاف و"body" فارغ.')
    elif style == "reel":
        n = max(3, min(int(slides_n or 5), 8))
        style_fields = (f'  "scenes": مصفوفة من {n} مشاهد لفيديو عمودي قصير (ريل)، كل مشهد كائن فيه: '
                        '"kicker" (كلمة أو كلمتان فوق العنوان مثل: المشكلة، الفكرة، الخطوة)، "title" (جملة قوية حتى 60 حرفاً تُقرأ في ثلاث ثوانٍ)، '
                        '"body" (جملة قصيرة حتى 120 حرفاً، أو فارغ)، "seconds" (رقم بين 2.5 و4)، '
                        '"photo_query" (2 إلى 4 كلمات إنجليزية للبحث عن صورة فوتوغرافية حقيقية تمثّل هذا المشهد: شيء ملموس مرئي).\n'
                        '    المشهد الأول خطّاف يوقف التمرير (سؤال أو مشكلة). الوسطى فكرة واحدة لكل مشهد. الأخير سؤال للمتابع ودعوة للحفظ والتعليق.\n'
                        '  "photo_query": "" (اتركه فارغاً)،\n  "visual_prompt": "" (اتركه فارغاً)،')
    elif style == "infographic":
        style_fields = ('  "points": من 3 إلى 5 نقاط قصيرة ومفيدة تلخّص المنشور كإنفوجرافك (كل نقطة حتى 60 حرفاً، بلا ترقيم)،\n'
                        '  "photo_query": "" (اتركه فارغاً)،\n  "visual_prompt": "" (اتركه فارغاً)،')
    else:
        style_fields = ('  "photo_query": 2 إلى 4 كلمات إنجليزية للبحث عن صورة فوتوغرافية حقيقية تمثّل فكرة المنشور مباشرة (شيء ملموس ومرئي، لا مفاهيم مجردة)،\n'
                        '  "visual_prompt": وصف إنجليزي قصير لمشهد واقعي يمثّل فكرة المنشور حرفياً (للتوليد الاحتياطي)،')
    caption_style = ""
    if style == "carousel":
        caption_style = (" بأسلوب حكاية شخصية بصيغة المتكلم: جملة افتتاحية تحكي موقفاً حقيقياً أو سؤالاً يعيشه الجمهور، ثم 3 إلى 4 نقاط "
                         "تبدأ كل واحدة بالرمز ✦ تلخّص ما في الشرائح، ثم سؤال تفاعلي في آخر النص قبل الهاشتاجات، وفي أول سطر اطلب «اسحب للآخر»")
    return f"""أنت كاتب محتوى عربي محترف لحساب «{brand.get('name', '')}» على وسائل التواصل.
اكتب {count} منشورات مختلفة تماماً عن الموضوع: «{topic['name']}».
وصف الموضوع: {topic.get('description') or 'غير محدد'}
الجمهور: {topic.get('audience') or 'عام'}
النبرة: {topic.get('tone') or 'ودّية ومباشرة'}
هاشتاجات ثابتة للموضوع: {fixed}
عناوين سبق نشرها (لا تكررها): {avoid}

قواعد صارمة:
- العربية الفصحى المبسّطة. معلومات صحيحة ومفيدة، بلا ادعاءات طبية أو مالية أو سياسية ولا أرقام مختلقة.
- ترند Google الحالي (مواضيع يبحث عنها الناس الآن): {trend_txt}
  استعمل منها كهاشتاج فقط ما يرتبط فعلاً بموضوع المنشور (قد لا يوجد شيء مناسب، وهذا مقبول ولا تُقحم ترنداً لا علاقة له).
  ثم أضف 3 إلى 4 هاشتاجات عربية متخصصة بالموضوع، مع الهاشتاجات الثابتة.
- لكل منشور هذه الحقول بالضبط:
  "title": عنوان قصير يظهر على الصورة (حتى 60 حرفاً)،
  "body": سطر صغير تحت العنوان (حتى 80 حرفاً، أو فارغ)،
{style_fields}
  "text_long": نص كامل لفيسبوك وإنستغرام وتيليجرام مع الهاشتاجات في آخره (حتى 900 حرف){caption_style}،
  "text_short": نص قصير لثريدز مع 2 إلى 3 هاشتاجات (حتى 380 حرفاً).
أخرج مصفوفة JSON فقط بلا أي شرح قبلها أو بعدها."""


def clip(text: str, limit: int) -> str:
    """قصّ عند آخر مسافة قبل الحد، فلا تنقطع كلمة في منتصفها."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit * 0.6 else cut).rstrip(" ،.") + "…"


def make_entries(items: list[dict], req: dict, topic: dict, existing_ids: set[str], used_styles: list[str] | None = None, used_hues: list[int] | None = None) -> list[dict]:
    start = parse_when(req["start"])
    platforms = req.get("platforms") or DEFAULT_PLATFORMS
    out = []
    used = list(used_styles or [])
    used_h = list(used_hues or [])
    for i, it in enumerate(items):
        when = start + timedelta(days=i)
        pid, n = f"{when:%Y-%m-%d}-g1", 1
        while pid in existing_ids:
            n += 1
            pid = f"{when:%Y-%m-%d}-g{n}"
        existing_ids.add(pid)
        long_t, short_t = str(it.get("text_long", "")).strip(), str(it.get("text_short", "")).strip()
        texts = {"facebook": long_t, "instagram": long_t, "telegram": long_t,
                 "linkedin": long_t, "threads": short_t or long_t}
        entry = {
            "id": pid, "approved": False, "publish_at": f"{when:%Y-%m-%d %H:%M}",
            "template": ("reel" if req.get("style") == "reel" else "carousel" if req.get("style") == "carousel" else "infographic" if req.get("style") == "infographic" else (req.get("template") or "split")),
        }
        if topic.get("id"):
            entry["topic"] = topic["id"]
        img = {"title": str(it.get("title", "")).strip(), "body": str(it.get("body", "")).strip()}
        if req.get("style") == "carousel":
            slides = []
            for sl in (it.get("slides") or [])[:10]:
                if not isinstance(sl, dict) or not str(sl.get("title", "")).strip():
                    continue
                one = {"kicker": str(sl.get("kicker", "") or "").strip()[:40], "title": str(sl["title"]).strip()[:110],
                       "body": str(sl.get("body", "") or "").strip()[:240],
                       "points": [str(x).strip()[:88] for x in (sl.get("points") or []) if str(x).strip()][:3]}
                if str(sl.get("photo_query", "") or "").strip():
                    one["photo_query"] = str(sl["photo_query"]).strip()[:60]
                slides.append(one)
            img["slides"] = slides
            img["title"] = slides[0]["title"] if slides else img["title"]
            img["body"] = ""
            if str(it.get("photo_query", "") or "").strip():      # احتياط الشرائح بلا كلمات خاصة
                img["photo_query"] = str(it["photo_query"]).strip()[:60]
        elif req.get("style") == "reel":
            scenes = []
            for sc in (it.get("scenes") or [])[:8]:
                if not isinstance(sc, dict) or not str(sc.get("title", "")).strip():
                    continue
                one = {"kicker": str(sc.get("kicker", "") or "").strip()[:30], "title": str(sc["title"]).strip()[:70],
                       "body": str(sc.get("body", "") or "").strip()[:150]}
                try:
                    one["seconds"] = round(min(8.0, max(1.5, float(sc.get("seconds") or 3.4))), 1)
                except (TypeError, ValueError):
                    one["seconds"] = 3.4
                if str(sc.get("photo_query", "") or "").strip():
                    one["photo_query"] = str(sc["photo_query"]).strip()[:60]
                scenes.append(one)
            img["scenes"] = scenes
            img["title"] = scenes[0]["title"] if scenes else img["title"]
            img["body"] = ""
        elif req.get("style") == "infographic":
            pts = [str(x).strip() for x in (it.get("points") or []) if str(x).strip()][:5]
            img["points"] = [x[:88] for x in pts]
        else:
            img["photo_query"] = str(it.get("photo_query", "")).strip()
            if str(it.get("visual_prompt", "")).strip():
                img["visual_prompt"] = str(it["visual_prompt"]).strip()
        # التصاميم بلا صور فوتوغرافية (قرار المالك): تُحذف كل كلمات البحث ولو كتبها النموذج
        img.pop("photo_query", None)
        img.pop("visual_prompt", None)
        for part in (img.get("slides") or []) + (img.get("scenes") or []):
            part.pop("photo_query", None)
        # نمط مختلف لكل منشور: يُختار الأقل استعمالاً مؤخراً، فلا يتكرّر التصميم نفسه
        pool = INFOGRAPHIC_STYLES if entry["template"] == "infographic" else CAROUSEL_STYLES_FLAT if entry["template"] == "carousel" else ()
        if pool:
            pick = max(pool, key=lambda st: (used[::-1].index(st) if st in used else 99, -pool.index(st)))
            img["style"] = pick
            used.append(pick)
        if entry["template"] in ("infographic", "reel"):
            hue = max(HUES, key=lambda h: (used_h[::-1].index(h) if h in used_h else 99, -HUES.index(h)))
            img["hue"] = hue
            used_h.append(hue)
        img["seed"] = 1 + (i * 7) % 90
        entry["image"] = img
        entry["platforms"] = {p: clip(texts[p], 480) if p == "threads" else texts[p]
                              for p in platforms if texts.get(p)}
        out.append(entry)
    return out


def write_log(**kw):
    LOG.write_text(json.dumps(kw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_entries(req: dict, queue: list[dict]) -> tuple[list[dict], dict, str]:
    """يولّد مسودات طلب واحد ويتحقق منها (دون كتابتها). يرجع (المسودات، الموضوع، وصف الطريقة)."""
    count = max(1, min(int(req.get("count", 1)), 7))
    topic = load_topic(req)
    recent = [p["image"]["title"] for p in queue if isinstance(p.get("image"), dict) and p["image"].get("title")]
    trends = fetch_trends()
    text, method = generator.generate_text(build_prompt(topic, count, load_brand(), recent, trends, req.get("style") or "photo", int(req.get("slides") or 7)))
    method += f" | ترند Google: {len(trends)} عنصر" if trends else " | ترند Google غير متاح"
    items = generator.extract_json(text)
    if not isinstance(items, list) or not items:
        raise generator.GeneratorError("قائمة المنشورات فارغة")
    recent_styles = [str((p.get("image") or {}).get("style")) for p in queue if isinstance(p.get("image"), dict) and (p.get("image") or {}).get("style")]
    recent_hues = [(p.get("image") or {}).get("hue") for p in queue if isinstance(p.get("image"), dict) and isinstance((p.get("image") or {}).get("hue"), int)]
    entries = make_entries(items[:count], req, topic, {p["id"] for p in queue}, recent_styles, recent_hues)
    entries = [e for e in entries if e["image"]["title"] and e["platforms"] and (e["template"] != "infographic" or len(e["image"].get("points", [])) >= 2) and (e["template"] != "carousel" or len(e["image"].get("slides", [])) >= 3) and (e["template"] != "reel" or len(e["image"].get("scenes", [])) >= 3)]
    if not entries:
        raise generator.GeneratorError("لم يصلح أي منشور مولَّد")
    errors = fatal(validate(queue + entries))
    if errors:
        raise generator.GeneratorError("فشل التحقق: " + "؛ ".join(errors)[:300])
    return entries, topic, method


def append_entries(entries: list[dict]) -> None:
    block = yaml.safe_dump(entries, allow_unicode=True, sort_keys=False, width=1000)
    current = QUEUE_PATH.read_text(encoding="utf-8") if QUEUE_PATH.exists() else ""
    current = re.sub(r"^\[\]\s*$", "", current, flags=re.M)
    if current and not current.endswith("\n"):
        current += "\n"
    QUEUE_PATH.write_text(current + block, encoding="utf-8")


DAILY_STYLES = ["infographic", "carousel", "infographic", "reel"]     # الريل بنسبة ربع المنشورات: بناؤه أثقل
# أوقات الذروة لجمهور عربي (بتوقيت الجهة): صباح قبل العمل، استراحة الظهيرة، وذروة المساء
SLOTS = ["08:00", "13:00", "21:00"]
PER_DAY = len(SLOTS)


def free_slots(queue: list[dict], day: str) -> list[str]:
    taken = {str(p["publish_at"])[11:16] for p in queue if str(p["publish_at"])[:10] == day}
    return [s for s in SLOTS if s not in taken]


def daily(target: str | None = None) -> int:
    """ثلاثة منشورات يومياً (8:00 و13:00 و21:00) من المواضيع الأقدم نشراً، مسودات تنتظر الموافقة.

    اليوم المستهدف: أول يوم من الغد فصاعداً فيه مواعيد شاغرة، فيتنظّم المخزون ذاتياً ولا يتراكم.
    آمن عند التكرار: لا يملأ إلا الأوقات الشاغرة.
    """
    import time
    from datetime import datetime
    from queue_io import now_local

    topics = yaml.safe_load(TOPICS_PATH.read_text(encoding="utf-8")).get("topics") if TOPICS_PATH.exists() else []
    topics = [t for t in (topics or []) if isinstance(t, dict) and t.get("id")]
    if not topics:
        print("لا مواضيع")
        return 0
    queue = load_queue()
    day = target
    if not day:
        d = (now_local() + timedelta(days=1)).date()
        while not free_slots(queue, d.strftime("%Y-%m-%d")):
            d += timedelta(days=1)
        day = d.strftime("%Y-%m-%d")
    slots = free_slots(queue, day)
    # الموضوع الأقدم نشراً أولاً (من لم يُنشر له شيء قط يتقدّم)
    last = {t["id"]: "" for t in topics}
    for p in queue:
        if p.get("topic") in last:
            last[p["topic"]] = max(last[p["topic"]], str(p["publish_at"]))
    order = sorted(topics, key=lambda t: (last[t["id"]], topics.index(t)))
    ordinal = datetime.strptime(day, "%Y-%m-%d").toordinal()
    done, failed = [], []
    for i, (t, slot) in enumerate(zip(order, slots)):
        queue = load_queue()
        style = DAILY_STYLES[(ordinal + i) % len(DAILY_STYLES)]
        req = {"id": f"daily-{day}-{t['id']}", "count": 1, "topic_id": t["id"], "style": style,
               "slides": 6 if style == "carousel" else 5, "start": f"{day} {slot}"}
        try:
            entries, topic, method = build_entries(req, queue)
            append_entries(entries)
            done.append(f"{topic['name']} ({style})")
            print(f"✓ {topic['name']} → {entries[0]['id']} [{style}] {slot}")
        except Exception as e:  # noqa: BLE001
            failed.append(f"{t.get('name', t['id'])}: {str(e)[:120]}")
            print(f"✗ {t.get('name', t['id'])}: {e}")
        time.sleep(8)                         # حدّ معدّل الطبقة المجانية
    msg = f"يومي {day}: وُلِّد {len(done)} مسودة" + (f"، وفشل {len(failed)}" if failed else "") + "."
    write_log(id=f"daily-{day}", ok=not failed or bool(done), count=len(done), topic="كل المواضيع", method="daily",
              message=msg + ((" " + " | ".join(failed))[:300] if failed else ""))
    print(msg)
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if "--daily" in sys.argv:
        i = sys.argv.index("--daily")
        return daily(sys.argv[i + 1] if len(sys.argv) > i + 1 and not sys.argv[i + 1].startswith("-") else None)
    if not REQUEST.exists():
        print("لا يوجد طلب توليد")
        return 0
    req = yaml.safe_load(REQUEST.read_text(encoding="utf-8")) or {}
    if req.get("style") not in ("carousel", "reel", "infographic"):
        req["style"] = "infographic"          # لا منشورات بصور فوتوغرافية بعد الآن
    rid = str(req.get("id", ""))
    try:
        entries, topic, method = build_entries(req, load_queue())
        append_entries(entries)
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
