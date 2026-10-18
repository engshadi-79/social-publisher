"""يولّد لوحة تحكم ثابتة (HTML) من الطابور والحالة، لتُنشر على GitHub Pages."""
import argparse
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from PIL import Image

import imagegen
from config import MEDIA_DIR, OUT_DIR, PLATFORMS, TIMEZONE
from queue_io import load_queue, load_state, now_local, parse_when
from render import Renderer

LABELS = {"facebook": "فيسبوك", "instagram": "إنستغرام", "threads": "ثريدز", "telegram": "تيليجرام"}
SITE = OUT_DIR / "dashboard"


def _chip(name, text, st, scheduled_txt):
    status = st.get("status")
    if status == "published":
        txt, cls, hint = "نُشر", "published", st.get("published_at", "")
    elif status == "failed":
        txt, cls, hint = "فشل", "failed", "فشل بعد كل المحاولات"
    elif status == "retry":
        txt, cls, hint = f"ستُعاد ({st.get('attempts', 0)}/3)", "retry", ""
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
        chips = [_chip(n, t, st.get(n, {}), "بانتظار الموعد" if past else "مجدول")
                 for n, t in p["platforms"].items()]
        statuses = [c["status"] for c in chips]
        all_done = all(s == "published" for s in statuses)
        if not p["approved"]:
            group, badge, badge_txt = "draft", "draft", "مسودة"
        elif "failed" in statuses or "retry" in statuses:
            group = "failed"
            badge, badge_txt = ("failed", "فيه خطأ") if "failed" in statuses else ("retry", "إعادة محاولة")
        elif all_done:
            group, badge, badge_txt = "published", "published", "منشور"
        elif past:
            group, badge, badge_txt = "upcoming", "due", "بانتظار النشر"
        else:
            group, badge, badge_txt = "upcoming", "scheduled", "مجدول"
        items.append({
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
    return ordered, counts, (upcoming[0] if upcoming else None)


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
            im.thumbnail((520, 650))
            im.save(img_dir / f"thumb-{it['id']}.jpg", quality=80)

    env = Environment(loader=FileSystemLoader(str(Path(__file__).parent)), autoescape=True)
    html = env.get_template("dashboard_template.html").render(
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
