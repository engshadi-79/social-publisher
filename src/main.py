"""نقطة الدخول: يجد المنشورات المستحقة، يعرضها، ينشرها، ويسجّل النتيجة."""
import argparse
import os
import sys
import time
from datetime import datetime

from PIL import Image

import accounts
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
    for v in accounts.secret_values():          # كل أسرار المستودع (حسابات إضافية أيضاً)
        text = text.replace(v, "***")
    return text


def pending_targets(post: dict, state: dict) -> list[accounts.Target]:
    """الأهداف (منصة + حساب) التي لم تُنشر بعد ولم تستنفد محاولاتها."""
    done = state.get(post["id"], {})
    out = []
    for t in accounts.targets_of(post):
        st = done.get(t.key, {})
        if st.get("status") == "published":
            continue
        if st.get("status") == "failed" or st.get("attempts", 0) >= MAX_ATTEMPTS:
            continue
        out.append(t)
    return out


def pending_platforms(post: dict, state: dict) -> list[str]:
    return [t.key for t in pending_targets(post, state)]


def due_posts(queue, state, now):
    return [p for p in queue
            if p["approved"] and parse_when(p["publish_at"]) <= now and pending_targets(p, state)]


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
            todo = pending_targets(post, state)
            warns: list[str] = []
            if post["template"] in ("carousel", "infographic", "reel"):
                bg = None                      # قوالب تبني صورها بنفسها
            elif args.dry_run:
                bg = imagegen.post_bg_path(post)
                bg = bg if bg.exists() else None
            else:
                bg, warns = imagegen.ensure_background(post)
            pngs = r.render_post(post, OUT_DIR, bg)
            if post["template"] == "reel":          # ملف واحد، ولا تحويل: يُرفع كما هو
                jpgs = list(pngs)
            else:
                jpgs = []
                for f in pngs:
                    j = f.with_suffix(".jpg")
                    Image.open(f).convert("RGB").save(j, quality=92)
                    jpgs.append(j)
            png, jpg = pngs[0], jpgs[0]
            post["_files"] = pngs              # للمنصات التي ترفع الملفات (تيليجرام)
            print(f"[{pid}] صور: {len(pngs)}  أهداف: {', '.join(t.key for t in todo)}")
            if args.dry_run:
                continue

            urls = {}
            if any(PUBLISHERS[t.platform].needs_url for t in todo):
                try:
                    import hosting
                    urls = hosting.upload(jpgs)
                    post["_urls"] = [urls[j.name] for j in jpgs]
                except Exception as e:  # noqa: BLE001
                    msg = redact(f"{type(e).__name__}: {e}")
                    for t in todo:
                        if PUBLISHERS[t.platform].needs_url:
                            _fail(state, pid, t.key, "فشل الاستضافة: " + msg)
                    report.append(f"❌ {pid}: فشل رفع الصورة — {msg[:200]}")
                    todo = [t for t in todo if not PUBLISHERS[t.platform].needs_url]

            for i, t in enumerate(todo):
                if i:
                    time.sleep(PLATFORM_DELAY_SEC)
                entry = state.setdefault(pid, {}).setdefault(t.key, {"attempts": 0})
                try:
                    ext_id = PUBLISHERS[t.platform].publish(post, post["platforms"][t.platform], png,
                                                            urls.get(jpg.name), t.account)
                    entry.update(status="published", platform_post_id=ext_id, error=None,
                                 account=t.account.label,
                                 published_at=datetime.now().astimezone().isoformat(timespec="seconds"))
                    report.append(f"✅ {pid} → {t.account.label}")
                except Exception as e:  # noqa: BLE001
                    _fail(state, pid, t.key, redact(f"{type(e).__name__}: {e}"))
                    report.append(f"❌ {pid} → {t.account.label}: {entry['error'][:200]} (محاولة {entry['attempts']}/{MAX_ATTEMPTS})")
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
