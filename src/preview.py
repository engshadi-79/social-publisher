"""معاينة كل المنشورات القادمة محلياً (وتوليد الخلفيات المخزّنة)."""
import argparse
import sys

import imagegen
from config import OUT_DIR
from queue_io import fatal, load_queue, load_state, validate
from render import Renderer


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen", metavar="POST_ID", help="أعد توليد خلفية منشور واحد")
    ap.add_argument("--seed", type=int, help="seed مختلف مع --regen")
    ap.add_argument("--all", action="store_true", help="شمل المنشورات المنشورة سابقاً")
    ap.add_argument("--no-gen", action="store_true", help="لا تولّد خلفيات (استعمل الموجود فقط)")
    args = ap.parse_args()

    queue = load_queue()
    errs = validate(queue)
    for e in errs:
        print(("خطأ: " if e in fatal(errs) else "تنبيه: ") + e)
    if fatal(errs):
        return 1
    state = load_state()
    posts = [p for p in queue if args.all or args.regen == p["id"] or
             not all(state.get(p["id"], {}).get(n, {}).get("status") == "published" for n in p["platforms"])]
    if args.regen:
        posts = [p for p in queue if p["id"] == args.regen]
        if not posts:
            print("لا يوجد منشور بهذا المعرّف")
            return 1
    with Renderer() as r:
        for p in posts:
            if args.no_gen:
                bg = imagegen.bg_path(p["id"])
                bg, warns = (bg if bg.exists() else None), []
            else:
                bg, warns = imagegen.ensure_background(p, regen=p["id"] == args.regen, seed=args.seed)
            out = r.render(p, OUT_DIR / f"{p['id']}.png", bg)
            print(f"{p['id']}: {out}" + ("" if bg else "  (خلفية متدرجة)"))
            for w in warns:
                print("  ⚠️", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
