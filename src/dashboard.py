"""يولّد لوحة تحكم ثابتة (HTML) من الطابور والحالة، لتُنشر على GitHub Pages."""
import argparse
import json
import os
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader
from PIL import Image

import imagegen
from config import ROOT, MEDIA_DIR, OUT_DIR, PLATFORMS, TIMEZONE, TOPICS_PATH
from queue_io import load_queue, load_state, now_local, parse_when
from render import Renderer

LABELS = {"facebook": "فيسبوك", "instagram": "إنستغرام", "threads": "ثريدز", "telegram": "تيليجرام"}
SITE = OUT_DIR / "dashboard"
DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


def when_ar(d):
    h = d.hour % 12 or 12
    part = "صباحاً" if d.hour < 12 else "مساءً"
    return f"يوم {DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} الساعة {h}:{d.minute:02d} {part}"


def join_ar(names):
    return " و".join(names)


def _chip(name, text, st, scheduled_txt):
    status = st.get("status")
    if status == "published":
        txt, cls, hint = "✅ نُشر", "published", st.get("published_at", "")
    elif status == "failed":
        txt, cls, hint = "❌ لم ينجح", "failed", "فشل بعد كل المحاولات"
    elif status == "retry":
        txt, cls, hint = "🔁 ستُعاد المحاولة", "retry", ""
    else:
        txt, cls, hint = scheduled_txt, "", ""
    url = None
    if name == "facebook" and status == "published" and st.get("platform_post_id"):
        url = f"https://www.facebook.com/{st['platform_post_id']}"
    return {"label": LABELS[name], "txt": txt, "status": cls, "hint": hint, "url": url,
            "text": text, "error": st.get("error") if status in ("failed", "retry") else None}


def build(posts, state, now):
    items = []
    for p in posts:
        when = parse_when(p["publish_at"])
        st = state.get(p["id"], {})
        past = when <= now
        chips = [_chip(n, t, st.get(n, {}), "⏳ ينتظر دوره" if past else "⏳ ينتظر موعده")
                 for n, t in p["platforms"].items()]
        statuses = [c["status"] for c in chips]
        all_done = all(s == "published" for s in statuses)
        if not p["approved"]:
            group, badge, badge_txt = "draft", "draft", "بانتظار موافقتك"
        elif "failed" in statuses or "retry" in statuses:
            group = "failed"
            badge, badge_txt = ("failed", "حدثت مشكلة") if "failed" in statuses else ("retry", "ستُعاد المحاولة")
        elif all_done:
            group, badge, badge_txt = "published", "published", "تم النشر"
        elif past:
            group, badge, badge_txt = "upcoming", "due", "سيُنشر خلال دقائق"
        else:
            group, badge, badge_txt = "upcoming", "scheduled", "سيُنشر في موعده"
        pl = join_ar(LABELS[n] for n in p["platforms"])
        line = {
            "draft": f"لن يُنشر حتى توافق عليه. الموعد المقترح: {when_ar(when)}. المنصات: {pl}.",
            "published": f"نُشر على: {pl}.",
            "failed": f"حدثت مشكلة عند النشر ({pl}). التفاصيل أدناه.",
            "upcoming": (f"حان موعده وسيُنشر خلال دقائق على: {pl}." if past
                         else f"سيُنشر {when_ar(when)} على: {pl}."),
        }[group]
        items.append({"line": line, "when_ar": when_ar(when),
            "id": p["id"], "template": p["template"], "title": p["image"]["title"],
            "when": when, "when_txt": when.strftime("%Y-%m-%d %H:%M"), "chips": chips,
            "group": group, "badge": badge, "badge_txt": badge_txt,
            "platforms_txt": "، ".join(LABELS[n] for n in p["platforms"]),
        })
    # الأحدث أولاً للمنشورة، والأقرب أولاً للقادمة
    items.sort(key=lambda x: x["when"])
    upcoming = [i for i in items if i["group"] == "upcoming"]
    rest = [i for i in items if i["group"] != "upcoming"][::-1]
    ordered = upcoming + rest
    counts = {g: sum(1 for i in items if i["group"] == g) for g in ("upcoming", "published", "draft", "failed")}
    parts = []
    if upcoming:
        parts.append(f"يوجد {counts['upcoming']} منشور مجدول، وأقربها {upcoming[0]['when_ar']}.")
    else:
        parts.append("لا يوجد أي منشور مجدول حالياً.")
    if counts["draft"]:
        parts.append(f"{counts['draft']} منشور ينتظر موافقتك ولن يُنشر قبلها.")
    if counts["failed"]:
        parts.append(f"⚠️ {counts['failed']} منشور فيه مشكلة وتحتاج نظرة.")
    if counts["published"]:
        parts.append(f"تم نشر {counts['published']} منشور حتى الآن.")
    counts["summary"] = " ".join(parts)
    return ordered, counts, (upcoming[0] if upcoming else None)


def load_topics() -> list[dict]:
    if not TOPICS_PATH.exists():
        return []
    data = yaml.safe_load(TOPICS_PATH.read_text(encoding="utf-8")) or {}
    return [t for t in (data.get("topics") or []) if isinstance(t, dict) and t.get("id")]


def load_health():
    f = ROOT / "content" / "health.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except Exception:  # noqa: BLE001
        return None


def load_gen_log():
    f = ROOT / "content" / "generate_log.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=SITE)
    ap.add_argument("--publish", action="store_true", help="ارفع اللوحة إلى gh-pages (داخل Actions)")
    args = ap.parse_args()

    posts, state, now = load_queue(), load_state(), now_local()
    items, counts, nxt = build(posts, state, now)

    img_dir = args.out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    by_id = {p["id"]: p for p in posts}
    with Renderer() as r:
        for it in items:
            bg = imagegen.bg_path(it["id"])
            png = r.render(by_id[it["id"]], OUT_DIR / "_tmp" / f"{it['id']}.png", bg if bg.exists() else None)
            im = Image.open(png).convert("RGB")
            im.save(img_dir / f"full-{it['id']}.jpg", quality=85)
            im.thumbnail((540, 960))
            im.save(img_dir / f"thumb-{it['id']}.jpg", quality=82)

    env = Environment(loader=FileSystemLoader(str(Path(__file__).parent)), autoescape=True)
    html = env.get_template("dashboard_template.html").render(
        topics_js=(Path(__file__).parent / "dashboard_topics.js").read_text(encoding="utf-8").replace("__REPO__", os.environ.get("GITHUB_REPOSITORY", "engshadi-79/social-publisher")),
        gen_log=load_gen_log(), health=load_health(),
        topics=load_topics(), repo=os.environ.get("GITHUB_REPOSITORY", "engshadi-79/social-publisher"),
        posts=items, counts=counts, next_post=nxt, tz=TIMEZONE,
        updated=now.strftime("%Y-%m-%d %H:%M"))
    (args.out / "index.html").write_text(html, encoding="utf-8")
    print(f"لوحة: {args.out / 'index.html'}  ({len(items)} منشور)")
    if args.publish:
        import hosting
        print("نُشرت على:", hosting.upload_site(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
