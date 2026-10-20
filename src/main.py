"""نقطة الدخول: يجد المنشورات المستحقة، يعرضها، ينشرها، ويسجّل النتيجة."""
import argparse
import os
import sys
import time
from datetime import datetime

from PIL import Image

import imagegen
import notify
from config import MAX_ATTEMPTS, OUT_DIR, PLATFORM_DELAY_SEC
from publishers import PUBLISHERS
from queue_io import (fatal, load_queue, load_state, now_local, parse_when,
                      save_state, validate)
from render import Renderer

SECRET_VARS = ("FB_PAGE_TOKEN", "THREADS_TOKEN", "TELEGRAM_BOT_TOKEN", "CF_API_TOKEN",
               "GH_PAT", "GEMINI_API_KEY")


def redact(text: str) -> str:
    for v in SECRET_VARS:
        s = os.environ.get(v)
        if s:
            text = text.replace(s, "***")
    return text


def pending_platforms(post: dict, state: dict) -> list[str]:
    done = state.get(post["id"], {})
    out = []
    for name in post["platforms"]:
        st = done.get(name, {})
        if st.get("status") == "published":
            continue
        if st.get("status") == "failed" or st.get("attempts", 0) >= MAX_ATTEMPTS:
            continue
        out.append(name)
    return out


def due_posts(queue, state, now):
    return [p for p in queue
            if p["approved"] and parse_when(p["publish_at"]) <= now and pending_platforms(p, state)]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="تحقق وعرض فقط بلا نشر")
    args = ap.parse_args()

    queue = load_queue()
    errors = validate(queue)
    for e in errors:
        print(("خطأ: " if e in fatal(errors) else "تنبيه: ") + e)
    if fatal(errors):
        notify.send("⛔ طابور النشر فيه أخطاء، لم يُنشر شيء:\n" + "\n".join(fatal(errors)[:10]))
        return 1

    state = load_state()
    posts = due_posts(queue, state, now_local())
    print(f"منشورات مستحقة: {len(posts)}")
    if not posts:
        return 0

    report: list[str] = []
    with Renderer() as r:
        for post in posts:
            pid = post["id"]
            todo = pending_platforms(post, state)
            warns: list[str] = []
            if post["template"] in ("carousel", "infographic"):
                bg = None                      # قوالب نصّية بلا خلفية خارجية
            elif args.dry_run:
                bg = imagegen.post_bg_path(post)
                bg = bg if bg.exists() else None
            else:
                bg, warns = imagegen.ensure_background(post)
            pngs = r.render_post(post, OUT_DIR, bg)
            jpgs = []
            for f in pngs:
                j = f.with_suffix(".jpg")
                Image.open(f).convert("RGB").save(j, quality=92)
                jpgs.append(j)
            png, jpg = pngs[0], jpgs[0]
            post["_files"] = pngs              # للمنصات التي ترفع الملفات (تيليجرام)
            print(f"[{pid}] صور: {len(pngs)}  منصات: {', '.join(todo)}")
            if args.dry_run:
                continue

            urls = {}
            if any(PUBLISHERS[n].needs_url for n in todo):
                try:
                    import hosting
                    urls = hosting.upload(jpgs)
                    post["_urls"] = [urls[j.name] for j in jpgs]
                except Exception as e:  # noqa: BLE001
                    msg = redact(f"{type(e).__name__}: {e}")
                    for n in todo:
                        if PUBLISHERS[n].needs_url:
                            _fail(state, pid, n, "فشل الاستضافة: " + msg)
                    report.append(f"❌ {pid}: فشل رفع الصورة — {msg[:200]}")
                    todo = [n for n in todo if not PUBLISHERS[n].needs_url]

            for i, name in enumerate(todo):
                if i:
                    time.sleep(PLATFORM_DELAY_SEC)
                entry = state.setdefault(pid, {}).setdefault(name, {"attempts": 0})
                try:
                    ext_id = PUBLISHERS[name].publish(post, post["platforms"][name], png, urls.get(jpg.name))
                    entry.update(status="published", platform_post_id=ext_id, error=None,
                                 published_at=datetime.now().astimezone().isoformat(timespec="seconds"))
                    report.append(f"✅ {pid} → {name}")
                except Exception as e:  # noqa: BLE001
                    _fail(state, pid, name, redact(f"{type(e).__name__}: {e}"))
                    report.append(f"❌ {pid} → {name}: {entry['error'][:200]} (محاولة {entry['attempts']}/{MAX_ATTEMPTS})")
            for w in warns:
                report.append(f"⚠️ {pid}: {w}")
            save_state(state)

    if not args.dry_run:
        save_state(state)
        notify.send("📣 ملخص النشر\n" + "\n".join(report))
        print("\n".join(report))
    return 0


def _fail(state, pid, name, msg):
    e = state.setdefault(pid, {}).setdefault(name, {"attempts": 0})
    e["attempts"] = e.get("attempts", 0) + 1
    e["error"] = msg
    e["status"] = "failed" if e["attempts"] >= MAX_ATTEMPTS else "retry"


if __name__ == "__main__":
    sys.exit(main())
