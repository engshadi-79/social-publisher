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
from config import TOPICS_PATH, INFOGRAPHIC_STYLES, CAROUSEL_STYLES_FLAT, REEL_MOTION_STYLES, HUES

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


# صيغ محتوى بأسماء سلاسل ثابتة (على نهج حسابات المحتوى الناجحة): كل صيغة لها قاعدة كتابة واسم سلسلة يظهر على التصميم
FORMATS = {
    "goodbye": {"series": "وداعاً للفوضى", "pillars": ["automation", "ai"],
                "rule": "- الصيغة «وداعاً لـ…»: العنوان يبدأ بعبارة «وداعاً لـ» ثم عادة يدوية مزعجة يعرفها صاحب العمل، والمنشور يشرح ما يحل محلها."},
    "versus": {"series": "مين أفضل؟", "pillars": ["automation", "ai"], "only": "infographic",
               "rule": "- الصيغة «مقارنة»: العنوان بالشكل «الطريقة القديمة ضد الجديدة: من يكسب؟» بأسماء محددة (مثل: إكسل ضد نظام مخصص)."},
    "trick": {"series": "أتمتة في دقيقة", "pillars": ["automation", "ai"],
              "rule": "- الصيغة «حيلة في دقيقة»: حيلة واحدة عملية مجانية أو شبه مجانية تُنفَّذ اليوم بخطوات مرقّمة قصيرة."},
    "dream": {"series": "حلم صاحب العمل", "pillars": ["automation"],
              "rule": "- الصيغة «حلم كل صاحب عمل»: صف مشهداً مثالياً يتمناه صاحب العمل في يومه، ثم كيف يصبح حقيقة بنظام بسيط."},
    "qa": {"series": "سين جيم الأنظمة", "pillars": ["ai", "automation", "case"],
           "rule": "- الصيغة «سؤال وجواب»: العنوان سؤال شائع يطرحه أصحاب الأعمال (لا تدّعِ أن شخصاً محدداً سأله)، والجواب مباشر وصريح."},
    "backstage": {"series": "خلف الكواليس", "pillars": ["case"],
                  "rule": "- الصيغة «خلف الكواليس»: قرار تصميمي واحد في نظام حقيقي، ولماذا اتُّخذ، وما البديل الذي رُفض."},
}


def pick_format(pillar: str, style: str, used: list[str]) -> str | None:
    """الصيغة الأقل استعمالاً مؤخراً لهذا المحور، مع احترام القوالب المقيّدة (المقارنة إنفوجرافك فقط)."""
    cands = [k for k, f in FORMATS.items() if pillar in f["pillars"] and f.get("only", style) == style]
    if not cands:
        return None
    return max(cands, key=lambda k: (used[::-1].index(k) if k in used else 99, -list(FORMATS).index(k)))


PILLAR_RULES = {
    "automation": "- محور «الأتمتة»: ابدأ بالألم ثم الحل. اشرح ما يُؤتمَت دون ذكر تقنيات، واذكر ما يربحه صاحب العمل (وقت، أخطاء، هدوء).",
    "case": "- محور «القصص»: اشرح كيف صُمّم نظام حقيقي ولماذا بهذه الطريقة، بصيغة المتكلم، مستخدماً الحقائق المذكورة في وصف الموضوع حصراً. ممنوع اختلاق عميل أو شخصية أو حوار أو قرار أو نتيجة، وممنوع ذكر أي اسم أو بيانات حساسة. إن لم تكفِ الحقائق فاكتفِ بشرح المشكلة وما يفعله النظام.",
    "ai": "- محور «الذكاء الاصطناعي»: أداة أو طريقة واحدة قابلة للتجربة اليوم، وما الخطأ الشائع فيها، وكيف يتحقق المستخدم من نتيجتها.",
}


def build_prompt(topic: dict, count: int, brand: dict, recent: list[str], trends: list[str], style: str = "photo", slides_n: int = 7, when_txt: str = "", fmt: str | None = None) -> str:
    fixed = " ".join(topic.get("hashtags_fixed") or []) or "(لا يوجد)"
    pillar_rules = PILLAR_RULES.get(str(topic.get("pillar") or ""), "")
    if fmt in FORMATS:
        pillar_rules = (pillar_rules + "\n" if pillar_rules else "") + FORMATS[fmt]["rule"]
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
    elif style == "infographic" and fmt == "versus":
        style_fields = ('  "vs": [اسم الطريقة القديمة، اسم الطريقة الجديدة] (كل اسم حتى 18 حرفاً)،\n  "points": من 4 إلى 5 عناصر، كل عنصر بالشكل «ما في القديمة || ما في الجديدة» (كل طرف حتى 40 حرفاً، الفاصل || إلزامي)،\n  "photo_query": "" (اتركه فارغاً)،\n  "visual_prompt": "" (اتركه فارغاً)،')
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
- ابدأ text_long بخطّاف قوي في السطر الأول: ألم يعرفه صاحب العمل، أو رقم من الموضوع نفسه، أو سؤال يستفزّ التفكير. ممنوع الافتتاحيات العامة مثل «في عالم اليوم» أو «هل تعلم أن».
- كل منشور يحمل مثالاً واقعياً محدداً أو مشهداً من يوم عمل حقيقي (من يفعل ماذا ومتى). ممنوع النصائح العامة المكررة التي تصلح لأي حساب.
- اكتب بصيغة المتكلم (أنا مهندس برمجيات أبني أنظمة لأصحاب الأعمال) حين يناسب ذلك، دون ادعاء تجارب أو أرقام أو عملاء لم تُذكر في وصف الموضوع. لا تختلق أرقاماً ولا أسماء ولا نتائج؛ صغ الأثر وصفياً عند غياب الرقم.
- اختم النص قبل الهاشتاجات بسؤال واحد محدد يدعو لإجابة قصيرة (لا «ما رأيك؟»)، ثم سطر إحالة قصير: «التفاصيل في السيرة 👆». لا تضع أي رابط داخل النص.
- 3 إلى 5 هاشتاجات فقط، مرتبطة بالموضوع.
{pillar_rules}
- العربية الفصحى المبسّطة. معلومات صحيحة ومفيدة، بلا ادعاءات طبية أو مالية أو سياسية ولا أرقام مختلقة.
- ترند Google الحالي (مواضيع يبحث عنها الناس الآن): {trend_txt}
  استعمل منها كهاشتاج فقط ما يرتبط فعلاً بموضوع المنشور (قد لا يوجد شيء مناسب، وهذا مقبول ولا تُقحم ترنداً لا علاقة له).
  موعد النشر: {when_txt or "غير محدد"}. اختر هاشتاجاً رائجاً مناسباً لهذا اليوم والموضوع (مثل جمعة_مباركة يوم الجمعة، وصباح_الخير في منشورات الصباح، أو مناسبة قائمة) إن وُجد، فهذا ما يجعل الهاشتاج جديداً كل يوم.
  ثم أضف 3 إلى 4 هاشتاجات عربية متخصصة بالموضوع، مع الهاشتاجات الثابتة (قد لا توجد).
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
        elif req.get("style") == "infographic" and req.get("format") == "versus":
            pairs = [str(x).strip() for x in (it.get("points") or []) if "||" in str(x)][:5]
            vs = [str(x).strip()[:24] for x in (it.get("vs") or []) if str(x).strip()][:2]
            if len(pairs) >= 3 and len(vs) == 2:
                img["points"] = ["||".join(p.strip()[:46] for p in x.split("||", 1)) for x in pairs]
                img["vs"] = vs
            else:                          # جاء النص بلا مقارنة صالحة: يُنشر إنفوجرافك عادياً
                img["points"] = [x.split("||")[-1].strip()[:88] for x in (it.get("points") or []) if str(x).strip()][:5]
                req = dict(req, format=None)
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
        if req.get("format") in FORMATS:
            img["format"] = req["format"]
            img["series"] = FORMATS[req["format"]]["series"]
        pool = tuple(x for x in INFOGRAPHIC_STYLES if x != "versus") if entry["template"] == "infographic" else CAROUSEL_STYLES_FLAT if entry["template"] == "carousel" else REEL_MOTION_STYLES if entry["template"] == "reel" else ()
        if img.get("format") == "versus":
            img["style"] = "versus"
        elif pool:
            pick = max(pool, key=lambda st: (used[::-1].index(st) if st in used else 99, -pool.index(st)))
            img["style"] = pick
            used.append(pick)
        if entry["template"] in ("infographic", "reel", "carousel") and img.get("format") != "versus":   # ألوان المقارنة دلالية (أحمر/أخضر)
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


def when_ar(start) -> str:
    """«يوم الجمعة 23 أكتوبر 2026 الساعة 08:00» لإرشاد النموذج في اختيار الهاشتاج."""
    try:
        d = parse_when(str(start))
    except Exception:  # noqa: BLE001
        return ""
    days = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    return f"يوم {days[d.weekday()]} {d:%Y-%m-%d} الساعة {d:%H:%M}"


def build_entries(req: dict, queue: list[dict]) -> tuple[list[dict], dict, str]:
    """يولّد مسودات طلب واحد ويتحقق منها (دون كتابتها). يرجع (المسودات، الموضوع، وصف الطريقة)."""
    count = max(1, min(int(req.get("count", 1)), 7))
    topic = load_topic(req)
    recent = [p["image"]["title"] for p in queue if isinstance(p.get("image"), dict) and p["image"].get("title")]
    trends = fetch_trends()
    text, method = generator.generate_text(build_prompt(topic, count, load_brand(), recent, trends, req.get("style") or "photo", int(req.get("slides") or 7), when_ar(req.get("start")), req.get("format")))
    method += f" | ترند Google: {len(trends)} عنصر" if trends else " | ترند Google غير متاح"
    items = generator.extract_json(text)
    if not isinstance(items, list) or not items:
        raise generator.GeneratorError("قائمة المنشورات فارغة")
    recent_styles = [str((p.get("image") or {}).get("style")) for p in queue if isinstance(p.get("image"), dict) and (p.get("image") or {}).get("style")]
    recent_hues = [(p.get("image") or {}).get("hue") for p in queue if isinstance(p.get("image"), dict) and isinstance((p.get("image") or {}).get("hue"), int)]
    entries = make_entries(items[:count], req, topic, {p["id"] for p in queue}, recent_styles, recent_hues)
    entries = [e for e in entries if e["image"]["title"] and e["platforms"] and (e["template"] != "infographic" or len(e["image"].get("points", [])) >= 2) and (e["template"] != "carousel" or len(e["image"].get("slides", [])) >= 3) and (e["template"] != "reel" or len(e["image"].get("scenes", [])) >= int(req.get("min_scenes") or 3))]
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


DAILY_STYLES = ["infographic", "carousel"]            # الريل له موعد يومي خاص به (REEL_SLOT) فلا يدخل هنا
# أوقات الذروة لجمهور عربي (بتوقيت الجهة): صباح قبل العمل، استراحة الظهيرة، وذروة المساء
SLOTS = ["08:00", "21:00"]                           # منشوران يومياً: صباح قبل العمل وذروة المساء
PER_DAY = len(SLOTS)
REEL_SLOT = "18:00"                                    # ريل أسبوعي على كل المنصات، قبل ذروة المساء
REEL_WEEKDAY = 3                                       # الخميس (الاثنين=0)
REEL_MIN_SCENES = 7                                    # لا يقل الريل عن 7 مشاهد (صور متحرّكة)
REEL_AHEAD_DAYS = 14                                   # يضمن وجود ريل لكل خميس خلال أسبوعين قادمين


def free_slots(queue: list[dict], day: str) -> list[str]:
    taken = {str(p["publish_at"])[11:16] for p in queue if str(p["publish_at"])[:10] == day}
    return [s for s in SLOTS if s not in taken]


def reel_free(queue: list[dict], day: str) -> bool:
    return not any(str(p["publish_at"])[:10] == day and str(p["publish_at"])[11:16] == REEL_SLOT for p in queue)


def daily(target: str | None = None) -> int:
    """كل يوم: 3 منشورات (8:00 و13:00 و21:00) وريل واحد (18:00) من 7 مشاهد على الأقل، كلها مسودات تنتظر موافقتك.

    المواضيع الأقدم نشراً أولاً. آمن عند التكرار: لا يملأ إلا المواعيد الشاغرة، وينظّم المخزون ذاتياً.
    """
    import time
    from datetime import datetime
    from queue_io import now_local

    topics = yaml.safe_load(TOPICS_PATH.read_text(encoding="utf-8")).get("topics") if TOPICS_PATH.exists() else []
    topics = [t for t in (topics or []) if isinstance(t, dict) and t.get("id") and not t.get("paused")]
    if not topics:
        print("لا مواضيع")
        return 0
    done, failed = [], []

    def order_topics(queue):
        last = {t["id"]: "" for t in topics}
        for p in queue:
            if p.get("topic") in last:
                last[p["topic"]] = max(last[p["topic"]], str(p["publish_at"]))
        return sorted(topics, key=lambda t: (last[t["id"]], topics.index(t)))

    def make(t, day, slot, style, slides, extra=None):
        used_f = [str((p.get("image") or {}).get("format")) for p in load_queue() if (p.get("image") or {}).get("format")]
        fmt = pick_format(str(t.get("pillar") or ""), style, used_f)
        extra = dict(extra or {}, format=fmt)
        req = {"id": f"daily-{day}-{t['id']}", "count": 1, "topic_id": t["id"], "style": style,
               "slides": slides, "start": f"{day} {slot}", **(extra or {})}
        for attempt in range(3):              # Gemini المجاني يزدحم (503/429): نعيد بتأخير متزايد
            try:
                entries, topic, method = build_entries(req, load_queue())
                append_entries(entries)
                done.append(f"{topic['name']} ({style})")
                print(f"✓ {topic['name']} → {entries[0]['id']} [{style}] {slot}")
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 2:
                    failed.append(f"{t.get('name', t['id'])}: {str(e)[:120]}")
                    print(f"✗ {t.get('name', t['id'])}: {e}")
                else:
                    print(f"… إعادة المحاولة {attempt + 2}/3 بعد خطأ: {str(e)[:80]}")
                    time.sleep(45 * (attempt + 1))
        time.sleep(8)                         # حدّ معدّل الطبقة المجانية

    start = (now_local() + timedelta(days=1)).date()
    # 1) الريلات: يوم واحد بعد آخر لأيام قادمة، من مواضيع غير صباحية
    for k in range(REEL_AHEAD_DAYS):
        rday = target or (start + timedelta(days=k)).strftime("%Y-%m-%d")
        if datetime.strptime(rday, "%Y-%m-%d").weekday() == REEL_WEEKDAY and reel_free(load_queue(), rday):
            pool = [t for t in order_topics(load_queue()) if t.get("time") != "morning"] or topics
            make(pool[0], rday, REEL_SLOT, "reel", 8, {"min_scenes": REEL_MIN_SCENES})
        if target:
            break

    # 2) المنشورات الثابتة
    queue = load_queue()
    day = target
    if not day:
        d = start
        while not free_slots(queue, d.strftime("%Y-%m-%d")):
            d += timedelta(days=1)
        day = d.strftime("%Y-%m-%d")
    slots = free_slots(queue, day)
    order = order_topics(queue)
    morning = [t for t in order if t.get("time") == "morning"]       # مواضيع الصباح: دائماً في موعد 8:00
    others = [t for t in order if t.get("time") != "morning"]
    pairs = []
    for slot in slots:
        pool = morning if slot == SLOTS[0] and morning else others or morning
        if pool:
            pairs.append((pool.pop(0), slot))
    ordinal = datetime.strptime(day, "%Y-%m-%d").toordinal()
    for i, (t, slot) in enumerate(pairs):
        style = DAILY_STYLES[(ordinal + i) % len(DAILY_STYLES)]
        make(t, day, slot, style, 6 if style == "carousel" else 5)
    try:
        weekly_scripts()
    except Exception as e:  # noqa: BLE001  — السكربتات إضافة، لا توقف التوليد اليومي
        print("تعذّر توليد سكربتات الأسبوع:", e)
    msg = f"يومي {day}: وُلِّد {len(done)} مسودة" + (f"، وفشل {len(failed)}" if failed else "") + "."
    write_log(id=f"daily-{day}", ok=not failed or bool(done), count=len(done), topic="كل المواضيع", method="daily",
              message=msg + ((" " + " | ".join(failed))[:300] if failed else ""))
    print(msg)
    return 0



SCRIPTS_PATH = ROOT / "content" / "scripts.json"


def weekly_scripts(force: bool = False) -> int:
    """سكربتان أسبوعياً لتصوّرهما بنفسك (وجهك وصوتك هما ما ترفعه الخوارزمية أكثر). مرة واحدة لكل أسبوع."""
    from datetime import datetime
    from queue_io import now_local

    d = now_local().date()
    iso = d.isocalendar()
    week = f"{iso[0]}-W{iso[1]:02d}"
    data = json.loads(SCRIPTS_PATH.read_text(encoding="utf-8")) if SCRIPTS_PATH.exists() else {"weeks": []}
    if not force and any(w.get("week") == week for w in data.get("weeks", [])):
        print("سكربتات هذا الأسبوع موجودة")
        return 0
    topics = yaml.safe_load(TOPICS_PATH.read_text(encoding="utf-8")).get("topics") if TOPICS_PATH.exists() else []
    active = [t for t in (topics or []) if isinstance(t, dict) and not t.get("paused")]
    facts = "\n".join(f"- {t['name']}: {t.get('description', '')}" for t in active)
    prompt = f"""أنت كاتب سكربتات فيديو قصيرة (ريلز) لمهندس برمجيات عربي يبني أنظمة ومواقع ومتاجر وتطبيقات لأصحاب الأعمال، ويريد جلب زوار لموقعه.
اكتب سكربتين يصوّرهما بنفسه بالجوال وهو يتكلم للكاميرا، مدة كل منهما 30 إلى 45 ثانية.
السكربت الأول من محور الأتمتة، والثاني من محور القصص أو الذكاء الاصطناعي العملي.
المحاور والحقائق المسموح بها:
{facts}
قواعد صارمة:
- عربية فصحى مبسّطة قريبة من الكلام اليومي، جمل قصيرة تُقال بسهولة.
- أول 3 ثوانٍ خطّاف يوقف التمرير. لا تبدأ بالتحية ولا بالتعريف بالنفس. وممنوع الافتتاحيات المستهلكة مثل «هل تعلم» و«في عالم اليوم».
- لا تختلق أرقاماً أو عملاء أو قصصاً أو نتائج؛ استعمل الحقائق المذكورة فقط.
- ختام واحد: سؤال محدد للتعليق ثم «الرابط في السيرة».
لكل سكربت هذه الحقول بالضبط:
  "title": عنوان داخلي قصير،
  "pillar": اسم المحور،
  "on_screen": نص الخطّاف الذي يُكتب أعلى الفيديو (حتى 40 حرفاً)،
  "hook": أول جملة تُقال (حتى 120 حرفاً)،
  "points": 3 جمل للمحتوى (كل جملة حتى 140 حرفاً)،
  "cta": جملة الختام،
  "tip": نصيحة تصوير واحدة عملية (المكان، الإطار، ما يظهر على الشاشة)،
  "seconds": المدة التقريبية بالثواني.
أخرج مصفوفة JSON فقط."""
    text, method = generator.generate_text(prompt)
    items = generator.extract_json(text)
    if not isinstance(items, list) or not items:
        raise generator.GeneratorError("لم تُولَّد سكربتات")
    keep = []
    for it in items[:2]:
        if not isinstance(it, dict) or not str(it.get("hook", "")).strip():
            continue
        keep.append({k: (it.get(k) if k == "points" else str(it.get(k, "")).strip()) for k in
                     ("title", "pillar", "on_screen", "hook", "points", "cta", "tip", "seconds")})
        keep[-1]["points"] = [str(x).strip() for x in (it.get("points") or []) if str(x).strip()][:3]
    data.setdefault("weeks", []).insert(0, {"week": week, "created": datetime.now().isoformat(timespec="minutes"), "items": keep})
    data["weeks"] = data["weeks"][:8]
    SCRIPTS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"سكربتات {week}: {len(keep)}")
    return len(keep)


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
