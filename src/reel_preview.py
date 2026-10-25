"""يبني فيديو ريل واحد قبل الموافقة ويرفعه إلى gh-pages لتشاهده في اللوحة.

الاستعمال (داخل Actions):  python reel_preview.py <post-id>
الاسم يحمل بصمة المحتوى (video.preview_name): أي تعديل بعده يعني فيديو جديداً،
والنشر يستعمل هذا الملف نفسه إن لم يتغيّر شيء، فما تشاهده هو ما يُنشر.
"""
import sys

import hosting
import video
from config import OUT_DIR
from queue_io import load_queue
from render import Renderer


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print("الاستعمال: python reel_preview.py <post-id>")
        return 2
    pid = sys.argv[1].strip()
    post = next((p for p in load_queue() if p["id"] == pid), None)
    if not post:
        print(f"لا يوجد منشور بالمعرّف {pid}")
        return 1
    if post["template"] != "reel":
        print(f"{pid} ليس ريلاً")
        return 1
    out_dir = OUT_DIR / "_preview"
    with Renderer() as r:
        mp4 = video.render_reel(r, post, out_dir, use_preview=False)
    final = mp4.with_name(video.preview_name(post))
    mp4.replace(final)
    urls = hosting.upload([final])
    print("فيديو المعاينة:", next(iter(urls.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
